from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOG_NAME = "abie_gpt"


def configure_logging(log_dir: Path) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "abie-gpt.log"
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    if not any(isinstance(h, RotatingFileHandler) and getattr(h, "baseFilename", "") == str(path)
               for h in logger.handlers):
        handler = RotatingFileHandler(path, maxBytes=5 * 1024 * 1024, backupCount=5,
                                      encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        ))
        logger.addHandler(handler)
    return path


def tail_log(path: Path, lines: int = 100) -> str:
    lines = max(1, min(lines, 1000))
    if not path.exists():
        return "Лог пока пуст."
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        tail = stream.readlines()[-lines:]
    return "".join(tail).strip() or "Лог пока пуст."
