from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import Product, User, get_db
from ..samples import sample_products, sample_profile
from ..schemas import Profile, ProductIn
from ..security import current_user

router = APIRouter(prefix="/api/products", tags=["products"])


def product_out(p: Product) -> dict[str, Any]:
    return {
        "id": p.id, "name": p.name, "description": p.description, "sample_key": p.sample_key,
        "profile": p.profile, "setup_chat": p.setup_chat or [], "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


def own_product(db: Session, user: User, product_id: int) -> Product:
    p = db.get(Product, product_id)
    if not p or p.user_id != user.id:
        raise HTTPException(404, "محصول پیدا نشد.")
    return p


@router.get("/samples")
def list_samples() -> list[dict[str, Any]]:
    return [
        {"key": k, "name": v["name"], "emoji": v["emoji"], "pitch": v["pitch"], "description": v["description"]}
        for k, v in sample_products().items()
    ]


@router.get("")
def list_products(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(Product).where(Product.user_id == user.id).order_by(Product.updated_at.desc()))
    return [product_out(p) for p in rows]


@router.post("")
def create_product(body: ProductIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    desc = body.description.strip()
    p = Product(user_id=user.id, name=body.name.strip() or desc[:40], description=desc, setup_chat=[])
    db.add(p)
    db.flush()
    return product_out(p)


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


@router.delete("/{product_id}")
def delete_product(product_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    db.delete(own_product(db, user, product_id))
    return {"ok": True}
