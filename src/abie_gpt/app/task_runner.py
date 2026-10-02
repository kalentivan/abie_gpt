from __future__ import annotations

from dataclasses import dataclass

from abie_gpt.storage import Database


@dataclass(frozen=True, slots=True)
class TaskStep:
    response: str
    iteration: int
    completed: bool
    stopped: bool


class TaskRunner:
    """Persistent step-based runner for arbitrary user tasks."""

    COMPLETION_MARKER = "TASK_COMPLETE"
    CONTINUE_PROMPT = (
        "Продолжай выполнение текущей задачи с того места, где остановился. "
        "Не повторяй уже выполненное. Выполняй реальную полезную работу, пока она остаётся. "
        "Когда исходное ТЗ полностью выполнено и больше ничего делать не требуется, "
        "заверши ответ отдельной строкой TASK_COMPLETE."
    )

    def __init__(self, database: Database):
        self.database = database

    def start(self, external_key: str, max_iterations: int = 50) -> None:
        self.database.set_autorun(
            external_key, True, max_iterations=max_iterations,
            stop_marker=self.COMPLETION_MARKER, reset=True,
        )

    def stop(self, external_key: str) -> None:
        self.database.set_autorun(external_key, False)

    def is_running(self, external_key: str) -> bool:
        state = self.database.get_autorun(external_key)
        return bool(state and state.enabled and state.iteration < state.max_iterations)

    def continuation_prompt(self) -> str:
        return self.CONTINUE_PROMPT

    def record_response(self, external_key: str, response: str) -> TaskStep:
        state = self.database.get_autorun(external_key)
        if not state or not state.enabled:
            return TaskStep(response, state.iteration if state else 0, False, True)
        iteration = self.database.advance_autorun(external_key)
        completed = state.stop_marker.casefold() in response.casefold()
        exhausted = iteration >= state.max_iterations
        if completed or exhausted:
            self.database.set_autorun(external_key, False)
        return TaskStep(response, iteration, completed, exhausted and not completed)
