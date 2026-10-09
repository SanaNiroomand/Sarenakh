"""Golden cache: the sample runs' stage-cache rows + sample-chat embeddings, shipped with the image
(samples/golden_cache.json.gz). Loaded at startup, so the "Try sample" flow replays instantly and for
free on a fresh server — even if OpenAI is unreachable during judging.

Export (after final prompt tuning):  cd backend && python -m app.golden export
"""

from __future__ import annotations

import base64
import gzip
import json
import logging
import sys

from sqlalchemy import select

from .config import get_settings
from .db import Message, StageCache, init_db, session
from .samples import SAMPLE_DATASET_KEY, ensure_sample_dataset

log = logging.getLogger("sarenakh.golden")


def _path():
    return get_settings().samples_dir / "golden_cache.json.gz"


def load_golden() -> None:
    path = _path()
    if not path.exists():
        return
    data = json.loads(gzip.decompress(path.read_bytes()))
    added = 0
    with session() as db:
        have = set(db.scalars(select(StageCache.key)))
        for row in data["stage_cache"]:
            if row["key"] not in have:
                db.add(StageCache(key=row["key"], stage=row["stage"], result=row["result"], cost_usd=row["cost_usd"]))
                added += 1
        ds = ensure_sample_dataset(db)
        emb = data.get("sample_embeddings", {})
        filled = 0
        for m in db.scalars(select(Message).where(Message.dataset_id == ds.id, Message.embedding.is_(None))):
            if (b := emb.get(str(m.msg_id))) is not None:
                m.embedding = base64.b64decode(b)
                filled += 1
    log.info("golden cache: %d stage rows added, %d sample embeddings filled", added, filled)


def export_golden() -> None:
    """Export every stage-cache row plus the sample chat's message embeddings."""
    init_db()
    with session() as db:
        rows = [{"key": r.key, "stage": r.stage, "result": r.result, "cost_usd": r.cost_usd}
                for r in db.scalars(select(StageCache))]
        ds = ensure_sample_dataset(db)
        emb = {str(m.msg_id): base64.b64encode(m.embedding).decode()
               for m in db.scalars(select(Message).where(Message.dataset_id == ds.id, Message.embedding.is_not(None)))}
    blob = gzip.compress(json.dumps({"dataset": SAMPLE_DATASET_KEY, "stage_cache": rows, "sample_embeddings": emb},
                                    ensure_ascii=False).encode(), compresslevel=9)
    _path().write_bytes(blob)
    print(f"wrote {_path().name}: {len(rows)} stage rows, {len(emb)} embeddings, {len(blob) / 1e6:.1f} MB")


if __name__ == "__main__" and sys.argv[1:] == ["export"]:
    export_golden()
