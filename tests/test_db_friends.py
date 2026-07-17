from __future__ import annotations

import sqlite3

from psnself import db_friends


class TestFriendCrud:
    def test_upsert_friend(self, conn: sqlite3.Connection) -> None:
        db_friends.upsert_friend(conn, {
            "account_id": "acc001",
            "online_id": "Player1",
            "trophy_level": 100,
            "platinum": 5,
            "gold": 20,
            "silver": 50,
            "bronze": 200,
            "is_private": 0,
            "fetched_at": "2024-12-25T10:00:00Z",
        })
        conn.commit()

        rows = db_friends.get_friends_leaderboard(conn)
        assert len(rows) == 1
        assert rows[0]["online_id"] == "Player1"
        assert rows[0]["total"] == 275

    def test_get_friend_by_account_id(self, conn: sqlite3.Connection) -> None:
        db_friends.upsert_friend(conn, {
            "account_id": "acc002",
            "online_id": "Player2",
            "trophy_level": 50,
            "platinum": 1,
            "gold": 5,
            "silver": 10,
            "bronze": 50,
            "is_private": 0,
            "fetched_at": "2024-12-25T10:00:00Z",
        })
        conn.commit()

        f = db_friends.get_friend_by_account_id(conn, "acc002")
        assert f is not None
        assert f["online_id"] == "Player2"

        f2 = db_friends.get_friend_by_account_id(conn, "nonexistent")
        assert f2 is None

    def test_private_friend(self, conn: sqlite3.Connection) -> None:
        db_friends.upsert_friend(conn, {
            "account_id": "acc003",
            "online_id": "PrivatePlayer",
            "trophy_level": None,
            "platinum": 0,
            "gold": 0,
            "silver": 0,
            "bronze": 0,
            "is_private": 1,
            "fetched_at": "2024-12-25T10:00:00Z",
        })
        conn.commit()

        rows = db_friends.get_friends_leaderboard(conn)
        assert len(rows) == 1
        assert rows[0]["is_private"] == 1

    def test_get_friends_fetched_at(self, conn: sqlite3.Connection) -> None:
        assert db_friends.get_friends_fetched_at(conn) is None

        db_friends.upsert_friend(conn, {
            "account_id": "acc001",
            "online_id": "P1",
            "trophy_level": 1,
            "platinum": 0, "gold": 0, "silver": 0, "bronze": 0,
            "is_private": 0,
            "fetched_at": "2024-12-26T10:00:00Z",
        })
        conn.commit()

        fetched = db_friends.get_friends_fetched_at(conn)
        assert fetched == "2024-12-26T10:00:00Z"


class TestFriendGame:
    def test_upsert_and_query(self, conn: sqlite3.Connection) -> None:
        db_friends.upsert_friend(conn, {
            "account_id": "acc001",
            "online_id": "Player1",
            "trophy_level": 100,
            "platinum": 5, "gold": 20, "silver": 50, "bronze": 200,
            "is_private": 0,
            "fetched_at": "2024-12-25T10:00:00Z",
        })
        db_friends.upsert_friend_game(conn, {
            "account_id": "acc001",
            "np_communication_id": "NPWR001",
            "progress": 80,
            "earned_platinum": 0,
            "earned_gold": 3,
            "earned_silver": 8,
            "earned_bronze": 30,
            "is_private": 0,
            "fetched_at": "2024-12-25T10:00:00Z",
        })
        conn.commit()

        comp = db_friends.get_friend_game_comparison(conn, "NPWR001")
        assert len(comp) == 1
        assert comp[0]["online_id"] == "Player1"
        assert comp[0]["earned_total"] == 41
