"""Shape a finished (or running) run into the dashboard payload."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .agents.scoring import temperature, weakest_axis
from .agents.schemas import Verdict
from .db import Analysis, Dataset, Feedback, Message, Product, Run

TEMP_SCORE = {"cold": 1, "warm": 2, "hot": 3}
FUNNEL_FA = {
    "scanned": "پیام‌های خوانده‌شده",
    "prefiltered": "پیش‌فیلتر معنایی",
    "triaged": "تریاژ سریع",
    "investigated": "بررسی عمیق",
    "leads": "سرنخ واقعی",
}


def _snip(t: str, n: int = 160) -> str:
    t = " ".join(t.split())
    return t if len(t) <= n else t[: n - 1] + "…"


def run_summary(db: Session, run: Run) -> dict[str, Any]:
    product = db.get(Product, run.product_id)
    ds = db.get(Dataset, run.dataset_id)
    st = run.stats or {}
    funnel = st.get("funnel", {})
    return {
        "id": run.id, "status": run.status, "budget_usd": run.budget_usd, "cost_usd": run.cost_usd,
        "saved_usd": run.saved_usd, "stop_reason": run.stop_reason, "error": run.error,
        "created_at": run.created_at, "started_at": run.started_at, "finished_at": run.finished_at,
        "product": {"id": product.id, "name": product.name, "sample_key": product.sample_key} if product else None,
        "dataset": {"id": ds.id, "name": ds.name, "sample_key": ds.sample_key} if ds else None,
        "leads": funnel.get("leads"), "scanned": funnel.get("scanned"),
        "duration_s": st.get("duration_s"),
    }


def build_results(db: Session, run: Run, user_id: int) -> dict[str, Any]:
    analyses = list(db.scalars(select(Analysis).where(Analysis.run_id == run.id)))
    msgs = {m.msg_id: m for m in db.scalars(select(Message).where(Message.dataset_id == run.dataset_id))}
    votes = {f.msg_id: f.vote for f in db.scalars(
        select(Feedback).where(Feedback.run_id == run.id, Feedback.user_id == user_id))}
    st = run.stats or {}
    stage_cost = st.get("stage_cost", {})
    stage_saved = st.get("stage_saved", {})

    def sc(*stages: str) -> float:
        return round(sum(stage_cost.get(s, 0) + stage_saved.get(s, 0) for s in stages), 6)

    def msg_brief(mid: int) -> dict | None:
        m = msgs.get(mid)
        return {"msg_id": mid, "author": m.author, "date": m.date, "text": _snip(m.text, 220)} if m else None

    leads, watch, rejected, opportunity = [], [], [], []
    triaged_n = sum(1 for a in analyses if a.triage)
    triage_unit = sc("triage") / triaged_n if triaged_n else 0.0

    for a in analyses:
        m = msgs.get(a.msg_id)
        if m is None:
            continue
        base = {
            "msg_id": a.msg_id, "author": m.author, "author_id": m.author_id, "date": m.date,
            "text": m.text, "lang": m.lang, "decision": a.decision, "why_not": a.why_not, "stage": a.stage,
            "triage": a.triage, "fit": a.fit, "cached": a.cached,
            "cost_usd": round(a.cost_usd or 0, 6), "equiv_cost_usd": round((a.cost_usd or 0) + (a.saved_usd or 0), 6),
        }
        if a.verdict:
            v = Verdict(**a.verdict)
            scores = v.scores.model_dump()
            temp = temperature(v)
            item = {
                **base, "scores": scores, "temperature": temp, "weak": weakest_axis(scores),
                "verdict": {"stated_need": v.stated_need, "reasoning": v.reasoning, "timing": v.timing,
                            "action": v.action, "disqualifiers_found": v.disqualifiers_found,
                            "thread_resolved": v.thread_resolved, "evidence_msg_ids": v.evidence_msg_ids},
                "evidence": [b for i in dict.fromkeys([a.msg_id, *v.evidence_msg_ids]) if (b := msg_brief(i))],
                "reply": a.reply, "critic": a.critic, "trace": a.trace or [], "vote": votes.get(a.msg_id, 0),
            }
            {"lead": leads, "watch": watch}.get(a.decision, rejected).append(item)
            opportunity.append({
                "msg_id": a.msg_id, "author": m.author, "decision": a.decision, "kind": "investigated",
                "cost": item["equiv_cost_usd"], "quality": a.fit or 0, "temperature": TEMP_SCORE[temp],
            })
        elif a.triage:
            rel = a.triage.get("relevance", 0)
            if a.decision == "skipped" and rel >= 3:
                rejected.append({**base, "relevance": rel})
            opportunity.append({
                "msg_id": a.msg_id, "author": m.author, "decision": a.decision, "kind": "triage",
                "cost": round(triage_unit, 7), "quality": rel, "temperature": 1,
            })

    leads.sort(key=lambda x: -(x["fit"] or 0))
    watch.sort(key=lambda x: -(x["fit"] or 0))
    rejected.sort(key=lambda x: (0 if x.get("verdict") else 1, -((x.get("fit") or x.get("relevance") or 0))))

    funnel = st.get("funnel", {})
    equiv = round((run.cost_usd or 0) + (run.saved_usd or 0), 6)
    n_leads = len(leads)
    return {
        "run": run_summary(db, run),
        "stats": st,
        "ideal_shape": (run.profile or {}).get("ideal_shape"),
        "product_name": (run.profile or {}).get("product_name"),
        "kpi": {
            "scanned": funnel.get("scanned", 0),
            "leads": n_leads,
            "cost_usd": round(run.cost_usd or 0, 6),
            "equivalent_cost_usd": equiv,
            "cost_per_lead_usd": round(equiv / n_leads, 6) if n_leads else None,
            "saved_usd": round(run.saved_usd or 0, 6),
        },
        "funnel": [
            {"stage": "scanned", "label": FUNNEL_FA["scanned"], "count": funnel.get("scanned", 0), "cost": 0.0},
            {"stage": "prefiltered", "label": FUNNEL_FA["prefiltered"], "count": funnel.get("prefiltered", 0), "cost": sc("embed")},
            {"stage": "triaged", "label": FUNNEL_FA["triaged"], "count": funnel.get("triaged", 0), "cost": sc("triage")},
            {"stage": "investigated", "label": FUNNEL_FA["investigated"], "count": funnel.get("investigated", 0), "cost": sc("investigate", "critic")},
            {"stage": "leads", "label": FUNNEL_FA["leads"], "count": n_leads, "cost": sc("draft")},
        ],
        "burn": st.get("burn", []),
        "leads": leads,
        "watch": watch,
        "rejected": rejected[:60],
        "opportunity": opportunity,
    }
