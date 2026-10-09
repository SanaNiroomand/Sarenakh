"""Compile samples/source/*.chat into a Telegram Desktop export + ground-truth labels.

    python samples/build_sample.py

Outputs (deterministic, committed to the repo):
    samples/python_iran_export.json   Telegram Desktop "Export chat history" (JSON) format
    samples/ground_truth.json         labeled leads/decoys per demo product
"""

from __future__ import annotations

import json
import random
import re
import zlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "source" / "python_iran.chat"
OUT_EXPORT = HERE / "python_iran_export.json"
OUT_TRUTH = HERE / "ground_truth.json"

TEHRAN = timezone(timedelta(hours=3, minutes=30))
FIRST_ID = 1001
SEED = 1405
NOT_INCLUDED = "(File not included. Change data exporting settings to download.)"
PRODUCT_OF = {"A": "quera_python", "B": "bluecut_glasses"}

# People who drop random reaction stickers (never leads/decoys, so labels stay clean).
REACTORS = ["javad", "farhad", "niloofar", "taha", "golnaz", "parisa", "sina"]
REACTION_STICKERS = ["😂", "👍", "🔥", "🙏", "😅", "👏", "💯"]

LABEL = r"[A-Z]-[A-Z]+\d+"
LINE_RE = re.compile(
    rf"^(?:#(?P<label>{LABEL})\s+)?(?P<who>[a-z_]+)(?:>(?P<ref>\^\d*|#{LABEL}))?:\s?(?P<text>.*)$"
)
SCENE_RE = re.compile(r"^@@\s+d(?P<day>\d+)\s+(?P<hh>\d\d):(?P<mm>\d\d)(?:\s+gap=(?P<lo>\d+)-(?P<hi>\d+))?\s*$")
MEDIA_RE = re.compile(r"^\[(?P<kind>sticker|photo|file|fwd|voice)(?:\s+(?P<arg>[^\]]+))?\]\s*(?P<rest>.*)$", re.S)
TOKEN_RE = re.compile(r"`([^`]+)`|(https?://\S+)|(@[A-Za-z0-9_]{4,})")


@dataclass
class Draft:
    who: str
    text: str
    ts: datetime
    scene: int
    ref: str | None = None
    label: str | None = None
    service: str | None = None
    reply_draft: "Draft | None" = None
    id: int = 0


def user_id(key: str) -> str:
    return f"user{5_000_000_000 + zlib.crc32(key.encode()) % 999_999_999}"


def parse_source(path: Path):
    chat_name, start = "chat", None
    users: dict[str, str] = {}
    labels: dict[str, tuple[str, str]] = {}
    scenes: list[dict] = []
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or (line.startswith("#") and not re.match(rf"#{LABEL}\s", line)):
            continue
        try:
            if line.startswith("!chat "):
                chat_name = line[6:].strip()
            elif line.startswith("!start "):
                start = datetime.strptime(line[7:].strip(), "%Y-%m-%d").replace(tzinfo=TEHRAN)
            elif line.startswith("!user "):
                key, name = (p.strip() for p in line[6:].split("|", 1))
                users[key] = name
            elif line.startswith("!label "):
                label, kind, note = (p.strip() for p in line[7:].split("|", 2))
                assert kind in ("lead", "decoy"), kind
                labels[label] = (kind, note)
            elif m := SCENE_RE.match(line):
                scenes.append({
                    "day": int(m["day"]), "hh": int(m["hh"]), "mm": int(m["mm"]),
                    "gap": (int(m["lo"] or 30), int(m["hi"] or 180)), "lines": [],
                })
            elif line.startswith("~ join "):
                scenes[-1]["lines"].append({"service": "join", "who": line[7:].strip()})
            elif m := LINE_RE.match(line):
                scenes[-1]["lines"].append({
                    "who": m["who"], "ref": m["ref"], "label": m["label"],
                    "text": m["text"].replace("\\n", "\n"),
                })
            else:
                raise ValueError("unrecognized line")
        except Exception as e:
            raise SystemExit(f"{path.name}:{n}: {e}: {raw!r}") from e
    assert start, "missing !start"
    return chat_name, start, users, labels, scenes


def build_drafts(start: datetime, users: dict[str, str], scenes: list[dict], rng: random.Random) -> list[Draft]:
    drafts: list[Draft] = []
    for si, sc in enumerate(scenes):
        ts = start + timedelta(days=sc["day"], hours=sc["hh"], minutes=sc["mm"], seconds=rng.randint(0, 59))
        in_scene: list[Draft] = []  # non-service messages, for ^N refs
        for ln in sc["lines"]:
            if ln["who"] not in users:
                raise SystemExit(f"unknown user '{ln['who']}' in scene {si}")
            if ln.get("service"):
                drafts.append(Draft(who=ln["who"], text="", ts=ts, scene=si, service=ln["service"]))
                ts += timedelta(seconds=rng.randint(5, 40))
                continue
            d = Draft(who=ln["who"], text=ln["text"], ts=ts, scene=si, ref=ln["ref"], label=ln["label"])
            if d.ref and d.ref.startswith("^"):
                back = int(d.ref[1:] or 1)
                if back > len(in_scene):
                    raise SystemExit(f"scene {si}: '{d.ref}' reaches before the scene start: {d.text[:40]!r}")
                d.reply_draft = in_scene[-back]
            in_scene.append(d)
            drafts.append(d)
            # occasional sticker reaction from a bystander
            if not d.text.startswith("[sticker") and rng.random() < 0.08:
                who = rng.choice([r for r in REACTORS if r != d.who])
                drafts.append(Draft(
                    who=who, text=f"[sticker {rng.choice(REACTION_STICKERS)}]",
                    ts=ts + timedelta(seconds=rng.randint(4, 25)), scene=si,
                    reply_draft=d if rng.random() < 0.5 else None,
                ))
            ts += timedelta(seconds=rng.randint(*sc["gap"]))
    return drafts


