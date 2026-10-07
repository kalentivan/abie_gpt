import mimetypes
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests

from config import settings
from .commands import ParsedCommand
from .models import HttpResult


class AbieHttpExecutor:
    """Restricted HTTP executor for ABIE and Loki."""

    def __init__(self) -> None:
        self.output_dir = settings.abie_http_output_dir.resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _base_url(self, target: str) -> str:
        value = settings.abie_api_url if target == "ABIE" else settings.loki_url
        if not value:
            raise RuntimeError(f"{target}_URL не настроен в .env")
        return value.rstrip("/") + "/"

    def _headers(self, target: str) -> dict[str, str]:
        headers = {"Accept": "*/*"}
        token = settings.abie_api_token if target == "ABIE" else settings.loki_token
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    @staticmethod
    def _safe_url(base_url: str, path: str) -> str:
        if not path.startswith("/") or path.startswith("//") or "://" in path:
            raise ValueError("Разрешён только относительный HTTP path, начинающийся с /")
        return urljoin(base_url, path.lstrip("/"))

    @staticmethod
    def _extension(content_type: str) -> str:
        media_type = content_type.split(";", 1)[0].strip().lower()
        if media_type in {"application/json", "application/problem+json"} or media_type.endswith("+json"):
            return ".txt"
        if media_type.startswith("text/") or not media_type:
            return ".txt"
        if media_type == "application/zip":
            return ".zip"
        return mimetypes.guess_extension(media_type) or ".bin"

    @staticmethod
    def _slug(path: str) -> str:
        value = path.split("?", 1)[0].strip("/") or "root"
        return re.sub(r"[^A-Za-z0-9._-]+", "_", value)[-80:]

    def execute(self, command: ParsedCommand) -> HttpResult:
        base_url = self._base_url(command.target)
        url = self._safe_url(base_url, command.path)
        timeout = settings.abie_api_timeout if command.target == "ABIE" else settings.loki_timeout
        started = time.monotonic()

        with requests.request(
            command.method,
            url,
            json=command.body,
            headers={"Accept": "*/*"},
            timeout=timeout,
            stream=True,
            allow_redirects=False,
        ) as response:
            content_type = response.headers.get("content-type", "")
            extension = self._extension(content_type)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            name = f"{command.target.lower()}_{stamp}_{command.method}_{self._slug(command.path)}{extension}"
            target = self.output_dir / name
            size = 0
            max_size = settings.abie_max_response_bytes

            with target.open("wb") as output:
                if extension == ".txt":
                    header = (
                        f"Timestamp: {datetime.now().astimezone().isoformat()}\n"
                        f"Target: {command.target}\n"
                        f"Method: {command.method}\n"
                        f"Path: {command.path}\n"
                        f"Status: {response.status_code}\n"
                        f"Content-Type: {content_type}\n"
                        f"\n--- RESPONSE ---\n\n"
                    ).encode("utf-8")
                    output.write(header)
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    size += len(chunk)
                    if size > max_size:
                        output.close()
                        target.unlink(missing_ok=True)
                        raise RuntimeError(
                            f"HTTP-ответ превышает лимит {max_size} байт"
                        )
                    output.write(chunk)

            duration = time.monotonic() - started
            return HttpResult(
                target=command.target,
                method=command.method,
                path=command.path,
                status_code=response.status_code,
                content_type=content_type,
                size=size,
                duration_seconds=duration,
                file_path=target,
            )

    def openapi_command(self) -> ParsedCommand:
        path = settings.abie_openapi_path.strip()
        if not path:
            raise RuntimeError("ABIE_OPENAPI_PATH не настроен в .env")
        if not path.startswith("/"):
            path = "/" + path
        return ParsedCommand(
            target="ABIE",
            method="GET",
            path=path,
            body=None,
            continue_work=False,
            raw_command=f"ABIE GET {path}",
        )
