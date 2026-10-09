"""Devil's advocate for borderline leads: tries to refute the verdict; the lead stays only if it survives."""

from __future__ import annotations

from ..chat.parse import ChatMessage
from .context import Reservation, RunContext, cache_get, cache_key, cache_put, charged
from .prompts import CRITIC_SYSTEM, PROMPT_VERSIONS, profile_block
from .schemas import CriticResult, Verdict


async def critique(
    ctx: RunContext, cand: ChatMessage, verdict: Verdict, fit: float, res: Reservation
) -> tuple[CriticResult, float, bool]:
    """Returns (result, cost, cached)."""
    key = cache_key("critic", ctx.settings.critic_model, PROMPT_VERSIONS["critic"], ctx.profile_fp, ctx.dataset_id,
                    cand.id, verdict.model_dump())
    if ctx.use_cache and (hit := cache_get(key)):
        ctx.budget.credit_cache("critic", hit[1])
        return CriticResult(**hit[0]), hit[1], True

    idx = ctx.index
    evidence_ids = list(dict.fromkeys([cand.id, *verdict.evidence_msg_ids]))
    evidence = [m for i in evidence_ids if (m := idx.get(i))]
    thread = idx.thread(cand.id)[:14]
    later = [m for m in idx.by_author.get(cand.author_id, []) if m.ts > cand.ts][:6]
    text = "\n".join([
        f"THE AGENT'S VERDICT (overall fit {fit}/10)",
        f"stated need: {verdict.stated_need}",
        f"reasoning: {verdict.reasoning}",
        f"scores: {verdict.scores.model_dump()}  timing: {verdict.timing}  action: {verdict.action}",
        "",
        "EVIDENCE MESSAGES", idx.render(evidence, focus=cand.id, max_chars=350),
        "",
        "THREAD", idx.render(thread, focus=cand.id, max_chars=250),
        "",
        "THE AUTHOR'S LATER MESSAGES", idx.render(later, max_chars=250) if later else "(none)",
    ])
    result, cost = await charged(ctx.budget, "critic", res, ctx.llm.structured(
        model=ctx.settings.critic_model,
        instructions=CRITIC_SYSTEM.format(profile=profile_block(ctx.profile)),
        input=text,
        output_type=CriticResult,
        reasoning=ctx.settings.agent_reasoning,
        max_output_tokens=1500,
        cache_key=f"sarenakh-critic-{ctx.profile_fp}",
    ))
    cache_put(key, "critic", result.model_dump(), cost)
    return result, cost, False
