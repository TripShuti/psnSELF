from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

Optional = Optional  # keep for runtime -- no-op alias


@dataclass
class Game:
    np_communication_id: str
    title_name: str
    platform: str
    progress: int
    earned_platinum: int
    earned_gold: int
    earned_silver: int
    earned_bronze: int
    np_title_id: str = ""
    last_updated_datetime: Optional[str] = None
    play_seconds: int = 0

    @staticmethod
    def from_row(row) -> Game:
        row = dict(row)
        return Game(
            np_communication_id=row["np_communication_id"],
            title_name=row["title_name"],
            platform=row["platform"],
            progress=row["progress"],
            earned_platinum=row["earned_platinum"],
            earned_gold=row["earned_gold"],
            earned_silver=row["earned_silver"],
            earned_bronze=row["earned_bronze"],
            np_title_id=row.get("np_title_id", ""),
            last_updated_datetime=row.get("last_updated_datetime"),
            play_seconds=row.get("play_seconds", 0),
        )


@dataclass
class Trophy:
    np_communication_id: str
    trophy_id: str
    trophy_name: str
    trophy_type: str
    trophy_rarity: Optional[str] = None
    trophy_earn_rate: Optional[float] = None
    earned: bool = False
    earned_date_time: Optional[str] = None
    title_name: str = ""

    @staticmethod
    def from_row(row) -> Trophy:
        row = dict(row)
        return Trophy(
            np_communication_id=row["np_communication_id"],
            trophy_id=row["trophy_id"],
            trophy_name=row["trophy_name"],
            trophy_type=row["trophy_type"],
            trophy_rarity=row.get("trophy_rarity"),
            trophy_earn_rate=row.get("trophy_earn_rate"),
            earned=bool(row.get("earned", 0)),
            earned_date_time=row.get("earned_date_time"),
            title_name=row.get("title_name", ""),
        )


@dataclass
class GameStats:
    np_communication_id: str
    title_id: Optional[str] = None
    total_seconds: int = 0
    play_count: int = 0
    first_played: Optional[str] = None
    last_played: Optional[str] = None

    @staticmethod
    def from_row(row) -> Optional[GameStats]:
        if row is None:
            return None
        row = dict(row)
        return GameStats(
            np_communication_id=row["np_communication_id"],
            title_id=row.get("title_id"),
            total_seconds=row.get("total_seconds", 0),
            play_count=row.get("play_count", 0),
            first_played=row.get("first_played"),
            last_played=row.get("last_played"),
        )


@dataclass
class Friend:
    account_id: str
    online_id: str
    trophy_level: Optional[int] = None
    platinum: int = 0
    gold: int = 0
    silver: int = 0
    bronze: int = 0
    total: int = 0
    is_private: bool = False

    @staticmethod
    def from_row(row) -> Friend:
        row = dict(row)
        return Friend(
            account_id=row["account_id"],
            online_id=row["online_id"],
            trophy_level=row.get("trophy_level"),
            platinum=row.get("platinum", 0),
            gold=row.get("gold", 0),
            silver=row.get("silver", 0),
            bronze=row.get("bronze", 0),
            total=row.get("total", 0),
            is_private=bool(row.get("is_private", 0)),
        )


@dataclass
class FriendGame:
    account_id: str
    np_communication_id: str
    progress: int = 0
    earned_platinum: int = 0
    earned_gold: int = 0
    earned_silver: int = 0
    earned_bronze: int = 0
    online_id: str = ""
    is_private: bool = False

    @staticmethod
    def from_row(row) -> FriendGame:
        row = dict(row)
        return FriendGame(
            account_id=row["account_id"],
            np_communication_id=row["np_communication_id"],
            progress=row.get("progress", 0),
            earned_platinum=row.get("earned_platinum", 0),
            earned_gold=row.get("earned_gold", 0),
            earned_silver=row.get("earned_silver", 0),
            earned_bronze=row.get("earned_bronze", 0),
            online_id=row.get("online_id", ""),
            is_private=bool(row.get("is_private", 0)),
        )



