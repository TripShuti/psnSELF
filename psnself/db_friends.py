from __future__ import annotations

import sqlite3


def upsert_friend(conn: sqlite3.Connection, f: dict) -> None:
    conn.execute("""
        INSERT INTO friends_cache
            (account_id, online_id, trophy_level, platinum, gold, silver, bronze,
             is_private, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(account_id)
        DO UPDATE SET
            online_id = excluded.online_id,
            trophy_level = excluded.trophy_level,
            platinum = excluded.platinum,
            gold = excluded.gold,
            silver = excluded.silver,
            bronze = excluded.bronze,
            is_private = excluded.is_private,
            fetched_at = excluded.fetched_at
    """, (
        f["account_id"], f["online_id"], f.get("trophy_level"),
        f.get("platinum", 0), f.get("gold", 0), f.get("silver", 0),
        f.get("bronze", 0), f.get("is_private", 0), f["fetched_at"],
    ))


def upsert_friend_game(conn: sqlite3.Connection, fg: dict) -> None:
    conn.execute("""
        INSERT INTO friend_game_cache
            (account_id, np_communication_id, progress,
             earned_platinum, earned_gold, earned_silver, earned_bronze,
             is_private, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(account_id, np_communication_id)
        DO UPDATE SET
            progress = excluded.progress,
            earned_platinum = excluded.earned_platinum,
            earned_gold = excluded.earned_gold,
            earned_silver = excluded.earned_silver,
            earned_bronze = excluded.earned_bronze,
            is_private = excluded.is_private,
            fetched_at = excluded.fetched_at
    """, (
        fg["account_id"], fg["np_communication_id"], fg.get("progress"),
        fg.get("earned_platinum", 0), fg.get("earned_gold", 0),
        fg.get("earned_silver", 0), fg.get("earned_bronze", 0),
        fg.get("is_private", 0), fg["fetched_at"],
    ))


def get_friends_leaderboard(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("""
        SELECT *, (COALESCE(platinum,0) + COALESCE(gold,0)
                   + COALESCE(silver,0) + COALESCE(bronze,0)) as total
        FROM friends_cache
        ORDER BY trophy_level DESC
    """).fetchall()


def get_friend_game_comparison(conn: sqlite3.Connection,
                                np_comm_id: str) -> list[sqlite3.Row]:
    return conn.execute("""
        SELECT fgc.*, fc.online_id,
            (COALESCE(earned_platinum,0) + COALESCE(earned_gold,0)
             + COALESCE(earned_silver,0) + COALESCE(earned_bronze,0)) as earned_total
        FROM friend_game_cache fgc
        JOIN friends_cache fc ON fc.account_id = fgc.account_id
        WHERE fgc.np_communication_id = ?
        ORDER BY earned_total DESC
    """, (np_comm_id,)).fetchall()


def get_friend_comparison_detail(conn: sqlite3.Connection,
                                  friend_account_id: str) -> list[sqlite3.Row]:
    return conn.execute("""
        SELECT
          g.title_name, g.platform,
          g.progress AS my_progress,
          g.earned_platinum AS my_plat, g.earned_gold AS my_gold,
          g.earned_silver AS my_silver, g.earned_bronze AS my_bronze,
          COALESCE(gs.total_seconds, 0) AS my_seconds,
          fgc.progress AS friend_progress,
          fgc.earned_platinum AS friend_plat, fgc.earned_gold AS friend_gold,
          fgc.earned_silver AS friend_silver, fgc.earned_bronze AS friend_bronze
        FROM friend_game_cache fgc
        JOIN games g ON g.np_communication_id = fgc.np_communication_id
        LEFT JOIN game_stats gs ON gs.np_communication_id = fgc.np_communication_id
        WHERE fgc.account_id = ?
          AND fgc.is_private = 0
        ORDER BY g.title_name
    """, (friend_account_id,)).fetchall()


def get_friend_by_account_id(conn: sqlite3.Connection,
                              account_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT *, (COALESCE(platinum,0) + COALESCE(gold,0)"
        " + COALESCE(silver,0) + COALESCE(bronze,0)) as total"
        " FROM friends_cache WHERE account_id = ?",
        (account_id,)
    ).fetchone()


def get_raw_friend(conn: sqlite3.Connection, account_id: str) -> dict | None:
    row = conn.execute(
        "SELECT online_id, trophy_level, platinum, gold, silver, bronze FROM friends_cache WHERE account_id = ?",
        (account_id,)
    ).fetchone()
    return dict(row) if row else None


def get_raw_trophy_level(conn: sqlite3.Connection, account_id: str) -> dict | None:
    row = conn.execute(
        "SELECT trophy_level FROM friends_cache WHERE account_id = ?",
        (account_id,)
    ).fetchone()
    return dict(row) if row else None


def get_raw_trophy_level_by_online_id(conn: sqlite3.Connection, online_id: str) -> dict | None:
    row = conn.execute(
        "SELECT trophy_level FROM friends_cache WHERE online_id = ?",
        (online_id,)
    ).fetchone()
    return dict(row) if row else None


def get_friends_fetched_at(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT MAX(fetched_at) as fetched_at FROM friends_cache"
    ).fetchone()
    return row["fetched_at"] if row and row["fetched_at"] else None


def delete_stale_friends(conn: sqlite3.Connection,
                          active_ids: set[str],
                          self_account_id: str) -> int:
    if not active_ids:
        return 0
    placeholders = ",".join("?" for _ in active_ids)
    params = (*active_ids, self_account_id)
    conn.execute(f"""
        DELETE FROM friend_game_cache
        WHERE account_id NOT IN ({placeholders})
          AND account_id != ?
    """, params)
    cur = conn.execute(f"""
        DELETE FROM friends_cache
        WHERE account_id NOT IN ({placeholders})
          AND account_id != ?
    """, params)
    friend_deleted = cur.rowcount
    return friend_deleted
