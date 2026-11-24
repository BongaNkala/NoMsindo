import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from server import licensing
from server.main import create_app
from server.models import Device, Org, User, utcnow
from server import api, portal

PW = "correct horse battery"


@pytest.fixture()
def app(tmp_path):
    api.limiter.hits.clear()
    portal.login_limiter.hits.clear()
    return create_app(data_dir=tmp_path)


def csrf(c: TestClient, path: str) -> str:
    html = c.get(path).text
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def signup(app, org="Acme", email="owner@acme.test") -> TestClient:
    c = TestClient(app)
    r = c.post("/signup", data={"csrf": csrf(c, "/signup"), "org_name": org, "email": email, "password": PW})
    assert r.status_code == 200 and org in r.text
    return c


def add_user(c, email, role="agent"):
    return c.post("/users", data={"csrf": csrf(c, "/users"), "email": email, "password": PW, "role": role})


def activate(app, email, dev="a" * 16, password=PW):
    return TestClient(app).post("/api/v1/activate", json={"email": email, "password": password,
                                                        "device_hash": dev, "device_name": "PC-" + dev[:2]})


def db(app):
    return app.state.SessionLocal()


def test_signup_starts_trial(app):
    c = signup(app)
    with db(app) as s:
        o = s.scalar(select(Org))
        assert o.seats == 5 and o.plan == "trial" and 13 <= o.days_left <= 14 and o.is_licensed
    assert "Free trial" in c.get("/").text


def test_login_wrong_and_right(app):
    signup(app)
    c = TestClient(app)
    assert c.post("/login", data={"csrf": csrf(c, "/login"), "email": "owner@acme.test", "password": "nope"}).status_code == 401
    r = c.post("/login", data={"csrf": csrf(c, "/login"), "email": "owner@acme.test", "password": PW})
    assert r.status_code == 200 and "Dashboard" in r.text


def test_weak_password_and_duplicate_email_rejected(app):
    c = TestClient(app)
    r = c.post("/signup", data={"csrf": csrf(c, "/signup"), "org_name": "X", "email": "a@b.co", "password": "short"})
    assert r.status_code == 400 and "at least 10" in r.text
    signup(app)
    r = c.post("/signup", data={"csrf": csrf(c, "/signup"), "org_name": "Y", "email": "owner@acme.test", "password": PW})
    assert r.status_code == 400 and "already exists" in r.text


def test_seat_limit_enforced(app):
    c = signup(app)
    for i in range(4):
        assert "Added" in add_user(c, f"a{i}@acme.test").text
    assert "seats are in use" in add_user(c, "a5@acme.test").text


def test_activate_issues_verifiable_token(app):
    c = signup(app); add_user(c, "agent@acme.test")
    r = activate(app, "agent@acme.test")
    assert r.status_code == 200
    p = licensing.verify(r.json()["token"], app.state.private_key.public_key())
    assert p["email"] == "agent@acme.test" and p["org_name"] == "Acme" and p["plan"] == "trial"
    assert p["refresh_after"] < p["expires"] and p["licence_until"] > p["issued"]


def test_bad_password_and_tampered_token(app):
    c = signup(app); add_user(c, "agent@acme.test")
    assert activate(app, "agent@acme.test", password="wrong-password").json()["error"] == "invalid_credentials"
    tok = activate(app, "agent@acme.test").json()["token"]
    bad = tok[:-4] + ("AAAA" if not tok.endswith("AAAA") else "BBBB")
    r = TestClient(app).post("/api/v1/refresh", json={"token": bad})
    assert r.status_code == 401 and r.json()["error"] == "invalid_token"


def test_device_limit_and_release(app):
    c = signup(app); add_user(c, "agent@acme.test")
    assert activate(app, "agent@acme.test", "1" * 16).status_code == 200
    assert activate(app, "agent@acme.test", "2" * 16).status_code == 200
    r = activate(app, "agent@acme.test", "3" * 16)
    assert r.status_code == 403 and r.json()["error"] == "device_limit"
    tok = activate(app, "agent@acme.test", "1" * 16).json()["token"]
    assert TestClient(app).post("/api/v1/deactivate", headers={"Authorization": "Bearer " + tok}).status_code == 200
    assert activate(app, "agent@acme.test", "3" * 16).status_code == 200


def test_expired_licence_blocks_activate_and_refresh(app):
    c = signup(app); add_user(c, "agent@acme.test")
    tok = activate(app, "agent@acme.test").json()["token"]
    with db(app) as s:
        o = s.scalar(select(Org)); o.trial_ends_at = utcnow() - timedelta(days=1); s.commit()
    assert activate(app, "agent@acme.test").json()["error"] == "licence_expired"
    r = TestClient(app).post("/api/v1/refresh", json={"token": tok})
    assert r.status_code == 402 and r.json()["error"] == "licence_expired"
    assert "has ended" in c.get("/").text


