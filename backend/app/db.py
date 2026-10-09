"""SQLite via SQLAlchemy 2.0. One file on a mounted volume; WAL mode for concurrent readers."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    func,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import get_settings


def now() -> float:
    return time.time()


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON}


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80), default="")
    password_hash: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[float] = mapped_column(Float, default=now)


class AuthSession(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[float] = mapped_column(Float, default=now)
    expires_at: Mapped[float] = mapped_column(Float)


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    sample_key: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # conversation with the profile agent: [{"role": "user"|"assistant", "content": str}]
    setup_chat: Mapped[list[Any]] = mapped_column(JSON, default=list)
    profile: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=now)
    updated_at: Mapped[float] = mapped_column(Float, default=now, onupdate=now)


class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(20))  # telegram_json | pasted_text | sample
    sample_key: Mapped[str | None] = mapped_column(String(40), nullable=True, unique=True)
    stats: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[float] = mapped_column(Float, default=now)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("dataset_id", "msg_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    msg_id: Mapped[int] = mapped_column(Integer)
    ts: Mapped[int] = mapped_column(Integer)
    date: Mapped[str] = mapped_column(String(20))
    author_id: Mapped[str] = mapped_column(String(80))
    author: Mapped[str] = mapped_column(String(120))
    text: Mapped[str] = mapped_column(Text)
    norm: Mapped[str] = mapped_column(Text)
    reply_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String(12), default="text")
    lang: Mapped[str] = mapped_column(String(10), default="fa")
    forwarded_from: Mapped[str | None] = mapped_column(String(200), nullable=True)
    emojis: Mapped[int] = mapped_column(Integer, default=0)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)  # float32, cached


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(12), default="queued")  # queued|running|done|failed|stopped
    budget_usd: Mapped[float] = mapped_column(Float)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    saved_usd: Mapped[float] = mapped_column(Float, default=0.0)  # cost avoided by cache hits
    profile: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # snapshot at run time
    stats: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # funnel counts, stage costs
    stop_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=now)
    started_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    finished_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class Analysis(Base):
    """One row per (run, message) that entered the pipeline; accumulates stage results."""

    __tablename__ = "analyses"
    __table_args__ = (UniqueConstraint("run_id", "msg_id"), Index("ix_analyses_run_decision", "run_id", "decision"))
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    msg_id: Mapped[int] = mapped_column(Integer)
    author_id: Mapped[str] = mapped_column(String(80))
    stage: Mapped[str] = mapped_column(String(16))  # furthest stage: prefilter|triage|investigate|critic|draft
    prefilter_sim: Mapped[float | None] = mapped_column(Float, nullable=True)
    triage: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    verdict: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    critic: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    reply: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    trace: Mapped[list[Any]] = mapped_column(JSON, default=list)  # investigator tool calls
    fit: Mapped[float | None] = mapped_column(Float, nullable=True)
    decision: Mapped[str] = mapped_column(String(12), default="pending")  # lead|rejected|pending|skipped
    why_not: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    saved_usd: Mapped[float] = mapped_column(Float, default=0.0)  # cost avoided by cache hits
    cached: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[float] = mapped_column(Float, default=now)


class AgentEvent(Base):
    __tablename__ = "agent_events"
    __table_args__ = (Index("ix_events_run_seq", "run_id", "seq"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer)
    ts: Mapped[float] = mapped_column(Float, default=now)
    type: Mapped[str] = mapped_column(String(20))
    msg_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text)  # readable Persian line for the live feed
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (UniqueConstraint("user_id", "run_id", "msg_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    msg_id: Mapped[int] = mapped_column(Integer)
    vote: Mapped[int] = mapped_column(Integer)  # +1 / -1
    note: Mapped[str] = mapped_column(Text, default="")
    message_text: Mapped[str] = mapped_column(Text)
    agent_decision: Mapped[str] = mapped_column(String(12))
    agent_reason: Mapped[str] = mapped_column(Text, default="")
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=now)


class StageCache(Base):
    """Results keyed by (product fingerprint, message text, stage, model, prompt version)."""

    __tablename__ = "stage_cache"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    stage: Mapped[str] = mapped_column(String(16))
    result: Mapped[dict[str, Any]] = mapped_column(JSON)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[float] = mapped_column(Float, default=now)


class SpendLog(Base):
    """Every paid API call. SUM(cost_usd) is the global spend checked against the hard cap."""

    __tablename__ = "spend_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[float] = mapped_column(Float, default=now, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(60))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float)


# --- engine & sessions ------------------------------------------------------------------------

_engine = None
_Session: sessionmaker[Session] | None = None


def engine():
    global _engine, _Session
    if _engine is None:
        s = get_settings()
        _engine = create_engine(
            f"sqlite:///{s.db_path}",
            connect_args={"check_same_thread": False, "timeout": 30},
        )

        @event.listens_for(_engine, "connect")
        def _pragmas(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()

        _Session = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def init_db() -> None:
    eng = engine()
    Base.metadata.create_all(eng)
    with eng.begin() as conn:  # tiny forward-only migration: add columns that are new in the models
        for table in Base.metadata.sorted_tables:
            existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table.name})")}
            for col in table.columns:
                if col.name in existing:
                    continue
                default = col.default.arg if col.default is not None and col.default.is_scalar else None
                ddl = f"ALTER TABLE {table.name} ADD COLUMN {col.name} {col.type.compile(dialect=conn.dialect)}"
                if isinstance(default, (int, float)) and not isinstance(default, bool):
                    ddl += f" DEFAULT {default}"
                elif isinstance(default, bool):
                    ddl += f" DEFAULT {int(default)}"
                conn.exec_driver_sql(ddl)


@contextmanager
def session() -> Iterator[Session]:
    engine()
    assert _Session is not None
    db = _Session()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    with session() as db:
        yield db


def total_spend(db: Session) -> float:
    return float(db.scalar(select(func.coalesce(func.sum(SpendLog.cost_usd), 0.0))) or 0.0)


def user_spend_since(db: Session, user_id: int, since_ts: float) -> float:
    q = select(func.coalesce(func.sum(SpendLog.cost_usd), 0.0)).where(
        SpendLog.user_id == user_id, SpendLog.ts >= since_ts
    )
    return float(db.scalar(q) or 0.0)
