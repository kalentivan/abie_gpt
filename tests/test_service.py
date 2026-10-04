from abie_gpt.app.service import ChatService
from abie_gpt.chatgpt.local import LocalChatGPTHandler


def test_service_uses_local_selenium_and_persists_chat(database):
    browser = LocalChatGPTHandler(["Привет!"])
    browser.start()
    service = ChatService(browser, database)
    assert service.ask("max:42", "Привет") == "Привет!"
    assert browser.prompts == ["Привет"]
    saved = database.get_conversation("max:42")
    assert saved.chatgpt_id == "local-chat"


def test_service_reopens_saved_conversation(database):
    database.save_conversation("max:42", "saved-chat", "https://chatgpt.local/c/saved-chat")
    browser = LocalChatGPTHandler(["ok"])
    browser.start()
    browser.chat_id = "other"
    service = ChatService(browser, database)
    service.ask("max:42", "continue")
    assert browser.chat_id == "saved-chat"


def test_named_dialog_create_list_and_select(database):
    browser = LocalChatGPTHandler(["ok"])
    browser.start()
    service = ChatService(browser, database)

    name, chat = service.new_chat("max:42", "ABIE")
    assert name == "ABIE"
    assert chat.id == "local-new-chat"
    assert service.list_chats("max:42") == [("ABIE", True)]

    browser.chat_id = "other"
    selected_name, selected = service.select_chat("max:42", "ABIE")
    assert selected_name == "ABIE"
    assert selected.id == "local-new-chat"


def test_add_current_chat_registers_existing_chat(database):
    browser = LocalChatGPTHandler()
    browser.start()
    browser.chat_id = "existing"
    service = ChatService(browser, database)

    service.add_current_chat("max:42", "Старый чат")
    assert database.get_named_dialog("max:42", "Старый чат").chatgpt_id == "existing"
