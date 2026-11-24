from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

TRIAL_DAYS = 14
TRIAL_SEATS = 5
MAX_DEVICES_PER_USER = 2
TOKEN_REFRESH_HOURS = 24      # app should refresh after this
TOKEN_EXPIRES_DAYS = 7        # offline grace: app stops working after this without a refresh


@dataclass
class Settings:
    data_dir: Path
    database_url: str
    secret_key: str
    cookie_secure: bool

    @classmethod
    def load(cls, data_dir: str | Path | None = None, database_url: str | None = None) -> "Settings":
        d = Path(data_dir or os.environ.get("NOMSINDO_DATA", "server_data"))
        d.mkdir(parents=True, exist_ok=True)
        key = os.environ.get("SECRET_KEY")
        if not key:
            f = d / "secret.key"
            if not f.exists():
                f.write_text(secrets.token_urlsafe(48))
                try:
                    f.chmod(0o600)
                except OSError:
                    pass
            key = f.read_text().strip()
        return cls(d, database_url or os.environ.get("DATABASE_URL", f"sqlite:///{d / 'nomsindo.db'}"),
                   key, os.environ.get("COOKIE_SECURE", "0") == "1")
