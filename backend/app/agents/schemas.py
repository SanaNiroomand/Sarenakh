"""Structured outputs of every agent. Field order matters: evidence and reasoning come before
scores, so the model's scores are conditioned on what it has already written."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ..schemas import AXES, Profile


class TriageItem(BaseModel):
    msg_id: int
    signal: Literal["question", "complaint", "purchase_intent", "noise"]
    reason: str = Field(description="One short Persian line (<= 15 words) explaining the score")
    relevance: int = Field(description="0-10, see anchors")

    @field_validator("relevance")
    @classmethod
    def _r(cls, v: int) -> int:
        return max(0, min(10, int(v)))


class TriageBatch(BaseModel):
    items: list[TriageItem]


class VerdictScores(BaseModel):
    need: int = Field(description="0 none · 2 mentions the topic · 5 has a related problem · 8 asks for a solution/recommendation · 10 urgent, explicit, ready to pay")
    product_fit: int = Field(description="0 product can't help · 3 tangential · 5 partly helps · 8 product matches the stated need · 10 exactly what they asked for")
    urgency: int = Field(description="0 none · 3 someday · 5 within weeks · 8 deadline this week/month · 10 right now")
    buying_intent: int = Field(description="0 refuses to pay / only free · 2 curious · 5 comparing options · 8 has budget or asks where to buy · 10 ready to pay now")
    reachability: int = Field(description="0 bot/ad/deleted account · 3 one-off lurker · 5 normal member · 8 active and open (asks for PV, replies to people) · 10 explicitly invites DMs")
    confidence: int = Field(description="0 guess · 5 some evidence · 8 clear evidence in thread/history · 10 unambiguous, several evidence messages")

    @field_validator(*AXES)
    @classmethod
    def _range(cls, v: int) -> int:
        return max(0, min(10, int(v)))


class Verdict(BaseModel):
    evidence_msg_ids: list[int] = Field(description="IDs of the messages that prove (or disprove) the need: the candidate plus supporting ones")
    stated_need: str = Field(description="What this person needs, in Persian, <= 25 words. Empty if no personal need")
    disqualifiers_found: list[str] = Field(description="Disqualifiers that apply, each a short Persian phrase citing the evidence (e.g. 'در #1120 گفته ثبت‌نام کرده'). Empty list if none")
    thread_resolved: bool = Field(description="True if the need is already satisfied: bought/enrolled/solved/changed mind")
    reasoning: str = Field(description="2-3 short Persian sentences connecting the evidence to the scores")
    scores: VerdictScores
    timing: Literal["browsing", "considering", "ready"]
    action: Literal["reply", "dm", "watch", "skip"]
    why_not: str = Field(description="If not worth contacting: one short Persian line why. Otherwise empty string")


class CriticResult(BaseModel):
    strongest_objection: str = Field(description="The best argument, in Persian, that this is NOT a real potential customer")
    evidence_against_msg_ids: list[int]
    survives: bool = Field(description="True if the lead still holds after your best objection")
    reason: str = Field(description="One short Persian line: why it survives or falls")


class ReplyDraft(BaseModel):
    help_points: list[str] = Field(description="Plan: the concrete help the reply gives (Persian, 1-3 items)")
    facts_used: list[int] = Field(description="Indexes of PRODUCT FACTS used in the reply; [] in pure_help mode")
    reply: str = Field(description="The message to post, Persian (or Finglish if the person wrote Finglish)")


class DraftCheck(BaseModel):
    answers_the_person: bool = Field(description="Does the reply genuinely help with what they asked/complained about?")
    invented_claims: list[str] = Field(description="Product claims not supported by PRODUCT FACTS (prices, features, discounts, guarantees)")
    breaks_mode: bool = Field(description="pure_help mode but mentions the product/brand, or mention mode but pushy/salesy")
    issues: list[str] = Field(description="Concrete fixes needed, Persian. Empty if the reply is good")
    ok: bool


class ProfileTurn(BaseModel):
    action: Literal["ask", "profile"]
    question: str = Field(description="If action=ask: one short, friendly Persian question. Otherwise empty")
    profile: Profile | None = Field(description="If action=profile: the full profile. Otherwise null")


class ProductFacts(BaseModel):
    """What the product page says, extracted by the page reader."""

    found: bool = Field(description="true if the page is about one specific product or service")
    product_name: str = Field(description="Short product name as on the page")
    seller: str = Field(description="Brand, shop or site selling it")
    summary: str = Field(description="1-2 Persian sentences: what it is, what problem it solves for whom")
    audience: str = Field(description="Who the page says it is for, or empty")
    price: str = Field(description="Price as written on the page with currency, or empty")
    features: list[str] = Field(description="4-12 short standalone Persian facts from the page, most concrete first")


class XQuery(BaseModel):
    why: str = Field(description="One short Persian line: whom this query finds")
    topic: list[str] = Field(description="2-5 terms naming the subject the way people do")
    need: list[str] = Field(description="3-8 terms showing a personal need")


class XQueryPlan(BaseModel):
    queries: list[XQuery]
