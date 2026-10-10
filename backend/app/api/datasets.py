import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..agents.context import GlobalSpend, record_spend
from ..chat.parse import ChatParseError, parse_pasted_text, parse_telegram_export
from ..config import get_settings
from ..db import Dataset, Message, User, get_db, user_spend_since
from ..llm import IncompleteOutputError, Usage, get_llm
from ..samples import ensure_sample_dataset, store_parsed
from ..schemas import PasteIn, Profile, XSearchIn
from ..security import current_user, rate_limit
from ..sources.x import XError, make_x_client, plan_queries, post_url, search_posts, to_parsed
from .products import check_paid_call, own_product

log = logging.getLogger("sarenakh.datasets")
router = APIRouter(prefix="/api/datasets", tags=["datasets"])

MAX_UPLOAD_BYTES = 15 * 1024 * 1024


def dataset_out(ds: Dataset, warnings: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": ds.id, "name": ds.name, "source": ds.source, "sample_key": ds.sample_key,
        "stats": ds.stats, "created_at": ds.created_at, "warnings": warnings or [],
    }


def readable_dataset(db: Session, user: User, dataset_id: int) -> Dataset:
    ds = db.get(Dataset, dataset_id)
    if not ds or (ds.user_id != user.id and ds.sample_key is None):
        raise HTTPException(404, "مجموعه پیام پیدا نشد.")
    return ds


def message_out(m: Message) -> dict[str, Any]:
    return {
        "msg_id": m.msg_id, "date": m.date, "author": m.author, "author_id": m.author_id, "text": m.text,
        "reply_to": m.reply_to, "kind": m.kind, "lang": m.lang, "forwarded_from": m.forwarded_from,
        "url": post_url(m.ext_id),
    }


@router.get("/sample")
def get_sample(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return dataset_out(ensure_sample_dataset(db))


@router.get("")
def list_datasets(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(
        select(Dataset).where(or_(Dataset.user_id == user.id, Dataset.sample_key.is_not(None)))
        .order_by(Dataset.created_at.desc())
    )
    return [dataset_out(d) for d in rows]


@router.post("/upload", dependencies=[Depends(rate_limit("upload", 30, 3600, per="user"))])
async def upload(
    file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "حجم فایل بیشتر از ۱۵ مگابایت است. بازه زمانی کوتاه‌تری از گروه خروجی بگیرید.")
    try:
        parsed = parse_telegram_export(raw)
    except ChatParseError as e:
        raise HTTPException(400, str(e)) from e
    ds = store_parsed(db, parsed, user_id=user.id, name=parsed.name or (file.filename or "upload"))
    return dataset_out(ds, parsed.warnings)


@router.post("/paste", dependencies=[Depends(rate_limit("upload", 30, 3600, per="user"))])
def paste(body: PasteIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    try:
        parsed = parse_pasted_text(body.text)
    except ChatParseError as e:
        raise HTTPException(400, str(e)) from e
    ds = store_parsed(db, parsed, user_id=user.id, name=body.name.strip() or "متن واردشده")
    return dataset_out(ds, parsed.warnings)


@router.post("/twitter", dependencies=[Depends(rate_limit("twitter", 20, 3600, per="user"))])
async def twitter(
    body: XSearchIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    """Search recent Persian posts on X for people who may need this product; store them as a dataset."""
    s = get_settings()
    if not s.x_source():
        raise HTTPException(400, "جستجوی ایکس فعال نیست: کلید twitterapi.io یا توکن X تنظیم نشده است.")
    p = own_product(db, user, body.product_id)
    if not p.profile:
        raise HTTPException(400, "اول پروفایل مشتری را بسازید.")
    check_paid_call(request, db, user)
    max_posts = min(body.max_posts, s.x_max_posts)
    worst = max_posts * s.x_price_per_post()
    if GlobalSpend.get() + worst > s.global_spend_cap_usd:
        raise HTTPException(403, "سقف هزینه کل سامانه برای این جستجو کافی نیست.")
    if user_spend_since(db, user.id, time.time() - 86400) + worst > s.user_daily_cap_usd:
        raise HTTPException(429, "سقف هزینه روزانه شما برای این جستجو کافی نیست. تعداد پست را کمتر کنید.")
    profile = Profile(**p.profile)
    try:
        queries, usage = await plan_queries(get_llm(), s, profile)
    except IncompleteOutputError as e:
        record_spend(user.id, "x_queries", e.usage)
        raise HTTPException(502, "ساخت عبارت‌های جستجو کامل نشد. دوباره تلاش کنید.") from e
    except Exception as e:  # noqa: BLE001
        log.warning("x query planner failed: %s", e)
        raise HTTPException(502, "ساخت عبارت‌های جستجو انجام نشد. چند لحظه بعد دوباره تلاش کنید.") from e
    if usage:
        record_spend(user.id, "x_queries", usage)
    if not queries:
        raise HTTPException(502, "عبارت جستجویی ساخته نشد. پروفایل را کامل‌تر کنید.")

    xc = make_x_client(s)
    try:
        async with xc:
            found = await search_posts(xc, queries, max_posts=max_posts, cache_s=s.x_cache_hours * 3600)
    except XError as e:
        raise HTTPException(502, str(e)) from e
    finally:
        if xc.cost_usd:  # billed even if a later page failed
            record_spend(user.id, "x_read", Usage(model="x-api", cost_usd=xc.cost_usd))
    if not found.posts:
        raise HTTPException(404, "در هفت روز گذشته پستی با این عبارت‌ها پیدا نشد.")

    parsed = to_parsed(found, name=f"ایکس: {profile.product_name}"[:200])
    ds = store_parsed(db, parsed, user_id=user.id, name=parsed.name)
    x_stats = {
        "product_id": p.id, "queries": found.queries, "posts": len(found.posts),
        "new_posts": xc.billed_posts, "cost_usd": round(xc.cost_usd, 6), "provider": xc.name,
    }
    ds.stats = {**parsed.stats, "x": x_stats}
    db.flush()
    return dataset_out(ds, parsed.warnings)


@router.get("/{dataset_id}")
def get_dataset(dataset_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return dataset_out(readable_dataset(db, user, dataset_id))


@router.get("/{dataset_id}/messages")
def list_messages(
    dataset_id: int,
    around: int | None = None,
    radius: int = 25,
    offset: int = 0,
    limit: int = 200,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    readable_dataset(db, user, dataset_id)
    limit = max(1, min(limit, 1000))
    base = select(Message).where(Message.dataset_id == dataset_id)
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    if around is not None:
        before = db.scalars(base.where(Message.msg_id <= around).order_by(Message.msg_id.desc()).limit(radius + 1))
        after = db.scalars(base.where(Message.msg_id > around).order_by(Message.msg_id).limit(radius))
        rows = sorted([*before, *after], key=lambda m: m.msg_id)
    else:
        rows = list(db.scalars(base.order_by(Message.msg_id).offset(offset).limit(limit)))
    return {"total": total, "messages": [message_out(m) for m in rows]}
