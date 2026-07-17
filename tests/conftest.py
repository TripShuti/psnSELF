from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import psnself


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    schema = (Path(psnself.__file__).parent / "schema.sql").read_text()
    c.executescript(schema)
    yield c
    c.close()
