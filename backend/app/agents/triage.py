"""Triage: the cheap model scores batches of ~25 messages (relevance 0-10, signal, one-line reason)."""

from __future__ import annotations

import asyncio
import logging

from ..chat.parse import ChatMessage
from ..llm import IncompleteOutputError
from .context import BudgetExceeded, GlobalCapReached, RunContext, cache_get, cache_key, cache_put
from .prompts import PROMPT_VERSIONS, TRIAGE_SYSTEM, profile_block
from .schemas import TriageBatch, TriageItem

log = logging.getLogger("sarenakh.triage")

BATCH_SIZE = 25
CONCURRENCY = 4
EST_BATCH_COST = 0.002  # reserved per batch; actual is usually ~$0.0004 on gpt-6-luna


def _render(ctx: RunContext, m: ChatMessage) -> str:
    text = m.norm.replace("\n", " ⏎ ")[:600]
    line = f"#{m.id} | {m.author}: {text}"
    parent = ctx.index.get(m.reply_to) if m.reply_to else None
    if parent:
        line += f"\n    (in reply to #{parent.id} {parent.author}: {parent.norm.replace(chr(10), ' ')[:120]})"
    return line


def _key(ctx: RunContext, m: ChatMessage) -> str:
    parent = ctx.index.get(m.reply_to) if m.reply_to else None
    return cache_key("triage", ctx.settings.triage_model, PROMPT_VERSIONS["triage"], ctx.profile_fp, m.norm,
                     parent.norm if parent else "")


async def triage(ctx: RunContext, msgs: list[ChatMessage]) -> tuple[dict[int, TriageItem], str | None]:
    """Returns (results, stop_reason). stop_reason is 'budget' or 'global_cap' if work was cut short."""
    results: dict[int, TriageItem] = {}
    todo: list[ChatMessage] = []
    for m in msgs:
        hit = cache_get(_key(ctx, m)) if ctx.use_cache else None
        if hit:
            results[m.id] = TriageItem(**{**hit[0], "msg_id": m.id})
            ctx.budget.credit_cache("triage", hit[1])
        else:
            todo.append(m)
    if results:
        n_batches = -(-len(results) // BATCH_SIZE)
        hot_cached = sum(1 for it in results.values() if it.relevance >= 6)
        for i in range(n_batches):  # replay batch progress so the feed reads like a live run
            await asyncio.sleep(ctx.replay_delay / 2)
            size = min(BATCH_SIZE, len(results) - i * BATCH_SIZE)
            await ctx.emit("triage", f"♻️ دسته {i + 1} از {n_batches}: {size} پیام از حافظه خوانده شد (بدون هزینه)",
                           data={"batch": i + 1, "batches": n_batches, "size": size, "cached": True})
        await ctx.emit("triage", f"⚖️ {hot_cached} پیام امیدوارکننده در نتایج حافظه",
                       data={"cached": len(results), "hot": hot_cached})

    batches = [todo[i : i + BATCH_SIZE] for i in range(0, len(todo), BATCH_SIZE)]
    instructions = TRIAGE_SYSTEM.format(profile=profile_block(ctx.profile, with_examples=True))
    sem = asyncio.Semaphore(CONCURRENCY)
    done = 0
    stopped: list[str] = []

    async def classify(batch: list[ChatMessage], res) -> tuple[dict[int, TriageItem], float]:
        """One model call; on a degenerate/truncated answer, split the batch in two and retry."""
        try:
            parsed, usage = await ctx.llm.structured(
                model=ctx.settings.triage_model,
                instructions=instructions,
                input="Messages:\n" + "\n".join(_render(ctx, m) for m in batch),
                output_type=TriageBatch,
                reasoning=ctx.settings.triage_reasoning,
                max_output_tokens=150 * len(batch) + 500,
                cache_key=f"sarenakh-triage-{ctx.profile_fp}",
            )
        except IncompleteOutputError as e:
            cost = ctx.budget.charge("triage", e.usage, res)
            log.warning("triage batch of %d failed (%s); splitting", len(batch), e)
            if len(batch) <= 3:
                return {m.id: TriageItem(msg_id=m.id, signal="noise", reason="تریاژ این پیام ناموفق بود",
                                         relevance=0) for m in batch}, cost
            half = len(batch) // 2
            a, ca = await classify(batch[:half], res)
            b, cb = await classify(batch[half:], res)
            return {**a, **b}, cost + ca + cb
        cost = ctx.budget.charge("triage", usage, res)
        by_id = {it.msg_id: it for it in parsed.items}
        share = usage.cost_usd / len(batch)
        out = {}
        for m in batch:
            item = by_id.get(m.id) or TriageItem(msg_id=m.id, signal="noise", reason="بدون خروجی", relevance=0)
            out[m.id] = item
            if m.id in by_id:
                cache_put(_key(ctx, m), "triage", item.model_dump(), share)
        return out, cost

    async def run(batch: list[ChatMessage]) -> None:
        nonlocal done
        async with sem:
            if stopped:
                return
            try:
                res = ctx.budget.reserve(EST_BATCH_COST)
            except BudgetExceeded:
                stopped.append("budget")
                return
            except GlobalCapReached:
                stopped.append("global_cap")
                return
            try:
                items, cost = await classify(batch, res)
            finally:
                ctx.budget.release(res)
            results.update(items)
            hot = sum(1 for it in items.values() if it.relevance >= 6)
            done += 1
            await ctx.emit(
                "triage",
                f"⚖️ دسته {done} از {len(batches)}: {len(batch)} پیام سنجیده شد، {hot} پیام امیدوارکننده",
                data={"batch": done, "batches": len(batches), "size": len(batch), "hot": hot},
                cost=cost,
            )

    await asyncio.gather(*(run(b) for b in batches))
    return results, (stopped[0] if stopped else None)
