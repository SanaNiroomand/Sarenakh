import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agents.context import GlobalSpend, record_spend
from ..agents.product_reader import facts_to_description, read_product
from ..agents.profile_agent import profile_turn
from ..config import get_settings
from ..db import Product, User, get_db, user_spend_since
from ..llm import IncompleteOutputError, get_llm
from ..samples import sample_products, sample_profile
from ..schemas import ChatTurnIn, ProductIn, ProductUrlIn, Profile
from ..security import current_user, rate_limit
from ..sources.web import PageError, fetch_page

log = logging.getLogger("sarenakh.products")
router = APIRouter(prefix="/api/products", tags=["products"])


def product_out(p: Product) -> dict[str, Any]:
    sp = sample_products().get(p.sample_key or "")
    return {
        "id": p.id, "name": p.name, "description": p.description, "sample_key": p.sample_key,
        "profile": p.profile, "setup_chat": p.setup_chat or [], "created_at": p.created_at,
        "updated_at": p.updated_at,
        "source": ({"url": sp["source_url"], "checked_at": sp["checked_at"]} if sp
                   else {"url": p.source_url, "checked_at": None} if p.source_url else None),
    }


def own_product(db: Session, user: User, product_id: int) -> Product:
    p = db.get(Product, product_id)
    if not p or p.user_id != user.id:
        raise HTTPException(404, "محصول پیدا نشد.")
    return p


@router.get("/samples")
def list_samples() -> list[dict[str, Any]]:
    return [
        {"key": k, "name": v["name"], "emoji": v["emoji"], "pitch": v["pitch"], "description": v["description"],
         "source_url": v["source_url"], "checked_at": v["checked_at"]}
        for k, v in sample_products().items()
    ]


@router.get("")
def list_products(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(Product).where(Product.user_id == user.id).order_by(Product.updated_at.desc()))
    return [product_out(p) for p in rows]


@router.post("")
def create_product(body: ProductIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    desc = body.description.strip()
    p = Product(user_id=user.id, name=body.name.strip() or desc[:40], description=desc,
                setup_chat=[{"role": "user", "content": desc}])
    db.add(p)
    db.flush()
    return product_out(p)


def check_paid_call(request: Request, db: Session, user: User) -> None:
    """Guards before a paid model call made outside a run."""
    s = get_settings()
    ms = request.app.state.model_status
    if not (ms.get("ok") or ms.get("skipped")):
        raise HTTPException(503, "سرویس هوش مصنوعی موقتا در دسترس نیست. کمی بعد دوباره تلاش کنید.")
    if GlobalSpend.get() >= s.global_spend_cap_usd:
        raise HTTPException(403, "سقف هزینه این نسخه نمایشی پر شده است. از محصولات نمونه استفاده کنید.")
    if user_spend_since(db, user.id, time.time() - 86400) >= s.user_daily_cap_usd:
        raise HTTPException(429, "سقف هزینه روزانه شما پر شده است. فردا دوباره امتحان کنید.")


@router.post("/from-url", dependencies=[Depends(rate_limit("from_url", 20, 3600, per="user"))])
async def create_from_url(
    body: ProductUrlIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    """Read the product page, extract its facts, and start the profile chat with them."""
    check_paid_call(request, db, user)
    try:
        page = await fetch_page(body.url)
    except PageError as e:
        raise HTTPException(400, str(e)) from e
    if len(page.text) < 200 and not page.structured:
        raise HTTPException(422, "این صفحه متن کافی نداشت (احتمالا با جاوااسکریپت ساخته می‌شود). محصول را چند خطی توضیح دهید.")
    try:
        facts, usage = await read_product(get_llm(), get_settings(), page)
    except IncompleteOutputError as e:
        record_spend(user.id, "page", e.usage)
        raise HTTPException(502, "خواندن صفحه کامل نشد. دوباره تلاش کنید.") from e
    except Exception as e:  # noqa: BLE001
        log.warning("product page reader failed: %s", e)
        raise HTTPException(502, "خواندن صفحه انجام نشد. چند لحظه بعد دوباره تلاش کنید.") from e
    if usage:
        record_spend(user.id, "page", usage)
    if not facts.found or not facts.features:
        raise HTTPException(422, "در این صفحه محصول مشخصی پیدا نشد. لینک صفحه خود محصول را بدهید یا توضیحش دهید.")
    desc = facts_to_description(facts, page.url)
    p = Product(user_id=user.id, name=facts.product_name[:120], description=desc, source_url=page.url[:1000],
                setup_chat=[{"role": "user", "content": desc}])
    db.add(p)
    db.flush()
    out = product_out(p)
    out["facts"] = facts.model_dump()
    out["read_cost_usd"] = round(usage.cost_usd, 6) if usage else 0.0
    return out


@router.post("/sample/{key}")
def create_from_sample(key: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    sp = sample_products().get(key)
    if not sp:
        raise HTTPException(404, "نمونه پیدا نشد.")
    existing = db.scalar(select(Product).where(Product.user_id == user.id, Product.sample_key == key))
    if existing:
        return product_out(existing)
    p = Product(
        user_id=user.id, name=sp["name"], description=sp["description"], sample_key=key,
        profile=sample_profile(key), setup_chat=[],
    )
    db.add(p)
    db.flush()
    return product_out(p)


@router.get("/{product_id}")
def get_product(product_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return product_out(own_product(db, user, product_id))


@router.put("/{product_id}/profile")
def save_profile(
    product_id: int, body: Profile, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    p = own_product(db, user, product_id)
    p.profile = body.model_dump()
    p.name = body.product_name or p.name
    db.flush()
    return product_out(p)


@router.post("/{product_id}/agent", dependencies=[Depends(rate_limit("profile", 30, 3600, per="user"))])
async def agent_turn(
    product_id: int, request: Request, body: ChatTurnIn | None = None,
    user: User = Depends(current_user), db: Session = Depends(get_db),
) -> dict:
    """One turn of the profile agent. Send {message} to answer its question; send nothing to start."""
    s = get_settings()
    p = own_product(db, user, product_id)
    chat = list(p.setup_chat or [])
    if not chat:
        chat = [{"role": "user", "content": p.description}]
    if body and body.message.strip():
        chat.append({"role": "user", "content": body.message.strip()})
    if chat[-1]["role"] != "user":
        raise HTTPException(400, "منتظر پاسخ شما به سوال عامل هستیم.")
    check_paid_call(request, db, user)
    try:
        turn, usage = await profile_turn(get_llm(), s, chat)
    except IncompleteOutputError as e:
        record_spend(user.id, "profile", e.usage)
        raise HTTPException(502, "عامل پروفایل پاسخ کاملی نداد. دوباره تلاش کنید.") from e
    except Exception as e:  # noqa: BLE001
        log.warning("profile agent failed: %s", e)
        raise HTTPException(502, "عامل پروفایل پاسخ نداد. چند لحظه بعد دوباره تلاش کنید.") from e
    record_spend(user.id, "profile", usage)
    if turn.action == "ask":
        chat.append({"role": "assistant", "content": turn.question})
    else:
        chat.append({"role": "assistant", "content": "✅ پروفایل مشتری ایده‌آل آماده شد. می‌توانید ویرایشش کنید."})
        p.profile = turn.profile.model_dump()
        p.name = turn.profile.product_name or p.name
    p.setup_chat = chat  # reassign so SQLAlchemy sees the JSON change
    db.flush()
    out = product_out(p)
    out["turn_cost_usd"] = round(usage.cost_usd, 6)
    return out


@router.delete("/{product_id}")
def delete_product(product_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    db.delete(own_product(db, user, product_id))
    return {"ok": True}
