import time
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient

from nomsindo.licensing import LicenceClient, LicenceError
from server.main import create_app
from tests.test_server import PW, add_user, signup


@pytest.fixture()
def setup(tmp_path):
    from server import api, portal
    api.limiter.hits.clear(); portal.login_limiter.hits.clear()
    app = create_app(data_dir=tmp_path / "srv")
    owner = signup(app); add_user(owner, "agent@acme.test")
    tc = TestClient(app)

    def transport(url, body, token=None):
        path = urlparse(url).path
        r = tc.post(path, json=body, headers={"Authorization": f"Bearer {token}"} if token else {})
        return r.status_code, r.json()

    mk = lambda name="c": LicenceClient("http://localhost:8000", tmp_path / f"{name}.json",
                                        public_key=app.state.private_key.public_key(), transport=transport)
    return app, mk


def test_sign_in_state_and_persistence(setup):
    app, mk = setup
    c = mk()
    assert c.state().status == "needs_signin"
    s = c.sign_in("http://localhost:8000", "agent@acme.test", PW)
    assert s.status == "ok" and s.org_name == "Acme" and s.plan == "trial" and 13 <= s.days_left <= 14
    assert not s.needs_refresh
    again = LicenceClient("http://localhost:8000", c.path, public_key=app.state.private_key.public_key())
    assert again.state().status == "ok"


def test_bad_password_and_insecure_server(setup):
    _, mk = setup
    with pytest.raises(LicenceError) as e:
        mk().sign_in("http://localhost:8000", "agent@acme.test", "wrong-password-x")
    assert e.value.code == "invalid_credentials"
    with pytest.raises(LicenceError) as e:
        mk().sign_in("http://example.com", "a@b.co", "x")
    assert e.value.code == "insecure_server"


def test_forged_token_rejected(setup):
    _, mk = setup
    c = mk(); c.sign_in("http://localhost:8000", "agent@acme.test", PW)
    c._data["token"] = c._data["token"][:-6] + "AAAAAA"; c._save()
    assert mk("other").state().status == "needs_signin" or LicenceClient(
        "x", c.path, public_key=c.public_key).state().status == "needs_signin"


def test_refresh_and_offline_expiry(setup, monkeypatch):
    _, mk = setup
    c = mk(); c.sign_in("http://localhost:8000", "agent@acme.test", PW)
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + 2 * 86400)
    assert c.state().needs_refresh and c.state().status == "ok"
    assert c.refresh().status == "ok"
    monkeypatch.setattr(time, "time", lambda: real() + 11 * 86400)   # past token expiry, still inside the trial, offline
    assert c.state().status == "needs_signin"


def test_server_side_revocation_signs_out_locally(setup):
    app, mk = setup
    from sqlalchemy import select
    from server.models import Device
    c = mk(); c.sign_in("http://localhost:8000", "agent@acme.test", PW)
    with app.state.SessionLocal() as s:
        d = s.scalar(select(Device)); d.revoked = True; s.commit()
    assert c.refresh().status == "needs_signin"


def test_usage_report_and_sign_out(setup):
    _, mk = setup
    c = mk(); c.sign_in("http://localhost:8000", "agent@acme.test", PW)
    assert c.report_usage(120, 60) is True and c.report_usage(0, 0) is False
    c.sign_out()
    assert c.state().status == "needs_signin"
