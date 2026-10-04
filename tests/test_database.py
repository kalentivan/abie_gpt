def test_conversation_roundtrip(database):
    database.save_conversation("max:1", "chat-1", "https://chatgpt.local/c/chat-1")
    row = database.get_conversation("max:1")
    assert row is not None
    assert row.chatgpt_id == "chat-1"


def test_autorun_persists_and_advances(database):
    database.set_autorun("max:1", True, max_iterations=3, reset=True)
    assert database.get_autorun("max:1").enabled is True
    assert database.advance_autorun("max:1") == 1
    assert database.get_autorun("max:1").iteration == 1


def test_named_dialog_registry(database):
    database.save_named_dialog("max:1", "ABIE", "chat-1", "https://chatgpt.local/c/chat-1")
    row = database.get_named_dialog("max:1", "ABIE")
    assert row is not None
    assert row.chatgpt_id == "chat-1"
    assert database.list_named_dialogs("max:1")[0].name == "ABIE"
    assert database.next_dialog_name("max:1") == "Диалог 1"


def test_default_dialog_names_increment(database):
    database.save_named_dialog("max:1", "Диалог 1", "chat-1", "https://chatgpt.local/c/chat-1")
    assert database.next_dialog_name("max:1") == "Диалог 2"
