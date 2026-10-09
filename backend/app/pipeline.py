"""Orchestrator: prefilter -> triage -> investigate (+critic, +draft), budget-aware, every step
logged as an AgentEvent and streamed to the UI."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import Any

import numpy as np
from sqlalchemy import func, select

from .agents.context import (
    Budget, BudgetExceeded, FewShot, GlobalCapReached, Reservation, RunContext,
)
from .agents.critic import critique
from .agents.drafter import draft_reply
from .agents.investigator import investigate, is_cached
from .agents.prefilter import prefilter
from .agents.scoring import MENTION_FIT, decide, fit_score, needs_critic, temperature, weakest_axis
from .agents.schemas import TriageItem
from .agents.triage import triage
from .chat.index import ChatIndex
from .chat.parse import ChatMessage
from .config import get_settings
from .db import AgentEvent, Analysis, Dataset, Feedback, Message, Product, Run, session
from .events import bus
from .llm import get_llm
from .schemas import Profile

log = logging.getLogger("sarenakh.pipeline")

MIN_RELEVANCE = 6  # triage score needed for a deep investigation
CONCURRENCY = 4  # investigations in flight
EST_FIRST = 0.03  # USD reserved per candidate until we have real numbers

TEMP_FA = {"hot": "داغ 🔥", "warm": "گرم", "cold": "سرد"}


def _snip(text: str, n: int = 60) -> str:
    t = " ".join(text.split())
    return t if len(t) <= n else t[: n - 1] + "…"


class Recorder:
    """Persists events/analyses for one run and publishes events to live subscribers."""

    def __init__(self, run_id: int):
        self.run_id = run_id
        with session() as db:
            self.seq = db.scalar(select(func.coalesce(func.max(AgentEvent.seq), 0)).where(AgentEvent.run_id == run_id))

    async def emit(self, type: str, text: str, *, msg_id: int | None = None, data: dict | None = None,
                   cost: float = 0.0) -> None:
        self.seq += 1
        ev = {"seq": self.seq, "ts": time.time(), "type": type, "msg_id": msg_id, "text": text,
              "data": data or {}, "cost_usd": round(cost, 6)}
        with session() as db:
            db.add(AgentEvent(run_id=self.run_id, seq=ev["seq"], ts=ev["ts"], type=type, msg_id=msg_id,
                              text=text, data=ev["data"], cost_usd=cost))
        bus.publish(self.run_id, ev)

    def save(self, rows: list[dict]) -> None:
        """Upsert analyses by (run_id, msg_id)."""
        if not rows:
            return
        with session() as db:
            existing = {a.msg_id: a for a in db.scalars(
                select(Analysis).where(Analysis.run_id == self.run_id,
                                       Analysis.msg_id.in_([r["msg_id"] for r in rows])))}
            for r in rows:
                a = existing.get(r["msg_id"])
                if a is None:
                    db.add(Analysis(run_id=self.run_id, **r))
                else:
                    for k, v in r.items():
                        setattr(a, k, v)

    def update_run(self, **fields: Any) -> None:
        with session() as db:
            run = db.get(Run, self.run_id)
            for k, v in fields.items():
                setattr(run, k, v)


def _load(run_id: int):
    with session() as db:
        run = db.get(Run, run_id)
        product = db.get(Product, run.product_id)
        ds = db.get(Dataset, run.dataset_id)
        rows = list(db.scalars(select(Message).where(Message.dataset_id == ds.id).order_by(Message.ts, Message.msg_id)))
        fb = list(db.scalars(select(Feedback).where(Feedback.product_id == product.id, Feedback.embedding.is_not(None))))
        msgs = [ChatMessage(id=r.msg_id, ts=r.ts, date=r.date, author_id=r.author_id, author=r.author, text=r.text,
                            norm=r.norm, reply_to=r.reply_to, kind=r.kind, lang=r.lang,
                            forwarded_from=r.forwarded_from, emojis=r.emojis) for r in rows]
        emb = {r.msg_id: np.frombuffer(r.embedding, dtype=np.float32) for r in rows if r.embedding}
        fewshot = [FewShot(text=f.message_text, vote=f.vote, agent_decision=f.agent_decision, note=f.note,
                           vec=np.frombuffer(f.embedding, dtype=np.float32)) for f in fb]
        return run, product, ds, msgs, emb, fewshot


def _persist_embeddings(dataset_id: int, new: dict[int, np.ndarray]) -> None:
    with session() as db:
        rows = db.scalars(select(Message).where(Message.dataset_id == dataset_id, Message.msg_id.in_(list(new))))
        for r in rows:
            r.embedding = new[r.msg_id].astype(np.float32).tobytes()


async def execute_run(run_id: int, *, replay_delay: float | None = None, use_cache: bool = True) -> None:
    s = get_settings()
    rec = Recorder(run_id)
    run, product, ds, msgs, emb, fewshot = _load(run_id)
    profile = Profile(**run.profile)
    budget = Budget(run.budget_usd, s.global_spend_cap_usd, run_id=run_id, user_id=run.user_id)
    ctx = RunContext(
        profile=profile, index=ChatIndex(msgs), llm=get_llm(), budget=budget, settings=s, emit=rec.emit,
        run_id=run_id, user_id=run.user_id, product_id=product.id, dataset_id=ds.id, embeddings=emb,
        fewshot=fewshot, on_new_embeddings=lambda new: _persist_embeddings(ds.id, new),
    )
    ctx.use_cache = use_cache
    if replay_delay is not None:
        ctx.replay_delay = replay_delay
    t0 = time.time()
    stats: dict[str, Any] = {"funnel": {}, "burn": [], "cache_hits": 0}
    rec.update_run(status="running", started_at=t0)
    status, stop_reason, error = "done", None, None

    def snapshot() -> None:
        stats["stage_cost"] = {k: round(v, 6) for k, v in budget.by_stage.items()}
        stats["stage_saved"] = {k: round(v, 6) for k, v in budget.saved_by_stage.items()}
        stats["duration_s"] = round(time.time() - t0, 1)
        rec.update_run(cost_usd=round(budget.spent, 6), saved_usd=round(budget.saved, 6), stats=dict(stats))

    try:
        analyzable = [m for m in msgs if m.analyzable]
        stats["funnel"]["scanned"] = len(analyzable)
        await rec.emit("stage", f"🧶 شروع: {len(analyzable)} پیام از «{ds.name}» برای «{profile.product_name}»",
                       data={"stage": "start", "scanned": len(analyzable), "budget": run.budget_usd})

        # 1) embedding pre-filter -------------------------------------------------------------
        await rec.emit("stage", "🪡 پیش‌فیلتر معنایی: مقایسه پیام‌ها با نشانه‌های خرید مشتری ایده‌آل…",
                       data={"stage": "prefilter"})
        kept = await prefilter(ctx, analyzable)
        stats["funnel"]["prefiltered"] = len(kept)
        rec.save([{"msg_id": m.id, "author_id": m.author_id, "stage": "prefilter", "prefilter_sim": round(sim, 4),
                   "decision": "pending"} for m, sim in kept])
        await rec.emit("stage", f"🪡 {len(kept)} از {len(analyzable)} پیام به نشانه‌های خرید نزدیک بودند؛ بقیه کنار رفتند",
                       data={"stage": "prefilter", "kept": len(kept), "of": len(analyzable)},
                       cost=budget.by_stage.get("embed", 0.0))
        snapshot()

        # 2) triage ---------------------------------------------------------------------------
        await rec.emit("stage", f"⚖️ تریاژ سریع با {s.triage_model}: دسته‌های ۲۵تایی…", data={"stage": "triage"})
        tri, tri_stop = await triage(ctx, [m for m, _ in kept])
        stats["funnel"]["triaged"] = len(tri)
        sim_of = {m.id: sim for m, sim in kept}
        rows = []
        for m, _ in kept:
            t = tri.get(m.id)
            if t is None:
                rows.append({"msg_id": m.id, "author_id": m.author_id, "stage": "prefilter", "decision": "pending",
                             "why_not": "بودجه به تریاژ این پیام نرسید"})
            elif t.relevance < MIN_RELEVANCE:
                rows.append({"msg_id": m.id, "author_id": m.author_id, "stage": "triage", "triage": t.model_dump(),
                             "decision": "skipped", "why_not": t.reason})
            else:
                rows.append({"msg_id": m.id, "author_id": m.author_id, "stage": "triage", "triage": t.model_dump(),
                             "decision": "pending"})
        rec.save(rows)
        snapshot()
        if tri_stop:
            raise BudgetExceeded() if tri_stop == "budget" else GlobalCapReached()

        # 3) pick candidates: best message per person, highest triage score first ---------------
        # ties: buying intent beats a question beats a complaint; then the more recent (current) need
        signal_rank = {"purchase_intent": 0, "question": 1, "complaint": 2, "noise": 3}
        hot = sorted((m for m, _ in kept if (t := tri.get(m.id)) and t.relevance >= MIN_RELEVANCE),
                     key=lambda m: (-tri[m.id].relevance, signal_rank[tri[m.id].signal], -m.ts, -sim_of[m.id]))
        cands: list[ChatMessage] = []
        others: dict[str, list[int]] = defaultdict(list)
        seen_authors: set[str] = set()
        merged = []
        for m in hot:
            if m.author_id in seen_authors:
                others[m.author_id].append(m.id)
                merged.append({"msg_id": m.id, "author_id": m.author_id, "stage": "triage", "decision": "skipped",
                               "why_not": "پیام دیگری از همین فرد بررسی شد (هر نفر یک بار)"})
            else:
                seen_authors.add(m.author_id)
                cands.append(m)
        rec.save(merged)
        await rec.emit("stage", f"🔦 {len(cands)} نفر برای پیگیری عمیق انتخاب شدند (به ترتیب امتیاز تریاژ)",
                       data={"stage": "investigate", "candidates": len(cands),
                             "list": [{"msg_id": m.id, "author": m.author, "relevance": tri[m.id].relevance}
                                      for m in cands]})

        # 4) investigate in priority order until the budget runs out ----------------------------
        stop_reason = await _investigate_all(ctx, rec, stats, cands, tri, others, snapshot)
    except BudgetExceeded:
        stop_reason = "budget"
    except GlobalCapReached:
        stop_reason, status = "global_cap", "stopped"
    except asyncio.CancelledError:
        status, stop_reason = "stopped", "user"
        raise
    except Exception as e:  # noqa: BLE001
        log.exception("run %s failed", run_id)
        status, error = "failed", f"{type(e).__name__}: {e}"
    finally:
        with session() as db:
            leads = db.scalar(select(func.count()).select_from(Analysis).where(
                Analysis.run_id == run_id, Analysis.decision == "lead"))
            investigated = db.scalar(select(func.count()).select_from(Analysis).where(
                Analysis.run_id == run_id, Analysis.verdict.is_not(None)))
        stats["funnel"]["investigated"] = investigated
        stats["funnel"]["leads"] = leads
        stats["stop_reason"] = stop_reason
        snapshot()
        rec.update_run(status=status, stop_reason=stop_reason, error=error, finished_at=time.time())
        cost_txt = f"${budget.spent:.4f}"
        if status == "failed":
            await rec.emit("error", "⚠️ اجرا با خطا متوقف شد. نتایج تا این لحظه ذخیره شده‌اند.", data={"error": error})
        msg = {
            "budget": "💸 بودجه این اجرا تمام شد؛ بقیه نامزدها بررسی نشدند.",
            "global_cap": "⛔ سقف هزینه کل سامانه پر شده است.",
            "user": "⏹ اجرا متوقف شد.",
        }.get(stop_reason or "", "")
        await rec.emit("done", f"🏁 پایان: {leads} سرنخ واقعی، هزینه {cost_txt}" + (f" — {msg}" if msg else ""),
                       data={"status": status, "leads": leads, "cost_usd": round(budget.spent, 6),
                             "saved_usd": round(budget.saved, 6), "stop_reason": stop_reason})


async def _investigate_all(ctx: RunContext, rec: Recorder, stats: dict, cands: list[ChatMessage],
                           tri: dict[int, TriageItem], others: dict[str, list[int]], snapshot) -> str | None:
    budget = ctx.budget
    all_cached = bool(cands) and all(is_cached(ctx, c) for c in cands)
    sem = asyncio.Semaphore(2 if all_cached else CONCURRENCY)  # a replay reads better two at a time
    lead_authors: set[str] = set()
    costs: list[float] = []
    tasks: list[asyncio.Task] = []
    stop_reason: str | None = None
    counters = {"leads": 0, "done": 0}

    def estimate() -> float:
        return max(0.01, (sum(costs) / len(costs)) * 1.25) if costs else EST_FIRST

    async def one(cand: ChatMessage, res: Reservation) -> None:
        spent_before, saved_before = budget.spent, budget.saved
        row: dict[str, Any] = {"msg_id": cand.id, "author_id": cand.author_id, "stage": "investigate"}
        try:
            await rec.emit("investigate", f"🔎 دنبال کردن سرنخ #{cand.id} از {cand.author}: «{_snip(cand.norm)}»",
                           msg_id=cand.id, data={"author": cand.author, "relevance": tri[cand.id].relevance})
            inv = await investigate(ctx, cand, tri[cand.id], others.get(cand.author_id, []), res)
            v = inv.verdict
            scores = v.scores.model_dump()
            fit = fit_score(scores)
            decision, why_not = decide(v, fit)
            if inv.cached:
                stats["cache_hits"] += 1
            row.update(verdict=v.model_dump(), trace=inv.trace, fit=fit, cached=inv.cached)

            if decision == "lead" and needs_critic(fit):
                row["stage"] = "critic"
                await rec.emit("critic", f"😈 وکیل مدافع شیطان: تلاش برای رد سرنخ {cand.author} (تناسب {fit}/۱۰ مرزی است)…",
                               msg_id=cand.id)
                try:
                    cr, _, _ = await critique(ctx, cand, v, fit, res)
                except (BudgetExceeded, GlobalCapReached):
                    raise
                except Exception as e:  # noqa: BLE001 — fail open: keep the investigator's verdict
                    log.warning("critic failed for %s: %s", cand.id, e)
                    await rec.emit("error", "😈 منتقد پاسخی نداد؛ نظر عامل بررسی حفظ شد", msg_id=cand.id)
                    cr = None
                if cr is not None:
                    row["critic"] = cr.model_dump()
                    verdict_txt = "سرنخ ماند ✅" if cr.survives else "سرنخ رد شد ❌"
                    await rec.emit("critic", f"😈 «{_snip(cr.strongest_objection, 110)}» → {verdict_txt}",
                                   msg_id=cand.id, data={"survives": cr.survives})
                    if not cr.survives:
                        decision, why_not = "rejected", f"منتقد: {cr.reason}"

            if inv.cached:  # pace replays so a human can follow the feed
                await asyncio.sleep(ctx.replay_delay)
            if decision == "lead" and cand.author_id in lead_authors:
                decision, why_not = "skipped", "به این فرد قبلا پیشنهاد داده شده (هرگز دوبار نه)"
            if decision == "lead":
                lead_authors.add(cand.author_id)
                mode = "help_soft_mention" if fit >= MENTION_FIT else "pure_help"
                mode_fa = "کمک + معرفی ملایم" if mode == "help_soft_mention" else "فقط کمک"
                row["stage"] = "draft"
                await rec.emit("draft", f"✍️ نوشتن پاسخ کمک‌محور برای {cand.author} ({mode_fa})", msg_id=cand.id)
                try:
                    reply, _, draft_cached = await draft_reply(ctx, cand, v, mode, res)
                    row["reply"] = reply
                    if draft_cached:
                        await asyncio.sleep(ctx.replay_delay)
                except (BudgetExceeded, GlobalCapReached):
                    raise
                except Exception as e:  # noqa: BLE001 — a lead without a draft is still a lead
                    log.warning("draft failed for %s: %s", cand.id, e)
                    await rec.emit("error", f"✍️ پیش‌نویس پاسخ برای {cand.author} ساخته نشد", msg_id=cand.id)

            row.update(decision=decision, why_not=why_not)
            temp = temperature(v)
            if decision == "lead":
                counters["leads"] += 1
                text = (f"🎯 {cand.author}: {_snip(v.stated_need, 70)} → تناسب {fit}/۱۰، "
                        f"{TEMP_FA[temp]}")
            elif decision == "watch":
                text = f"👀 {cand.author}: زیر نظر — {_snip(why_not or '', 80)}"
            else:
                text = f"✖️ {cand.author}: رد شد — {_snip(why_not or '', 80)}"
            await rec.emit("verdict", text, msg_id=cand.id, data={
                "decision": decision, "fit": fit, "scores": scores, "temperature": temp,
                "weak": weakest_axis(scores), "cached": inv.cached, "steps": inv.steps,
            }, cost=budget.spent - spent_before)
        except (BudgetExceeded, GlobalCapReached):
            row.update(decision="pending", why_not="بودجه در میانه بررسی تمام شد")
        except Exception as e:  # noqa: BLE001
            log.exception("investigation of %s failed", cand.id)
            row.update(decision="rejected", why_not="خطا در بررسی این پیام")
            await rec.emit("error", f"⚠️ بررسی پیام #{cand.id} با خطا روبه‌رو شد و رد شد", msg_id=cand.id,
                           data={"error": f"{type(e).__name__}: {e}"})
        finally:
            spent = budget.spent - spent_before
            row["cost_usd"] = round(spent, 6)
            row["saved_usd"] = round(budget.saved - saved_before, 6)
            if not row.get("cached") and spent > 0:
                costs.append(spent)
            budget.release(res)
            rec.save([row])
            counters["done"] += 1
            stats["burn"].append({"n": counters["done"], "cost": round(budget.spent, 6),
                                  "equiv_cost": round(budget.spent + budget.saved, 6), "leads": counters["leads"]})
            snapshot()

    not_reached: list[ChatMessage] = []
    for cand in cands:
        if stop_reason:
            not_reached.append(cand)
            continue
        await sem.acquire()
        try:
            res = budget.reserve(0.0 if is_cached(ctx, cand) else estimate())
        except BudgetExceeded:
            stop_reason = "budget"
        except GlobalCapReached:
            stop_reason = "global_cap"
        if stop_reason:
            sem.release()
            not_reached.append(cand)
            continue
        t = asyncio.create_task(one(cand, res))
        t.add_done_callback(lambda _: sem.release())
        tasks.append(t)
    await asyncio.gather(*tasks)

    if not_reached:
        rec.save([{"msg_id": m.id, "author_id": m.author_id, "stage": "triage", "decision": "pending",
                   "why_not": "بودجه به بررسی عمیق این پیام نرسید"} for m in not_reached])
        await rec.emit("stage", f"💸 بودجه تمام شد؛ {len(not_reached)} نامزد بررسی نشدند. با بودجه بیشتر می‌شود ادامه داد.",
                       data={"stage": "budget", "not_reached": [m.id for m in not_reached]})
    return stop_reason
