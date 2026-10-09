"""Startup verification that every configured model works with this key.

For each distinct chat model: one forced tool call + one strict JSON-schema output.
For the embedding model: one embedding. Total cost is a fraction of a cent.

CLI:  cd backend && python -m app.model_check
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from dataclasses import asdict, dataclass, field

from .config import Settings, get_settings
from .llm import LLM, describe_error, is_fatal

_TOOL = {
    "type": "function",
    "name": "get_thread",
    "description": "Return the reply chain for a chat message.",
    "parameters": {
        "type": "object",
        "properties": {"msg_id": {"type": "integer", "description": "Telegram message id"}},
        "required": ["msg_id"],
        "additionalProperties": False,
    },
    "strict": True,
}

_SCHEMA = {
    "type": "object",
    "properties": {
        "signal": {"type": "string", "enum": ["question", "complaint", "purchase_intent", "noise"]},
        "score": {"type": "integer"},
    },
    "required": ["signal", "score"],
    "additionalProperties": False,
}

_MSG = "سلام، کسی دوره پایتون خوب برای مبتدی سراغ داره؟ حاضرم پول بدم."


@dataclass
class CheckResult:
    model: str
    kind: str  # "chat" | "embedding"
    ok: bool = False
    fatal: bool = False
    checks: dict[str, str] = field(default_factory=dict)
    error: str | None = None
    cost_usd: float = 0.0
    latency_ms: int = 0


async def _check_chat(llm: LLM, model: str, effort: str) -> CheckResult:
    r = CheckResult(model=model, kind="chat")
    t0 = time.perf_counter()
    try:
        resp, u1 = await llm.respond(
            model=model,
            instructions="You are a test harness. Call the tool.",
            input="Fetch the thread for message 42.",
            tools=[_TOOL],
            tool_choice="required",
            reasoning=effort,
            max_output_tokens=600,
        )
        calls = [it for it in resp.output if it.type == "function_call"]
        if not calls or json.loads(calls[0].arguments).get("msg_id") != 42:
            raise RuntimeError(f"tool call missing or wrong: {[it.type for it in resp.output]}")
        r.checks["tool_call"] = "ok"

        resp, u2 = await llm.respond(
            model=model,
            instructions="Classify the Telegram message. score is relevance 0-10.",
            input=_MSG,
            json_schema=_SCHEMA,
            schema_name="triage_probe",
            reasoning=effort,
            max_output_tokens=600,
        )
        data = json.loads(resp.output_text)
        r.checks["json_schema"] = f"ok ({data['signal']}, {data['score']})"
        r.cost_usd = u1.cost_usd + u2.cost_usd
        r.ok = True
    except Exception as e:  # noqa: BLE001 — we report every failure mode
        r.error = describe_error(e)
        r.fatal = is_fatal(e)
    r.latency_ms = int((time.perf_counter() - t0) * 1000)
    return r


async def _check_embedding(llm: LLM, model: str) -> CheckResult:
    r = CheckResult(model=model, kind="embedding")
    t0 = time.perf_counter()
    try:
        vecs, u = await llm.embed([_MSG])
        r.checks["embedding"] = f"ok (dim={vecs.shape[1]})"
        r.cost_usd = u.cost_usd
        r.ok = True
    except Exception as e:  # noqa: BLE001
        r.error = describe_error(e)
        r.fatal = is_fatal(e)
    r.latency_ms = int((time.perf_counter() - t0) * 1000)
    return r


async def check_models(settings: Settings | None = None) -> dict:
    s = settings or get_settings()
    if not s.openai_api_key:
        return {
            "ok": False,
            "fatal": True,
            "error": "OPENAI_API_KEY is not set. Put it in .env (see .env.example).",
            "results": [],
        }
    llm = LLM(s)
    tasks = [_check_chat(llm, m, effort) for m, effort in s.chat_models().items()]
    tasks.append(_check_embedding(llm, s.embedding_model))
    results = await asyncio.gather(*tasks)
    return {
        "ok": all(r.ok for r in results),
        "fatal": any(r.fatal for r in results),
        "error": None if all(r.ok for r in results) else "; ".join(f"{r.model}: {r.error}" for r in results if not r.ok),
        "results": [asdict(r) for r in results],
        "cost_usd": round(sum(r.cost_usd for r in results), 6),
        "checked_at": int(time.time()),
    }


def format_report(report: dict) -> str:
    lines = ["", "=== Sarenakh model check ==="]
    if not report["results"]:
        lines.append(f"  FAILED: {report['error']}")
    for r in report["results"]:
        status = "OK  " if r["ok"] else "FAIL"
        detail = ", ".join(f"{k}={v}" for k, v in r["checks"].items()) if r["ok"] else r["error"]
        lines.append(f"  [{status}] {r['kind']:<9} {r['model']:<24} {r['latency_ms']:>5} ms  {detail}")
    if report["results"]:
        lines.append(f"  total check cost: ${report['cost_usd']:.6f}")
    lines.append("============================")
    return "\n".join(lines)


if __name__ == "__main__":
    rep = asyncio.run(check_models())
    print(format_report(rep))
    sys.exit(0 if rep["ok"] else 1)
