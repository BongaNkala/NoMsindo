from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


def _path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    d = Path(base) / "NoMsindo"
    d.mkdir(parents=True, exist_ok=True)
    return d / "settings.json"


@dataclass
class Channel:
    enabled: bool = False
    input_name: str = ""
    output_name: str = ""
    strength: int = 100   # percent
    mode: int = 1         # 1 standard, 2 strong


@dataclass
class Settings:
    mic: Channel = field(default_factory=Channel)
    speaker: Channel = field(default_factory=Channel)
    run_at_login: bool = False
    start_minimized: bool = False
    autostart_audio: bool = True
    close_to_tray: bool = True

    @classmethod
    def load(cls) -> "Settings":
        try:
            raw = json.loads(_path().read_text())
            top = {k: v for k, v in raw.items() if k not in ("mic", "speaker")}
            return cls(mic=Channel(**raw.get("mic", {})), speaker=Channel(**raw.get("speaker", {})), **top)
        except Exception:
            return cls()

    def save(self) -> None:
        _path().write_text(json.dumps(asdict(self), indent=2))
