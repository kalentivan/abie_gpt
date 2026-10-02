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
        values = {
            "MAX_BOT_TOKEN": os.getenv("MAX_BOT_TOKEN", "").strip(),
            "BRAVE_PATH": os.getenv("BRAVE_PATH", "").strip(),
            "BOT_PROFILE": os.getenv("BOT_PROFILE", "").strip(),
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise RuntimeError("Missing required settings: " + ", ".join(missing))
        screenshots = Path(os.getenv("SCREENSHOT_DIR", "./var/screenshots")).resolve()
        screenshots.mkdir(parents=True, exist_ok=True)
        return cls(
            max_bot_token=values["MAX_BOT_TOKEN"],
            brave_path=values["BRAVE_PATH"],
            browser_profile=values["BOT_PROFILE"],
            screenshot_dir=screenshots,
            gpt_timeout=int(os.getenv("GPT_TIMEOUT", "900")),
            max_message_length=int(os.getenv("MAX_MESSAGE_LENGTH", "3900")),
        )
