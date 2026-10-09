"""Background run management: one asyncio task per run inside the single uvicorn worker."""

from __future__ import annotations

import asyncio
import logging
import time

from sqlalchemy import select

from .config import get_settings
from .db import Run, session
from .pipeline import execute_run

log = logging.getLogger("sarenakh.runner")

_tasks: dict[int, asyncio.Task] = {}


def start_run(run_id: int) -> None:
    task = asyncio.create_task(execute_run(run_id, replay_delay=get_settings().replay_delay_s))
    _tasks[run_id] = task

    def _done(t: asyncio.Task) -> None:
        _tasks.pop(run_id, None)
        if not t.cancelled() and t.exception():
            log.error("run %s crashed: %s", run_id, t.exception())

    task.add_done_callback(_done)


def is_active(run_id: int) -> bool:
    return run_id in _tasks


def stop_run(run_id: int) -> bool:
    t = _tasks.get(run_id)
    if t:
        t.cancel()
        return True
    return False


def active_runs_for(user_id: int) -> list[int]:
    with session() as db:
        ids = db.scalars(select(Run.id).where(Run.user_id == user_id, Run.status.in_(["queued", "running"])))
        return [i for i in ids if i in _tasks]


def recover_stale_runs() -> None:
    """Runs left queued/running by a restart can't continue; close them honestly."""
    with session() as db:
        for run in db.scalars(select(Run).where(Run.status.in_(["queued", "running"]))):
            run.status = "failed"
            run.error = "server restarted during the run"
            run.finished_at = time.time()
