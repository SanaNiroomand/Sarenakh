"""Score a run on the sample chat against samples/ground_truth.json (leads counted per person)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from .db import Analysis, Dataset, Product, Run, session
from .samples import SAMPLE_DATASET_KEY, ground_truth


def _outcome(a: Analysis | None) -> dict[str, Any]:
    if a is None:
        return {"stage": "prefilter_dropped", "decision": "dropped", "fit": None, "relevance": None, "why_not": None}
    return {
        "stage": a.stage, "decision": a.decision, "fit": a.fit,
        "relevance": (a.triage or {}).get("relevance"), "why_not": a.why_not,
    }


def evaluate_run(run_id: int) -> dict[str, Any] | None:
    """None if the run is not on the sample chat with a sample product."""
    with session() as db:
        run = db.get(Run, run_id)
        if run is None:
            return None
        product = db.get(Product, run.product_id)
        ds = db.get(Dataset, run.dataset_id)
        if ds.sample_key != SAMPLE_DATASET_KEY or not product.sample_key:
            return None
        gt = ground_truth()["products"].get(product.sample_key)
        if gt is None:
            return None
        analyses = list(db.scalars(select(Analysis).where(Analysis.run_id == run_id)))

    by_msg = {a.msg_id: a for a in analyses}
    lead_rows = [a for a in analyses if a.decision == "lead"]
    pred_users = {a.author_id for a in lead_rows}
    gt_users = {e["user_id"] for e in gt["leads"]}
    tp = pred_users & gt_users
    fp = pred_users - gt_users
    fn = gt_users - pred_users

    def best_for_user(uid: str, msg_id: int) -> Analysis | None:
        """The analysis for the labeled message, or any lead row for that person."""
        return next((a for a in lead_rows if a.author_id == uid), None) or by_msg.get(msg_id)

    leads = [{**e, "found": e["user_id"] in tp, **_outcome(best_for_user(e["user_id"], e["msg_id"]))}
             for e in gt["leads"]]
    decoys = [{**e, "fooled": e["user_id"] in pred_users, **_outcome(by_msg.get(e["msg_id"]))}
              for e in gt["decoys"]]
    false_pos = [{"msg_id": a.msg_id, "author_id": a.author_id, "fit": a.fit,
                  "stated_need": (a.verdict or {}).get("stated_need")} for a in lead_rows if a.author_id in fp]

    precision = len(tp) / len(pred_users) if pred_users else 0.0
    recall = len(tp) / len(gt_users) if gt_users else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    cost = run.cost_usd
    equiv = run.cost_usd + run.saved_usd
    gt_msg_ids = {e["msg_id"] for e in gt["leads"]}
    return {
        "run_id": run_id,
        "product": product.sample_key,
        "real_leads": len(gt_users),
        "found": len(tp),
        "false_positives": len(fp),
        "missed": len(fn),
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "cost_usd": round(cost, 6),
        "equivalent_cost_usd": round(equiv, 6),  # what it would cost without the cache
        "cost_per_lead_usd": round(equiv / len(pred_users), 6) if pred_users else None,
        "prefilter_recall": round(sum(1 for i in gt_msg_ids if i in by_msg) / len(gt_msg_ids), 3),
        "leads": leads,
        "decoys": decoys,
        "false_positive_rows": false_pos,
        "stop_reason": run.stop_reason,
        "status": run.status,
    }
