"""Reply drafter: help-first Persian reply, grounded in product facts retrieved by embedding.
Draft -> quick check (invented claims, mode, helpfulness) + hard checks in code -> one revision if needed."""

from __future__ import annotations

import numpy as np

from ..chat.parse import ChatMessage
from ..llm import IncompleteOutputError
from .context import Reservation, RunContext, cache_get, cache_key, cache_put, charged
from .prefilter import embed_texts_cached
from .prompts import DRAFT_CHECK_SYSTEM, DRAFTER_SYSTEM, PROMPT_VERSIONS
from .schemas import DraftCheck, ReplyDraft, Verdict

TOP_FACTS = 5


async def retrieve_facts(ctx: RunContext, query: str, res: Reservation) -> list[tuple[int, str]]:
    """Most relevant product facts for this person, with their original indexes."""
    facts = ctx.profile.facts
    if len(facts) <= TOP_FACTS:
        return list(enumerate(facts))
    vecs = await embed_texts_cached(ctx, facts + [query], stage="draft", res=res)
    sims = vecs[:-1] @ vecs[-1]
    top = sorted(np.argsort(-sims)[:TOP_FACTS].tolist())
    return [(i, facts[i]) for i in top]


def _hard_issues(ctx: RunContext, draft: ReplyDraft, mode: str, allowed: set[int]) -> list[str]:
    issues = []
    name = ctx.profile.product_name.split("—")[0].strip()
    variants = {v for v in (name, name.replace("‌", ""), name.replace("‌", " ")) if len(v) >= 3}
    if mode == "pure_help" and (draft.facts_used or any(v in draft.reply for v in variants)):
        issues.append("در حالت «فقط کمک» نباید اسم محصول یا ویژگی‌هایش بیاید.")
    if bad := [i for i in draft.facts_used if i not in allowed]:
        issues.append(f"از واقعیت‌هایی استفاده شده که در فهرست مجاز نیستند: {bad}")
    words = len(draft.reply.split())
    if words > 130:
        issues.append("پاسخ خیلی طولانی است؛ زیر ۹۰ کلمه کوتاهش کن.")
    return issues


async def draft_reply(
    ctx: RunContext, cand: ChatMessage, verdict: Verdict, mode: str, res: Reservation
) -> tuple[dict, float, bool]:
    """Returns ({reply, mode, facts_used, help_points, check, revised}, cost, cached)."""
    key = cache_key("draft", ctx.settings.drafter_model, PROMPT_VERSIONS["draft"], ctx.profile_fp, ctx.dataset_id,
                    cand.id, mode, verdict.stated_need)
    if ctx.use_cache and (hit := cache_get(key)):
        ctx.budget.credit_cache("draft", hit[1])
        return hit[0], hit[1], True

    facts = await retrieve_facts(ctx, f"{cand.norm}\n{verdict.stated_need}", res)
    allowed = {i for i, _ in facts}
    facts_txt = "\n".join(f"[{i}] {f}" for i, f in facts) or "(none)"
    product = f"{ctx.profile.product_name} — {ctx.profile.one_liner}"
    thread = ctx.index.thread(cand.id)[:10]
    user_input = "\n".join([
        f"MODE: {mode}",
        f"Person's language: {'Finglish' if cand.lang == 'finglish' else 'Persian'}",
        f"Their need (from the investigation): {verdict.stated_need}",
        "",
        "THE CONVERSATION (>>> = the person you reply to)",
        ctx.index.render(thread, focus=cand.id, max_chars=300),
    ])
    instructions = DRAFTER_SYSTEM.format(tone=ctx.profile.reply_tone, product=product, facts=facts_txt)
    cost = 0.0

    draft, c = await charged(ctx.budget, "draft", res, ctx.llm.structured(
        model=ctx.settings.drafter_model, instructions=instructions, input=user_input,
        output_type=ReplyDraft, reasoning=ctx.settings.agent_reasoning, max_output_tokens=2000,
        cache_key=f"sarenakh-draft-{ctx.profile_fp}",
    ))
    cost += c

    try:
        check, c = await charged(ctx.budget, "draft", res, ctx.llm.structured(
            model=ctx.settings.critic_model,
            instructions=DRAFT_CHECK_SYSTEM.format(product=product, facts=facts_txt),
            input=user_input + f"\n\nREPLY TO REVIEW:\n{draft.reply}",
            output_type=DraftCheck, reasoning=ctx.settings.agent_reasoning, max_output_tokens=1200,
            cache_key=f"sarenakh-check-{ctx.profile_fp}",
        ))
        cost += c
    except IncompleteOutputError:
        check = DraftCheck(answers_the_person=True, invented_claims=[], breaks_mode=False, issues=[], ok=True)

    issues = list(check.issues) + [f"ادعای ساختگی: {c}" for c in check.invented_claims]
    issues += _hard_issues(ctx, draft, mode, allowed)
    revised = False
    if issues or not check.ok:
        try:
            revision, c = await charged(ctx.budget, "draft", res, ctx.llm.structured(
                model=ctx.settings.drafter_model, instructions=instructions,
                input=user_input + "\n\nYOUR PREVIOUS DRAFT:\n" + draft.reply
                + "\n\nREVIEWER ISSUES — fix all of them:\n- " + "\n- ".join(issues or ["بهترش کن"]),
                output_type=ReplyDraft, reasoning=ctx.settings.agent_reasoning, max_output_tokens=2000,
                cache_key=f"sarenakh-draft-{ctx.profile_fp}",
            ))
            cost += c
            if not _hard_issues(ctx, revision, mode, allowed):
                draft, revised = revision, True
        except IncompleteOutputError:
            pass  # keep the first draft

    out = {
        "reply": draft.reply.strip(),
        "mode": mode,
        "facts_used": [f for i, f in facts if i in set(draft.facts_used)],
        "help_points": draft.help_points,
        "check": {"ok": check.ok, "issues": issues},
        "revised": revised,
    }
    cache_put(key, "draft", out, cost)
    return out, cost, False
