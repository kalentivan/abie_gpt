import json
import shlex
from dataclasses import dataclass
from typing import Any

CONTINUE_MARKER = "ПРОДОЛЖАЕМ РАБОТУ"
_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}

REQUEST_PROMPT = """Нужно выполнить HTTP-запрос к работающей ABIE.
Ответь ТОЛЬКО машинной командой, которую должен выполнить бот.

Форматы:
ABIE GET <relative-path>
ABIE POST <relative-path> <json-body>
ABIE PUT <relative-path> <json-body>
ABIE PATCH <relative-path> <json-body>
ABIE DELETE <relative-path>
LOKI GET <relative-path>

ABIE и LOKI принимают только относительный path, начиная с /.
Query-параметры передавай прямо в path.
Для POST/PUT/PATCH JSON body должен быть валидным JSON.

Если после результата этого запроса автоматически нужен следующий запрос,
добавь отдельной последней строкой:
ПРОДОЛЖАЕМ РАБОТУ

Не используй Markdown и не добавляй никаких пояснений."""


@dataclass(frozen=True)
class ParsedCommand:
    target: str
    method: str
    path: str
    body: Any | None
    continue_work: bool
    raw_command: str


def parse_command(text: str) -> ParsedCommand | None:
    """Parse a machine command returned by ChatGPT."""
    lines = [line.strip() for line in (text or "").strip().splitlines() if line.strip()]
    if not lines:
        return None

    continue_work = lines[-1].casefold() == CONTINUE_MARKER.casefold()
    if continue_work:
        lines.pop()
    if not lines:
        return None

    command_text = "\n".join(lines)
    try:
        parts = shlex.split(command_text, posix=False)
    except ValueError:
        return None
    if len(parts) < 3:
        return None

    target = parts[0].upper()
    method = parts[1].upper()
    if target not in {"ABIE", "LOKI"} or method not in _ALLOWED_METHODS:
        return None

    # Split the original command instead of rebuilding it with shlex so JSON
    # quotes remain intact.
    first = command_text.split(None, 2)
    remainder = first[2].strip()
    path_parts = remainder.split(None, 1)
    path = path_parts[0]
    if not path.startswith("/") or path.startswith("//") or "://" in path:
        return None

    body = None
    if len(path_parts) == 2:
        if method not in {"POST", "PUT", "PATCH"}:
            return None
        try:
            body = json.loads(path_parts[1])
        except json.JSONDecodeError:
            return None

    return ParsedCommand(
        target=target,
        method=method,
        path=path,
        body=body,
        continue_work=continue_work,
        raw_command=command_text,
    )
