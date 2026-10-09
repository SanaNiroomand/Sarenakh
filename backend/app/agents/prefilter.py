"""Embedding pre-filter: keep only messages semantically close to the profile's buying signals,
before any LLM call. Message embeddings are cached in the DB, seed embeddings in the stage cache."""

from __future__ import annotations

import base64

import numpy as np

from ..chat.parse import ChatMessage
from .context import Reservation, RunContext, cache_get, cache_key, cache_put

# Tuned on the sample chat (scripts/sims.py): every planted lead scores >= 0.38, so 0.36 keeps all
# of them while dropping ~2/3 of the chat. Replies are also scored together with the message they
# answer, so context-dependent messages ("me too", "same here") are not lost.
SIM_THRESHOLD = 0.36
CTX_PENALTY = 0.02
MIN_KEEP = 15
MAX_KEEP = 250


def _seed_texts(ctx: RunContext) -> list[str]:
    p = ctx.profile
    return [t for t in (p.signal_examples + p.buying_signals + p.pain_points) if t.strip()]


async def embed_texts_cached(
    ctx: RunContext, texts: list[str], stage: str = "embed", res: Reservation | None = None
) -> np.ndarray:
    """Embeddings for arbitrary short texts, cached by (model, text). Charges `res` if given."""
    model = ctx.settings.embedding_model
    out: list[np.ndarray | None] = [None] * len(texts)
    missing: list[int] = []
    for i, t in enumerate(texts):
        hit = cache_get(cache_key("emb", model, t))
        if hit:
            out[i] = np.frombuffer(base64.b64decode(hit[0]["v"]), dtype=np.float32)
        else:
            missing.append(i)
    if missing:
        own = res is None
        r = ctx.budget.reserve(0.0005) if own else res
        try:
            vecs, usage = await ctx.llm.embed([texts[i] for i in missing])
            ctx.budget.charge(stage, usage, r)
        finally:
            if own:
                ctx.budget.release(r)
        per = usage.cost_usd / max(len(missing), 1)
        for j, i in enumerate(missing):
            out[i] = vecs[j]
            cache_put(cache_key("emb", model, texts[i]), "embed", {"v": base64.b64encode(vecs[j].tobytes()).decode()}, per)
    return np.vstack(out) if out else np.zeros((0, 1536), dtype=np.float32)


async def embed_messages(ctx: RunContext, msgs: list[ChatMessage]) -> None:
    missing = [m for m in msgs if m.id not in ctx.embeddings]
    if not missing:
        return
    new: dict[int, np.ndarray] = {}
    for i in range(0, len(missing), 512):
        chunk = missing[i : i + 512]
        res = ctx.budget.reserve(0.001)
        try:
            vecs, usage = await ctx.llm.embed([m.norm for m in chunk])
            ctx.budget.charge("embed", usage, res)
        finally:
            ctx.budget.release(res)
        for m, v in zip(chunk, vecs):
            new[m.id] = v
    ctx.embeddings.update(new)
    if ctx.on_new_embeddings:
        ctx.on_new_embeddings(new)


async def prefilter(ctx: RunContext, msgs: list[ChatMessage]) -> list[tuple[ChatMessage, float]]:
    """Returns (message, similarity) for kept messages, most similar first."""
    if not msgs:
        return []
    await embed_messages(ctx, msgs)
    seeds = await embed_texts_cached(ctx, _seed_texts(ctx))
    mat = np.vstack([ctx.embeddings[m.id] for m in msgs])
    sims = (mat @ seeds.T).max(axis=1)

    # replies: also score "parent ↩ reply" so the reply inherits its conversation's meaning
    replies = [(i, m, p) for i, m in enumerate(msgs)
               if m.reply_to and (p := ctx.index.get(m.reply_to)) and p.analyzable]
    if replies:
        ctx_vecs = await embed_texts_cached(ctx, [f"{p.norm[:300]}\n↩ {m.norm}" for _, m, p in replies])
        ctx_sims = (ctx_vecs @ seeds.T).max(axis=1) - CTX_PENALTY
        for (i, _, _), s in zip(replies, ctx_sims):
            sims[i] = max(sims[i], s)

    order = np.argsort(-sims)
    kept: list[tuple[ChatMessage, float]] = []
    for rank, i in enumerate(order):
        s = float(sims[i])
        if (s >= SIM_THRESHOLD or rank < MIN_KEEP) and len(kept) < MAX_KEEP:
            kept.append((msgs[i], s))
    return kept


def similarities(ctx: RunContext, msgs: list[ChatMessage], seeds: np.ndarray) -> dict[int, float]:
    mat = np.vstack([ctx.embeddings[m.id] for m in msgs])
    return {m.id: float(s) for m, s in zip(msgs, (mat @ seeds.T).max(axis=1))}
