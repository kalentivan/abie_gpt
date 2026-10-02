from __future__ import annotations

from pathlib import Path
from typing import Protocol


class Transcriber(Protocol):
    def transcribe(self, path: Path) -> str: ...


class FasterWhisperTranscriber:
    """Local speech-to-text adapter. Model is loaded lazily on first voice message."""

    def __init__(self, model_name: str = "small", device: str = "cpu", compute_type: str = "int8"):
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self._model = None

    def transcribe(self, path: Path) -> str:
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                self.model_name, device=self.device, compute_type=self.compute_type
            )
        segments, _ = self._model.transcribe(str(path), vad_filter=True)
        text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
        if not text:
            raise RuntimeError("Voice message transcription is empty")
        return text
