"""HTML admin portal."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import config
from .api import get_db
from .models import AuditLog, Device, Org, UsageDaily, User, utcnow
from .security import (RateLimiter, check_csrf, csrf_token, hash_password, password_problem,
                       verify_password)

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
login_limiter = RateLimiter(limit=8, window=900)


class NeedLogin(Exception):
    pass


def current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    uid = request.session.get("uid")
    u = db.get(User, uid) if uid else None
    return u if u and u.active else None


def require_user(user: User | None = Depends(current_user)) -> User:
    if user is None:
        raise NeedLogin()
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "Administrator access required.")
    return user


def require_platform(user: User = Depends(require_user)) -> User:
    if not user.is_platform_admin:
        raise HTTPException(403, "Platform administrator access required.")
    return user


def render(request: Request, name: str, user: User | None = None, status: int = 200, **ctx):
    flash = request.session.pop("flash", None)
    ctx.update(user=user, csrf=csrf_token(request), flash=flash, config=config)
    return templates.TemplateResponse(request, name, ctx, status_code=status)


def flash(request: Request, kind: str, msg: str) -> None:
    request.session["flash"] = {"kind": kind, "msg": msg}


def audit(db: Session, org_id, actor: User, action: str, detail: str = "") -> None:
    db.add(AuditLog(org_id=org_id, actor=actor.email, action=action, detail=detail))


def go(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)


def _seats_used(db: Session, org_id: int) -> int:
    return db.scalar(select(func.count()).select_from(User).where(User.org_id == org_id, User.active.is_(True))) or 0


# ---------- auth ----------
@router.get("/login")
def login_page(request: Request, user: User | None = Depends(current_user)):
    if user:
        return go("/")
    return render(request, "login.html")


@router.post("/login")
def login(request: Request, email: str = Form(""), password: str = Form(""), csrf: str = Form(""),
          db: Session = Depends(get_db)):
    check_csrf(request, csrf)
    email = email.strip().lower()
    key = f"{request.client.host if request.client else '?'}|{email}"
    if login_limiter.blocked(key):
        return render(request, "login.html", status=429, error="Too many failed attempts. Try again in 15 minutes.")
    u = db.scalar(select(User).where(User.email == email))
    if not u or not u.active or not verify_password(password, u.password_hash):
        login_limiter.fail(key)
        return render(request, "login.html", status=401, error="Email or password is incorrect.", email=email)
    login_limiter.reset(key)
    request.session.clear()
    request.session["uid"] = u.id
    u.last_login = utcnow()
    db.commit()
    return go("/")


@router.post("/logout")
def logout(request: Request, csrf: str = Form("")):
    check_csrf(request, csrf)
    request.session.clear()
    return go("/login")


@router.get("/signup")
def signup_page(request: Request):
    return render(request, "signup.html")


@router.post("/signup")
def signup(request: Request, org_name: str = Form(""), email: str = Form(""), password: str = Form(""),
           csrf: str = Form(""), db: Session = Depends(get_db)):
    check_csrf(request, csrf)
    email, org_name = email.strip().lower(), org_name.strip()
    problem = (None if org_name else "Organisation name is required.") or \
        (None if "@" in email and "." in email.split("@")[-1] else "Enter a valid email address.") or \
        password_problem(password)
    if not problem and db.scalar(select(User).where(User.email == email)):
        problem = "An account with this email already exists."
    if problem:
        return render(request, "signup.html", status=400, error=problem, email=email, org_name=org_name)
    org = Org(name=org_name, seats=config.TRIAL_SEATS, trial_ends_at=utcnow() + timedelta(days=config.TRIAL_DAYS))
    db.add(org)
    db.flush()
    u = User(org_id=org.id, email=email, password_hash=hash_password(password), role="owner")
    db.add(u)
    db.add(AuditLog(org_id=org.id, actor=email, action="org.signup", detail=org_name))
    db.commit()
    request.session.clear()
    request.session["uid"] = u.id
    flash(request, "ok", f"Welcome! Your {config.TRIAL_DAYS}-day free trial with {config.TRIAL_SEATS} seats has started.")
    return go("/")


# ---------- dashboard ----------
def _series(db: Session, org_id: int, days: int):
    start = utcnow().date() - timedelta(days=days - 1)
    rows = db.execute(select(UsageDaily.day, func.sum(UsageDaily.mic_seconds + UsageDaily.speaker_seconds))
                      .where(UsageDaily.org_id == org_id, UsageDaily.day >= start).group_by(UsageDaily.day)).all()
    m = {d: int(s or 0) // 60 for d, s in rows}
    return [{"day": start + timedelta(days=i), "minutes": m.get(start + timedelta(days=i), 0)} for i in range(days)]


@router.get("/")
def dashboard(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    if not user.is_admin:
        return go("/account")
    org = user.org
    series = _series(db, org.id, 14)
    total30 = sum(x["minutes"] for x in _series(db, org.id, 30))
    devices = db.scalar(select(func.count()).select_from(Device).where(
        Device.org_id == org.id, Device.revoked.is_(False), Device.released.is_(False))) or 0
    recent = db.scalars(select(AuditLog).where(AuditLog.org_id == org.id).order_by(AuditLog.id.desc()).limit(10)).all()
    return render(request, "dashboard.html", user, org=org, series=series, max_min=max([x["minutes"] for x in series] + [1]),
                  total30=total30, seats_used=_seats_used(db, org.id), devices=devices, recent=recent, page="dashboard")


# ---------- users ----------
@router.get("/users")
def users_page(request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.scalars(select(User).where(User.org_id == user.org_id).order_by(User.email)).all()
    return render(request, "users.html", user, users=users, org=user.org, seats_used=_seats_used(db, user.org_id), page="users")


@router.post("/users")
def users_add(request: Request, email: str = Form(""), password: str = Form(""), role: str = Form("agent"),
              csrf: str = Form(""), user: User = Depends(require_admin), db: Session = Depends(get_db)):
    check_csrf(request, csrf)
    email = email.strip().lower()
    role = role if role in ("agent", "admin") else "agent"
    problem = (None if "@" in email and "." in email.split("@")[-1] else "Enter a valid email address.") or \
        password_problem(password)
    if not problem and db.scalar(select(User).where(User.email == email)):
        problem = "A user with this email already exists."
    if not problem and _seats_used(db, user.org_id) >= user.org.seats:
        problem = f"All {user.org.seats} seats are in use. Deactivate a user or ask for more seats."
    if problem:
        flash(request, "err", problem)
        return go("/users")
    db.add(User(org_id=user.org_id, email=email, password_hash=hash_password(password), role=role))
    audit(db, user.org_id, user, "user.add", f"{email} ({role})")
    db.commit()
    flash(request, "ok", f"Added {email}. Give them the password you set; they sign in to the NoMsindo app with it.")
    return go("/users")


def _own_user(db: Session, admin: User, uid: int) -> User:
    t = db.get(User, uid)
    if not t or t.org_id != admin.org_id:   # tenant isolation
        raise HTTPException(404, "User not found.")
    return t


@router.post("/users/{uid}/toggle")
def users_toggle(uid: int, request: Request, csrf: str = Form(""), user: User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    check_csrf(request, csrf)
    t = _own_user(db, user, uid)
    if t.id == user.id or t.role == "owner":
        flash(request, "err", "You can't deactivate yourself or the owner.")
        return go("/users")
    if not t.active and _seats_used(db, user.org_id) >= user.org.seats:
        flash(request, "err", "No free seats to reactivate this user.")
        return go("/users")
    t.active = not t.active
    audit(db, user.org_id, user, "user.activate" if t.active else "user.deactivate", t.email)
    db.commit()
    return go("/users")


@router.post("/users/{uid}/reset")
def users_reset(uid: int, request: Request, password: str = Form(""), csrf: str = Form(""),
                user: User = Depends(require_admin), db: Session = Depends(get_db)):
    check_csrf(request, csrf)
    t = _own_user(db, user, uid)
    problem = password_problem(password)
    if problem:
        flash(request, "err", problem)
    else:
        t.password_hash = hash_password(password)
        audit(db, user.org_id, user, "user.reset_password", t.email)
        db.commit()
        flash(request, "ok", f"Password reset for {t.email}.")
    return go("/users")


# ---------- devices ----------
@router.get("/devices")
def devices_page(request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    devs = db.scalars(select(Device).where(Device.org_id == user.org_id, Device.released.is_(False))
                      .order_by(Device.last_seen.desc())).all()
    return render(request, "devices.html", user, devices=devs, page="devices", max_devices=config.MAX_DEVICES_PER_USER)


@router.post("/devices/{did}/revoke")
def devices_revoke(did: int, request: Request, csrf: str = Form(""), user: User = Depends(require_admin),
                   db: Session = Depends(get_db)):
    check_csrf(request, csrf)
    d = db.get(Device, did)
    if not d or d.org_id != user.org_id:
        raise HTTPException(404, "Device not found.")
    d.revoked = True
    audit(db, user.org_id, user, "device.revoke", f"{d.user.email} / {d.name}")
    db.commit()
    flash(request, "ok", "Device removed. The app stops working on it at its next licence check (within 24 hours).")
    return go("/devices")


# ---------- usage ----------
@router.get("/usage")
def usage_page(request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    start = utcnow().date() - timedelta(days=29)
    rows = db.execute(
        select(User.email, func.coalesce(func.sum(UsageDaily.mic_seconds), 0), func.coalesce(func.sum(UsageDaily.speaker_seconds), 0),
               func.count(func.distinct(UsageDaily.day)))
        .join(UsageDaily, (UsageDaily.user_id == User.id) & (UsageDaily.day >= start), isouter=True)
        .where(User.org_id == user.org_id).group_by(User.id, User.email).order_by(User.email)).all()
    table = [{"email": e, "mic": int(m) // 60, "speaker": int(s) // 60, "days": d if (m or s) else 0} for e, m, s, d in rows]
    return render(request, "usage.html", user, table=table, page="usage",
                  total_mic=sum(r["mic"] for r in table), total_spk=sum(r["speaker"] for r in table))


# ---------- my account ----------
@router.get("/account")
def account(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    devs = db.scalars(select(Device).where(Device.user_id == user.id, Device.released.is_(False))).all()
    return render(request, "account.html", user, devices=devs, page="account", org=user.org)


@router.post("/account/password")
def account_password(request: Request, current: str = Form(""), new: str = Form(""), csrf: str = Form(""),
                     user: User = Depends(require_user), db: Session = Depends(get_db)):
    check_csrf(request, csrf)
    if not verify_password(current, user.password_hash):
        flash(request, "err", "Current password is incorrect.")
    elif password_problem(new):
        flash(request, "err", password_problem(new))
    else:
        user.password_hash = hash_password(new)
        audit(db, user.org_id, user, "user.change_password", user.email)
        db.commit()
        flash(request, "ok", "Password changed.")
    return go("/account")


# ---------- platform (Thee Landlord staff) ----------
@router.get("/platform")
def platform_orgs(request: Request, user: User = Depends(require_platform), db: Session = Depends(get_db)):
    orgs = db.scalars(select(Org).order_by(Org.id.desc())).all()
    used = {o.id: _seats_used(db, o.id) for o in orgs}
    return render(request, "platform_orgs.html", user, orgs=orgs, used=used, page="platform")


@router.post("/platform/orgs/{oid}")
def platform_update(oid: int, request: Request, seats: int = Form(...), paid_until: str = Form(""),
                    csrf: str = Form(""), user: User = Depends(require_platform), db: Session = Depends(get_db)):
    check_csrf(request, csrf)
    o = db.get(Org, oid)
    if not o:
        raise HTTPException(404, "Organisation not found.")
    if seats < 1 or seats > 100000:
        flash(request, "err", "Seats must be between 1 and 100000.")
        return go("/platform")
    try:
        pu = datetime.combine(date.fromisoformat(paid_until), datetime.max.time()).replace(microsecond=0) if paid_until else None
    except ValueError:
        flash(request, "err", "Paid-until must be a date like 2027-03-31.")
        return go("/platform")
    o.seats, o.paid_until = seats, pu
    audit(db, o.id, user, "platform.update_org", f"seats={seats} paid_until={paid_until or '-'}")
    db.commit()
    flash(request, "ok", f"Updated {o.name}.")
    return go("/platform")
