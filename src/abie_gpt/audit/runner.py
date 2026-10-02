from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from abie_gpt.chatgpt import ChatGPTHandler
from .config import WorkerConfig


@dataclass(frozen=True, slots=True)
class AuditResult:
    worker_id: str
    iterations: int
    completed: bool
    last_response: str


class AuditWorker:
    """Runs one config-defined audit using the shared ChatGPT adapter."""

    def __init__(self, config: WorkerConfig, chatgpt: ChatGPTHandler):
        self.config = config
        self.chatgpt = chatgpt

    def run(self) -> AuditResult:
        if not self.config.enabled:
            return AuditResult(self.config.id, 0, False, "")
        initial = self._prompt(self.config.initial_prompt_file)
        continuation = self._prompt(self.config.continuation_prompt_file)
        self.chatgpt.new_chat()
        response = self.chatgpt.send_and_wait(initial).text
        iterations = 1
        while iterations < self.config.max_iterations and not self._complete(response):
            response = self.chatgpt.send_and_wait(continuation).text
            iterations += 1
        return AuditResult(self.config.id, iterations, self._complete(response), response)

    def _complete(self, response: str) -> bool:
        upper = response.upper()
        return any(marker.upper() in upper for marker in self.config.completion_markers)

    def _prompt(self, path: Path) -> str:
        return path.read_text(encoding="utf-8").replace("{MICROSERVICE}", self.config.target)
