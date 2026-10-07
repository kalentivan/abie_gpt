from pathlib import Path

import pytest

from integrations.dialogs import DialogRegistry


def test_remember_list_and_select(tmp_path: Path):
    registry = DialogRegistry(tmp_path / "dialogs.json")

    registry.remember("Основной", "https://chatgpt.com/c/11111111-1111-1111-1111-111111111111")
    registry.remember("ABIE", "https://chatgpt.com/c/22222222-2222-2222-2222-222222222222")

    assert registry.active()["title"] == "ABIE"

    items = registry.list()
    assert {item["title"] for item in items} == {"Основной", "ABIE"}

    selected = registry.select("Основной")
    assert selected["title"] == "Основной"
    assert registry.active()["title"] == "Основной"

    selected = registry.select("1")
    assert selected["title"] in {"Основной", "ABIE"}


def test_rejects_non_chatgpt_conversation_url(tmp_path: Path):
    registry = DialogRegistry(tmp_path / "dialogs.json")

    with pytest.raises(ValueError):
        registry.remember("bad", "https://example.com/c/123")


def test_same_url_is_renamed_without_duplicate(tmp_path: Path):
    registry = DialogRegistry(tmp_path / "dialogs.json")
    url = "https://chatgpt.com/c/33333333-3333-3333-3333-333333333333"

    registry.remember("Старое имя", url)
    registry.remember("Новое имя", url)

    items = registry.list()
    assert len(items) == 1
    assert items[0]["title"] == "Новое имя"
