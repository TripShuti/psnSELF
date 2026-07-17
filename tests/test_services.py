from __future__ import annotations

import sqlite3

from psnself import db as db_module
from psnself import db_gamestats
from psnself.web.services.game_service import GameService
from psnself.web.services.friend_service import FriendService
from psnself.web.services.stats_service import StatsService
from psnself import db_friends


def _seed_game(conn: sqlite3.Connection, np_comm_id: str, title_name: str) -> None:
    db_module.upsert_game(conn, {
        "np_communication_id": np_comm_id,
        "title_name": title_name, "platform": "PS5",
        "defined_bronze": 10, "defined_silver": 5,
        "defined_gold": 2, "defined_platinum": 1,
        "earned_bronze": 5, "earned_silver": 2,
        "earned_gold": 1, "earned_platinum": 0,
        "progress": 50,
        "last_updated_datetime": "2024-12-25T10:00:00Z",
    })
    conn.commit()


def _seed_trophy(conn: sqlite3.Connection, np_comm_id: str, trophy_id: int,
                 name: str, trophy_type: str = "bronze",
                 earned: bool = True,
                 earned_rate: float = 50.0,
                 rarity: str = "common") -> None:
    db_module.upsert_trophy(conn, {
        "np_communication_id": np_comm_id,
        "trophy_id": trophy_id,
        "trophy_name": name,
        "trophy_type": trophy_type,
        "trophy_rarity": rarity,
        "trophy_earn_rate": earned_rate,
        "earned": int(earned),
        "earned_date_time": "2024-12-26T10:00:00Z" if earned else None,
    })
    conn.commit()


class TestGameService:
    def test_get_games(self, conn: sqlite3.Connection) -> None:
        _seed_game(conn, "NPWR001", "Game A")
        _seed_game(conn, "NPWR002", "Game B")
        gs = GameService(conn)
        games = gs.get_games()
        assert len(games) == 2
        assert games[0].title_name == "Game A"

    def test_get_game_not_found(self, conn: sqlite3.Connection) -> None:
        gs = GameService(conn)
        assert gs.get_game("NONEXIST") is None

    def test_get_rarest(self, conn: sqlite3.Connection) -> None:
        _seed_game(conn, "NPWR001", "Game")
        _seed_trophy(conn, "NPWR001", 1, "Common Trophy", earned_rate=80.0)
        _seed_trophy(conn, "NPWR001", 2, "Rare Trophy", earned_rate=5.0)
        _seed_trophy(conn, "NPWR001", 3, "Mid Trophy", earned_rate=30.0)
        gs = GameService(conn)
        rarest = gs.get_rarest(limit=2)
        assert len(rarest) == 2
        assert rarest[0]["trophy_name"] == "Rare Trophy"

    def test_set_manual_time(self, conn: sqlite3.Connection) -> None:
        _seed_game(conn, "NPWR_M", "Manual")
        gs = GameService(conn)
        gs.set_manual_time("NPWR_M", 3600)
        gs2 = gs.get_game_stats("NPWR_M")
        assert gs2 is not None
        assert gs2.total_seconds == 3600

    def test_get_play_time_periods(self, conn: sqlite3.Connection) -> None:
        _seed_game(conn, "NPWR001", "Game")
        db_gamestats.update_game_stats(
            conn, "NPWR001", title_id="TID", total_seconds=1000,
            play_count=1, first_played=None,
            last_played="2024-12-25T10:00:00Z",
        )
        conn.commit()
        gs = GameService(conn)
        periods = gs.get_play_time_periods("NPWR001")
        assert "today_sec" in periods


class TestFriendService:
    def test_empty_leaderboard(self, conn: sqlite3.Connection) -> None:
        fs = FriendService(conn)
        assert fs.get_leaderboard() == []

    def test_leaderboard(self, conn: sqlite3.Connection) -> None:
        db_friends.upsert_friend(conn, {
            "account_id": "acc001",
            "online_id": "Player1",
            "trophy_level": 100,
            "platinum": 5, "gold": 20, "silver": 50, "bronze": 200,
            "is_private": 0,
            "fetched_at": "2024-12-25T10:00:00Z",
        })
        conn.commit()
        fs = FriendService(conn)
        lb = fs.get_leaderboard()
        assert len(lb) == 1
        assert lb[0].online_id == "Player1"

    def test_get_by_account_id(self, conn: sqlite3.Connection) -> None:
        db_friends.upsert_friend(conn, {
            "account_id": "acc001",
            "online_id": "Player1",
            "trophy_level": 100,
            "platinum": 5, "gold": 20, "silver": 50, "bronze": 200,
            "is_private": 0,
            "fetched_at": "2024-12-25T10:00:00Z",
        })
        conn.commit()
        fs = FriendService(conn)
        f = fs.get_by_account_id("acc001")
        assert f is not None
        assert f.online_id == "Player1"
        assert fs.get_by_account_id("NONEXIST") is None

    def test_raw_friend_fallback(self, conn: sqlite3.Connection) -> None:
        fs = FriendService(conn)
        assert fs.get_raw_friend("acc001") is None

    def test_comparison_no_shared_games(self, conn: sqlite3.Connection) -> None:
        fs = FriendService(conn)
        assert fs.get_comparison("NPWR001") == []

    def test_fetched_at_label_never(self, conn: sqlite3.Connection) -> None:
        fs = FriendService(conn)
        label = fs.get_fetched_at_label()
        assert "Never" in label


class TestStatsService:
    def test_heatmap_empty(self, conn: sqlite3.Connection) -> None:
        from datetime import date
        ss = StatsService(conn)
        hm = ss.build_heatmap(date(2024, 12, 25), weeks_back=4)
        assert len(hm["rows"]) == 7

    def test_playtime_summary_empty(self, conn: sqlite3.Connection) -> None:
        from datetime import date
        ss = StatsService(conn)
        s = ss.get_playtime_summary(date(2024, 12, 25))
        assert s["total"] == "0m"
        assert s["today"] == "0m"

    def test_calendar_data_empty(self, conn: sqlite3.Connection) -> None:
        ss = StatsService(conn)
        cells = ss.get_calendar_data(2024, 12)
        assert len(cells) > 0

    def test_play_day_details_empty(self, conn: sqlite3.Connection) -> None:
        ss = StatsService(conn)
        details = ss.get_play_day_details("2024-12-25")
        assert details == []
