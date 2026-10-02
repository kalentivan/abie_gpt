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
