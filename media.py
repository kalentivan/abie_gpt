import os
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests

MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "runtime/media")).resolve()
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_SUFFIXES = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav", ".webm"}
MAX_EXTRACTED_FILES = int(os.getenv("MAX_EXTRACTED_FILES", "200"))
MAX_EXTRACTED_BYTES = int(os.getenv("MAX_EXTRACTED_BYTES", str(512 * 1024 * 1024)))


def _plain(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _walk(value):
    value = _plain(value)
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _attachment_url(attachment):
    candidates = []
    for obj in _walk(attachment):
        for key, value in obj.items():
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                score = (2 if "url" in key.lower() else 0) + (
                    2 if any(x in key.lower() for x in ("download", "file", "audio", "video")) else 0
                )
                candidates.append((score, value))
    return max(candidates, default=(0, None), key=lambda item: item[0])[1]


def _attachment_name(attachment, url, index):
    for obj in _walk(attachment):
        for key in ("name", "filename", "file_name", "title"):
            value = obj.get(key)
            if isinstance(value, str) and value.strip():
                return Path(value).name
    return Path(unquote(urlparse(url).path)).name or f"attachment-{index}"


def download_attachments(attachments) -> list[Path]:
    result = []
    for index, attachment in enumerate(attachments, 1):
        url = _attachment_url(attachment)
        if not url:
            continue
        target = MEDIA_DIR / f"in-{index}-{_attachment_name(attachment, url, index)}"
        with requests.get(url, timeout=120, stream=True) as response:
            response.raise_for_status()
            with target.open("wb") as output:
                shutil.copyfileobj(response.raw, output)
        result.append(target)
    return result


def is_audio_file(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_SUFFIXES


def transcribe_audio(path: Path) -> str:
    from faster_whisper import WhisperModel
    model = WhisperModel(os.getenv("WHISPER_MODEL", "small"), device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(path), vad_filter=True)
    return " ".join(segment.text.strip() for segment in segments).strip()


def _safe_target(root: Path, member: str) -> None:
    target = (root / member).resolve()
    if root != target and root not in target.parents:
        raise ValueError(f"Опасный путь в архиве: {member}")


def _check_limits(files: list[Path]) -> None:
    if len(files) > MAX_EXTRACTED_FILES:
        raise ValueError(f"Слишком много файлов в архиве: {len(files)}")
    total = sum(path.stat().st_size for path in files)
    if total > MAX_EXTRACTED_BYTES:
        raise ValueError(f"Распаковано слишком много данных: {total} байт")


def _extract_zip(path: Path, root: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            _safe_target(root, info.filename)
        archive.extractall(root)


def _extract_tar(path: Path, root: Path) -> None:
    with tarfile.open(path) as archive:
        members = archive.getmembers()
        for member in members:
            _safe_target(root, member.name)
            if member.issym() or member.islnk():
                raise ValueError("Ссылки внутри tar-архива запрещены")
        archive.extractall(root, members=members, filter="data")


def _extract_7z(path: Path, root: Path) -> None:
    import py7zr
    with py7zr.SevenZipFile(path, mode="r") as archive:
        for name in archive.getnames():
            _safe_target(root, name)
        archive.extractall(path=root)


def extract_archives(paths: list[Path]) -> list[Path]:
    root = MEDIA_DIR / f"unpacked-{next(tempfile._get_candidate_names())}"
    root.mkdir(parents=True, exist_ok=False)
    handled = False
    for path in paths:
        if path.suffix.lower() == ".zip":
            _extract_zip(path, root); handled = True
        elif path.suffix.lower() == ".7z":
            _extract_7z(path, root); handled = True
        elif tarfile.is_tarfile(path):
            _extract_tar(path, root); handled = True
    if not handled:
        raise ValueError("Поддерживаются ZIP, 7Z и TAR/TGZ/GZ/BZ2/XZ архивы")
    files = sorted(path for path in root.rglob("*") if path.is_file())
    _check_limits(files)
    return files
