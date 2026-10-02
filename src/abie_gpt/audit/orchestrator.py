from __future__ import annotations

import time
from pathlib import Path

from abie_gpt.chatgpt import ChatGPTHandler
from abie_gpt.storage import Database
from .config import load_workers
from .runner import AuditWorker


class AuditOrchestrator:
    """Config-driven sequential worker flow with persistent checkpoints."""

    def __init__(self, config_path: Path, chatgpt: ChatGPTHandler, database: Database, poll_interval: int):
        self.config_path = config_path
        self.chatgpt = chatgpt
        self.database = database
        self.poll_interval = poll_interval
        self.stopping = False

    def run_forever(self) -> None:
        while not self.stopping:
            workers = load_workers(self.config_path)
            for config in workers.values():
                if self.stopping:
                    break
                if not config.enabled:
                    continue
                self.database.save_worker_state(config.id, "running", 0, None, None, False)
                try:
                    result = AuditWorker(config, self.chatgpt).run()
                    chat = self.chatgpt.current_chat()
                    self.database.save_worker_state(
                        config.id,
                        "completed" if result.completed else "limit_reached",
                        result.iterations,
                        chat.id,
                        result.last_response,
                        result.completed,
                    )
                except Exception as exc:
                    self.database.save_worker_state(config.id, "failed", 0, None, str(exc), False)
            time.sleep(self.poll_interval)

    def stop(self) -> None:
        self.stopping = True
