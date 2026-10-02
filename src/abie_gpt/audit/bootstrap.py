from __future__ import annotations

import os
import signal
from pathlib import Path

from abie_gpt.chatgpt import ChatGPTHandler
from abie_gpt.core.config import Settings
from abie_gpt.storage import Database
from .orchestrator import AuditOrchestrator


def main() -> None:
    settings = Settings.from_env(require_max_token=False)
    database = Database(settings.database_url)
    database.create_schema()
    chatgpt = ChatGPTHandler(settings)
    chatgpt.start()
    orchestrator = AuditOrchestrator(
        Path(os.getenv("WORKERS_CONFIG", "config/workers.yaml")),
        chatgpt,
        database,
        int(os.getenv("WORKER_POLL_INTERVAL", "30")),
    )
    signal.signal(signal.SIGTERM, lambda *_: orchestrator.stop())
    signal.signal(signal.SIGINT, lambda *_: orchestrator.stop())
    try:
        orchestrator.run_forever()
    finally:
        chatgpt.close()
