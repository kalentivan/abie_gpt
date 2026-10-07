import json
import os
import shlex
import subprocess
import tempfile
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


DEFAULT_COMMANDS = {
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
        "systemctl", "list-units", "--type=service", "--all", "--no-pager", "--plain",
    ],
}

_ALLOWED_ARGS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_./:@")


class ServerCommandExecutor:
    def __init__(
        self,
        output_dir: Path,
        registry_path: Path,
        timeout: int = 120,
        max_bytes: int = 32 * 1024 * 1024,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.registry_path = Path(registry_path)
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.max_bytes = max_bytes

    def _custom(self) -> dict[str, list[str]]:
        if not self.registry_path.exists():
            return {}
        try:
            data = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return {
            str(name): [str(token) for token in command]
            for name, command in data.items()
            if isinstance(command, list) and command
        }

    def commands(self) -> dict[str, list[str]]:
        result = dict(DEFAULT_COMMANDS)
        result.update(self._custom())
        return result

    def command_names(self) -> list[str]:
        return sorted(self.commands())

    def registry_text(self) -> str:
        return json.dumps(self.commands(), ensure_ascii=False, indent=2)

    def add_command(self, name: str, command_text: str) -> None:
        name = name.strip()
        if not name or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in name):
            raise ValueError("Имя команды: только буквы, цифры, - и _")
        if name in DEFAULT_COMMANDS:
            raise ValueError("Встроенную SERVER-команду нельзя перезаписать")

        command = shlex.split(command_text)
        if not command:
            raise ValueError("Пустая команда")

        custom = self._custom()
        custom[name] = command
        fd, tmp_name = tempfile.mkstemp(
            prefix=self.registry_path.name + ".",
            suffix=".tmp",
            dir=self.registry_path.parent,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump(custom, output, ensure_ascii=False, indent=2)
                output.write("\n")
            os.replace(tmp_name, self.registry_path)
        finally:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass

    def _validate(self, name: str, args: dict[str, str]) -> list[str]:
        commands = self.commands()
        if name not in commands:
            raise ValueError(f"Неизвестная SERVER-команда: {name}")

        template = commands[name]
        required = set()
        for token in template:
            for part in token.split("{")[1:]:
                if "}" in part:
                    required.add(part.split("}", 1)[0])

        if set(args) != required:
            raise ValueError(
                f"{name}: нужны аргументы {sorted(required)}, получены {sorted(args)}"
            )

        values = dict(args)
        for key, value in values.items():
            if not value or any(ch not in _ALLOWED_ARGS for ch in value):
                raise ValueError(f"Недопустимое значение {key}: {value!r}")
            if key == "tail":
                try:
                    tail = int(value)
                except ValueError:
                    raise ValueError("tail должен быть целым числом") from None
                if not 1 <= tail <= 10000:
                    raise ValueError("tail должен быть от 1 до 10000")

        return [token.format(**values) for token in template]

    def _run(self, name: str, command: list[str]) -> ServerResult:
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
            raise RuntimeError(f"SERVER output превышает лимит {self.max_bytes} bytes")

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

    def execute(self, name: str, args: dict[str, str]) -> ServerResult:
        return self._run(name, self._validate(name, args))

    def execute_unrestricted(self, command_text: str) -> ServerResult:
        # This method is deliberately reachable only from the explicit MAX -U
        # command path. ChatGPT machine output never invokes it automatically.
        command = shlex.split(command_text)
        if not command:
            raise ValueError("Пустая команда")
        return self._run("unrestricted", command)
