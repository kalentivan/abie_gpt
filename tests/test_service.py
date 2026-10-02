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
