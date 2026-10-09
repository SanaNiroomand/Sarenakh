"""Run the profile agent on each demo product (answering its clarifying questions with the canned
answers in samples/products.json) and save samples/profiles/<key>.json for the instant demo flow.

    cd backend && python -m scripts.build_sample_profiles
"""

from __future__ import annotations

import asyncio
import json
import sys

from app.agents.profile_agent import profile_turn
from app.config import get_settings
from app.llm import LLM
from app.samples import sample_products


async def main() -> None:
    s = get_settings()
    llm = LLM(s)
    out_dir = s.samples_dir / "profiles"
    out_dir.mkdir(exist_ok=True)
    only = set(sys.argv[1:])
    total = 0.0
    for key, sp in sample_products().items():
        if only and key not in only:
            continue
        chat = [{"role": "user", "content": sp["description"]}]
        answers = list(sp["clarifying_answers"].values())
        for _ in range(3):
            turn, usage = await profile_turn(llm, s, chat)
            total += usage.cost_usd
            if turn.action == "profile":
                break
            answer = " ".join(answers) if answers else "همین کافیه، پروفایل رو بساز."
            answers = []
            print(f"[{key}] Q: {turn.question}\n[{key}] A: {answer}")
            chat += [{"role": "assistant", "content": turn.question}, {"role": "user", "content": answer}]
        profile = turn.profile
        assert profile is not None
        profile.facts = sp["facts"]  # the business's own curated fact sheet (editable in the app)
        path = out_dir / f"{key}.json"
        path.write_text(json.dumps(profile.model_dump(), ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[{key}] wrote {path.name}: {len(profile.signal_examples)} signal examples, "
              f"{len(profile.disqualifiers)} disqualifiers, ideal={profile.ideal_shape.model_dump()}")
    print(f"total cost ${total:.5f}")


if __name__ == "__main__":
    asyncio.run(main())
