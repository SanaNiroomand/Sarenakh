"""Thin async wrapper over the OpenAI Responses + Embeddings APIs.

Every call returns a Usage with its USD cost computed from `response.usage` x the
price table in config.py, so callers can charge it to a run budget.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypeVar

from functools import lru_cache

import numpy as np
import openai
from openai import AsyncOpenAI
from openai.lib._pydantic import to_strict_json_schema
from pydantic import BaseModel, ValidationError

from .config import Price, Settings, get_settings

T = TypeVar("T", bound=BaseModel)


@lru_cache
def _strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    return to_strict_json_schema(model)


class MissingPriceError(RuntimeError):
    pass


class IncompleteOutputError(RuntimeError):
    """The model returned no parsable structured output (e.g. hit max_output_tokens).
    Carries the usage so callers can still charge what was spent."""

    def __init__(self, message: str, usage: "Usage"):
        super().__init__(message)
        self.usage = usage


@dataclass
class Usage:
    model: str
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd: float = 0.0
    calls: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "input_tokens": self.input_tokens,
            "cached_tokens": self.cached_tokens,
            "output_tokens": self.output_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "cost_usd": round(self.cost_usd, 8),
            "calls": self.calls,
        }


@dataclass
class UsageTotal:
    """Accumulates usage across many calls (possibly different models)."""

    cost_usd: float = 0.0
    calls: int = 0
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    by_model: dict[str, float] = field(default_factory=dict)

    def add(self, u: Usage) -> None:
        self.cost_usd += u.cost_usd
        self.calls += u.calls
        self.input_tokens += u.input_tokens
        self.cached_tokens += u.cached_tokens
        self.output_tokens += u.output_tokens
        self.by_model[u.model] = self.by_model.get(u.model, 0.0) + u.cost_usd


def compute_cost(price: Price, input_tokens: int, cached_tokens: int, output_tokens: int) -> float:
    long = price.long_context_threshold is not None and input_tokens > price.long_context_threshold
    p_in = (price.long_input if long else None) or price.input
    p_cached = (price.long_cached_input if long else None) or price.cached_input
    p_out = (price.long_output if long else None) or price.output
    uncached = max(input_tokens - cached_tokens, 0)
    return (uncached * p_in + cached_tokens * p_cached + output_tokens * p_out) / 1_000_000


def is_fatal(err: Exception) -> bool:
    """Errors that retrying won't fix: bad key, unknown model, region block, bad request."""
    return isinstance(
        err,
        (
            openai.AuthenticationError,
            openai.PermissionDeniedError,
            openai.NotFoundError,
            openai.BadRequestError,
            openai.UnprocessableEntityError,
            MissingPriceError,
        ),
    )


def describe_error(err: Exception) -> str:
    if isinstance(err, openai.AuthenticationError):
        return "Invalid OPENAI_API_KEY (401)."
    if isinstance(err, openai.PermissionDeniedError):
        return f"Permission denied (403) — key lacks access or the server's region is blocked: {err.message}"
    if isinstance(err, openai.NotFoundError):
        return f"Model not found for this key (404): {err.message}"
    if isinstance(err, openai.RateLimitError):
        return f"Rate limited / quota exceeded (429): {err.message}"
    if isinstance(err, openai.APIStatusError):
        return f"OpenAI error {err.status_code}: {err.message}"
    if isinstance(err, openai.APIConnectionError):
        return f"Cannot reach OpenAI at the configured base URL: {err}"
    return f"{type(err).__name__}: {err}"