def test_paid_until_extends_licence(app):
    c = signup(app); add_user(c, "agent@acme.test")
    with db(app) as s:
        o = s.scalar(select(Org)); o.trial_ends_at = utcnow() - timedelta(days=1)
        o.paid_until = utcnow() + timedelta(days=90); s.commit()
    r = activate(app, "agent@acme.test")
    assert r.status_code == 200 and r.json()["plan"] == "paid"


def test_admin_revoke_device_and_deactivate_user(app):
    c = signup(app); add_user(c, "agent@acme.test")
    tok = activate(app, "agent@acme.test").json()["token"]
    with db(app) as s:
        did = s.scalar(select(Device)).id
    c.post(f"/devices/{did}/revoke", data={"csrf": csrf(c, "/devices")})
    r = TestClient(app).post("/api/v1/refresh", json={"token": tok})
    assert r.status_code == 403 and r.json()["error"] == "device_revoked"
    assert activate(app, "agent@acme.test").json()["error"] == "device_revoked"
    # deactivate user
    c2 = signup(app, "Beta", "owner@beta.test"); add_user(c2, "agent@beta.test")
    tok2 = activate(app, "agent@beta.test", "b" * 16).json()["token"]
    with db(app) as s:
        uid = s.scalar(select(User).where(User.email == "agent@beta.test")).id
    c2.post(f"/users/{uid}/toggle", data={"csrf": csrf(c2, "/users")})
    r = TestClient(app).post("/api/v1/refresh", json={"token": tok2})
    assert r.json()["error"] == "account_disabled"


def test_usage_accumulates_and_shows(app):
    c = signup(app); add_user(c, "agent@acme.test")
    tok = activate(app, "agent@acme.test").json()["token"]
    h = {"Authorization": "Bearer " + tok}
    for _ in range(2):
        assert TestClient(app).post("/api/v1/usage", json={"mic_seconds": 600, "speaker_seconds": 300}, headers=h).status_code == 200
    page = c.get("/usage").text
    assert "agent@acme.test" in page and "<td>20</td><td>10</td>" in page
    assert TestClient(app).post("/api/v1/usage", json={"mic_seconds": -5}, headers=h).status_code == 422
    assert TestClient(app).post("/api/v1/usage", json={"mic_seconds": 5}).status_code == 401


def test_tenant_isolation(app):
    a = signup(app, "Acme", "owner@acme.test"); add_user(a, "agent@acme.test")
    activate(app, "agent@acme.test")
    b = signup(app, "Beta", "owner@beta.test")
    with db(app) as s:
        uid = s.scalar(select(User).where(User.email == "agent@acme.test")).id
        did = s.scalar(select(Device)).id
    t = csrf(b, "/users")
    assert b.post(f"/users/{uid}/toggle", data={"csrf": t}).status_code == 404
    assert b.post(f"/users/{uid}/reset", data={"csrf": t, "password": PW + "x"}).status_code == 404
    assert b.post(f"/devices/{did}/revoke", data={"csrf": t}).status_code == 404
    assert "agent@acme.test" not in b.get("/users").text and "agent@acme.test" not in b.get("/devices").text
    assert b.get("/platform").status_code == 403


def test_agent_cannot_use_admin_pages(app):
    a = signup(app); add_user(a, "agent@acme.test")
    c = TestClient(app)
    c.post("/login", data={"csrf": csrf(c, "/login"), "email": "agent@acme.test", "password": PW})
    assert c.get("/users").status_code == 403 and c.get("/usage").status_code == 403
    assert "My account" in c.get("/account").text


def test_csrf_required_and_login_required(app):
    c = signup(app)
    assert c.post("/users", data={"email": "x@acme.test", "password": PW}).status_code == 403
    assert TestClient(app).get("/users", follow_redirects=False).status_code == 303


def test_platform_admin_can_set_seats_and_paid_until(app):
    from server.manage import hash_password
    signup(app)
    with db(app) as s:
        org = s.scalar(select(Org))
        s.add(User(org_id=org.id, email="staff@tl.test", password_hash=hash_password(PW), role="owner", is_platform_admin=True))
        s.commit(); oid = org.id
    c = TestClient(app)
    c.post("/login", data={"csrf": csrf(c, "/login"), "email": "staff@tl.test", "password": PW})
    r = c.post(f"/platform/orgs/{oid}", data={"csrf": csrf(c, "/platform"), "seats": "25", "paid_until": "2099-01-31"})
    assert "Updated" in r.text
    with db(app) as s:
        o = s.get(Org, oid); assert o.seats == 25 and o.plan == "paid"


def test_activate_rate_limited(app):
    signup(app)
    for _ in range(8):
        assert activate(app, "owner@acme.test", password="wrong-wrong-wrong").status_code == 401
    assert activate(app, "owner@acme.test").status_code == 429
