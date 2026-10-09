"""Scores -> decision. Deterministic Python, not prompts: overall fit, temperature, weak spot,
and the hard rules (disqualifier or resolved thread => skip; never pitch the same person twice)."""

from __future__ import annotations

from ..schemas import AXES_FA
from .schemas import Verdict

WEIGHTS = {"need": 0.25, "product_fit": 0.25, "buying_intent": 0.20, "urgency": 0.10,
           "reachability": 0.10, "confidence": 0.10}
LEAD_FIT = 6.0  # overall fit needed to be a lead
CRITIC_BAND = (5.0, 7.0)  # borderline leads get a devil's-advocate pass
MENTION_FIT = 7.0  # below this, replies are pure help (no product mention)


def fit_score(scores: dict[str, int]) -> float:
    return round(sum(scores[k] * w for k, w in WEIGHTS.items()), 1)


def temperature(v: Verdict) -> str:
    s = v.scores
    if v.timing == "ready" or s.buying_intent >= 8:
        return "hot"
    if v.timing == "considering" or s.buying_intent >= 5:
        return "warm"
    return "cold"


def weakest_axis(scores: dict[str, int]) -> dict:
    k = min(AXES_FA, key=lambda a: (scores[a], a))
    return {"axis": k, "label": AXES_FA[k], "score": scores[k]}


def decide(v: Verdict, fit: float) -> tuple[str, str | None]:
    """(decision, why_not). decision: lead | watch | rejected."""
    if v.disqualifiers_found:
        return "rejected", v.why_not or v.disqualifiers_found[0]
    if v.thread_resolved:
        return "rejected", v.why_not or "نیازش قبلا برطرف شده است"
    if v.action == "skip":
        return "rejected", v.why_not or "نیاز شخصی مرتبط با محصول دیده نشد"
    if fit < LEAD_FIT:
        if v.action == "watch" or fit >= LEAD_FIT - 1.5:
            return "watch", v.why_not or f"فعلا آماده نیست (تناسب {fit}/۱۰)"
        return "rejected", v.why_not or f"تناسب پایین ({fit}/۱۰)"
    if v.action == "watch":
        return "watch", v.why_not or "علاقه دارد ولی هنوز آماده نیست"
    return "lead", None


def needs_critic(fit: float) -> bool:
    return CRITIC_BAND[0] <= fit < CRITIC_BAND[1]
