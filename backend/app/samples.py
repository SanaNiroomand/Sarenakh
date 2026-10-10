"""Bundled demo data: the sample chat, demo products, prebuilt profiles, ground truth."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from typing import Any

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from .chat.parse import ParsedChat, parse_telegram_export
from .config import get_settings
from .db import Dataset, Message

SAMPLE_DATASET_KEY = "python_iran"


def _dir():
    return get_settings().samples_dir


@lru_cache
def sample_products() -> dict[str, dict[str, Any]]:
    return json.loads((_dir() / "products.json").read_text(encoding="utf-8"))


@lru_cache
def ground_truth() -> dict[str, Any]:
    return json.loads((_dir() / "ground_truth.json").read_text(encoding="utf-8"))


def sample_profile(key: str) -> dict[str, Any] | None:
    """Profile prebuilt by the profile agent (samples/profiles/<key>.json) so the demo is instant."""
    path = _dir() / "profiles" / f"{key}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def store_parsed(
    db: Session, parsed: ParsedChat, *, user_id: int | None, name: str, sample_key: str | None = None
) -> Dataset:
    ds = Dataset(
        user_id=user_id, name=name[:200], source="sample" if sample_key else parsed.source,
        sample_key=sample_key, stats=parsed.stats,
    )
    db.add(ds)
    db.flush()
    rows = [
        {
            "dataset_id": ds.id, "msg_id": m.id, "ts": m.ts, "date": m.date, "author_id": m.author_id,
            "author": m.author, "text": m.text, "norm": m.norm, "reply_to": m.reply_to, "kind": m.kind,
            "lang": m.lang, "forwarded_from": m.forwarded_from, "emojis": m.emojis, "ext_id": m.ext_id,
        }
        for m in parsed.messages
    ]
    for i in range(0, len(rows), 1000):
        db.execute(insert(Message), rows[i : i + 1000])
    return ds


def ensure_sample_dataset(db: Session) -> Dataset:
    """Seed the shared sample chat; if the bundled file changed since seeding, refresh it in place
    (same dataset id and message ids; embeddings kept for messages whose text did not change)."""
    raw = (_dir() / ground_truth()["chat_file"]).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()[:16]
    ds = db.scalar(select(Dataset).where(Dataset.sample_key == SAMPLE_DATASET_KEY))
    if ds and (ds.stats or {}).get("source_hash") == digest:
        return ds
    parsed = parse_telegram_export(raw)
    if ds is None:
        ds = store_parsed(db, parsed, user_id=None, name=parsed.name, sample_key=SAMPLE_DATASET_KEY)
    else:
        old = {m.msg_id: m for m in db.scalars(select(Message).where(Message.dataset_id == ds.id))}
        keep = {mid: m.embedding for mid, m in old.items() if m.embedding is not None}
        old_norm = {mid: m.norm for mid, m in old.items()}
        db.execute(delete(Message).where(Message.dataset_id == ds.id))
        db.flush()
        rows = [
            {
                "dataset_id": ds.id, "msg_id": m.id, "ts": m.ts, "date": m.date, "author_id": m.author_id,
                "author": m.author, "text": m.text, "norm": m.norm, "reply_to": m.reply_to, "kind": m.kind,
                "lang": m.lang, "forwarded_from": m.forwarded_from, "emojis": m.emojis,
                "embedding": keep.get(m.id) if old_norm.get(m.id) == m.norm else None,
            }
            for m in parsed.messages
        ]
        db.execute(insert(Message), rows)
        ds.name = parsed.name
    ds.stats = {**parsed.stats, "source_hash": digest}
    return ds
