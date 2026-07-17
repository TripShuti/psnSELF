from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from psnawp_api import PSNAWP
from psnawp_api.core.psnawp_exceptions import PSNAWPForbiddenError

from .. import auth, db
from .. import db_friends
from ..sync import _sync_lock
from .extractor import _DEFAULT_RATE_LIMIT, _ensure_request_timeout, ProgressCB


def fetch_friends_leaderboard(npsso: str, progress_callback: ProgressCB = None) -> dict[str, Any]:
    with _sync_lock:
        return _do_fetch_friends(npsso, progress_callback)


def _do_fetch_friends(npsso: str, progress_callback: ProgressCB = None) -> dict[str, Any]:
    _ensure_request_timeout()
    conn = db.get_conn()
    try:
        psnawp = PSNAWP(npsso_cookie=npsso, rate_limit=_DEFAULT_RATE_LIMIT)
        client = psnawp.me()
        friends = list(client.friends_list(limit=1000))
        now = datetime.now(timezone.utc).isoformat()
        processed = 0
        private = 0
        errors = 0
        games_stored = 0

        total = len(friends)
        for i, friend in enumerate(friends):
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
                print(f"[friends] Error processing {friend.online_id}: {e}")
                errors += 1
            if progress_callback:
                progress_callback(i + 1, total, friend.online_id)

        _sync_self(conn, client, now)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
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
        print(f"[friends] Error storing self: {e}")
