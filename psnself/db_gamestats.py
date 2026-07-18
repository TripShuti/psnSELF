from __future__ import annotations

import sqlite3
from datetime import date

MAX_DELTA_SECONDS = 86400


def get_game_stats(conn: sqlite3.Connection, np_comm_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM game_stats WHERE np_communication_id = ?", (np_comm_id,)
    ).fetchone()


def update_game_stats(conn: sqlite3.Connection, np_comm_id: str,
                      title_id: str | None,
                      total_seconds: int,
                      play_count: int | None,
                      first_played: str | None,
                      last_played: str | None) -> None:
    old = conn.execute(
        "SELECT total_seconds FROM game_stats WHERE np_communication_id = ?",
        (np_comm_id,)
    ).fetchone()

    conn.execute("""
        INSERT INTO game_stats
            (np_communication_id, title_id, total_seconds, play_count, first_played, last_played)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(np_communication_id) DO UPDATE SET
            title_id = excluded.title_id,
            total_seconds = excluded.total_seconds,
            play_count = excluded.play_count,
            first_played = excluded.first_played,
            last_played = excluded.last_played
    """, (np_comm_id, title_id, total_seconds, play_count or 0,
          first_played, last_played))

    if old is not None:
        delta = total_seconds - old["total_seconds"]
        if delta > 0:
            play_date = last_played[:10] if last_played else date.today().isoformat()
            conn.execute("""
                INSERT INTO play_delta_history (np_communication_id, date, delta_seconds)
                VALUES (?, ?, ?)
                ON CONFLICT(np_communication_id, date)
                DO UPDATE SET delta_seconds = delta_seconds + excluded.delta_seconds
            """, (np_comm_id, play_date, delta))


def get_play_time(conn: sqlite3.Connection, np_comm_id: str,
                  since: str, until: str) -> int:
    row = conn.execute("""
        SELECT COALESCE(SUM(delta_seconds), 0) as total
        FROM play_delta_history
        WHERE np_communication_id = ? AND date >= ? AND date <= ?
    """, (np_comm_id, since, until)).fetchone()
    return row["total"] if row else 0


def get_total_play_time(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(total_seconds), 0) as total FROM game_stats"
    ).fetchone()
    return row["total"] if row else 0


def get_total_play_delta(conn: sqlite3.Connection,
                         since: str, until: str) -> int:
    row = conn.execute("""
        SELECT COALESCE(SUM(delta_seconds), 0) as total
        FROM play_delta_history
        WHERE date >= ? AND date <= ?
    """, (since, until)).fetchone()
    return row["total"] if row else 0


def _month_bounds(year: int, month: int) -> tuple[str, str]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start.isoformat(), end.isoformat()


def get_daily_play_time(conn: sqlite3.Connection,
                        year: int, month: int) -> dict[str, int]:
    since, until = _month_bounds(year, month)
    rows = conn.execute("""
        SELECT date, COALESCE(SUM(delta_seconds), 0) as total
        FROM play_delta_history
        WHERE date >= ? AND date < ?
        GROUP BY date
    """, (since, until)).fetchall()
    return {r["date"]: r["total"] for r in rows}


def get_daily_play_details(conn: sqlite3.Connection,
                           date_str: str) -> list[dict]:
    return conn.execute("""
        SELECT g.title_name, pdh.delta_seconds
        FROM play_delta_history pdh
        JOIN games g ON g.np_communication_id = pdh.np_communication_id
        WHERE pdh.date = ? AND pdh.delta_seconds > 0
        ORDER BY pdh.delta_seconds DESC
    """, (date_str,)).fetchall()


def set_manual_play_time(conn: sqlite3.Connection,
                         np_comm_id: str,
                         total_seconds: int) -> None:
    old = conn.execute(
        "SELECT total_seconds FROM game_stats WHERE np_communication_id = ?",
        (np_comm_id,)
    ).fetchone()
    delta = total_seconds - (old["total_seconds"] if old else 0)
    conn.execute("""
        INSERT INTO game_stats
            (np_communication_id, title_id, total_seconds, play_count)
        VALUES (?, NULL, ?, 0)
        ON CONFLICT(np_communication_id) DO UPDATE SET
            title_id = NULL,
            total_seconds = excluded.total_seconds,
            play_count = 0
    """, (np_comm_id, total_seconds))
    if delta > 0:
        today = date.today().isoformat()
        conn.execute("""
            INSERT INTO play_delta_history (np_communication_id, date, delta_seconds)
            VALUES (?, ?, ?)
            ON CONFLICT(np_communication_id, date)
            DO UPDATE SET delta_seconds = delta_seconds + excluded.delta_seconds
        """, (np_comm_id, today, delta))
