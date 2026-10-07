from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HttpResult:
    target: str
    method: str
    path: str
    status_code: int
    content_type: str
    size: int
    duration_seconds: float
    file_path: Path
