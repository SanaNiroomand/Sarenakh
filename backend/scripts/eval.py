"""Run the full pipeline on the sample chat and print precision, recall and cost vs ground truth.

    cd backend && python -m scripts.eval --product quera_python --budget 1.0
    python -m scripts.eval --product bluecut_glasses --no-cache        # force fresh model calls
    python -m scripts.eval --run 12                               # re-score an existing run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import secrets

from sqlalchemy import select

from app.db import Product, Run, User, init_db, session
from app.evaluation import evaluate_run
from app.events import bus
from app.pipeline import execute_run
from app.samples import ensure_sample_dataset, sample_products, sample_profile
from app.security import hash_password

EVAL_EMAIL = "eval@sarenakh.local"


def _setup(product_key: str, budget: float) -> int:
    with session() as db:
        ds = ensure_sample_dataset(db)
        user = db.scalar(select(User).where(User.email == EVAL_EMAIL))
        if user is None:
            user = User(email=EVAL_EMAIL, name="eval", password_hash=hash_password(secrets.token_urlsafe(24)))
            db.add(user)
            db.flush()
        product = db.scalar(select(Product).where(Product.user_id == user.id, Product.sample_key == product_key))
        sp = sample_products()[product_key]
        if product is None:
            product = Product(user_id=user.id, name=sp["name"], description=sp["description"], sample_key=product_key)
            db.add(product)
        product.profile = sample_profile(product_key)  # always the latest committed profile
        db.flush()
        run = Run(user_id=user.id, product_id=product.id, dataset_id=ds.id, budget_usd=budget, profile=product.profile)
        db.add(run)
        db.flush()
        return run.id


async def _printer(run_id: int, quiet: bool) -> None:
    q = bus.subscribe(run_id)
    try:
        while True:
            ev = await q.get()
            if not quiet or ev["type"] in ("stage", "verdict", "done", "error"):
                cost = f"  (${ev['cost_usd']:.4f})" if ev["cost_usd"] else ""
                print(f"[{ev['type']:<11}] {ev['text']}{cost}", flush=True)
            if ev["type"] == "done":
                return
    finally:
        bus.unsubscribe(run_id, q)


def _report(rep: dict) -> None:
    print("\n" + "=" * 72)
    print(f"run #{rep['run_id']}  product={rep['product']}  status={rep['status']}  stop={rep['stop_reason']}")
    print(f"found {rep['found']}/{rep['real_leads']} real leads, {rep['false_positives']} false positives")
    print(f"precision={rep['precision']:.2f}  recall={rep['recall']:.2f}  f1={rep['f1']:.2f}  "
          f"prefilter_recall={rep['prefilter_recall']:.2f}")
    cpl = f"${rep['cost_per_lead_usd']:.4f}" if rep["cost_per_lead_usd"] is not None else "-"
    print(f"cost=${rep['cost_usd']:.4f}  equivalent (no cache)=${rep['equivalent_cost_usd']:.4f}  cost/lead={cpl}")
    print("-" * 72)
    for e in rep["leads"]:
        mark = "✓" if e["found"] else "✗"
        print(f" {mark} {e['label']:<6} #{e['msg_id']} {e['author'][:14]:<14} stage={e['stage']:<17} "
              f"decision={e['decision']:<8} rel={e['relevance']} fit={e['fit']}  {e['why_not'] or ''}")
    print("-" * 72)
    for e in rep["decoys"]:
        mark = "✗ FOOLED" if e["fooled"] else "✓"
        print(f" {mark} {e['label']:<6} #{e['msg_id']} {e['author'][:14]:<14} stage={e['stage']:<17} "
              f"decision={e['decision']:<8} rel={e['relevance']} fit={e['fit']}")
    for fp in rep["false_positive_rows"]:
        print(f" FP #{fp['msg_id']} fit={fp['fit']} need={fp['stated_need']}")
    print("=" * 72)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--product", default="quera_python", choices=list(sample_products()))
    ap.add_argument("--budget", type=float, default=1.0)
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--run", type=int, help="only re-score an existing run")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    init_db()
    if a.run:
        run_id = a.run
    else:
        run_id = _setup(a.product, a.budget)
        printer = asyncio.create_task(_printer(run_id, a.quiet))
        await execute_run(run_id, replay_delay=0, use_cache=not a.no_cache)
        await printer
    rep = evaluate_run(run_id)
    if rep is None:
        print("run is not on the sample chat with a sample product")
        return
    _report(rep)
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
    with session() as db:
        r = db.get(Run, run_id)
        print("stage cost:", r.stats.get("stage_cost"), " duration:", r.stats.get("duration_s"), "s",
              " funnel:", r.stats.get("funnel"))


if __name__ == "__main__":
    asyncio.run(main())
