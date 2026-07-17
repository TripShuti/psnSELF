from __future__ import annotations

import sqlite3
from pathlib import Path
from datetime import datetime
import threading

from psnself.db_gamestats import MAX_DELTA_SECONDS

_HERE = Path(__file__).parent

DB_PATH: Path | None = None

_local = threading.local()


_lock = threading.Lock()


def set_db_path(path: Path) -> None:
    global DB_PATH
    with _lock:
        DB_PATH = path


def get_conn() -> sqlite3.Connection:
    if DB_PATH is None:
        raise RuntimeError("DB_PATH not set")
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.execute("SELECT 1")
            path_match = conn.execute(
                "PRAGMA database_list"
            ).fetchone()
            if path_match and path_match[2] == str(DB_PATH):
                return conn
        except sqlite3.DatabaseError:
            try:
                conn.close()
            except sqlite3.Error:
                pass
    conn = sqlite3.connect(str(DB_PATH), timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _local.conn = conn
    return conn


def close_conn() -> None:
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except sqlite3.Error:
            pass
        _local.conn = None


def _read_schema() -> str:
    return (_HERE / "schema.sql").read_text()


def init_db() -> None:
    conn = get_conn()
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.OperationalError:
        pass
    conn.executescript(_read_schema())

    conn.execute(
        "DELETE FROM play_delta_history WHERE delta_seconds > ?",
        (MAX_DELTA_SECONDS,)
    )

    try:
        conn.execute(
            "UPDATE sync_log SET status = 'error', error_message = 'Cancelled (stuck)',"
            " finished_at = datetime('now') WHERE status = 'running'"
        )
        conn.commit()
    except sqlite3.OperationalError:
        conn.rollback()


def upsert_game(conn: sqlite3.Connection, g: dict) -> None:
    conn.execute("""
        INSERT INTO games (
            np_communication_id, np_title_id, title_name, title_icon_url, platform,
            defined_bronze, defined_silver, defined_gold, defined_platinum,
            earned_bronze, earned_silver, earned_gold, earned_platinum,
            progress, last_updated_datetime, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(np_communication_id) DO UPDATE SET
            np_title_id=excluded.np_title_id, title_name=excluded.title_name,
            title_icon_url=excluded.title_icon_url, platform=excluded.platform,
            defined_bronze=excluded.defined_bronze, defined_silver=excluded.defined_silver,
            defined_gold=excluded.defined_gold, defined_platinum=excluded.defined_platinum,
            earned_bronze=excluded.earned_bronze, earned_silver=excluded.earned_silver,
            earned_gold=excluded.earned_gold, earned_platinum=excluded.earned_platinum,
            progress=excluded.progress, last_updated_datetime=excluded.last_updated_datetime,
            updated_at=excluded.updated_at
    """, (
        g["np_communication_id"], g.get("np_title_id"), g["title_name"],
        g.get("title_icon_url"), g.get("platform"),
        g.get("defined_bronze", 0), g.get("defined_silver", 0),
        g.get("defined_gold", 0), g.get("defined_platinum", 0),
        g.get("earned_bronze", 0), g.get("earned_silver", 0),
        g.get("earned_gold", 0), g.get("earned_platinum", 0),
        g.get("progress", 0), g.get("last_updated_datetime"),
    ))


def upsert_trophy(conn: sqlite3.Connection, t: dict) -> None:
    conn.execute("""
        INSERT INTO trophies (
            np_communication_id, trophy_id, trophy_name, trophy_detail,
            trophy_type, trophy_icon_url, trophy_hidden, trophy_group_id,
            earned, earned_date_time, trophy_rarity, trophy_earn_rate,
            progress, progress_rate
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(np_communication_id, trophy_id) DO UPDATE SET
            trophy_name=excluded.trophy_name, trophy_detail=excluded.trophy_detail,
            trophy_type=excluded.trophy_type, trophy_icon_url=excluded.trophy_icon_url,
            trophy_hidden=excluded.trophy_hidden,
            earned=excluded.earned, earned_date_time=excluded.earned_date_time,
            trophy_rarity=excluded.trophy_rarity, trophy_earn_rate=excluded.trophy_earn_rate,
            progress=excluded.progress, progress_rate=excluded.progress_rate
    """, (
        t["np_communication_id"], t["trophy_id"], t.get("trophy_name"),
        t.get("trophy_detail"), t.get("trophy_type"), t.get("trophy_icon_url"),
        int(t.get("trophy_hidden", False)), t.get("trophy_group_id", "default"),
        int(t.get("earned", False)), t.get("earned_date_time"),
        t.get("trophy_rarity"), t.get("trophy_earn_rate"),
        t.get("progress"), t.get("progress_rate"),
    ))


def write_game_with_trophies(conn: sqlite3.Connection, game: dict, trophies: list[dict]) -> None:
    upsert_game(conn, game)
    for t in trophies:
        upsert_trophy(conn, t)


def start_sync(conn: sqlite3.Connection) -> int:
    cur = conn.execute("INSERT INTO sync_log (started_at) VALUES (datetime('now'))")
    return cur.lastrowid or 0


def finish_sync(conn: sqlite3.Connection, sync_id: int, status: str, trophies_added: int = 0,
                games_updated: int = 0, error_message: str | None = None) -> None:
    conn.execute("""
        UPDATE sync_log SET finished_at = datetime('now'), status = ?, trophies_added = ?,
            games_updated = ?, error_message = ?
        WHERE id = ?
    """, (status, trophies_added, games_updated, error_message, sync_id))


def get_last_sync_time(conn: sqlite3.Connection) -> datetime | None:
    row = conn.execute(
        "SELECT started_at FROM sync_log WHERE status = 'success' ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    if row:
        try:
            return datetime.fromisoformat(row["started_at"])
        except ValueError:
            return None
    return None


def game_exists(conn: sqlite3.Connection, np_comm_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM games WHERE np_communication_id = ?", (np_comm_id,)
    ).fetchone()
    return row is not None


def get_games(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("""
        SELECT g.*, COALESCE(gs.total_seconds, 0) as play_seconds
        FROM games g
        LEFT JOIN game_stats gs ON gs.np_communication_id = g.np_communication_id
        ORDER BY g.last_updated_datetime DESC NULLS LAST
    """).fetchall()


def get_game(conn: sqlite3.Connection, np_comm_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM games WHERE np_communication_id = ?", (np_comm_id,)
    ).fetchone()


def get_trophies(conn: sqlite3.Connection, np_comm_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM trophies WHERE np_communication_id = ? ORDER BY trophy_id",
        (np_comm_id,)
    ).fetchall()


def get_recent_earned(conn: sqlite3.Connection, limit: int = 10) -> list[sqlite3.Row]:
    return conn.execute("""
        SELECT t.*, g.title_name, g.title_icon_url
        FROM trophies t
        JOIN games g ON g.np_communication_id = t.np_communication_id
        WHERE t.earned = 1 AND t.earned_date_time IS NOT NULL
        ORDER BY t.earned_date_time DESC
        LIMIT ?
    """, (limit,)).fetchall()



def get_earned_by_date_range(conn: sqlite3.Connection, since: str, until: str) -> list[sqlite3.Row]:
    return conn.execute("""
        SELECT DATE(earned_date_time) as day, COUNT(*) as count
        FROM trophies
        WHERE earned = 1 AND earned_date_time >= ? AND earned_date_time < ?
        GROUP BY DATE(earned_date_time)
        ORDER BY day
    """, (since, until)).fetchall()


def get_rarest_trophies(conn: sqlite3.Connection, limit: int = 5) -> list[dict]:
    rows = conn.execute("""
        SELECT t.trophy_name, t.trophy_rarity,
               ROUND(COALESCE(t.trophy_earn_rate, 0), 1) as trophy_earn_rate,
               t.trophy_type, g.title_name
        FROM trophies t
        LEFT JOIN games g ON g.np_communication_id = t.np_communication_id
        WHERE t.earned = 1 AND t.trophy_earn_rate IS NOT NULL
        ORDER BY t.trophy_earn_rate ASC
        LIMIT ?
    """, (limit,)).fetchall()
    return [dict(r) for r in rows]


def get_trophies_by_date(conn: sqlite3.Connection, date_str: str) -> list[sqlite3.Row]:
    return conn.execute("""
        SELECT t.*, g.title_name
        FROM trophies t
        JOIN games g ON g.np_communication_id = t.np_communication_id
        WHERE t.earned = 1 AND DATE(t.earned_date_time) = ?
        ORDER BY t.earned_date_time
    """, (date_str,)).fetchall()


