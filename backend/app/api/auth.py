from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import User, get_db
from ..schemas import LoginIn, SignupIn, UserOut
from ..security import current_user, end_session, hash_password, rate_limit, start_session, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _out(u: User) -> UserOut:
    return UserOut(id=u.id, email=u.email, name=u.name)


@router.post("/signup", dependencies=[Depends(rate_limit("signup", 20, 3600))])
def signup(body: SignupIn, response: Response, db: Session = Depends(get_db)) -> UserOut:
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(409, "با این ایمیل قبلا ثبت‌نام شده است. وارد شوید.")
    user = User(
        email=body.email,
        name=body.name.strip() or body.email.split("@")[0],
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.flush()
    start_session(db, response, user)
    return _out(user)


@router.post("/login", dependencies=[Depends(rate_limit("login", 20, 300))])
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)) -> UserOut:
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "ایمیل یا رمز عبور اشتباه است.")
    start_session(db, response, user)
    return _out(user)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    end_session(db, request, response)
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)) -> UserOut:
    return _out(user)
