"""Investigator agent: a hand-written tool-calling loop over the Responses API (max 5 model
steps per lead). The model picks which tools to call; every call carries a short Persian `why`
that is streamed to the live feed. The loop ends with submit_verdict (forced on the last step)."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

import numpy as np
from openai.lib._pydantic import to_strict_json_schema
from pydantic import BaseModel, Field, ValidationError

from ..chat.parse import ChatMessage
from .context import Reservation, RunContext, cache_get, cache_key, cache_put
from .prefilter import embed_texts_cached
from .prompts import INVESTIGATOR_SYSTEM, PROMPT_VERSIONS, profile_block
from .schemas import TriageItem, Verdict

MAX_STEPS = 5
_WHY = Field(description="Short Persian reason for this call (<= 12 words), shown to the user")


class GetThreadArgs(BaseModel):
    msg_id: int
    why: str = _WHY


class GetUserHistoryArgs(BaseModel):
    user_id: str = Field(description="The author id shown in parentheses, e.g. user5091272307")
    why: str = _WHY


class GetNearbyArgs(BaseModel):
    msg_id: int
    n: int = Field(description="Messages before and after, 2-8")
    why: str = _WHY


class CheckResolvedArgs(BaseModel):
    msg_id: int
    why: str = _WHY


class SearchChatArgs(BaseModel):
    query: str = Field(description="Persian/Finglish/English keywords or a short phrase")
    why: str = _WHY


def _tool(name: str, description: str, model: type[BaseModel]) -> dict:
    return {"type": "function", "name": name, "description": description,
            "parameters": to_strict_json_schema(model), "strict": True}


TOOLS = [
    _tool("get_thread", "Reply chain around a message: what it answers and every reply below it.", GetThreadArgs),
    _tool("get_user_history", "The author's other messages in this chat (up to 15, closest in time).", GetUserHistoryArgs),
    _tool("get_nearby", "Messages posted right before and after a message (for context without replies).", GetNearbyArgs),
    _tool("check_resolved", "Whether the need was already satisfied: replies below the message, the author's later messages, and automatic hints like 'bought/enrolled/solved'.", CheckResolvedArgs),
    _tool("search_chat", "Semantic + keyword search over the whole chat for related discussions.", SearchChatArgs),
    _tool("submit_verdict", "Submit the final structured verdict. Call exactly once, as the last step.", Verdict),
]

TOOL_FA = {
    "get_thread": "🧵 خواندن رشته گفتگوی پیام #{msg_id}",
    "get_user_history": "👤 مرور پیام‌های دیگر {author}",
    "get_nearby": "↕️ نگاه به پیام‌های اطراف #{msg_id}",
    "check_resolved": "✅ بررسی اینکه نیازش قبلا برطرف شده یا نه",
    "search_chat": "🔍 جستجو در گروه برای «{query}»",
}

RESOLVED_HINTS = [
    "ثبت‌نام کردم", "ثبت نام کردم", "ثبتنام کردم", "خریدم", "خریدمش", "گرفتمش", "حل شد", "درست شد",
    "دیگه نیاز ندارم", "نیازی ندارم", "بیخیال", "پیدا کردم", "رفتم سراغ", "sabtenam kardam", "kharidam",
    "hal shod", "dorost shod", "peyda kardam", "enrolled", "bought", "solved", "fixed",
]


@dataclass
class Investigation:
    verdict: Verdict
    trace: list[dict] = field(default_factory=list)
    cost: float = 0.0
    cached: bool = False
    steps: int = 0


def select_fewshot(ctx: RunContext, cand: ChatMessage, k: int = 4, min_sim: float = 0.35):
    v = ctx.embeddings.get(cand.id)
    if v is None or not ctx.fewshot:
        return []
    scored = sorted(((float(f.vec @ v), f) for f in ctx.fewshot), key=lambda x: -x[0])
    return [f for s, f in scored[:k] if s >= min_sim]


def _initial_context(ctx: RunContext, cand: ChatMessage, tri: TriageItem, others: list[int], fewshot) -> str:
    idx = ctx.index
    thread = idx.thread(cand.id)[:16]
    earlier = [m for m in idx.user_history(cand.author_id, around=cand.id, limit=40)
               if m.ts < cand.ts and m.id not in {t.id for t in thread}][-5:]
    parts = [
        "CANDIDATE",
        idx.line(cand, focus=cand.id),
        f"Triage: {tri.signal}, relevance {tri.relevance}/10 — {tri.reason}",
        "",
        "REPLY THREAD (chronological, >>> marks the candidate)",
        idx.render(thread, focus=cand.id, max_chars=350) if len(thread) > 1 else "(no replies, not a reply)",
        "",
        "AUTHOR'S EARLIER MESSAGES (up to 5, before the candidate)",
        idx.render(earlier, max_chars=250) if earlier else "(none)",
    ]
    if others:
        parts += ["", "OTHER FLAGGED MESSAGES BY THE SAME AUTHOR: " + ", ".join(f"#{i}" for i in others)]
    if fewshot:
        parts += ["", "PAST JUDGMENTS BY THE BUSINESS OWNER ON SIMILAR MESSAGES (follow these preferences)"]
        for f in fewshot:
            if f.vote > 0:
                parts.append(f'- 👍 owner confirmed a real lead: "{f.text[:200]}"' + (f" — {f.note}" if f.note else ""))
            else:
                parts.append(f'- 👎 owner said NOT a lead (agent had said {f.agent_decision}): "{f.text[:200]}"'
                             + (f" — {f.note}" if f.note else ""))
    parts += ["", "Investigate only what is unclear, then call submit_verdict."]
    return "\n".join(parts)


async def run_tool(ctx: RunContext, name: str, args: dict, cand: ChatMessage, res: Reservation) -> str:
    idx = ctx.index
    if name == "get_thread":
        return idx.render(idx.thread(int(args["msg_id"]))[:25], focus=cand.id)
    if name == "get_user_history":
        hist = idx.user_history(str(args["user_id"]), around=cand.id, limit=15)
        return idx.render(hist, focus=cand.id, max_chars=300) if hist else "(no messages from this user id)"
    if name == "get_nearby":
        n = max(2, min(8, int(args.get("n", 5))))
        return idx.render(idx.nearby(int(args["msg_id"]), n), focus=cand.id, max_chars=250)
    if name == "check_resolved":
        m = idx.get(int(args["msg_id"]))
        if not m:
            return "(message not found)"
        replies = idx.descendants(m.id)
        later = [x for x in idx.by_author.get(m.author_id, []) if x.ts > m.ts and x.id not in {r.id for r in replies}]
        hints = [f"#{x.id} contains «{h}»" for x in replies + later for h in RESOLVED_HINTS if h in x.norm.lower()]
        return "\n".join([
            "REPLIES BELOW THE MESSAGE", idx.render(replies, max_chars=250) if replies else "(none)", "",
            "AUTHOR'S LATER MESSAGES", idx.render(later[:10], max_chars=250) if later else "(none)", "",
            "AUTOMATIC HINTS", "\n".join(hints) if hints else "(no resolution keywords found)",
        ])
    if name == "search_chat":
        query = str(args.get("query", ""))[:200]
        hits = {m.id: m for m in idx.search(query, limit=6)}
        if ctx.embeddings:
            qv = (await embed_texts_cached(ctx, [query], stage="investigate", res=res))[0]
            ids = list(ctx.embeddings)
            sims = np.vstack([ctx.embeddings[i] for i in ids]) @ qv
            for j in np.argsort(-sims)[:6]:
                if sims[j] >= 0.3 and (m := idx.get(ids[j])):
                    hits[m.id] = m
        ordered = sorted(hits.values(), key=lambda m: (m.ts, m.id))[:10]
        return idx.render(ordered, focus=cand.id, max_chars=250) if ordered else "(no matches)"
    return f"(unknown tool {name})"


def _tool_text(name: str, args: dict, cand: ChatMessage) -> str:
    tmpl = TOOL_FA.get(name, name)
    text = tmpl.format(msg_id=args.get("msg_id", cand.id), author=cand.author, query=str(args.get("query", ""))[:40])
    why = str(args.get("why", "")).strip()
    return f"{text}… {('— ' + why) if why else ''}".strip()


def _as_input(output_items) -> list[dict]:
    return [o.model_dump(exclude_none=True, mode="json") for o in output_items]


async def investigate(
    ctx: RunContext, cand: ChatMessage, tri: TriageItem, others: list[int], res: Reservation
) -> Investigation:
    fewshot = select_fewshot(ctx, cand)
    key = cache_key("inv", ctx.settings.investigator_model, PROMPT_VERSIONS["investigate"], ctx.profile_fp, ctx.dataset_id,
                    cand.id, cand.norm, [(f.text, f.vote, f.note) for f in fewshot])
    if fewshot:
        await ctx.emit("memory", f"🧠 {len(fewshot)} قضاوت قبلی شما روی پیام‌های مشابه به عامل داده شد",
                       msg_id=cand.id, data={"fewshot": len(fewshot)})
    if ctx.use_cache and (hit := cache_get(key)):
        result, cost = hit
        for t in result["trace"]:
            await asyncio.sleep(ctx.replay_delay)
            await ctx.emit("tool", _tool_text(t["tool"], t["args"], cand), msg_id=cand.id,
                           data={"tool": t["tool"], "args": t["args"], "cached": True})
        ctx.budget.credit_cache("investigate", cost)
        return Investigation(verdict=Verdict(**result["verdict"]), trace=result["trace"], cost=cost,
                             cached=True, steps=result.get("steps", 0))

    instructions = INVESTIGATOR_SYSTEM.format(profile=profile_block(ctx.profile))
    items: list[dict] = [{"role": "user", "content": _initial_context(ctx, cand, tri, others, fewshot)}]
    trace: list[dict] = []
    verdict: Verdict | None = None
    cost = 0.0
    steps = 0
    for step in range(MAX_STEPS):
        steps = step + 1
        last = step == MAX_STEPS - 1
        resp, usage = await ctx.llm.respond(
            model=ctx.settings.investigator_model,
            instructions=instructions,
            input=items,
            tools=TOOLS,
            tool_choice={"type": "function", "name": "submit_verdict"} if last else "required",
            reasoning=ctx.settings.agent_reasoning,
            max_output_tokens=3000,
            cache_key=f"sarenakh-inv-{ctx.profile_fp}",
        )
        cost += ctx.budget.charge("investigate", usage, res)
        items.extend(_as_input(resp.output))
        calls = [o for o in resp.output if o.type == "function_call"]
        if not calls:
            items.append({"role": "developer", "content": "Call a tool, or submit_verdict if you are done."})
            continue
        for c in calls:
            if c.name == "submit_verdict":
                try:
                    verdict = Verdict.model_validate_json(c.arguments)
                except ValidationError as e:
                    items.append({"type": "function_call_output", "call_id": c.call_id,
                                  "output": f"Invalid verdict, fix and resubmit: {e.errors()[:3]}"})
                continue
            try:
                args = json.loads(c.arguments)
            except json.JSONDecodeError:
                args = {}
            await ctx.emit("tool", _tool_text(c.name, args, cand), msg_id=cand.id,
                           data={"tool": c.name, "args": args, "step": steps})
            out = await run_tool(ctx, c.name, args, cand, res)
            trace.append({"tool": c.name, "args": args, "step": steps})
            items.append({"type": "function_call_output", "call_id": c.call_id, "output": out})
        if verdict:
            break

    if verdict is None:
        verdict = Verdict(
            evidence_msg_ids=[cand.id], stated_need="", disqualifiers_found=[], thread_resolved=False,
            reasoning="عامل در سقف مراحل به نتیجه نرسید.",
            scores={"need": 0, "product_fit": 0, "urgency": 0, "buying_intent": 0, "reachability": 0, "confidence": 0},
            timing="browsing", action="skip", why_not="بررسی ناتمام ماند (سقف ۵ مرحله)",
        )
    cache_put(key, "investigate", {"verdict": verdict.model_dump(), "trace": trace, "steps": steps}, cost)
    return Investigation(verdict=verdict, trace=trace, cost=cost, steps=steps)