class LLM:
    def __init__(self, settings: Settings | None = None):
        self.s = settings or get_settings()
        self.client = AsyncOpenAI(
            api_key=self.s.openai_api_key or "missing-key",
            base_url=self.s.openai_base_url,
            timeout=self.s.openai_timeout_s,
            max_retries=2,
        )
        self.prices = self.s.prices()

    def price(self, model: str) -> Price:
        if model not in self.prices:
            raise MissingPriceError(f"No price row for model '{model}'. Add it to PRICES in config.py or PRICES_JSON.")
        return self.prices[model]

    def _usage(self, model: str, usage: Any) -> Usage:
        if usage is None:
            return Usage(model=model, calls=1)
        cached = getattr(getattr(usage, "input_tokens_details", None), "cached_tokens", 0) or 0
        reasoning = getattr(getattr(usage, "output_tokens_details", None), "reasoning_tokens", 0) or 0
        u = Usage(
            model=model,
            input_tokens=usage.input_tokens,
            cached_tokens=cached,
            output_tokens=usage.output_tokens,
            reasoning_tokens=reasoning,
            calls=1,
        )
        u.cost_usd = compute_cost(self.price(model), u.input_tokens, u.cached_tokens, u.output_tokens)
        return u

    def _common(
        self,
        model: str,
        input: Any,
        instructions: str | None,
        reasoning: str | None,
        max_output_tokens: int,
        cache_key: str | None,
    ) -> dict[str, Any]:
        self.price(model)  # fail before spending if we can't account for it
        kwargs: dict[str, Any] = {
            "model": model,
            "input": input,
            "max_output_tokens": max_output_tokens,
            "store": False,
        }
        if instructions:
            kwargs["instructions"] = instructions
        if reasoning:
            kwargs["reasoning"] = {"effort": reasoning}
            if reasoning != "none":
                # Needed to pass reasoning items back in a stateless (store=False) tool loop.
                kwargs["include"] = ["reasoning.encrypted_content"]
        if cache_key:
            kwargs["prompt_cache_key"] = cache_key
        return kwargs

    async def respond(
        self,
        *,
        model: str,
        input: Any,
        instructions: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: Any = None,
        json_schema: dict[str, Any] | None = None,
        schema_name: str = "output",
        reasoning: str | None = None,
        max_output_tokens: int = 4000,
        cache_key: str | None = None,
    ):
        """Raw Responses call (used by the tool loop). Returns (response, Usage)."""
        kwargs = self._common(model, input, instructions, reasoning, max_output_tokens, cache_key)
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice or "auto"
            kwargs["parallel_tool_calls"] = True
        if json_schema:
            kwargs["text"] = {
                "format": {"type": "json_schema", "name": schema_name, "schema": json_schema, "strict": True}
            }
        resp = await self.client.responses.create(**kwargs)
        return resp, self._usage(model, resp.usage)

    async def structured(
        self,
        *,
        model: str,
        input: Any,
        output_type: type[T],
        instructions: str | None = None,
        reasoning: str | None = None,
        max_output_tokens: int = 4000,
        cache_key: str | None = None,
    ) -> tuple[T, Usage]:
        """Strict JSON-schema output validated into a Pydantic model. Returns (parsed, Usage).
        Raises IncompleteOutputError (with usage, so it can still be charged) on truncated/invalid output."""
        kwargs = self._common(model, input, instructions, reasoning, max_output_tokens, cache_key)
        kwargs["text"] = {"format": {"type": "json_schema", "name": output_type.__name__,
                                     "schema": _strict_schema(output_type), "strict": True}}
        resp = await self.client.responses.create(**kwargs)
        usage = self._usage(model, resp.usage)
        text = resp.output_text or ""
        if resp.status != "completed" or not text:
            reason = getattr(resp.incomplete_details, "reason", None) or resp.status
            raise IncompleteOutputError(f"{model} returned no complete output (status={reason})", usage)
        try:
            return output_type.model_validate_json(text), usage
        except ValidationError as e:
            raise IncompleteOutputError(f"{model} returned invalid structured output: {e}", usage) from e

    async def embed(self, texts: list[str], batch_size: int = 256) -> tuple[np.ndarray, Usage]:
        """L2-normalized float32 embeddings, shape (len(texts), dim)."""
        model = self.s.embedding_model
        price = self.price(model)
        total = Usage(model=model)
        vecs: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = [t.strip() or "-" for t in texts[i : i + batch_size]]
            resp = await self.client.embeddings.create(model=model, input=batch)
            vecs.extend(d.embedding for d in sorted(resp.data, key=lambda d: d.index))
            total.input_tokens += resp.usage.prompt_tokens
            total.calls += 1
        total.cost_usd = compute_cost(price, total.input_tokens, 0, 0)
        if not vecs:
            return np.zeros((0, 0), dtype=np.float32), total
        arr = np.asarray(vecs, dtype=np.float32)
        arr /= np.linalg.norm(arr, axis=1, keepdims=True) + 1e-12
        return arr, total


_llm: LLM | None = None


def get_llm() -> LLM:
    global _llm
    if _llm is None:
        _llm = LLM()
    return _llm
