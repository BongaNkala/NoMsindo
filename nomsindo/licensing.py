"""Licence client: sign in once, keep a signed token, refresh it daily, report usage minutes.

The token is signed by the server (Ed25519); the app verifies it offline with the bundled public key
(assets/license_public.pem). Without a refresh the app keeps working until the token's `expires`
time (7 days), then asks the user to go online and sign in again.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import socket
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization

def _default_server() -> str:
    if os.environ.get("NOMSINDO_SERVER"):
        return os.environ["NOMSINDO_SERVER"]
    for base in (getattr(__import__("sys"), "_MEIPASS", None), str(Path(__file__).resolve().parent.parent)):
        f = Path(base) / "assets" / "server.txt" if base else None
        if f and f.exists():
            return f.read_text().strip()
    return ""


DEFAULT_SERVER = _default_server()


def _public_key():
    for base in (getattr(__import__("sys"), "_MEIPASS", None), str(Path(__file__).resolve().parent.parent)):
        if base and (Path(base) / "assets" / "license_public.pem").exists():
            return serialization.load_pem_public_key((Path(base) / "assets" / "license_public.pem").read_bytes())
    return None


def verify_token(token: str, public_key=None) -> dict | None:
    pk = public_key or _public_key()
    if pk is None:
        return None
    try:
        body, sig = token.split(".", 1)
        pad = lambda s: s + "=" * (-len(s) % 4)
        pk.verify(base64.urlsafe_b64decode(pad(sig)), body.encode())
        return json.loads(base64.urlsafe_b64decode(pad(body)))
    except (ValueError, InvalidSignature, json.JSONDecodeError):
        return None


def device_hash() -> str:
    """Stable, non-reversible machine identifier."""
    raw = ""
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0,
                           winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0))
        raw = winreg.QueryValueEx(k, "MachineGuid")[0]
    except Exception:
        raw = f"{uuid.getnode()}-{platform.node()}"
    return hashlib.sha256(("nomsindo|" + raw).encode()).hexdigest()[:40]


def store_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    d = Path(base) / "NoMsindo"
    d.mkdir(parents=True, exist_ok=True)
    return d / "licence.json"


class LicenceError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass
class State:
    status: str            # "ok" | "needs_signin" | "expired" | "unconfigured"
    message: str = ""
    org_name: str = ""
    email: str = ""
    plan: str = ""
    days_left: int = 0
    needs_refresh: bool = False


class LicenceClient:
    def __init__(self, server: str = "", path: Path | None = None, public_key=None, transport=None):
        self.path = path or store_path()
        self.public_key = public_key
        self._post = transport or self._http_post
        self._data = self._load()
        self.server = (server or self._data.get("server") or DEFAULT_SERVER).rstrip("/")

    # ---- storage
    def _load(self) -> dict:
        try:
            return json.loads(self.path.read_text())
        except Exception:
            return {}

    def _save(self) -> None:
        self.path.write_text(json.dumps(self._data))

    # ---- http
    def _http_post(self, url: str, body: dict, token: str | None = None) -> tuple[int, dict]:
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json",
                                              **({"Authorization": f"Bearer {token}"} if token else {})})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or b"{}")
            except Exception:
                return e.code, {"error": "http_error", "message": f"Server error {e.code}"}
        except (urllib.error.URLError, socket.timeout, OSError) as e:
            raise LicenceError("offline", "Can't reach the licence server. Check your internet connection.") from e

    # ---- state
    def state(self) -> State:
        if self.public_key is None and _public_key() is None:
            return State("unconfigured", "This build has no licence key (assets/license_public.pem).")
        tok = self._data.get("token")
        p = verify_token(tok, self.public_key) if tok else None
        if not p:
            return State("needs_signin", "Sign in to activate NoMsindo.")
        now = time.time()
        days = max(0, int((p["licence_until"] - now) // 86400))
        if now > p["licence_until"]:
            return State("expired", "Your organisation's trial or subscription has ended.", p["org_name"], p["email"], p["plan"], 0)
        if now > p["expires"]:
            return State("needs_signin", "Licence check needed. Connect to the internet and sign in again.",
                         p["org_name"], p["email"], p["plan"], days)
        return State("ok", "", p["org_name"], p["email"], p["plan"], days, needs_refresh=now > p["refresh_after"])

    # ---- actions
    def _accept(self, d: dict) -> None:
        self._data.update(token=d["token"], server=self.server)
        self._save()

    def sign_in(self, server: str, email: str, password: str) -> State:
        self.server = server.strip().rstrip("/")
        if not self.server.startswith(("https://", "http://localhost", "http://127.0.0.1")):
            raise LicenceError("insecure_server", "The server address must start with https://")
        code, d = self._post(f"{self.server}/api/v1/activate",
                             {"email": email, "password": password, "device_hash": device_hash(),
                              "device_name": platform.node()[:60]})
        if code != 200:
            raise LicenceError(d.get("error", "error"), d.get("message", "Sign-in failed."))
        self._accept(d)
        return self.state()

    def refresh(self) -> State:
        tok = self._data.get("token")
        if not tok:
            return self.state()
        code, d = self._post(f"{self.server}/api/v1/refresh", {"token": tok})
        if code == 200:
            self._accept(d)
        elif d.get("error") in ("device_revoked", "account_disabled", "invalid_token", "token_expired"):
            self._data.pop("token", None); self._save()      # server says no: sign out locally
        elif d.get("error") == "licence_expired":
            pass                                              # keep token; state() reports expiry
        return self.state()

    def report_usage(self, mic_seconds: int, speaker_seconds: int) -> bool:
        tok = self._data.get("token")
        if not tok or (mic_seconds <= 0 and speaker_seconds <= 0):
            return False
        try:
            code, _ = self._post(f"{self.server}/api/v1/usage",
                                 {"mic_seconds": int(mic_seconds), "speaker_seconds": int(speaker_seconds)}, token=tok)
            return code == 200
        except LicenceError:
            return False

    def sign_out(self) -> None:
        tok = self._data.get("token")
        if tok:
            try:
                self._post(f"{self.server}/api/v1/deactivate", {}, token=tok)
            except LicenceError:
                pass
        self._data.pop("token", None); self._save()
