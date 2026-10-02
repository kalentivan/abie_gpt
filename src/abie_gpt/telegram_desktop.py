from __future__ import annotations

import argparse
import asyncio
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from dotenv import load_dotenv

from abie_gpt.telegram.local import FakeTelegramClient
from abie_gpt.telegram.service import TelegramService
from abie_gpt.telegram.telethon_client import TelethonTelegramClient


class AsyncBridge:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit(self, coro, callback=None):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        if callback:
            future.add_done_callback(lambda f: callback(f))
        return future

    def close(self):
        self.loop.call_soon_threadsafe(self.loop.stop)


class TelegramDesktopApp:
    def __init__(self, root, service):
        self.root, self.service = root, service
        self.bridge = AsyncBridge()
        self.events = queue.Queue()
        self.dialogs = []
        self.selected_id = None
        self.root.title("ABIE Telegram")
        self.root.geometry("1050x700")
        self._build()
        self.service.subscribe(lambda msg: self.events.put(("message", msg)))
        self.root.after(100, self._poll_events)
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self._async(self.service.connect(), self._connected)

    def _build(self):
        outer = ttk.Panedwindow(self.root, orient="horizontal")
        outer.pack(fill="both", expand=True)
        left, right = ttk.Frame(outer, padding=8), ttk.Frame(outer, padding=8)
        outer.add(left, weight=1); outer.add(right, weight=3)
        self.search = tk.StringVar()
        entry = ttk.Entry(left, textvariable=self.search)
        entry.pack(fill="x", pady=(0, 6))
        entry.bind("<KeyRelease>", lambda e: self._render_dialogs())
        ttk.Button(left, text="↻ Обновить", command=self.refresh).pack(fill="x", pady=(0, 6))
        self.dialog_list = tk.Listbox(left, activestyle="none")
        self.dialog_list.pack(fill="both", expand=True)
        self.dialog_list.bind("<<ListboxSelect>>", self._select_dialog)
        self.header = ttk.Label(right, text="Выберите диалог", font=("", 13, "bold"))
        self.header.pack(fill="x", pady=(0, 8))
        self.history = tk.Text(right, state="disabled", wrap="word")
        self.history.pack(fill="both", expand=True)
        composer = ttk.Frame(right); composer.pack(fill="x", pady=(8, 0))
        self.input = tk.Text(composer, height=3, wrap="word")
        self.input.pack(side="left", fill="x", expand=True)
        self.input.bind("<Return>", self._enter)
        ttk.Button(composer, text="Отправить", command=self.send).pack(side="left", padx=(8, 0))
        self.status = tk.StringVar(value="Подключение…")
        ttk.Label(self.root, textvariable=self.status, anchor="w").pack(fill="x")

    def _async(self, coro, callback=None):
        def done(future):
            self.root.after(0, self._finish, future, callback)
        self.bridge.submit(coro, done)

    def _finish(self, future, callback):
        try:
            value = future.result()
            if callback: callback(value)
        except Exception as exc:
            self.status.set(f"Ошибка: {exc}")
            messagebox.showerror("ABIE Telegram", str(exc))

    def _connected(self, _):
        self._async(self.service.is_authorized(), self._authorized)

    def _authorized(self, authorized):
        if authorized:
            self.status.set("Подключено")
            self.refresh()
            return
        phone = simpledialog.askstring("Telegram", "Номер телефона:", parent=self.root)
        if not phone: return
        self._async(self.service.send_code(phone), lambda _: self._ask_code(phone))

    def _ask_code(self, phone):
        code = simpledialog.askstring("Telegram", "Код из Telegram:", parent=self.root)
        if not code: return
        password = simpledialog.askstring("Telegram", "2FA пароль (если есть):", show="*", parent=self.root)
        self._async(self.service.sign_in(phone, code, password or None), lambda _: self.refresh())

    def refresh(self):
        self.status.set("Загрузка диалогов…")
        self._async(self.service.dialogs(), self._dialogs_loaded)

    def _dialogs_loaded(self, dialogs):
        self.dialogs = dialogs
        self._render_dialogs()
        self.status.set(f"Диалогов: {len(dialogs)}")

    def _render_dialogs(self):
        needle = self.search.get().casefold().strip()
        self.visible = [d for d in self.dialogs if not needle or needle in d.title.casefold()]
        self.dialog_list.delete(0, "end")
        for d in self.visible:
            unread = f"  • {d.unread_count}" if d.unread_count else ""
            preview = (" — " + d.last_message.replace("\n", " ")[:35]) if d.last_message else ""
            self.dialog_list.insert("end", f"{d.title}{unread}{preview}")

    def _select_dialog(self, _event=None):
        selection = self.dialog_list.curselection()
        if not selection: return
        dialog = self.visible[selection[0]]
        self.selected_id = dialog.id
        self.header.config(text=dialog.title)
        self.status.set("Загрузка сообщений…")
        self._async(self.service.messages(dialog.id), self._messages_loaded)

    def _messages_loaded(self, messages):
        self.history.config(state="normal"); self.history.delete("1.0", "end")
        for msg in messages: self._append(msg)
        self.history.config(state="disabled"); self.history.see("end")
        self.status.set("Готово")

    def _append(self, msg):
        stamp = msg.sent_at.astimezone().strftime("%H:%M") if msg.sent_at else ""
        prefix = "Вы" if msg.outgoing else msg.sender_name
        self.history.insert("end", f"{prefix} · {stamp}\n{msg.text}\n\n")

    def _enter(self, event):
        if event.state & 0x1: return None
        self.send(); return "break"

    def send(self):
        if self.selected_id is None: return
        text = self.input.get("1.0", "end").strip()
        if not text: return
        self.input.delete("1.0", "end")
        self._async(self.service.send(self.selected_id, text), self._sent)

    def _sent(self, msg):
        self.history.config(state="normal"); self._append(msg)
        self.history.config(state="disabled"); self.history.see("end")

    def _poll_events(self):
        while True:
            try: kind, value = self.events.get_nowait()
            except queue.Empty: break
            if kind == "message":
                if value.dialog_id == self.selected_id:
                    self.history.config(state="normal"); self._append(value)
                    self.history.config(state="disabled"); self.history.see("end")
                self.refresh()
        self.root.after(150, self._poll_events)

    def _close(self):
        try: self.bridge.submit(self.service.disconnect()).result(timeout=3)
        except Exception: pass
        self.bridge.close(); self.root.destroy()


def build_service(demo=False):
    if demo:
        return TelegramService(FakeTelegramClient())
    api_id = int(os.getenv("TELEGRAM_API_ID", "0"))
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    session = Path(os.getenv("TELEGRAM_SESSION", "./data/telegram")).resolve()
    return TelegramService(TelethonTelegramClient(api_id, api_hash, session))


def main():
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    root = tk.Tk()
    TelegramDesktopApp(root, build_service(args.demo))
    root.mainloop()


if __name__ == "__main__":
    main()
