"""JSON API used by the desktop app."""
from __future__ import annotations

import time
from datetime import date

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config, licensing
from .models import AuditLog, Device, Org, UsageDaily, User, utcnow
from .security import RateLimiter, verify_password

router = APIRouter(prefix="/api/v1")
limiter = RateLimiter(limit=8, window=900)


def get_db(request: Request):
    db = request.app.state.SessionLocal()
    try:
        yield db
    finally:
        db.close()


def err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": code, "message": message})


class ActivateIn(BaseModel):
    email: str
    password: str
    device_hash: str = Field(min_length=8, max_length=128)
    device_name: str = Field(default="", max_length=200)


class RefreshIn(BaseModel):
    token: str


class UsageIn(BaseModel):
    day: date | None = None
    mic_seconds: int = Field(default=0, ge=0, le=86400)
    speaker_seconds: int = Field(default=0, ge=0, le=86400)


def _check_state(db: Session, user: User | None, device: Device | None):
    if user is None or not user.active:
        return err(403, "account_disabled", "This account is disabled. Contact your administrator.")
    if device is not None and device.revoked:
        return err(403, "device_revoked", "This device was removed by your administrator.")
    if not user.org.is_licensed:
        return err(402, "licence_expired", "Your organisation's trial or subscription has ended.")
    return None


@router.post("/activate")
def activate(body: ActivateIn, request: Request, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    key = f"{request.client.host if request.client else '?'}|{email}"
    if limiter.blocked(key):
        return err(429, "too_many_attempts", "Too many failed attempts. Try again in 15 minutes.")
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(body.password, user.password_hash):
        limiter.fail(key)
        return err(401, "invalid_credentials", "Email or password is incorrect.")
    limiter.reset(key)
    device = db.scalar(select(Device).where(Device.user_id == user.id, Device.device_hash == body.device_hash))
    bad = _check_state(db, user, device)
    if bad:
        return bad
    if device is not None and device.released:
        n = len(db.scalars(select(Device).where(Device.user_id == user.id, Device.revoked.is_(False),
                                                Device.released.is_(False))).all())
        if n >= config.MAX_DEVICES_PER_USER:
            return err(403, "device_limit", "This account is already active on the maximum number of devices.")
        device.released = False
    if device is None:
        n = len(db.scalars(select(Device).where(Device.user_id == user.id, Device.revoked.is_(False),
                                                Device.released.is_(False))).all())
        if n >= config.MAX_DEVICES_PER_USER:
            return err(403, "device_limit", f"This account is already active on {config.MAX_DEVICES_PER_USER} devices. "
                       "Ask your administrator to remove one.")
        device = Device(org_id=user.org_id, user_id=user.id, device_hash=body.device_hash, name=body.device_name)
        db.add(device)
        db.add(AuditLog(org_id=user.org_id, actor=user.email, action="device.activate", detail=body.device_name))
    device.last_seen = utcnow()
    user.last_login = utcnow()
    db.commit()
    db.refresh(device)
    token, payload = licensing.issue(request.app.state.private_key, user.org, user, device)
    return {"token": token, **_public(payload)}


def _public(p: dict) -> dict:
    return {k: p[k] for k in ("org_name", "email", "plan", "licence_until", "refresh_after", "expires")}


def _auth(db: Session, request: Request, token: str):
    payload = licensing.verify(token, request.app.state.private_key.public_key())
    if not payload:
        return None, None, None, err(401, "invalid_token", "Licence token is not valid.")
    if payload["expires"] < time.time():
        return None, None, None, err(401, "token_expired", "Licence token expired. Sign in again.")
    user = db.get(User, payload["user_id"])
    device = db.scalar(select(Device).where(Device.user_id == payload["user_id"],
                                            Device.device_hash == payload["device"]))
    if device is None or device.released:
        return None, None, None, err(403, "device_revoked", "This device is no longer registered.")
    bad = _check_state(db, user, device)
    return user, device, payload, bad


@router.post("/refresh")
def refresh(body: RefreshIn, request: Request, db: Session = Depends(get_db)):
    user, device, _, bad = _auth(db, request, body.token)
    if bad:
        return bad
    device.last_seen = utcnow()
    db.commit()
    token, payload = licensing.issue(request.app.state.private_key, user.org, user, device)
    return {"token": token, **_public(payload)}


def _bearer(authorization: str | None) -> str:
    return (authorization or "").removeprefix("Bearer ").strip()


@router.post("/usage")
def usage(body: UsageIn, request: Request, authorization: str | None = Header(default=None),
          db: Session = Depends(get_db)):
    user, device, _, bad = _auth(db, request, _bearer(authorization))
    if bad:
        return bad
    day = body.day or utcnow().date()
    row = db.scalar(select(UsageDaily).where(UsageDaily.device_id == device.id, UsageDaily.day == day))
    if row is None:
        row = UsageDaily(org_id=user.org_id, user_id=user.id, device_id=device.id, day=day,
                         mic_seconds=0, speaker_seconds=0)
        db.add(row)
    row.mic_seconds = min(86400, (row.mic_seconds or 0) + body.mic_seconds)
    row.speaker_seconds = min(86400, (row.speaker_seconds or 0) + body.speaker_seconds)
    device.last_seen = utcnow()
    db.commit()
    return {"ok": True}


@router.post("/deactivate")
def deactivate(request: Request, authorization: str | None = Header(default=None),
               db: Session = Depends(get_db)):
    user, device, _, bad = _auth(db, request, _bearer(authorization))
    if bad:
        return bad
    db.add(AuditLog(org_id=user.org_id, actor=user.email, action="device.deactivate", detail=device.name))
    device.released = True  # frees the device slot; usage history is kept
    db.commit()
    return {"ok": True}