def entities(text: str) -> tuple[str | list, list[dict]]:
    parts: list[dict] = []
    pos = 0
    for m in TOKEN_RE.finditer(text):
        if m.start() > pos:
            parts.append({"type": "plain", "text": text[pos : m.start()]})
        if m.group(1) is not None:
            code = m.group(1)
            parts.append({"type": "pre", "text": code, "language": ""} if "\n" in code else {"type": "code", "text": code})
        elif m.group(2):
            parts.append({"type": "link", "text": m.group(2)})
        else:
            parts.append({"type": "mention", "text": m.group(3)})
        pos = m.end()
    if pos < len(text):
        parts.append({"type": "plain", "text": text[pos:]})
    if all(p["type"] == "plain" for p in parts):
        return text, parts
    return [p["text"] if p["type"] == "plain" else p for p in parts], parts


def to_export(d: Draft, users: dict[str, str], rng: random.Random) -> dict:
    base = {
        "id": d.id,
        "type": "service" if d.service else "message",
        "date": d.ts.strftime("%Y-%m-%dT%H:%M:%S"),
        "date_unixtime": str(int(d.ts.timestamp())),
    }
    if d.service:
        base.update({
            "actor": users[d.who], "actor_id": user_id(d.who),
            "action": "join_group_by_link", "inviter": "Group", "text": "", "text_entities": [],
        })
        return base
    base.update({"from": users[d.who], "from_id": user_id(d.who)})
    if d.reply_draft:
        base["reply_to_message_id"] = d.reply_draft.id
    text = d.text
    if m := MEDIA_RE.match(text):
        kind, arg, text = m["kind"], m["arg"], m["rest"]
        if kind == "sticker":
            base.update({"file": NOT_INCLUDED, "thumbnail": NOT_INCLUDED, "media_type": "sticker",
                         "sticker_emoji": arg or "🙂", "width": 512, "height": 512})
        elif kind == "photo":
            base.update({"photo": NOT_INCLUDED, "width": 1280, "height": 720})
        elif kind == "file":
            base.update({"file": NOT_INCLUDED, "file_name": arg, "mime_type": "text/x-python"})
        elif kind == "voice":
            base.update({"file": NOT_INCLUDED, "media_type": "voice_message",
                         "mime_type": "audio/ogg", "duration_seconds": int(arg or 10)})
        elif kind == "fwd":
            base["forwarded_from"] = arg
    if text and rng.random() < 0.04:
        edited = d.ts + timedelta(seconds=rng.randint(30, 300))
        base["edited"] = edited.strftime("%Y-%m-%dT%H:%M:%S")
        base["edited_unixtime"] = str(int(edited.timestamp()))
    base["text"], base["text_entities"] = entities(text)
    return base


def main() -> None:
    rng = random.Random(SEED)
    chat_name, start, users, labels, scenes = parse_source(SRC)
    drafts = build_drafts(start, users, scenes, rng)
    drafts.sort(key=lambda d: d.ts)  # stable: interleaves overlapping scenes realistically
    for i, d in enumerate(drafts):
        d.id = FIRST_ID + i

    by_label: dict[str, Draft] = {}
    for d in drafts:
        if d.label:
            if d.label in by_label:
                raise SystemExit(f"label {d.label} used twice")
            by_label[d.label] = d
    for d in drafts:
        if d.ref and d.ref.startswith("#"):
            target = by_label.get(d.ref[1:])
            if target is None:
                raise SystemExit(f"reply to unknown label {d.ref}")
            d.reply_draft = target
        if d.reply_draft and d.reply_draft.ts >= d.ts:
            raise SystemExit(f"message {d.id} replies to a later message {d.reply_draft.id}")
    missing = set(labels) - set(by_label)
    undeclared = set(by_label) - set(labels)
    if missing or undeclared:
        raise SystemExit(f"label mismatch: missing in chat={sorted(missing)}, undeclared={sorted(undeclared)}")

    export = {
        "name": chat_name,
        "type": "public_supergroup",
        "id": 1_987_654_321,
        "messages": [to_export(d, users, rng) for d in drafts],
    }
    OUT_EXPORT.write_text(json.dumps(export, ensure_ascii=False, indent=1), encoding="utf-8")

    truth: dict = {
        "chat_file": OUT_EXPORT.name,
        "note": "Leads are counted per person (a lead's user_id), matching the never-pitch-twice rule.",
        "products": {},
    }
    for label, (kind, note) in labels.items():
        d = by_label[label]
        prod = truth["products"].setdefault(PRODUCT_OF[label[0]], {"leads": [], "decoys": []})
        prod["leads" if kind == "lead" else "decoys"].append({
            "label": label, "msg_id": d.id, "user_id": user_id(d.who), "author": users[d.who], "note": note,
        })
    OUT_TRUTH.write_text(json.dumps(truth, ensure_ascii=False, indent=1), encoding="utf-8")

    msgs = export["messages"]
    kinds: dict[str, int] = {}
    for m in msgs:
        k = m["type"] if m["type"] == "service" else m.get("media_type") or ("photo" if "photo" in m else "text")
        kinds[k] = kinds.get(k, 0) + 1
    print(f"{len(msgs)} messages ({kinds}), {len(users)} users, "
          f"{sum(1 for m in msgs if 'reply_to_message_id' in m)} replies")
    for prod, v in truth["products"].items():
        print(f"  {prod}: {len(v['leads'])} leads, {len(v['decoys'])} decoys")
    print(f"wrote {OUT_EXPORT.relative_to(HERE.parent)} and {OUT_TRUTH.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
