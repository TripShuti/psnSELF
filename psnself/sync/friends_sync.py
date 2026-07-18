from __future__ import annotations

import time
import sqlite3
from datetime import datetime, timezone
from typing import Any

from psnawp_api import PSNAWP
from psnawp_api.core.psnawp_exceptions import PSNAWPForbiddenError

from .. import auth, db
from .. import db_friends
from ..sync import sync_lock
from ..log import get_logger
from .extractor import _DEFAULT_RATE_LIMIT, _ensure_request_timeout, ProgressCB

logger = get_logger("friends_sync")


def fetch_friends_leaderboard(npsso: str, progress_callback: ProgressCB = None) -> dict[str, Any]:
    with sync_lock:
        return _do_fetch_friends(npsso, progress_callback)


def _do_fetch_friends(npsso: str, progress_callback: ProgressCB = None) -> dict[str, Any]:
    _t0 = time.time()
    _ensure_request_timeout()
    conn = db.get_conn()
    try:
        psnawp = PSNAWP(npsso_cookie=npsso, rate_limit=_DEFAULT_RATE_LIMIT)
        client = psnawp.me()
        friends = list(client.friends_list(limit=1000))
        logger.info("Found %d friends", len(friends))
        now = datetime.now(timezone.utc).isoformat()
        processed = 0
        private = 0
        errors = 0
        games_stored = 0

        total = len(friends)
        active_ids: set[str] = set()
        for i, friend in enumerate(friends):
            active_ids.add(friend.account_id)
            try:
                summary = friend.trophy_summary()
                db_friends.upsert_friend(conn, {
                    "account_id": friend.account_id,
                    "online_id": friend.online_id,
                    "trophy_level": summary.trophy_level,
                    "platinum": summary.earned_trophies.platinum,
                    "gold": summary.earned_trophies.gold,
                    "silver": summary.earned_trophies.silver,
                    "bronze": summary.earned_trophies.bronze,
                    "is_private": 0,
                    "fetched_at": now,
                })

                try:
                    for tt in friend.trophy_titles():
                        npid = tt.np_communication_id
                        if not npid or not npid.startswith("NPWR"):
                            continue
                        db_friends.upsert_friend_game(conn, {
                            "account_id": friend.account_id,
                            "np_communication_id": npid,
                            "progress": tt.progress or 0,
                            "earned_platinum": tt.earned_trophies.platinum,
                            "earned_gold": tt.earned_trophies.gold,
                            "earned_silver": tt.earned_trophies.silver,
                            "earned_bronze": tt.earned_trophies.bronze,
                            "is_private": 0,
                            "fetched_at": now,
                        })
                        games_stored += 1
                except Exception:
                    pass

                processed += 1
            except PSNAWPForbiddenError:
                db_friends.upsert_friend(conn, {
                    "account_id": friend.account_id,
                    "online_id": friend.online_id,
                    "trophy_level": None,
                    "platinum": 0, "gold": 0, "silver": 0, "bronze": 0,
                    "is_private": 1,
                    "fetched_at": now,
                })
                private += 1
            except Exception as e:
                logger.warning("Error processing %s: %s", friend.online_id, e)
                errors += 1
            if progress_callback:
                progress_callback(i + 1, total, friend.online_id)

        _sync_self(conn, client, now)
        active_ids.add(client.account_id)
        removed = db_friends.delete_stale_friends(conn, active_ids, client.account_id)
        if removed:
            logger.info("Removed %d stale friends from local DB", removed)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    _elapsed = time.time() - _t0
    logger.info(
        "Friends sync done: %d processed, %d private, %d errors (took %.1fs)",
        processed, private, errors, _elapsed,
    )
    return {
        "processed": processed,
        "private": private,
        "errors": errors,
        "total": total,
        "games_stored": games_stored,
    }


def _sync_self(conn: sqlite3.Connection, client, now: str) -> None:
    try:
        summary = client.trophy_summary()
        db_friends.upsert_friend(conn, {
            "account_id": client.account_id,
            "online_id": client.online_id,
            "trophy_level": summary.trophy_level,
            "platinum": summary.earned_trophies.platinum,
            "gold": summary.earned_trophies.gold,
            "silver": summary.earned_trophies.silver,
            "bronze": summary.earned_trophies.bronze,
            "is_private": 0,
            "fetched_at": now,
        })
        cfg = auth.load_config()
        changed = False
        if not cfg.get("account_id"):
            cfg["account_id"] = client.account_id
            cfg["online_id"] = client.online_id
            changed = True
        if changed:
            auth.save_config(cfg)
    except Exception as e:
        logger.error("Error storing self data: %s", e)
