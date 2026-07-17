from __future__ import annotations

import sqlite3
from typing import Optional

from psnself import db_friends
from psnself.models import Friend, FriendGame


class FriendService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_leaderboard(self) -> list[Friend]:
        return [Friend.from_row(r) for r in db_friends.get_friends_leaderboard(self.conn)]

    def get_by_account_id(self, account_id: str) -> Optional[Friend]:
        row = db_friends.get_friend_by_account_id(self.conn, account_id)
        return Friend.from_row(row) if row else None

    def get_comparison(self, np_comm_id: str) -> list[FriendGame]:
        return [FriendGame.from_row(r) for r in db_friends.get_friend_game_comparison(self.conn, np_comm_id)]

    def get_comparison_detail(self, friend_account_id: str) -> list[dict]:
        return [dict(r) for r in db_friends.get_friend_comparison_detail(self.conn, friend_account_id)]

    def get_fetched_at_label(self) -> str:
        fetched_at = db_friends.get_friends_fetched_at(self.conn)
        if not fetched_at:
            return "Never refreshed — press Refresh now above"
        from datetime import datetime
        dt = datetime.fromisoformat(fetched_at)
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        mins = int((now - dt).total_seconds() // 60)
        return f"Last updated {mins} min ago" if mins < 60 else f"Last updated {mins // 60}h ago"

    def get_raw_friend(self, account_id: str) -> Optional[dict]:
        return db_friends.get_raw_friend(self.conn, account_id)

    def get_raw_level(self, account_id: str) -> Optional[dict]:
        return db_friends.get_raw_trophy_level(self.conn, account_id)
