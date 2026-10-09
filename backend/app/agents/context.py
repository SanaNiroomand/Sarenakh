"""Shared run state: budget with reservations, global spend cap, stage cache, event emitter."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from ..chat.index import ChatIndex
from ..config import Settings
from ..db import SpendLog, StageCache, session, total_spend
from ..llm import LLM, Usage
from ..schemas import Profile


class BudgetExceeded(Exception):
    """The run budget cannot cover the next unit of work."""


class GlobalCapReached(Exception):
    """The app-wide spending cap is reached; no new paid work."""


class GlobalSpend:
    """App-wide running total of paid API spend (single process; seeded from the DB)."""

    total: float | None = None

    @classmethod
    def get(cls) -> float:
        if cls.total is None:
            with session() as db:
                cls.total = total_spend(db)
        return cls.total

    @classmethod
    def add(cls, usd: float) -> None:
        cls.total = cls.get() + usd


@dataclass(eq=False)
class Reservation:
    amount: float
    charged: float = 0.0

    def outstanding(self) -> float:
        return max(0.0, self.amount - self.charged)


class Budget:
    """Run budget. Work is started only if its estimated cost can be reserved; actual charges
    are recorded to spend_log and count against both the run budget and the global cap."""

    def __init__(self, limit_usd: float, global_cap_usd: float, *, run_id: int | None, user_id: int | None):
        self.limit = limit_usd
        self.global_cap = global_cap_usd
        self.run_id = run_id
        self.user_id = user_id
        self.spent = 0.0
        self.saved = 0.0
        self.by_stage: dict[str, float] = defaultdict(float)
        self.saved_by_stage: dict[str, float] = defaultdict(float)
        self._active: set[Reservation] = set()

    def outstanding(self) -> float:
        return sum(r.outstanding() for r in self._active)

    @property
    def remaining(self) -> float:
        return self.limit - self.spent - self.outstanding()

    def reserve(self, estimate: float) -> Reservation:
        if self.remaining < estimate:
            raise BudgetExceeded()
        if GlobalSpend.get() + self.outstanding() + estimate > self.global_cap:
            raise GlobalCapReached()
        r = Reservation(estimate)
        self._active.add(r)
        return r

    def release(self, r: Reservation) -> None:
        self._active.discard(r)

    def charge(self, stage: str, usage: Usage, res: Reservation | None = None) -> float:
        cost = usage.cost_usd
        self.spent += cost
        self.by_stage[stage] += cost
        if res is not None:
            res.charged += cost
        GlobalSpend.add(cost)
        with session() as db:
            db.add(SpendLog(
                user_id=self.user_id, run_id=self.run_id, kind=stage, model=usage.model,
                input_tokens=usage.input_tokens, cached_tokens=usage.cached_tokens,
                output_tokens=usage.output_tokens, cost_usd=cost,
            ))
        return cost

    def credit_cache(self, stage: str, original_cost: float) -> None:
        self.saved += original_cost
        self.saved_by_stage[stage] += original_cost


async def charged(budget: "Budget", stage: str, res: Reservation | None, call: Awaitable) -> tuple[Any, float]:
    """Await a structured LLM call and charge it, including failed calls that still cost tokens."""
    from ..llm import IncompleteOutputError

    try:
        parsed, usage = await call
    except IncompleteOutputError as e:
        budget.charge(stage, e.usage, res)
        raise
    return parsed, budget.charge(stage, usage, res)


# --- stage cache ------------------------------------------------------------------------------


def cache_key(*parts: Any) -> str:
    raw = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def cache_get(key: str) -> tuple[dict, float] | None:
    with session() as db:
        row = db.get(StageCache, key)
        return (row.result, row.cost_usd) if row else None


def cache_put(key: str, stage: str, result: dict, cost: float) -> None:
    with session() as db:
        row = db.get(StageCache, key)
        if row is None:
            db.add(StageCache(key=key, stage=stage, result=result, cost_usd=cost))


def profile_fingerprint(profile: Profile) -> str:
    return cache_key(profile.model_dump())[:24]


# --- run context ------------------------------------------------------------------------------


class Emit(Protocol):
    def __call__(
        self, type: str, text: str, *, msg_id: int | None = None, data: dict | None = None, cost: float = 0.0
    ) -> Awaitable[None]: ...


@dataclass
class FewShot:
    text: str
    vote: int  # +1 lead confirmed, -1 rejected by the owner
    agent_decision: str
    note: str
    vec: np.ndarray


@dataclass
class RunContext:
    profile: Profile
    index: ChatIndex
    llm: LLM
    budget: Budget
    settings: Settings
    emit: Emit
    run_id: int | None = None
    user_id: int | None = None
    product_id: int | None = None
    dataset_id: int | None = None
    embeddings: dict[int, np.ndarray] = field(default_factory=dict)
    fewshot: list[FewShot] = field(default_factory=list)
    use_cache: bool = True
    replay_delay: float = 0.2  # seconds between replayed events from cache
    on_new_embeddings: Callable[[dict[int, np.ndarray]], None] | None = None

    def __post_init__(self) -> None:
        self.profile_fp = profile_fingerprint(self.profile)
