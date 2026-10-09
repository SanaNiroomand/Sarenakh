import asyncio
import json
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agents.context import GlobalSpend
from ..config import get_settings
from ..db import AgentEvent, Analysis, Feedback, Message, Run, User, get_db, session, user_spend_since
from ..evaluation import evaluate_run
from ..events import bus
from ..results import build_results, run_summary
from ..runner import active_runs_for, is_active, start_run, stop_run
from ..samples import SAMPLE_DATASET_KEY, sample_profile
from ..security import current_user, rate_limit
from .datasets import readable_dataset
from .products import own_product

router = APIRouter(prefix="/api/runs", tags=["runs"])


class RunIn(BaseModel):
    product_id: int
    dataset_id: int
    budget_usd: float = Field(gt=0)


class FeedbackIn(BaseModel):
    msg_id: int
    vote: Literal[1, -1, 0]
    note: str = Field(default="", max_length=500)


def own_run(db: Session, user: User, run_id: int) -> Run:
    run = db.get(Run, run_id)
    if not run or run.user_id != user.id:
        raise HTTPException(404, "اجرا پیدا نشد.")
    return run


def _fa_usd(x: float) -> str:
    return f"{x:.2f}$"


@router.post("", dependencies=[Depends(rate_limit("run", 20, 3600, per="user")), Depends(rate_limit("run-ip", 60, 3600))])
async def create_run(body: RunIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    s = get_settings()
    product = own_product(db, user, body.product_id)
    if not product.profile:
        raise HTTPException(400, "اول پروفایل مشتری را بسازید (مرحله معرفی محصول).")
    ds = readable_dataset(db, user, body.dataset_id)
    if not (ds.stats or {}).get("analyzable"):
        raise HTTPException(400, "این مجموعه پیام متنی قابل بررسی ندارد.")
    budget = round(body.budget_usd, 4)
    if not (0.02 <= budget <= s.max_run_budget_usd):
        raise HTTPException(422, f"بودجه هر اجرا باید بین ۰٫۰۲ تا {s.max_run_budget_usd:.2f} دلار باشد.")
    if active_runs_for(user.id):
        raise HTTPException(409, "یک اجرای دیگر هنوز در حال انجام است. صبر کنید تا تمام شود.")
    ms = request.app.state.model_status
    if not (ms.get("ok") or ms.get("skipped")):
        raise HTTPException(503, "سرویس هوش مصنوعی موقتا در دسترس نیست. نتایج قبلی قابل مشاهده‌اند؛ کمی بعد دوباره تلاش کنید.")

    # A sample product, unchanged, on the sample chat replays stored results: (almost) free.
    is_replay = (ds.sample_key == SAMPLE_DATASET_KEY and product.sample_key is not None
                 and product.profile == sample_profile(product.sample_key))
    if not is_replay:
        if GlobalSpend.get() + budget > s.global_spend_cap_usd:
            raise HTTPException(403, "سقف هزینه این نسخه نمایشی پر شده است. اجرای نمونه (Try sample) همچنان کار می‌کند.")
        spent_today = user_spend_since(db, user.id, time.time() - 86400)
        if spent_today + budget > s.user_daily_cap_usd:
            left = max(0.0, s.user_daily_cap_usd - spent_today)
            raise HTTPException(429, f"سقف هزینه روزانه شما ({_fa_usd(s.user_daily_cap_usd)}) نزدیک است؛ "
                                     f"حداکثر {_fa_usd(left)} دیگر می‌توانید خرج کنید.")

    run = Run(user_id=user.id, product_id=product.id, dataset_id=ds.id, budget_usd=budget,
              profile=product.profile, status="queued", stats={"replay": is_replay})
    db.add(run)
    db.commit()
    start_run(run.id)
    return run_summary(db, run)


@router.get("")
def list_runs(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    runs = db.scalars(select(Run).where(Run.user_id == user.id).order_by(Run.created_at.desc()).limit(50))
    return [run_summary(db, r) for r in runs]


@router.get("/{run_id}")
def get_run(run_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return run_summary(db, own_run(db, user, run_id))


@router.get("/{run_id}/results")
def results(run_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return build_results(db, own_run(db, user, run_id), user.id)


@router.get("/{run_id}/evaluation")
def evaluation(run_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    own_run(db, user, run_id)
    rep = evaluate_run(run_id)
    if rep is None:
        raise HTTPException(404, "ارزیابی فقط برای اجرای محصولات نمونه روی گفتگوی نمونه در دسترس است.")
    return rep


@router.get("/{run_id}/events")
def events(run_id: int, after: int = 0, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    own_run(db, user, run_id)
    rows = db.scalars(select(AgentEvent).where(AgentEvent.run_id == run_id, AgentEvent.seq > after)
                      .order_by(AgentEvent.seq).limit(2000))
    return [_event_dict(e) for e in rows]


def _event_dict(e: AgentEvent) -> dict:
    return {"seq": e.seq, "ts": e.ts, "type": e.type, "msg_id": e.msg_id, "text": e.text, "data": e.data,
            "cost_usd": round(e.cost_usd or 0, 6)}


def _sse(ev: dict) -> str:
    return f"id: {ev['seq']}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"


@router.get("/{run_id}/stream")
async def stream(run_id: int, request: Request, after: int = 0, user: User = Depends(current_user),
                 db: Session = Depends(get_db)) -> StreamingResponse:
    own_run(db, user, run_id)
    last = int(request.headers.get("last-event-id") or after or 0)

    async def gen():
        nonlocal last
        q = bus.subscribe(run_id)  # subscribe first so nothing falls between backlog and live
        try:
            with session() as s:
                backlog = [_event_dict(e) for e in s.scalars(
                    select(AgentEvent).where(AgentEvent.run_id == run_id, AgentEvent.seq > last).order_by(AgentEvent.seq))]
                status = s.get(Run, run_id).status
            for ev in backlog:
                yield _sse(ev)
                last = ev["seq"]
                if ev["type"] == "done":
                    return
            if status not in ("queued", "running") and not is_active(run_id):
                yield _sse({"seq": last + 1, "ts": time.time(), "type": "done", "msg_id": None,
                            "text": "🏁 اجرا پایان یافته است.", "data": {"status": status}, "cost_usd": 0})
                return
            while True:
                if await request.is_disconnected():
                    return
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                except TimeoutError:
                    yield ": ping\n\n"
                    if not is_active(run_id):
                        return
                    continue
                if ev["seq"] <= last:
                    continue
                yield _sse(ev)
                last = ev["seq"]
                if ev["type"] == "done":
                    return
        finally:
            bus.unsubscribe(run_id, q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/{run_id}/stop")
def stop(run_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    own_run(db, user, run_id)
    return {"stopped": stop_run(run_id)}


@router.post("/{run_id}/feedback")
def feedback(run_id: int, body: FeedbackIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    run = own_run(db, user, run_id)
    a = db.scalar(select(Analysis).where(Analysis.run_id == run_id, Analysis.msg_id == body.msg_id))
    m = db.scalar(select(Message).where(Message.dataset_id == run.dataset_id, Message.msg_id == body.msg_id))
    if a is None or m is None:
        raise HTTPException(404, "این پیام در نتایج این اجرا نیست.")
    fb = db.scalar(select(Feedback).where(Feedback.user_id == user.id, Feedback.run_id == run_id,
                                          Feedback.msg_id == body.msg_id))
    if body.vote == 0:
        if fb:
            db.delete(fb)
        return {"ok": True, "vote": 0}
    reason = a.why_not or (a.verdict or {}).get("reasoning", "")
    if fb is None:
        fb = Feedback(user_id=user.id, product_id=run.product_id, run_id=run_id, msg_id=body.msg_id,
                      vote=body.vote, message_text=m.norm, agent_decision=a.decision)
        db.add(fb)
    fb.vote, fb.note, fb.agent_reason, fb.embedding = body.vote, body.note.strip(), reason, m.embedding
    return {"ok": True, "vote": body.vote}
