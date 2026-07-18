from __future__ import annotations

import time
import sqlite3
from typing import Any

from psnawp_api import PSNAWP

from .. import db
from .. import db_gamestats
from ..sync import sync_lock
from ..log import get_logger
from .extractor import (
    _DEFAULT_RATE_LIMIT,
    _ensure_request_timeout,
    _ensure_utc,
    _extract_game_data,
    _extract_trophy_data,
    _get_platform,
    _normalize_name,
    _parse_date_utc,
    ProgressCB,
)

logger = get_logger("trophy_sync")


def sync_trophies(npsso: str, progress_callback: ProgressCB = None) -> dict[str, Any]:
    with sync_lock:
        return _do_sync(npsso, progress_callback)


def _do_sync(npsso: str, progress_callback: ProgressCB = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "success",
        "trophies_added": 0,
        "games_updated": 0,
        "error": None,
        "warnings": [],
    }

    conn: sqlite3.Connection | None = None
    sync_id = 0
    last_sync = None
    last_sync_utc = None

    for attempt in range(3):
        try:
            conn = db.get_conn()
        except sqlite3.Error as e:
            result["status"] = "error"
            result["error"] = f"Database connection failed: {e}"
            return result

        conn.rollback()
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.OperationalError:
            pass

        try:
            last_sync = db.get_last_sync_time(conn)
            last_sync_utc = _ensure_utc(last_sync) if last_sync else None
            sync_id = db.start_sync(conn)
            conn.commit()
            break
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and attempt < 2:
                conn.rollback()
                time.sleep(2)
                continue
            result["status"] = "error"
            result["error"] = f"Database locked after retries: {e}"
            return result

    if conn is None:
        result["status"] = "error"
        result["error"] = "Database connection failed after retries"
        return result

    try:
        _ensure_request_timeout()
        psnawp = PSNAWP(npsso_cookie=npsso, rate_limit=_DEFAULT_RATE_LIMIT)
        client = psnawp.me()
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"Authentication failed: {e}"
        db.finish_sync(conn, sync_id, "error", error_message=str(e))
        conn.commit()
        return result

    logger.info("Starting trophy sync for %s", client.online_id)
    _t0 = time.time()
    all_titles = list(client.trophy_titles(limit=None))
    logger.info("Found %d titles on account", len(all_titles))

    stats_by_id: dict[str, Any] = {}
    stats_by_name: dict[str, Any] = {}
    try:
        for ts in client.title_stats(limit=None):
            if ts.title_id and ts.title_id not in stats_by_id:
                stats_by_id[ts.title_id] = ts
            if ts.name:
                key = _normalize_name(ts.name)
                if key not in stats_by_name:
                    stats_by_name[key] = ts
    except (ValueError, TypeError, OSError) as e:
        result["warnings"].append(f"Could not fetch play time stats: {e}")

    for idx, title in enumerate(all_titles):
        if progress_callback:
            progress_callback(idx, len(all_titles), title.title_name or "")

        np_comm_id = title.np_communication_id
        if not np_comm_id:
            continue

        game_in_db = db.game_exists(conn, np_comm_id)
        needs_update = not game_in_db

        if not needs_update and title.last_updated_datetime and last_sync_utc:
            ts = _ensure_utc(title.last_updated_datetime)
            needs_update = ts > last_sync_utc

        if needs_update:
            logger.debug("Processing %s (%s)", title.title_name, np_comm_id)
            platform = _get_platform(title)
            try:
                trophies = list(
                    client.trophies(
                        np_comm_id,
                        platform,
                        include_progress=True,
                    )
                )
            except Exception as e:
                if len(result["warnings"]) < 20:
                    result["warnings"].append(f"Skipped {title.title_name}: {e}")
                continue

            trophy_dicts = []
            for t in trophies:
                try:
                    trophy_dicts.append(_extract_trophy_data(np_comm_id, t))
                except (KeyError, TypeError):
                    continue
            game_data = _extract_game_data(title)

            db.write_game_with_trophies(conn, game_data, trophy_dicts)

            result["games_updated"] += 1
            if last_sync_utc:
                new_trophies = [
                    t
                    for t in trophy_dicts
                    if t["earned"]
                    and t["earned_date_time"]
                    and _parse_date_utc(t["earned_date_time"]) > last_sync_utc
                ]
                result["trophies_added"] += len(new_trophies)
            else:
                result["trophies_added"] += sum(1 for t in trophy_dicts if t["earned"])

        ts_stats = stats_by_id.get(title.np_title_id or "")
        if not ts_stats:
            ts_stats = stats_by_name.get(_normalize_name(title.title_name or ""))
        if ts_stats:
            if ts_stats.title_id and ts_stats.title_id != title.np_title_id:
                conn.execute(
                    "UPDATE games SET np_title_id = ? WHERE np_communication_id = ?",
                    (ts_stats.title_id, np_comm_id)
                )
            if ts_stats.play_duration is not None:
                psn_secs = int(ts_stats.play_duration.total_seconds())
                existing_gs = db_gamestats.get_game_stats(conn, np_comm_id)
                if existing_gs and existing_gs["title_id"] is None and psn_secs == 0:
                    continue
                db_gamestats.update_game_stats(
                    conn, np_comm_id,
                    title_id=ts_stats.title_id,
                    total_seconds=psn_secs,
                    play_count=ts_stats.play_count,
                    first_played=ts_stats.first_played_date_time.isoformat()
                    if ts_stats.first_played_date_time else None,
                    last_played=ts_stats.last_played_date_time.isoformat()
                    if ts_stats.last_played_date_time else None,
                )
        else:
            existing = db_gamestats.get_game_stats(conn, np_comm_id)
            if not existing or existing["total_seconds"] == 0:
                title_id_hint = ""
                if title.np_title_id:
                    title_id_hint = f" (id={title.np_title_id})"
                result["warnings"].append(
                    f"No play time data for '{title.title_name}'{title_id_hint} "
                    f"— not in PSN gamelist"
                )

    _elapsed = time.time() - _t0
    try:
        db.finish_sync(
            conn, sync_id, result["status"],
            trophies_added=result["trophies_added"],
            games_updated=result["games_updated"],
        )
        conn.commit()
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"Failed to finalise sync: {e}"

    logger.info(
        "Sync done: +%d trophies, %d games (took %.1fs, %d warnings)",
        result["trophies_added"], result["games_updated"],
        _elapsed, len(result.get("warnings", [])),
    )
    return result
