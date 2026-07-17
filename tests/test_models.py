from __future__ import annotations

from psnself.models import Game, Trophy, GameStats, Friend, FriendGame


class TestGameFromRow:
    def test_all_fields(self) -> None:
        row = {
            "np_communication_id": "NPWR001",
            "title_name": "Test Game",
            "platform": "PS5",
            "progress": 75,
            "earned_platinum": 1,
            "earned_gold": 5,
            "earned_silver": 10,
            "earned_bronze": 50,
            "np_title_id": "TITLE001",
            "last_updated_datetime": "2024-12-25T10:00:00Z",
            "play_seconds": 36000,
        }
        g = Game.from_row(row)
        assert g.np_communication_id == "NPWR001"
        assert g.title_name == "Test Game"
        assert g.platform == "PS5"
        assert g.progress == 75
        assert g.earned_platinum == 1
        assert g.play_seconds == 36000
        assert g.np_title_id == "TITLE001"

    def test_missing_optionals(self) -> None:
        row = {
            "np_communication_id": "NPWR002",
            "title_name": "Game 2",
            "platform": "PS4",
            "progress": 50,
            "earned_platinum": 0,
            "earned_gold": 2,
            "earned_silver": 5,
            "earned_bronze": 20,
        }
        g = Game.from_row(row)
        assert g.np_title_id == ""
        assert g.last_updated_datetime is None
        assert g.play_seconds == 0


class TestTrophyFromRow:
    def test_all_fields(self) -> None:
        row = {
            "np_communication_id": "NPWR001",
            "trophy_id": 1,
            "trophy_name": "First Trophy",
            "trophy_type": "bronze",
            "trophy_rarity": "rare",
            "trophy_earn_rate": 25.5,
            "earned": 1,
            "earned_date_time": "2024-12-25T10:00:00Z",
            "title_name": "Test Game",
        }
        t = Trophy.from_row(row)
        assert t.trophy_name == "First Trophy"
        assert t.trophy_type == "bronze"
        assert t.trophy_rarity == "rare"
        assert t.trophy_earn_rate == 25.5
        assert t.earned is True
        assert t.title_name == "Test Game"

    def test_not_earned(self) -> None:
        row = {
            "np_communication_id": "NPWR001",
            "trophy_id": 2,
            "trophy_name": "Hidden Trophy",
            "trophy_type": "gold",
            "earned": 0,
        }
        t = Trophy.from_row(row)
        assert t.earned is False
        assert t.earned_date_time is None


class TestGameStatsFromRow:
    def test_all_fields(self) -> None:
        row = {
            "np_communication_id": "NPWR001",
            "title_id": "TITLE001",
            "total_seconds": 36000,
            "play_count": 42,
            "first_played": "2024-01-01T00:00:00Z",
            "last_played": "2024-12-25T10:00:00Z",
        }
        gs = GameStats.from_row(row)
        assert gs is not None
        assert gs.title_id == "TITLE001"
        assert gs.total_seconds == 36000
        assert gs.play_count == 42

    def test_none_row(self) -> None:
        assert GameStats.from_row(None) is None


class TestFriendFromRow:
    def test_all_fields(self) -> None:
        row = {
            "account_id": "acc001",
            "online_id": "Player1",
            "trophy_level": 250,
            "platinum": 10,
            "gold": 50,
            "silver": 100,
            "bronze": 500,
            "total": 660,
            "is_private": 0,
        }
        f = Friend.from_row(row)
        assert f.online_id == "Player1"
        assert f.trophy_level == 250
        assert f.total == 660
        assert f.is_private is False


class TestFriendGameFromRow:
    def test_all_fields(self) -> None:
        row = {
            "account_id": "acc001",
            "np_communication_id": "NPWR001",
            "progress": 80,
            "earned_platinum": 0,
            "earned_gold": 3,
            "earned_silver": 8,
            "earned_bronze": 30,
            "online_id": "Player1",
            "is_private": 0,
        }
        fg = FriendGame.from_row(row)
        assert fg.progress == 80
        assert fg.online_id == "Player1"
