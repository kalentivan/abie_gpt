from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    max_bot_token: str
    brave_path: str
    browser_profile: str
    screenshot_dir: Path
    gpt_timeout: int = 900
    max_message_length: int = 3900

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.getenv("MAX_BOT_TOKEN", "").strip()
        brave = os.getenv("BRAVE_PATH", "").strip()
        profile = os.getenv("BOT_PROFILE", "").strip()
        missing = [name for name, value in {
            "MAX_BOT_TOKEN": token, "BRAVE_PATH": brave, "BOT_PROFILE": profile
        }.items() if not value]
        if missing:
            raise RuntimeError("Missing required settings: " + ", ".join(missing))
        screenshot_dir = Path(os.getenv("SCREENSHOT_DIR", "./var/screenshots")).resolve()
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        return cls(
            max_bot_token=token,
            brave_path=brave,
            browser_profile=profile,
            screenshot_dir=screenshot_dir,
            gpt_timeout=int(os.getenv("GPT_TIMEOUT", "900")),
            max_message_length=int(os.getenv("MAX_MESSAGE_LENGTH", "3900")),
        )
