from pathlib import Path

import pytest

from abie_gpt.storage import Database


@pytest.fixture
def database(tmp_path: Path) -> Database:
    db = Database(f"sqlite:///{tmp_path / 'test.db'}")
    db.create_schema()
    return db
