import json
from datetime import timedelta

import jwt
from fastapi.testclient import TestClient

from app.auth import hash_password
from app.db import SessionLocal
from app.main import app
from app.models import Listing, User, utcnow

client = TestClient(app)


def setup_users_and_listing(portions=2):
    with SessionLocal() as db:
        host = User(name="hana", email="hana@school.edu", password_hash=hash_password("password123"), is_host=True)
        sam = User(name="sam", email="sam@school.edu", password_hash=hash_password("password123"))
        db.add_all([host, sam])
        db.commit()
        listing = Listing(host_id=host.id, title="Bagels", location="Library", portions=portions,
                          available_until=utcnow() + timedelta(hours=1))
        db.add(listing)
        db.commit()
        return listing.id


def token_for(email="sam@school.edu", password="password123"):
    return client.post("/api/token", data={"username": email, "password": password})


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_login_returns_a_jwt():
    setup_users_and_listing()
    r = token_for()
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == 3600
    assert client.get("/api/me", headers=auth(body["access_token"])).json()["name"] == "sam"


def test_wrong_password_is_rejected():
    setup_users_and_listing()
    assert token_for(password="nope").status_code == 401


def test_protected_endpoints_need_a_valid_token():
    setup_users_and_listing()
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/me", headers=auth("garbage")).status_code == 401
    expired = jwt.encode({"sub": "1", "exp": utcnow() - timedelta(minutes=1)}, "dev-only-secret-change-me-before-deploying")
    assert client.get("/api/me", headers=auth(expired)).status_code == 401
    forged = jwt.encode({"sub": "1", "exp": utcnow() + timedelta(minutes=5)}, "someone-elses-secret-that-is-long-enough")
    assert client.get("/api/me", headers=auth(forged)).status_code == 401


def test_claim_through_the_api():
    listing_id = setup_users_and_listing(portions=1)
    token = token_for().json()["access_token"]
    assert client.post(f"/api/listings/{listing_id}/claim").status_code == 401

    r = client.post(f"/api/listings/{listing_id}/claim", headers=auth(token))
    assert r.status_code == 201 and len(r.json()["pickup_code"]) == 4
    assert client.post(f"/api/listings/{listing_id}/claim", headers=auth(token)).status_code == 409
    assert client.get("/api/listings").json()[0]["remaining"] == 0
    assert [c["listing_title"] for c in client.get("/api/me/claims", headers=auth(token)).json()] == ["Bagels"]


def test_daily_stats_has_one_row_per_day():
    setup_users_and_listing(portions=5)
    rows = client.get("/api/stats/daily?days=7").json()
    assert len(rows) == 7
    assert rows[-1]["portions_posted"] == 5 and rows[-1]["meals_rescued"] == 0


def test_health_and_request_logging(capsys):
    assert client.get("/health").json() == {"status": "ok"}
    line = [l for l in capsys.readouterr().out.splitlines() if '"endpoint"' in l][-1]
    entry = json.loads(line)
    assert entry["endpoint"] == "/health" and entry["status"] == 200 and entry["method"] == "GET"
    assert entry["duration_ms"] >= 0 and "timestamp" in entry


def test_logs_use_route_templates_not_raw_ids(capsys):
    client.get("/api/listings/12345/claim")  # wrong method, still logged
    client.post("/api/listings/12345/claim")
    entry = json.loads([l for l in capsys.readouterr().out.splitlines() if '"endpoint"' in l][-1])
    assert entry["endpoint"] == "/api/listings/{listing_id}/claim" and entry["status"] == 401
