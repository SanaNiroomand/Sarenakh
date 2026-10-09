from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _signup(client, email, password="correct-horse-1"):
    return client.post("/api/auth/signup", json={"email": email, "password": password, "name": "تست"})


def _is_persian(s: str) -> bool:
    return any("؀" <= ch <= "ۿ" for ch in s)


def test_auth_flow(client):
    r = _signup(client, "Judge@Example.com")
    assert r.status_code == 200, r.text
    assert r.json()["email"] == "judge@example.com"
    assert "sarenakh_session" in r.cookies or client.cookies.get("sarenakh_session")
    assert client.get("/api/auth/me").status_code == 200

    r = _signup(client, "judge@example.com")
    assert r.status_code == 409 and _is_persian(r.json()["detail"])

    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401

    r = client.post("/api/auth/login", json={"email": "judge@example.com", "password": "wrong-pass"})
    assert r.status_code == 401 and _is_persian(r.json()["detail"])
    r = client.post("/api/auth/login", json={"email": "JUDGE@example.com ", "password": "correct-horse-1"})
    assert r.status_code == 200
    assert client.get("/api/auth/me").json()["email"] == "judge@example.com"


@pytest.mark.parametrize("body", [
    {"email": "not-an-email", "password": "longenough1"},
    {"email": "a@b.co", "password": "short"},
])
def test_signup_validation_is_persian(client, body):
    r = client.post("/api/auth/signup", json=body)
    assert r.status_code == 422 and _is_persian(r.json()["detail"])


def test_persian_password_longer_than_72_bytes(client):
    pw = "رمزعبورخیلیطولانیفارسی" * 3  # > 72 bytes in UTF-8
    assert _signup(client, "persian@example.com", pw).status_code == 200
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"email": "persian@example.com", "password": pw}).status_code == 200


def test_products_and_isolation(client):
    _signup(client, "owner@example.com")
    samples = client.get("/api/products/samples").json()
    assert {s["key"] for s in samples} == {"pystart", "cheshmaram"}

    p = client.post("/api/products/sample/pystart").json()
    assert p["sample_key"] == "pystart"
    assert client.post("/api/products/sample/pystart").json()["id"] == p["id"]  # idempotent

    r = client.post("/api/products", json={"description": "یک اپ مدیریت مالی شخصی برای فریلنسرها که درآمد و مالیات را حساب می‌کند"})
    assert r.status_code == 200
    mine = r.json()["id"]

    profile = {
        "product_name": "حساب‌یار", "one_liner": "x", "persona": "x", "pain_points": ["a"],
        "buying_signals": ["b"], "signal_examples": ["c"], "disqualifiers": ["d"], "reply_tone": "e",
        "ideal_shape": {"need": 9, "product_fit": 9, "urgency": 6, "buying_intent": 8, "reachability": 7, "confidence": 15},
        "facts": ["f"],
    }
    r = client.put(f"/api/products/{mine}/profile", json=profile)
    assert r.status_code == 200
    assert r.json()["profile"]["ideal_shape"]["confidence"] == 10  # clamped to 0..10
    assert r.json()["name"] == "حساب‌یار"

    client.post("/api/auth/logout")
    _signup(client, "intruder@example.com")
    assert client.get(f"/api/products/{mine}").status_code == 404
    assert all(x["id"] != mine for x in client.get("/api/products").json())


def test_datasets(client):
    _signup(client, "data@example.com")
    sample = client.get("/api/datasets/sample").json()
    assert sample["stats"]["messages"] > 300

    page = client.get(f"/api/datasets/{sample['id']}/messages", params={"around": 1100, "radius": 5}).json()
    ids = [m["msg_id"] for m in page["messages"]]
    assert 1100 in ids and len(ids) == 11

    raw = (SAMPLES / "python_iran_export.json").read_bytes()
    r = client.post("/api/datasets/upload", files={"file": ("result.json", raw, "application/json")})
    assert r.status_code == 200, r.text
    uploaded = r.json()
    assert uploaded["stats"]["messages"] == sample["stats"]["messages"]

    r = client.post("/api/datasets/upload", files={"file": ("result.json", b"{oops", "application/json")})
    assert r.status_code == 400 and _is_persian(r.json()["detail"])

    r = client.post("/api/datasets/paste", json={"text": "سارا: سلام کسی دوره پایتون سراغ داره؟\nعلی: آره مکتب‌خونه"})
    assert r.status_code == 200 and r.json()["stats"]["messages"] == 2

    listed = {d["id"] for d in client.get("/api/datasets").json()}
    assert {sample["id"], uploaded["id"]} <= listed

    client.post("/api/auth/logout")
    _signup(client, "other-data@example.com")
    assert client.get(f"/api/datasets/{uploaded['id']}").status_code == 404
    assert client.get(f"/api/datasets/{sample['id']}").status_code == 200  # sample is shared


def test_requires_login(client):
    client.post("/api/auth/logout")
    assert client.get("/api/products").status_code == 401
    assert _is_persian(client.get("/api/products").json()["detail"])
