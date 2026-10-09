"""Debug: run raw triage batches for a sample product and show output sizes / failures.

    cd backend && python -m scripts.debug_triage bluecut_glasses
"""

import asyncio
import sys

from openai.lib._pydantic import to_strict_json_schema

from app.agents.prompts import TRIAGE_SYSTEM, profile_block
from app.agents.schemas import TriageBatch
from app.chat.index import ChatIndex
from app.chat.parse import parse_telegram_export
from app.config import get_settings
from app.llm import LLM
from app.samples import sample_profile
from app.schemas import Profile


async def main(key: str) -> None:
    s = get_settings()
    llm = LLM(s)
    profile = Profile(**sample_profile(key))
    chat = parse_telegram_export((s.samples_dir / "python_iran_export.json").read_bytes())
    msgs = [m for m in chat.messages if m.analyzable][:100]
    idx = ChatIndex(chat.messages)
    instructions = TRIAGE_SYSTEM.format(profile=profile_block(profile, with_examples=True))
    schema = to_strict_json_schema(TriageBatch)
    for i in range(0, len(msgs), 25):
        batch = msgs[i : i + 25]
        text = "Messages:\n" + "\n".join(f"#{m.id} | {m.author}: {m.norm[:600]}" for m in batch)
        resp, u = await llm.respond(model=s.triage_model, instructions=instructions, input=text,
                                    json_schema=schema, schema_name="TriageBatch", reasoning=s.triage_reasoning,
                                    max_output_tokens=5000)
        out = resp.output_text or ""
        print(f"batch {i // 25}: status={resp.status} in={u.input_tokens} out={u.output_tokens} "
              f"reasoning={u.reasoning_tokens} chars={len(out)}")
        if resp.status != "completed":
            print("TAIL:", out[-600:])


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "bluecut_glasses"))
