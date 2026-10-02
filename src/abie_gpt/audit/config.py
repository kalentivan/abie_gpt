from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True, slots=True)
class WorkerConfig:
    id: str
    enabled: bool
    target: str
    initial_prompt_file: Path
    continuation_prompt_file: Path
    max_iterations: int
    completion_markers: tuple[str, ...]

    @classmethod
    def parse(cls, worker_id: str, raw: dict[str, Any]) -> "WorkerConfig":
        maximum = int(raw.get("max_iterations", 20))
        if maximum < 1:
            raise ValueError(f"{worker_id}: max_iterations must be positive")
        return cls(
            id=worker_id,
            enabled=bool(raw.get("enabled", True)),
            target=str(raw.get("target", worker_id)),
            initial_prompt_file=Path(raw["initial_prompt_file"]),
            continuation_prompt_file=Path(raw["continuation_prompt_file"]),
            max_iterations=maximum,
            completion_markers=tuple(raw.get("completion_markers", ("СТОП АУДИТ",))),
        )


def load_workers(path: Path) -> dict[str, WorkerConfig]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if payload.get("version") != 1:
        raise ValueError("Unsupported worker config version")
    raw = payload.get("workers")
    if not isinstance(raw, dict):
        raise ValueError("workers must be a mapping")
    return {worker_id: WorkerConfig.parse(worker_id, item) for worker_id, item in raw.items()}
