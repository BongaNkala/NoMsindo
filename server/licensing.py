"""Signed licence tokens (Ed25519). Format: base64url(json payload) + '.' + base64url(signature)."""
from __future__ import annotations

import base64
import calendar
import json
import time
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from . import config


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def load_or_create_private_key(data_dir: Path) -> Ed25519PrivateKey:
    f = data_dir / "license_private.pem"
    if f.exists():
        return serialization.load_pem_private_key(f.read_bytes(), password=None)
    key = Ed25519PrivateKey.generate()
    f.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption()))
    try:
        f.chmod(0o600)
    except OSError:
        pass
    return key


def public_pem(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(serialization.Encoding.PEM,
                                         serialization.PublicFormat.SubjectPublicKeyInfo)


def issue(key: Ed25519PrivateKey, org, user, device) -> tuple[str, dict]:
    now = int(time.time())
    payload = {
        "v": 1, "org_id": org.id, "org_name": org.name, "user_id": user.id, "email": user.email,
        "device": device.device_hash, "plan": org.plan,
        "licence_until": calendar.timegm(org.licence_until.timetuple()),
        "issued": now, "refresh_after": now + config.TOKEN_REFRESH_HOURS * 3600,
        "expires": now + config.TOKEN_EXPIRES_DAYS * 86400,
    }
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    return body + "." + _b64(key.sign(body.encode())), payload


def verify(token: str, public_key: Ed25519PublicKey) -> dict | None:
    try:
        body, sig = token.split(".", 1)
        public_key.verify(_unb64(sig), body.encode())
        return json.loads(_unb64(body))
    except (ValueError, InvalidSignature, json.JSONDecodeError):
        return None
