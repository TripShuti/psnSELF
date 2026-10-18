from __future__ import annotations

import time
import sqlite3
from typing import Any

from psnawp_api import PSNAWP
from psnawp_api.models.trophies.trophy_titles import BASE_PATH, API_PATH

from .. import db
from .. import db_gamestats
from ..sync import sync_lock
from ..log import get_logger
from .extractor import (
    _DEFAULT_RATE_LIMIT,
    _ensure_request_timeout,
    _ensure_utc,
    _extract_game_data,
    _extract_group_data,
    _extract_trophy_data,
    _get_platform,
    _normalize_name,
    _parse_date_utc,
    ProgressCB,
)

logger = get_logger("trophy_sync")


def _find_ts_stats(
    conn: sqlite3.Connection,
    title: Any,
    np_comm_id: str,
    stats_by_id: dict[str, Any],
    stats_by_name: dict[str, Any],
) -> Any | None:
    # Match a trophy title to its PSN gamelist (play time) entry.
    # The API title often has np_title_id=None and Sony sometimes renames
    # the gamelist entry ("Genshin Impact" -> "Genshin Impact 6th
    # Anniversary"), so fall back to title IDs already stored in the DB
    # and to a rename-tolerant name lookup.
    title_ids: list[str] = []
    api_tid = getattr(title, "np_title_id", None)
    if api_tid and api_tid not in title_ids:
        title_ids.append(api_tid)
    try:
        row = conn.execute(
            "SELECT np_title_id FROM games WHERE np_communication_id = ?",
            (np_comm_id,),
        ).fetchone()
        if row and row["np_title_id"] and row["np_title_id"] not in title_ids:
            title_ids.append(row["np_title_id"])
    except sqlite3.Error:
        pass
    try:
        gs = db_gamestats.get_game_stats(conn, np_comm_id)
        if gs and gs["title_id"] and gs["title_id"] not in title_ids:
            title_ids.append(gs["title_id"])
    except sqlite3.Error:
        pass
    for tid in title_ids:
        if tid in stats_by_id:
            return stats_by_id[tid]

    key = _normalize_name(getattr(title, "title_name", None) or "")
    if not key:
        return None
    if key in stats_by_name:
        return stats_by_name[key]
    # Rename-tolerant fallback: gamelist entry kept the base name and gained
    # a suffix. Only accept an unambiguous single candidate so that e.g.
    # "Game" never grabs play time of "Game II" when both exist.
    candidates: list[Any] = []
    for stats_key, ts in stats_by_name.items():
        if (stats_key == key
                or stats_key.startswith((key + " ", key + ":"))
                or key.startswith((stats_key + " ", stats_key + ":"))):
            if not any(c is ts for c in candidates):
                candidates.append(ts)
    if len(candidates) == 1:
        return candidates[0]
    return None


def _resolve_unmatched_stats(
    conn: sqlite3.Connection,
    titles: list[Any],
    stats_by_id: dict[str, Any],
    stats_by_name: dict[str, Any],
    authenticator: Any,
) -> dict[str, Any]:
    """Link unmatched gamelist IDs to trophy sets using Sony's own mapping."""
    unresolved: set[str] = set()
    used_ids: set[str] = set()
    for title in titles:
        comm_id = title.np_communication_id
        if not comm_id:
            continue
        matched = _find_ts_stats(conn, title, comm_id, stats_by_id, stats_by_name)
        if matched is None:
            unresolved.add(comm_id)
        elif matched.title_id:
            used_ids.add(matched.title_id)
    if not unresolved:
        return {}
    remaining = [tid for tid in stats_by_id if tid not in used_ids]
    candidates: dict[str, dict[str, Any]] = {}
    url = BASE_PATH["trophies"] + API_PATH["trophy_titles_for_title"].format(account_id="me")
    try:
        # Sony accepts at most five IDs. Check all batches before accepting a
        # mapping: regional editions can share a trophy set.
        for offset in range(0, len(remaining), 5):
            batch = remaining[offset:offset + 5]
            payload = authenticator.get(
                url=url, params={"npTitleIds": ",".join(batch)}
            ).json()
            for entry in payload["titles"]:
                tid = entry.get("npTitleId")
                if tid not in batch:
                    continue
                for trophy in entry.get("trophyTitles", []):
                    comm_id = trophy.get("npCommunicationId")
                    if comm_id in unresolved:
                        candidates.setdefault(comm_id, {})[tid] = stats_by_id[tid]
    except Exception as exc:
        # Do not abort sync or accept a partial, potentially ambiguous result.
        # Log only the exception class to avoid exposing authentication data.
        logger.warning("Could not resolve PSN title IDs (%s)", type(exc).__name__)
        return {}
    return {
        comm_id: next(iter(matches.values()))
        for comm_id, matches in candidates.items() if len(matches) == 1
    }


