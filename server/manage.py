"""Server admin commands:
  python -m server.manage init                       create signing keys, write the app's public key
  python -m server.manage create-platform-admin EMAIL
  python -m server.manage run [--host H] [--port P]
"""
from __future__ import annotations

import argparse
import getpass
import sys
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from . import licensing
from .config import Settings
from .models import Org, User, utcnow
from .security import hash_password, password_problem

APP_KEY = Path(__file__).resolve().parent.parent / "assets" / "license_public.pem"


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    pa = sub.add_parser("create-platform-admin"); pa.add_argument("email")
    r = sub.add_parser("run"); r.add_argument("--host", default="127.0.0.1"); r.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()

    if a.cmd == "run":
        import uvicorn
        uvicorn.run("server.main:app_factory", factory=True, host=a.host, port=a.port)
        return

    from .main import create_app
    app = create_app()
    st: Settings = app.state.settings
    if a.cmd == "init":
        pem = licensing.public_pem(app.state.private_key)
        APP_KEY.write_bytes(pem)
        print(f"Signing key: {st.data_dir / 'license_private.pem'}  (KEEP SECRET, never commit it)")
        print(f"Public key written to {APP_KEY}. Commit it and rebuild the installer so the app can verify licences.")
        return
    if a.cmd == "create-platform-admin":
        email = a.email.strip().lower()
        pw = getpass.getpass("Password: ")
        if pw != getpass.getpass("Repeat password: "):
            sys.exit("Passwords differ.")
        if (p := password_problem(pw)):
            sys.exit(p)
        db = app.state.SessionLocal()
        if db.scalar(select(User).where(User.email == email)):
            sys.exit("That email already exists.")
        org = db.scalar(select(Org).where(Org.name == "Thee Landlord (platform)"))
        if not org:
            org = Org(name="Thee Landlord (platform)", seats=1000, trial_ends_at=utcnow() + timedelta(days=36500))
            db.add(org); db.flush()
        db.add(User(org_id=org.id, email=email, password_hash=hash_password(pw), role="owner", is_platform_admin=True))
        db.commit()
        print(f"Platform admin {email} created. Sign in at /login, then open /platform.")


if __name__ == "__main__":
    main()
