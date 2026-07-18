from __future__ import annotations

import sqlite3
from calendar import Calendar
from datetime import date, timedelta

from psnself import db
from psnself import db_gamestats
from psnself.models import Trophy
from psnself.web.utils import fmt_hms


class StatsService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def build_heatmap(self, today: date, weeks_back: int = 10) -> dict:
        start_date = today - timedelta(weeks=weeks_back, days=today.weekday())
        since = start_date.isoformat()
        until = (today + timedelta(days=1)).isoformat()
        earned_rows = db.get_earned_by_date_range(self.conn, since, until)
        counts = {r["day"]: r["count"] for r in earned_rows}
        max_count = max(counts.values(), default=1)

        week_labels = [(start_date + timedelta(weeks=w)).strftime("%b %d") for w in range(weeks_back + 1)]
        levels = ["#0d5a45", "#1a7a65", "#2a9a80", "#3abaa0", "#00c8a0"]
        rows = []
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for d_idx, day_name in enumerate(day_names):
            cells = []
            for w in range(weeks_back + 1):
                cell_date = start_date + timedelta(weeks=w, days=d_idx)
                if cell_date > today:
                    cells.append({"count": None})
                    continue
                count = counts.get(cell_date.isoformat(), 0)
                if count == 0:
                    color = levels[0]
                else:
                    idx = min(int((count / max_count) * (len(levels) - 1)) + 1, len(levels) - 1) if max_count else len(levels) - 1
                    color = levels[idx]
                cells.append({"count": count, "date": cell_date.isoformat(), "color": color})
            rows.append((day_name, cells))
        return {"week_labels": week_labels, "rows": rows}

    def get_playtime_summary(self, today: date) -> dict:
        day_start = today.isoformat()
        week_start = (today - timedelta(days=today.weekday())).isoformat()
        month_start = date(today.year, today.month, 1).isoformat()
        tomorrow = (today + timedelta(days=1)).isoformat()
        return {
            "total": fmt_hms(db_gamestats.get_total_play_time(self.conn)),
            "today": fmt_hms(db_gamestats.get_total_play_delta(self.conn, day_start, tomorrow)),
            "week": fmt_hms(db_gamestats.get_total_play_delta(self.conn, week_start, tomorrow)),
            "month": fmt_hms(db_gamestats.get_total_play_delta(self.conn, month_start, tomorrow)),
        }

    def get_daily_counts(self, date_str: str) -> list[Trophy]:
        return [Trophy.from_row(r) for r in db.get_trophies_by_date(self.conn, date_str)]

    def get_calendar_data(self, year: int, month: int) -> list:
        daily = db_gamestats.get_daily_play_time(self.conn, year, month)
        cal = Calendar(firstweekday=0)
        cells = []
        for day in cal.itermonthdates(year, month):
            if day.month != month:
                cells.append(None)
                continue
            secs = daily.get(day.isoformat(), 0)
            cells.append({
                "day": day.day, "date": day.isoformat(),
                "seconds": secs, "label": fmt_hms(secs) if secs else "",
            })
        return cells

    def get_range_play_details(self, since: str, until: str) -> list[dict]:
        raw = db_gamestats.get_play_time_detail_by_range(self.conn, since, until)
        return [{"title_name": r["title_name"], "label": fmt_hms(r["delta_seconds"])} for r in raw]

    def get_play_day_details(self, date_str: str) -> list[dict]:
        raw = db_gamestats.get_daily_play_details(self.conn, date_str)
        return [{"title_name": r["title_name"], "label": fmt_hms(r["delta_seconds"])} for r in raw]
