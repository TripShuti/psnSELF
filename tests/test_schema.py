from __future__ import annotations

from pathlib import Path


SCHEMA_PATH = Path(__file__).parent.parent / "psnself" / "schema.sql"


class TestSchema:
    def test_schema_file_exists(self) -> None:
        assert SCHEMA_PATH.exists()

    def test_schema_has_games_table(self) -> None:
        text = SCHEMA_PATH.read_text()
        assert "CREATE TABLE IF NOT EXISTS games" in text
        assert "np_communication_id TEXT PRIMARY KEY" in text

    def test_schema_has_trophies_table(self) -> None:
        text = SCHEMA_PATH.read_text()
        assert "CREATE TABLE IF NOT EXISTS trophies" in text

    def test_schema_has_game_stats(self) -> None:
        text = SCHEMA_PATH.read_text()
        assert "CREATE TABLE IF NOT EXISTS game_stats" in text

    def test_schema_has_friends_tables(self) -> None:
        text = SCHEMA_PATH.read_text()
        assert "friends_cache" in text
        assert "friend_game_cache" in text

    def test_schema_has_foreign_keys(self) -> None:
        text = SCHEMA_PATH.read_text()
        assert text.count("FOREIGN KEY") >= 3
