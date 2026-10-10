"""All tunables in one place: models, prices, budgets, paths.

Model IDs and prices are swappable via .env (see .env.example) without code changes.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Price(BaseModel):
    """USD per 1M tokens. Reasoning tokens are billed as output."""

    input: float
    cached_input: float
    output: float = 0.0
    # Prompts above this many input tokens are billed at the long_* rates.
    long_context_threshold: int | None = None
    long_input: float | None = None
    long_cached_input: float | None = None
    long_output: float | None = None


# Standard tier, from developers.openai.com/api/docs/pricing (checked 2026-10-09).
PRICES: dict[str, Price] = {
    "gpt-6-luna": Price(
        input=0.10, cached_input=0.01, output=0.50,
        long_context_threshold=272_000, long_input=0.20, long_cached_input=0.02, long_output=0.75,
    ),
    "gpt-6.1-sol": Price(
        input=2.00, cached_input=0.10, output=10.00,
        long_context_threshold=272_000, long_input=4.00, long_cached_input=0.20, long_output=15.00,
    ),
    "gpt-6-sol": Price(
        input=2.00, cached_input=0.20, output=10.00,
        long_context_threshold=272_000, long_input=4.00, long_cached_input=0.40, long_output=15.00,
    ),
    "text-embedding-3-small": Price(input=0.02, cached_input=0.02),
    "text-embedding-3-large": Price(input=0.13, cached_input=0.13),
}

Role = Literal["triage", "profile", "investigator", "critic", "drafter"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    # OpenAI
    openai_api_key: str = Field(default="", repr=False)  # secrets stay out of logs and tracebacks
    openai_base_url: str = "https://api.openai.com/v1"
    openai_timeout_s: float = 90.0

    triage_model: str = "gpt-6-luna"
    profile_model: str = "gpt-6.1-sol"
    investigator_model: str = "gpt-6.1-sol"
    critic_model: str = "gpt-6.1-sol"
    drafter_model: str = "gpt-6.1-sol"
    embedding_model: str = "text-embedding-3-small"

    triage_reasoning: str = "none"
    agent_reasoning: str = "low"

    prices_json: str = ""
    model_check: Literal["strict", "warn", "off"] = "strict"

    # Spending safety
    global_spend_cap_usd: float = 20.0
    default_run_budget_usd: float = 0.25
    max_run_budget_usd: float = 1.00
    user_daily_cap_usd: float = 1.50  # paid spend per user per 24h (profile chat + runs)
    replay_delay_s: float = 0.7  # pacing of replayed (cached) agent steps in the live feed

    # X (Twitter). twitterapi.io is used when its key is set (unofficial, ~33x cheaper, pays by crypto);
    # otherwise the official API v2 (pay-per-use, needs prepaid credits).
    twitterapi_key: str = Field(default="", repr=False)
    twitterapi_base: str = "https://api.twitterapi.io"
    twitterapi_price_per_tweet_usd: float = 0.00015
    x_bearer_token: str = Field(default="", repr=False)
    x_api_base: str = "https://api.x.com/2"
    x_price_per_post_usd: float = 0.005
    x_price_per_user_usd: float = 0.010
    x_max_posts: int = 300  # per search
    x_cache_hours: int = 24  # reuse search results and posts this long
    x_window_days: int = 7  # how far back posts count as current (the official API stops at 7)

    # Web
    session_secret: str = Field(default="dev-insecure-secret", repr=False)
    cookie_secure: bool = False

    # Paths
    data_dir: Path = ROOT / "data"
    static_dir: Path = ROOT / "frontend" / "dist"
    samples_dir: Path = ROOT / "samples"

    def model_for(self, role: Role) -> str:
        return getattr(self, f"{role}_model")

    def reasoning_for(self, role: Role) -> str:
        return self.triage_reasoning if role == "triage" else self.agent_reasoning

    def chat_models(self) -> dict[str, str]:
        """Distinct chat model IDs -> reasoning effort used for them."""
        out: dict[str, str] = {}
        for role in ("triage", "profile", "investigator", "critic", "drafter"):
            out.setdefault(self.model_for(role), self.reasoning_for(role))
        return out

    def x_source(self) -> Literal["twitterapi", "official"] | None:
        if self.twitterapi_key:
            return "twitterapi"
        return "official" if self.x_bearer_token else None

    def x_price_per_post(self) -> float:
        return self.twitterapi_price_per_tweet_usd if self.x_source() == "twitterapi" else self.x_price_per_post_usd

    def prices(self) -> dict[str, Price]:
        table = dict(PRICES)
        if self.prices_json.strip():
            for model, row in json.loads(self.prices_json).items():
                table[model] = Price(**row)
        return table

    @property
    def db_path(self) -> Path:
        return self.data_dir / "sarenakh.sqlite3"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return s
