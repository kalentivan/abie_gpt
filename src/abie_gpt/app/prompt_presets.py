from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PromptPreset:
    id: str
    title: str
    suffix: str


PRESETS: dict[str, PromptPreset] = {
    "long": PromptPreset(
        "long",
        "🔥 Работай долго",
        "Работай максимально долго в пределах текущего запуска. Не завершай работу после первого результата и не трать запуск на промежуточный ответ. Продолжай, пока не исчерпаешь полезную работу.",
    ),
    "deep_audit": PromptPreset(
        "deep_audit",
        "🔍 Глубокий аудит",
        "Проведи максимально глубокий аудит: ищи новые проблемы, проверяй edge cases, контракты, интеграции и тесты. Исправляй разрешённые проблемы и не останавливайся после первого успешного результата.",
    ),
    "continue": PromptPreset(
        "continue",
        "▶️ Продолжай",
        "Сразу продолжай работу с того места, где остановился. Не повторяй уже сделанное и не трать запуск на объяснение статуса.",
    ),
}


def apply_preset(text: str, preset_id: str | None) -> str:
    preset = PRESETS.get(preset_id or "")
    if preset is None:
        return text
    return f"{text.rstrip()}\n\n{preset.suffix}"