def _update_ts_stats(conn: sqlite3.Connection, np_comm_id: str, stats: Any) -> None:
    """Refresh available metadata even when PSN has no usable play duration."""
    existing = db_gamestats.get_game_stats(conn, np_comm_id)
    duration = stats.play_duration
    seconds = int(duration.total_seconds()) if duration is not None else 0
    keep_time = existing is not None and (
        duration is None or (seconds == 0 and existing["total_seconds"] > 0)
    )
    if keep_time:
        seconds = existing["total_seconds"]
    # Keep the manual-time marker while retaining a manual duration. Store the
    # matched title ID on games so future syncs can use an exact ID lookup.
    stats_title_id = existing["title_id"] if keep_time else (
        stats.title_id or (existing["title_id"] if existing is not None else None)
    )
    if stats.title_id:
        conn.execute(
            "UPDATE games SET np_title_id = ? WHERE np_communication_id = ?",
            (stats.title_id, np_comm_id),
        )
    first = stats.first_played_date_time
    last = stats.last_played_date_time
    count = stats.play_count
    db_gamestats.update_game_stats(
        conn, np_comm_id,
        title_id=stats_title_id,
        total_seconds=seconds,
        play_count=(count if count is not None else
                    existing["play_count"] if existing is not None else None),
        first_played=(first.isoformat() if first is not None else
                      existing["first_played"] if existing is not None else None),
        last_played=(last.isoformat() if last is not None else
                     existing["last_played"] if existing is not None else None),
    )


def _defined_trophy_total(title: Any) -> int | None:
    # Total trophies across all groups, from the title summary.
    try:
        d = title.defined_trophies
        return int(d.bronze) + int(d.silver) + int(d.gold) + int(d.platinum)
    except (AttributeError, TypeError, ValueError):
        return None


def _stored_trophy_count(conn: sqlite3.Connection, np_comm_id: str) -> int | None:
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM trophies WHERE np_communication_id = ?",
            (np_comm_id,),
        ).fetchone()
        return int(row["c"]) if row else None
    except (sqlite3.Error, TypeError, ValueError):
        return None


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

    resolved_stats = _resolve_unmatched_stats(
        conn, all_titles, stats_by_id, stats_by_name, psnawp.authenticator
    )

    # Capture stored-ID matches before trophy upserts can replace a missing
    # np_title_id with NULL (notably when play time remains manual).
    for title in all_titles:
        comm_id = title.np_communication_id
        if comm_id and comm_id not in resolved_stats:
            matched = _find_ts_stats(conn, title, comm_id, stats_by_id, stats_by_name)
            if matched is not None:
                resolved_stats[comm_id] = matched

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

        if not needs_update:
            # Self-heal: older syncs stored only the default trophy group,
            # so re-fetch games whose stored count lags behind PSN.
            defined_total = _defined_trophy_total(title)
            if defined_total is not None:
                stored = _stored_trophy_count(conn, np_comm_id)
                if stored is not None and stored != defined_total:
                    logger.debug(
                        "Backfilling %s (%s): stored %d != defined %d",
                        title.title_name, np_comm_id, stored, defined_total,
                    )
                    needs_update = True

        if needs_update:
            logger.debug("Processing %s (%s)", title.title_name, np_comm_id)
            platform = _get_platform(title)
            try:
                trophies = list(
                    client.trophies(
                        np_comm_id,
                        platform,
                        include_progress=True,
                        trophy_group_id="all",
                    )
                )
            except Exception as e:
                if len(result["warnings"]) < 20:
                    result["warnings"].append(f"Skipped {title.title_name}: {e}")
                continue

            try:
                groups = client.trophy_groups_summary(np_comm_id, platform)
                for g in groups.trophy_groups:
                    db.upsert_trophy_group(
                        conn, _extract_group_data(np_comm_id, g)
                    )
            except Exception as e:
                logger.debug(
                    "No trophy group names for %s: %s", np_comm_id, e
                )

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

        ts_stats = resolved_stats.get(np_comm_id)
        if ts_stats:
            _update_ts_stats(conn, np_comm_id, ts_stats)
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
