import json
from pathlib import Path

import pytest

from app.chat.index import ChatIndex
from app.chat.normalize import ZWNJ, detect_lang, normalize
from app.chat.parse import ChatParseError, parse_pasted_text, parse_telegram_export

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


@pytest.fixture(scope="module")
def chat():
    return parse_telegram_export((SAMPLES / "python_iran_export.json").read_bytes())


@pytest.fixture(scope="module")
def truth():
    return json.loads((SAMPLES / "ground_truth.json").read_text(encoding="utf-8"))


def _gt(truth, label):
    for prod in truth["products"].values():
        for e in prod["leads"] + prod["decoys"]:
            if e["label"] == label:
                return e
    raise KeyError(label)


# --- normalization ---------------------------------------------------------------------------


def test_arabic_letters_and_digits():
    assert normalize("كيف يك ۱۲۳ ٤٥") == "کیف یک 123 45"


def test_zwnj_unification():
    assert normalize("می خوام") == f"می{ZWNJ}خوام"
    assert normalize("نمی دونم") == f"نمی{ZWNJ}دونم"
    assert normalize("کتاب ها") == f"کتاب{ZWNJ}ها"
    assert normalize("می​خوام") == f"می{ZWNJ}خوام"  # zero-width space -> ZWNJ
    assert normalize(f"سلام{ZWNJ}{ZWNJ} دنیا") == "سلام دنیا"


def test_emoji_spam_and_letter_runs():
    assert normalize("فقط امروز 🔥🔥🔥 تخفیف 💰 💰") == "فقط امروز 🔥 تخفیف 💰"
    assert normalize("سلاااااام") == "سلام"
    assert normalize("salaaaaam khooob") == "salaam khoob"
    assert normalize("https://www.example.com/aaa") == "https://www.example.com/aaa"


def test_detect_lang():
    assert detect_lang("salam bachea, mikham python ro az sefr shoroo konam") == "finglish"
    assert detect_lang("سلام، یه دوره پایتون خوب سراغ دارید؟") == "fa"
    assert detect_lang("کسی bootcamp پایتون job-ready سراغ داره؟") in ("fa", "mixed")
    assert detect_lang("Python 3.14 is out with free-threading") == "en"


# --- Telegram export parsing -----------------------------------------------------------------


def test_parse_sample(chat):
    assert 300 <= len(chat.messages) <= 500
    assert chat.stats["authors"] >= 30
    kinds = {m.kind for m in chat.messages}
    assert {"text", "sticker"} <= kinds
    assert not any(m.analyzable for m in chat.messages if m.kind == "sticker")
    assert chat.stats["analyzable"] < len(chat.messages)
    ids = [m.id for m in chat.messages]
    assert ids == sorted(ids)  # chronological == id order in the sample
    # entity arrays are flattened
    m = next(m for m in chat.messages if "npm install" in m.text)
    assert "`" not in m.text and "نیم ساعته" in m.text


def test_finglish_lead_detected(chat, truth):
    m = next(x for x in chat.messages if x.id == _gt(truth, "A-L1")["msg_id"])
    assert m.lang == "finglish"


def test_full_account_export_picks_biggest_chat():
    data = {"chats": {"list": [
        {"name": "small", "messages": [{"id": 1, "type": "message", "date": "2026-10-01T10:00:00", "from": "a", "from_id": "user1", "text": "سلام دوستان"}]},
        {"name": "big", "messages": [
            {"id": i, "type": "message", "date": "2026-10-01T10:00:00", "from": "b", "from_id": "user2", "text": f"پیام شماره {i}"}
            for i in range(1, 4)
        ]},
    ]}}
    parsed = parse_telegram_export(data)
    assert parsed.name == "big" and len(parsed.messages) == 3


def test_garbage_raises_persian_error():
    with pytest.raises(ChatParseError):
        parse_telegram_export(b"not json")
    with pytest.raises(ChatParseError):
        parse_telegram_export({"foo": 1})


# --- threads & history -----------------------------------------------------------------------


def test_me_too_reply_needs_thread(chat, truth):
    idx = ChatIndex(chat.messages)
    l9 = _gt(truth, "A-L9")["msg_id"]
    thread_ids = [m.id for m in idx.thread(l9)]
    assert _gt(truth, "A-L2")["msg_id"] in thread_ids  # the question "me too" refers to
    assert thread_ids.index(_gt(truth, "A-L2")["msg_id"]) < thread_ids.index(l9)


def test_resolved_in_thread(chat, truth):
    idx = ChatIndex(chat.messages)
    d2 = _gt(truth, "A-D2")
    later = [m.norm for m in idx.descendants(d2["msg_id"]) if m.author_id == d2["user_id"]]
    assert any("ثبت" in t for t in later)


def test_user_history_reveals_changed_mind(chat, truth):
    idx = ChatIndex(chat.messages)
    d10 = _gt(truth, "A-D10")
    hist = idx.user_history(d10["user_id"], around=d10["msg_id"])
    assert any("Go" in m.norm and "بیخیال" in m.norm for m in hist)


def test_nearby_and_search(chat, truth):
    idx = ChatIndex(chat.messages)
    l1 = _gt(truth, "A-L1")["msg_id"]
    near = idx.nearby(l1, 3)
    assert l1 in [m.id for m in near] and len(near) == 7
    hits = idx.search("عینک محافظ نور آبی")
    assert any("عینک" in m.norm for m in hits)
    assert "↩#" in idx.render(idx.thread(_gt(truth, "A-L9")["msg_id"]))


# --- pasted text -----------------------------------------------------------------------------


def test_paste_telegram_copy_format():
    text = "Sara, [02.10.26 10:21]\nسلام کسی دوره پایتون سراغ داره؟\n\nAli, [02.10.26 10:23]\nآره مکتب‌خونه\nخوبه"
    p = parse_pasted_text(text)
    assert [m.author for m in p.messages] == ["Sara", "Ali"]
    assert "مکتب" in p.messages[1].text and "خوبه" in p.messages[1].text
    assert p.messages[0].ts < p.messages[1].ts


def test_paste_name_colon_format():
    p = parse_pasted_text("سارا: سلام بچه‌ها\nعلی: سلام خوبی؟\nسارا: دنبال دوره پایتونم\nادامه پیام قبلی")
    assert [m.author for m in p.messages] == ["سارا", "علی", "سارا"]
    assert "ادامه" in p.messages[2].text


def test_paste_plain_lines():
    p = parse_pasted_text("سلام کسی عینک محافظ داره؟\nمن دنبال یه دوره پایتونم")
    assert len(p.messages) == 2 and p.messages[0].author_id != p.messages[1].author_id


def test_paste_too_short():
    with pytest.raises(ChatParseError):
        parse_pasted_text("سلام")
