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
    database_url: str
    gpt_timeout: int = 900
    max_message_length: int = 3900

    @classmethod
    def from_env(cls, require_max_token: bool = True) -> "Settings":
        token = os.getenv("MAX_BOT_TOKEN", "").strip()
        brave = os.getenv("BRAVE_PATH", "").strip()
        profile = os.getenv("BOT_PROFILE", "").strip()
        required = {"BRAVE_PATH": brave, "BOT_PROFILE": profile}
        if require_max_token:
            required["MAX_BOT_TOKEN"] = token
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError("Missing required settings: " + ", ".join(missing))

        screenshots = Path(os.getenv("SCREENSHOT_DIR", "./var/screenshots")).resolve()
        screenshots.mkdir(parents=True, exist_ok=True)
        data_dir = Path(os.getenv("DATA_DIR", "./data")).resolve()
        data_dir.mkdir(parents=True, exist_ok=True)
        database_url = os.getenv("DATABASE_URL", f"sqlite:///{data_dir / 'abie_gpt.db'}")

        return cls(
            max_bot_token=token,
            brave_path=brave,
            browser_profile=profile,
            screenshot_dir=screenshots,
            database_url=database_url,
            gpt_timeout=int(os.getenv("GPT_TIMEOUT", "900")),
            max_message_length=int(os.getenv("MAX_MESSAGE_LENGTH", "3900")),
        )
