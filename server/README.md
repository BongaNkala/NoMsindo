# NoMsindo licensing server and admin portal

FastAPI + SQLAlchemy. SQLite by default (fine for a pilot), PostgreSQL by setting `DATABASE_URL`.
Modules: accounts and orgs, 14-day trial, seats, devices (2 per user), signed licence tokens (Ed25519),
usage minutes, audit log, platform admin page for manual billing.

## First-time setup
```
pip install -r requirements-server.txt
python -m server.manage init                        # creates the signing key + writes assets/license_public.pem
python -m server.manage create-platform-admin you@thee-landlord.example
python -m server.manage run --host 0.0.0.0 --port 8000
```
Commit `assets/license_public.pem` (public) and rebuild the installer. **Never commit**
`server_data/license_private.pem`, `server_data/secret.key` or the database; they are in `.gitignore`.
Back up `server_data/` regularly: if the private key is lost, every installed app must be rebuilt.

## Production checklist
- Put it behind HTTPS (Caddy or nginx) and set `COOKIE_SECURE=1`. The app refuses non-HTTPS servers.
- Set the default server for installers: write the URL into `assets/server.txt` before building.
- `SECRET_KEY` (env) overrides the generated session secret; `DATABASE_URL` selects the database.
- Run one worker process: the login/activation rate limiter is in memory.

## How licensing works
1. Agent signs in to the app (email + password set by their admin) -> server returns a signed token.
2. The app verifies the token offline with the bundled public key, refreshes it every 24 hours, and
   keeps working offline for up to 7 days. Revoking a device or deactivating a user takes effect at the
   next refresh (within 24 hours). A finished trial/subscription stops the app at its next check.
3. The app reports minutes of audio cleaned (mic/speaker) every 5 minutes. No audio or call content is
   ever sent or stored.

## Not built yet
Payment gateway (billing is manual: set seats and paid-until on `/platform`), email (no invitations or
password-reset emails; admins set passwords), MFA, SSO, data export/delete tooling, hosted downloads page.
