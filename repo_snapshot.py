import os
import re
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

REPO_URL = os.getenv("ABIE_REPO_URL", "https://github.com/kalentivan/abie.git")
PROJECT_DIR = Path(__file__).resolve().parent
SNAPSHOT_DIR = Path(os.getenv("ABIE_SNAPSHOT_DIR", str(PROJECT_DIR / "snapshots"))).resolve()
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

VERSION_BRANCHES = {
    "v2": "v2-dev",
    "2": "v2-dev",
    "v3": "v3-dev",
    "3": "v3-dev",
}


def parse_pull_command(text: str) -> str | None:
    match = re.fullmatch(r"(?i)\s*(?:ПУЛЛ|PULL)\s+([^\s]+)\s*", text or "")
    return match.group(1) if match else None


def _branch_for(version: str) -> str:
    value = version.strip()
    return VERSION_BRANCHES.get(value.lower(), value)


def _remove_readonly(func, path, exc_info):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        raise exc_info[1]


def _rmtree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, onerror=_remove_readonly)


def _run(*args: str, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.stdout.strip()


def create_repo_snapshot(version: str) -> tuple[Path, str, str]:
    branch = _branch_for(version)
    safe_branch = re.sub(r"[^a-zA-Z0-9._-]+", "_", branch).strip("._-") or "snapshot"

    root = Path(tempfile.mkdtemp(prefix="abie-pull-"))
    try:
        checkout = root / "ABIE"

        _run(
            "git",
            "clone",
            "--depth",
            "1",
            "--single-branch",
            "--branch",
            branch,
            REPO_URL,
            str(checkout),
        )
        commit = _run("git", "rev-parse", "HEAD", cwd=checkout)

        git_dir = checkout / ".git"
        _rmtree(git_dir)

        target_base = SNAPSHOT_DIR / f"ABIE-{safe_branch}-{commit[:8]}"
        archive = Path(
            shutil.make_archive(
                str(target_base),
                "zip",
                root_dir=checkout,
            )
        )
        return archive, branch, commit
    finally:
        _rmtree(root)
