"""Shared Pydantic models: the customer profile and API payloads."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

AXES = ("need", "product_fit", "urgency", "buying_intent", "reachability", "confidence")
AXES_FA = {
    "need": "نیاز",
    "product_fit": "تناسب محصول",
    "urgency": "فوریت",
    "buying_intent": "قصد خرید",
    "reachability": "دسترس‌پذیری",
    "confidence": "اطمینان",
}


def _clamp(v: int) -> int:
    return max(0, min(10, int(v)))


class Axes(BaseModel):
    """Six 0-10 scores. Used for verdicts and for the profile's ideal-customer shape."""

    need: int
    product_fit: int
    urgency: int
    buying_intent: int
    reachability: int
    confidence: int

    @field_validator(*AXES)
    @classmethod
    def _range(cls, v: int) -> int:
        return _clamp(v)


class Profile(BaseModel):
    """Structured customer profile produced by the profile agent, editable by the user."""

    product_name: str = Field(description="اسم کوتاه محصول")
    one_liner: str = Field(description="یک جمله: محصول چه مشکلی را برای چه کسی حل می‌کند")
    persona: str = Field(description="مشتری ایده‌آل چه کسی است (۲-۳ جمله)")
    pain_points: list[str] = Field(description="دردها و مشکلاتی که محصول حل می‌کند (۴ تا ۸ مورد)")
    buying_signals: list[str] = Field(description="نشانه‌هایی در پیام که نشان می‌دهد فرد مشتری بالقوه است (۵ تا ۱۰ مورد)")
    signal_examples: list[str] = Field(
        description="۱۰ تا ۱۵ پیام نمونه که یک مشتری واقعی ممکن است در گروه بنویسد؛ ترکیبی از فارسی محاوره، "
        "فینگلیش (فارسی با حروف لاتین) و فارسی با اصطلاحات انگلیسی"
    )
    disqualifiers: list[str] = Field(
        description="نشانه‌هایی که فرد را رد می‌کند، مثلا حرفه‌ای است، قبلا خریده، فقط رایگان می‌خواهد، فروشنده رقیب است"
    )
    reply_tone: str = Field(description="لحن پاسخ پیشنهادی به این مشتری‌ها")
    ideal_shape: Axes = Field(description="شکل مشتری ایده‌آل روی شش محور ۰ تا ۱۰")
    facts: list[str] = Field(description="حقایق قطعی محصول (قیمت، ویژگی، شرایط) که در پاسخ‌ها مجاز به گفتن آن‌ها هستیم")


# --- auth ---------------------------------------------------------------------------------------

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


class SignupIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)
    name: str = Field(default="", max_length=80)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL.match(v):
            raise ValueError("ایمیل معتبر نیست.")
        return v

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("رمز عبور باید حداقل ۸ کاراکتر باشد.")
        return v


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


class UserOut(BaseModel):
    id: int
    email: str
    name: str


# --- products & datasets --------------------------------------------------------------------------


class ProductIn(BaseModel):
    description: str = Field(min_length=20, max_length=4000)
    name: str = Field(default="", max_length=120)


class ChatTurnIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class PasteIn(BaseModel):
    text: str = Field(min_length=10, max_length=400_000)
    name: str = Field(default="", max_length=200)
