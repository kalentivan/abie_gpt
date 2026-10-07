import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path


CHAT_URL_RE = re.compile(r"^https://chatgpt\.com/c/[A-Za-z0-9-]+(?:[/?#].*)?$")


class DialogRegistry:
    """Persistent registry of named ChatGPT conversations."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict:
        if not self.path.exists():
            return {"active": None, "dialogs": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"active": None, "dialogs": {}}
        if not isinstance(data, dict):
            return {"active": None, "dialogs": {}}
        data.setdefault("active", None)
        data.setdefault("dialogs", {})
        return data

    def _save(self, data: dict) -> None:
        fd, tmp_name = tempfile.mkstemp(
            prefix=self.path.name + ".",
            suffix=".tmp",
            dir=self.path.parent,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump(data, output, ensure_ascii=False, indent=2)
                output.write("\n")
            os.replace(tmp_name, self.path)
        finally:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass

    @staticmethod
    def valid_chat_url(url: str) -> bool:
        return bool(CHAT_URL_RE.match(url or ""))

    def remember(self, title: str, url: str, *, make_active: bool = True) -> dict:
        if not self.valid_chat_url(url):
            raise ValueError(f"Не удалось получить URL диалога ChatGPT: {url!r}")
        title = title.strip()
        if not title:
            raise ValueError("Название диалога не может быть пустым")

        data = self._load()
        dialogs = data["dialogs"]
        # A URL identifies one conversation. Rename an existing entry instead
        # of creating aliases for the same ChatGPT chat.
        for old_title, item in list(dialogs.items()):
            if item.get("url") == url and old_title != title:
                del dialogs[old_title]

        now = datetime.now().astimezone().isoformat(timespec="seconds")
        created_at = dialogs.get(title, {}).get("created_at", now)
        dialogs[title] = {
            "title": title,
            "url": url,
            "created_at": created_at,
            "updated_at": now,
        }
        if make_active:
            data["active"] = title
        self._save(data)
        return dialogs[title]

    def touch_active(self, url: str) -> None:
        if not self.valid_chat_url(url):
            return
        data = self._load()
        active = data.get("active")
        if active and active in data["dialogs"]:
            item = data["dialogs"][active]
            if item.get("url") == url:
                item["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
                self._save(data)

    def active(self) -> dict | None:
        data = self._load()
        active = data.get("active")
        item = data["dialogs"].get(active)
        return dict(item) if item else None

    def list(self) -> list[dict]:
        data = self._load()
        active = data.get("active")
        result = []
        for item in data["dialogs"].values():
            value = dict(item)
            value["active"] = value.get("title") == active
            result.append(value)
        result.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        return result

    def select(self, selector: str) -> dict:
        selector = selector.strip()
        items = self.list()
        if selector.isdigit():
            index = int(selector)
            if index < 1 or index > len(items):
                raise ValueError(f"Диалога №{index} нет")
            selected = items[index - 1]
        else:
            selected = next(
                (item for item in items if item["title"].casefold() == selector.casefold()),
                None,
            )
            if selected is None:
                raise ValueError(f"Диалог {selector!r} не найден")

        data = self._load()
        data["active"] = selected["title"]
        self._save(data)
        return selected
