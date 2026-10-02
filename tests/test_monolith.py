from abie_gpt.app.service import ChatService
from abie_gpt.app.task_runner import TaskRunner
from abie_gpt.chatgpt.local import LocalChatGPTHandler


def test_local_monolith_task_until_complete(database):
    browser = LocalChatGPTHandler(["Шаг 1 готов", "Финальный результат\nTASK_COMPLETE"])
    browser.start()
    service = ChatService(browser, database)
    runner = TaskRunner(database)
    key = "max:test-user"

    runner.start(key, max_iterations=5)
    first = service.ask(key, "Сделай задачу полностью")
    step1 = runner.record_response(key, first)
    assert not step1.completed
    assert runner.is_running(key)

    second = service.ask(key, runner.continuation_prompt())
    step2 = runner.record_response(key, second)
    assert step2.completed
    assert not runner.is_running(key)
    assert database.get_conversation(key).chatgpt_id == "local-chat"
    assert browser.prompts[0] == "Сделай задачу полностью"
    assert "Продолжай выполнение" in browser.prompts[1]
