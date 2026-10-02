from __future__ import annotations

import tempfile
from pathlib import Path

from abie_gpt.app.service import ChatService
from abie_gpt.app.task_runner import TaskRunner
from abie_gpt.chatgpt.local import LocalChatGPTHandler
from abie_gpt.storage import Database


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="abie-gpt-") as directory:
        db = Database(f"sqlite:///{Path(directory) / 'monolith.db'}")
        db.create_schema()
        browser = LocalChatGPTHandler([
            "Принял задачу. Выполняю первый этап.",
            "Задача выполнена полностью.\nTASK_COMPLETE",
        ])
        browser.start()
        service = ChatService(browser, db)
        runner = TaskRunner(db)
        key = "local:max:test"

        runner.start(key, max_iterations=5)
        prompt = "Выполни тестовую задачу полностью"
        while runner.is_running(key):
            answer = service.ask(key, prompt)
            step = runner.record_response(key, answer)
            print(f"[iteration={step.iteration}] {answer}")
            if step.completed or step.stopped:
                break
            prompt = runner.continuation_prompt()

        saved = db.get_conversation(key)
        assert saved and saved.chatgpt_id == "local-chat"
        assert not runner.is_running(key)
        print("MONOLITH SMOKE: OK")


if __name__ == "__main__":
    main()
