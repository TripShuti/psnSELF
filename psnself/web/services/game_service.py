from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Optional

from psnself import db
from psnself import db_gamestats
from psnself.models import Game, GameStats, Trophy


class GameService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_games(self) -> list[Game]:
        return [Game.from_row(r) for r in db.get_games(self.conn)]

    def get_game(self, np_comm_id: str) -> Optional[Game]:
        row = db.get_game(self.conn, np_comm_id)
        return Game.from_row(row) if row else None

    def get_trophies(self, np_comm_id: str) -> list[Trophy]:
        return [Trophy.from_row(r) for r in db.get_trophies(self.conn, np_comm_id)]

    def get_game_stats(self, np_comm_id: str) -> Optional[GameStats]:
        return GameStats.from_row(db_gamestats.get_game_stats(self.conn, np_comm_id))

    def get_play_time(self, np_comm_id: str, since: str, until: str) -> int:
        return db_gamestats.get_play_time(self.conn, np_comm_id, since, until)

    def get_rarest(self, limit: int = 5) -> list[dict]:
        return db.get_rarest_trophies(self.conn, limit=limit)

    def set_manual_time(self, np_comm_id: str, seconds: int) -> None:
        db_gamestats.set_manual_play_time(self.conn, np_comm_id, seconds)
        self.conn.commit()

    def get_recent(self, limit: int = 10) -> list[Trophy]:
        return [Trophy.from_row(r) for r in db.get_recent_earned(self.conn, limit=limit)]

    def get_play_time_periods(self, np_comm_id: str) -> dict:
        today = date.today()
        today_sec = self.get_play_time(np_comm_id, today.isoformat(), today.isoformat())
        week_start = today - timedelta(days=today.weekday())
        week_sec = self.get_play_time(np_comm_id, week_start.isoformat(), today.isoformat())
        month_sec = self.get_play_time(np_comm_id, today.replace(day=1).isoformat(), today.isoformat())
        return {"today_sec": today_sec, "week_sec": week_sec, "month_sec": month_sec}
