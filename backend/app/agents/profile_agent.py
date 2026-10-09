"""Profile agent: a short conversation (<= 2 clarifying questions) that ends in a Profile."""

from __future__ import annotations

from ..config import Settings
from ..llm import LLM, Usage
from .prompts import PROFILE_SYSTEM
from .schemas import ProfileTurn

MAX_QUESTIONS = 2


async def profile_turn(llm: LLM, settings: Settings, chat: list[dict]) -> tuple[ProfileTurn, Usage]:
    """`chat` alternates user/assistant turns; the first user turn is the product description."""
    asked = sum(1 for t in chat if t["role"] == "assistant")
    items = [{"role": t["role"], "content": t["content"]} for t in chat]
    items.append({
        "role": "developer",
        "content": (
            f"Clarifying questions asked so far: {asked}/{MAX_QUESTIONS}. "
            + ("You must now produce the profile (action=profile)." if asked >= MAX_QUESTIONS
               else "Ask your first clarifying question (action=ask)." if asked == 0 else "")
        ),
    })
    turn, usage = await llm.structured(
        model=settings.profile_model,
        instructions=PROFILE_SYSTEM,
        input=items,
        output_type=ProfileTurn,
        reasoning=settings.agent_reasoning,
        max_output_tokens=6000,
        cache_key="sarenakh-profile",
    )
    if turn.action == "ask" and (asked >= MAX_QUESTIONS or not turn.question.strip()):
        raise RuntimeError("profile agent asked a question after the question limit")
    if turn.action == "profile" and turn.profile is None:
        raise RuntimeError("profile agent returned no profile")
    return turn, usage
