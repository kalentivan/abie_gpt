import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ServerResult:
    name: str
    command: str
    return_code: int
    size: int
    duration_seconds: float
    file_path: Path


# Commands are intentionally finite. ChatGPT chooses a command by name and
# supplies validated arguments; it never gets an unrestricted shell.
COMMANDS = {
    "pods": ["kubectl", "get", "pods", "-A", "-o", "wide"],
    "services": ["kubectl", "get", "svc", "-A", "-o", "wide"],
    "deployments": ["kubectl", "get", "deployments", "-A", "-o", "wide"],
    "events": ["kubectl", "get", "events", "-A", "--sort-by=.lastTimestamp"],
    "nodes": ["kubectl", "get", "nodes", "-o", "wide"],
    "pod-logs": ["kubectl", "logs", "-n", "{namespace}", "{pod}", "--tail={tail}"],
    "pod-logs-previous": [
        "kubectl", "logs", "-n", "{namespace}", "{pod}", "--previous", "--tail={tail}",
    ],
    "pod-describe": ["kubectl", "describe", "pod", "-n", "{namespace}", "{pod}"],
    "deployment-describe": [
        "kubectl", "describe", "deployment", "-n", "{namespace}", "{deployment}",
    ],
    "kind-clusters": ["kind", "get", "clusters"],
    "abie-services": [
        "systemctl", "list-units", "--type=service", "--all", "--no-pager",
        "--plain",
    ],
}

_ALLOWED_ARGS = {
    "namespace": set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."),
    "pod": set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."),
    "deployment": set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."),
}


class ServerCommandExecutor:
    def __init__(self, output_dir: Path, timeout: int = 120, max_bytes: int = 32 * 1024 * 1024):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.max_bytes = max_bytes

    @staticmethod
    def command_names() -> list[str]:
        return sorted(COMMANDS)

    def _validate(self, name: str, args: dict[str, str]) -> list[str]:
        if name not in COMMANDS:
            raise ValueError(f"Неизвестная SERVER-команда: {name}")

        template = COMMANDS[name]
        required = {
            token[1:-1]
            for token in template
            if token.startswith("{") and token.endswith("}")
        }
        if "tail" in " ".join(template):
            required.add("tail")

        if set(args) != required:
            raise ValueError(
                f"{name}: нужны аргументы {sorted(required)}, получены {sorted(args)}"
            )

        values = dict(args)
        for key in required - {"tail"}:
            value = values[key]
            if not value or any(ch not in _ALLOWED_ARGS[key] for ch in value):
                raise ValueError(f"Недопустимое значение {key}: {value!r}")

        if "tail" in required:
            try:
                tail = int(values["tail"])
            except (TypeError, ValueError):
                raise ValueError("tail должен быть целым числом") from None
            if not 1 <= tail <= 10000:
                raise ValueError("tail должен быть от 1 до 10000")
            values["tail"] = str(tail)

        return [token.format(**values) for token in template]

    def execute(self, name: str, args: dict[str, str]) -> ServerResult:
        command = self._validate(name, args)
        started = time.monotonic()
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=self.timeout,
            check=False,
        )
        payload = completed.stdout
        if len(payload) > self.max_bytes:
            raise RuntimeError(
                f"SERVER output превышает лимит {self.max_bytes} bytes"
            )

        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = self.output_dir / f"server-{name}-{stamp}.txt"
        header = (
            f"$ {shlex.join(command)}\n"
            f"exit_code={completed.returncode}\n\n"
        ).encode("utf-8")
        path.write_bytes(header + payload)
        return ServerResult(
            name=name,
            command=shlex.join(command),
            return_code=completed.returncode,
            size=len(payload),
            duration_seconds=time.monotonic() - started,
            file_path=path,
        )
