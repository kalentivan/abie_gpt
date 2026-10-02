from __future__ import annotations

import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from dotenv import dotenv_values

FIELDS = (
    ("MAX_BOT_TOKEN", "MAX bot token", True),
    ("BRAVE_PATH", "Brave executable", False),
    ("BOT_PROFILE", "Browser profile", False),
    ("DATA_DIR", "Data directory", False),
    ("SCREENSHOT_DIR", "Screenshots", False),
    ("GPT_TIMEOUT", "GPT timeout, sec", False),
    ("MAX_MESSAGE_LENGTH", "MAX message length", False),
    ("WHISPER_MODEL", "Whisper model", False),
    ("WHISPER_DEVICE", "Whisper device", False),
    ("WHISPER_COMPUTE_TYPE", "Whisper compute type", False),
)
DEFAULTS = {
    "DATA_DIR": "./data", "SCREENSHOT_DIR": "./var/screenshots",
    "GPT_TIMEOUT": "900", "MAX_MESSAGE_LENGTH": "3900",
    "WHISPER_MODEL": "small", "WHISPER_DEVICE": "cpu",
    "WHISPER_COMPUTE_TYPE": "int8",
}


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


class DesktopApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("ABIE GPT")
        self.root.geometry("720x560")
        self.env_path = app_dir() / ".env"
        self.process: subprocess.Popen[str] | None = None
        self.vars: dict[str, tk.StringVar] = {}
        self.status = tk.StringVar(value="Остановлен")
        self._build()
        self._load()
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="ABIE GPT · MAX ↔ ChatGPT", font=("", 16, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 14)
        )
        for row, (key, label, secret) in enumerate(FIELDS, 1):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
            var = tk.StringVar()
            self.vars[key] = var
            entry = ttk.Entry(frame, textvariable=var, show="•" if secret else "")
            entry.grid(row=row, column=1, sticky="ew", padx=8, pady=4)
            if key in {"BRAVE_PATH", "BOT_PROFILE", "DATA_DIR", "SCREENSHOT_DIR"}:
                ttk.Button(frame, text="…", width=3,
                    command=lambda k=key: self._browse(k)).grid(row=row, column=2)
        frame.columnconfigure(1, weight=1)
        row = len(FIELDS) + 1
        buttons = ttk.Frame(frame)
        buttons.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(18, 8))
        ttk.Button(buttons, text="Сохранить", command=self.save).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="▶ Запустить бота", command=self.start).pack(side="left", padx=8)
        ttk.Button(buttons, text="■ Остановить", command=self.stop).pack(side="left", padx=8)
        ttk.Button(buttons, text="Открыть папку", command=self.open_folder).pack(side="left", padx=8)
        ttk.Label(frame, textvariable=self.status).grid(row=row + 1, column=0, columnspan=3, sticky="w")
        self.log = tk.Text(frame, height=10, state="disabled", wrap="word")
        self.log.grid(row=row + 2, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
        frame.rowconfigure(row + 2, weight=1)

    def _load(self) -> None:
        values = {**DEFAULTS, **{k: v for k, v in dotenv_values(self.env_path).items() if v}}
        for key, var in self.vars.items():
            var.set(str(values.get(key, "")))

    def save(self) -> None:
        lines = []
        for key, _, _ in FIELDS:
            value = self.vars[key].get().strip().replace("\n", " ")
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{key}="{escaped}"')
        self.env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.status.set(f"Настройки сохранены: {self.env_path}")

    def _browse(self, key: str) -> None:
        if key == "BRAVE_PATH":
            value = filedialog.askopenfilename(title="Выберите brave.exe")
        else:
            value = filedialog.askdirectory(title="Выберите папку")
        if value:
            self.vars[key].set(value)

    def start(self) -> None:
        if self.process and self.process.poll() is None:
            self.status.set("Бот уже работает")
            return
        self.save()
        env = os.environ.copy()
        env.update({k: v or "" for k, v in dotenv_values(self.env_path).items()})
        if getattr(sys, "frozen", False):
            command = [sys.executable, "--run-bot"]
        else:
            command = [sys.executable, "-m", "abie_gpt.bootstrap"]
        try:
            self.process = subprocess.Popen(command, cwd=app_dir(), env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                encoding="utf-8", errors="replace")
        except Exception as exc:
            messagebox.showerror("ABIE GPT", str(exc))
            return
        self.status.set("● Бот запущен")
        threading.Thread(target=self._read_output, daemon=True).start()

    def _read_output(self) -> None:
        assert self.process and self.process.stdout
        for line in self.process.stdout:
            self.root.after(0, self._append_log, line)
        code = self.process.wait()
        self.root.after(0, self.status.set, f"Бот остановлен (код {code})")

    def _append_log(self, line: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", line)
        self.log.see("end")
        self.log.configure(state="disabled")

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.status.set("Останавливается…")
        else:
            self.status.set("Остановлен")

    def open_folder(self) -> None:
        path = app_dir()
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def _close(self) -> None:
        self.stop()
        self.root.destroy()


def main() -> None:
    if "--run-bot" in sys.argv:
        from abie_gpt.bootstrap import main as bot_main
        bot_main()
        return
    root = tk.Tk()
    DesktopApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
