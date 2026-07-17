from __future__ import annotations

import sqlite3

from psnself import db as db_module
from psnself import db_gamestats


class TestGameCrud:
    def test_game_exists_returns_false_for_missing(self, conn: sqlite3.Connection) -> None:
        assert db_module.game_exists(conn, "NPWR_NONEXIST") is False

    def test_insert_and_query_game(self, conn: sqlite3.Connection) -> None:
        game = {
            "np_communication_id": "NPWR001",
            "np_title_id": "TITLE001",
            "title_name": "Test Game",
            "title_icon_url": "https://example.com/icon.png",
            "platform": "PS5",
            "defined_bronze": 50,
            "defined_silver": 20,
            "defined_gold": 5,
            "defined_platinum": 1,
            "earned_bronze": 10,
            "earned_silver": 5,
            "earned_gold": 1,
            "earned_platinum": 0,
            "progress": 30,
            "last_updated_datetime": "2024-12-25T10:00:00Z",
        }
        db_module.upsert_game(conn, game)
        conn.commit()

        assert db_module.game_exists(conn, "NPWR001") is True
        games = db_module.get_games(conn)
        assert len(games) == 1
        assert games[0]["title_name"] == "Test Game"
        assert games[0]["play_seconds"] == 0

    def test_get_games_joins_stats(self, conn: sqlite3.Connection) -> None:
        game = {
            "np_communication_id": "NPWR001",
            "np_title_id": "TITLE001",
            "title_name": "Game With Stats",
            "platform": "PS5",
            "defined_bronze": 50,
            "defined_silver": 20,
            "defined_gold": 5,
            "defined_platinum": 1,
            "earned_bronze": 10,
            "earned_silver": 5,
            "earned_gold": 1,
            "earned_platinum": 0,
            "progress": 30,
        }
        db_module.upsert_game(conn, game)
        db_gamestats.update_game_stats(
            conn, "NPWR001",
            title_id="TITLE001",
            total_seconds=36000,
            play_count=5,
            first_played="2024-01-01T00:00:00Z",
            last_played="2024-12-25T10:00:00Z",
        )
        conn.commit()

        games = db_module.get_games(conn)
        assert games[0]["play_seconds"] == 36000
        assert "has_psn_time" not in games[0].keys()


class TestTrophyCrud:
    def test_insert_trophies(self, conn: sqlite3.Connection) -> None:
        game = {
            "np_communication_id": "NPWR001",
            "title_name": "Test Game", "platform": "PS5",
            "defined_bronze": 50, "defined_silver": 20,
            "defined_gold": 5, "defined_platinum": 1,
            "earned_bronze": 0, "earned_silver": 0,
            "earned_gold": 0, "earned_platinum": 0,
            "progress": 0,
        }
        db_module.upsert_game(conn, game)

        trophies = [
            {
                "np_communication_id": "NPWR001",
                "trophy_id": 1,
                "trophy_name": "Bronze Trophy",
                "trophy_type": "bronze",
                "trophy_rarity": "common",
                "trophy_earn_rate": 80.0,
                "earned": 1,
                "earned_date_time": "2024-12-25T10:00:00Z",
            },
            {
                "np_communication_id": "NPWR001",
                "trophy_id": 2,
                "trophy_name": "Gold Trophy",
                "trophy_type": "gold",
                "trophy_rarity": "rare",
                "trophy_earn_rate": 15.5,
                "earned": 0,
            },
        ]
        for t in trophies:
            db_module.upsert_trophy(conn, t)
        conn.commit()

        rows = db_module.get_trophies(conn, "NPWR001")
        assert len(rows) == 2

    def test_get_recent_earned(self, conn: sqlite3.Connection) -> None:
        game = {
            "np_communication_id": "NPWR001",
            "title_name": "Test Game", "platform": "PS5",
            "defined_bronze": 1, "defined_silver": 0,
            "defined_gold": 0, "defined_platinum": 0,
            "earned_bronze": 0, "earned_silver": 0,
            "earned_gold": 0, "earned_platinum": 0,
            "progress": 0,
        }
        db_module.upsert_game(conn, game)
        trophy = {
            "np_communication_id": "NPWR001",
            "trophy_id": 1,
            "trophy_name": "Recent Trophy",
            "trophy_type": "bronze",
            "earned": 1,
            "earned_date_time": "2024-12-26T10:00:00Z",
        }
        db_module.upsert_trophy(conn, trophy)
        conn.commit()

        recent = db_module.get_recent_earned(conn, limit=5)
        assert len(recent) == 1
        assert recent[0]["trophy_name"] == "Recent Trophy"


class TestSyncLog:
    def test_sync_lifecycle(self, conn: sqlite3.Connection) -> None:
        sync_id = db_module.start_sync(conn)
        assert sync_id > 0

        assert db_module.get_last_sync_time(conn) is None
        conn.commit()

        db_module.finish_sync(conn, sync_id, "success", trophies_added=5, games_updated=2)
        conn.commit()

        last = db_module.get_last_sync_time(conn)
        assert last is not None

    def test_game_stats_delta(self, conn: sqlite3.Connection) -> None:
        game = {
            "np_communication_id": "NPWR001",
            "title_name": "Delta Test", "platform": "PS4",
            "defined_bronze": 10, "defined_silver": 0,
            "defined_gold": 0, "defined_platinum": 0,
            "earned_bronze": 0, "earned_silver": 0,
            "earned_gold": 0, "earned_platinum": 0,
            "progress": 0,
        }
        db_module.upsert_game(conn, game)
        db_gamestats.update_game_stats(
            conn, "NPWR001", title_id="TID", total_seconds=500,
            play_count=1, first_played=None, last_played="2024-12-25T10:00:00Z",
        )
        db_gamestats.update_game_stats(
            conn, "NPWR001", title_id="TID", total_seconds=1000,
            play_count=2, first_played=None, last_played="2024-12-26T10:00:00Z",
        )
        conn.commit()

        total = conn.execute(
            "SELECT COALESCE(SUM(delta_seconds), 0) FROM play_delta_history"
        ).fetchone()[0]
        assert total == 500

    def test_get_game_stats(self, conn: sqlite3.Connection) -> None:
        assert db_gamestats.get_game_stats(conn, "NPWR_NONE") is None


class TestManualPlayTime:
    def test_set_manual_time_creates_entry(self, conn: sqlite3.Connection) -> None:
        db_module.upsert_game(conn, {
            "np_communication_id": "NPWR_MANUAL",
            "title_name": "Manual Game", "platform": "PS5",
            "defined_bronze": 10, "defined_silver": 0,
            "defined_gold": 0, "defined_platinum": 0,
            "earned_bronze": 0, "earned_silver": 0,
            "earned_gold": 0, "earned_platinum": 0,
            "progress": 0,
        })
        db_gamestats.set_manual_play_time(conn, "NPWR_MANUAL", 7200)
        conn.commit()
        gs = db_gamestats.get_game_stats(conn, "NPWR_MANUAL")
        assert gs is not None
        assert gs["total_seconds"] == 7200
        assert gs["title_id"] is None
