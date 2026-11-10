from __future__ import annotations

import hashlib
import json
import os
import random
import time
from datetime import datetime, timedelta, timezone
from threading import RLock

from psnself import auth, db, notifications
from psnself.log import get_logger
from psnself.sync import sync_trophies

SCHEDULE_PATH = auth.get_config_path().parent / "schedule.json"

_schedule_lock = RLock()

logger = get_logger("scheduler")


def _load_schedule() -> dict:
    if SCHEDULE_PATH.exists():
        return json.loads(SCHEDULE_PATH.read_text())
    return {}


def _save_schedule(data: dict) -> None:
    with _schedule_lock:
        existing = _load_schedule()
        existing.update(data)
        # Retire settings from the former interval and minute-only schedules.
        for key in ("trophy_interval_hours", "friends_interval_hours",
                    "last_trophy_sync", "last_friends_sync",
                    "scheduled_minute", "scheduled_date"):
            existing.pop(key, None)
        SCHEDULE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = SCHEDULE_PATH.with_suffix(".tmp")
        with temporary.open("w") as handle:
            json.dump(existing, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(SCHEDULE_PATH)
        directory = os.open(SCHEDULE_PATH.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


def _last_success() -> float | None:
    # Sync log timestamps are UTC, including manual syncs.
    value = db.get_last_sync_time(db.get_conn())
    return value.replace(tzinfo=timezone.utc).timestamp() if value else None


def _evening(day) -> float:
    return datetime.combine(day, datetime.min.time()).replace(
        hour=23, minute=random.randint(0, 59)
    ).timestamp()


def _scheduler_tick() -> None:
    notifications.notify_pending()
    cfg = _load_schedule()
    if not cfg.get("daily_sync_enabled", False):
        return
    npsso = auth.load_config().get("npsso")
    if not npsso:
        return
    now = time.time()
    local_now = datetime.fromtimestamp(now)
    success = _last_success()
    due = cfg.get("next_sync_at")
    if due is None:
        # Recover even if power failed before a schedule could be saved.
        day = local_now.date() - timedelta(days=1)
        due = _evening(day)
        _save_schedule({"next_sync_at": due})

    if success is not None and success >= due:
        # A manual sync satisfies a missed run. Skip elapsed days.
        success_local = datetime.fromtimestamp(success)
        day = success_local.date() + timedelta(days=success_local.hour >= 23)
        due = _evening(day)
        _save_schedule({"next_sync_at": due, "retry_at": None,
                        "retry_count": 0, "blocked_token": None})
        cfg = _load_schedule()
    if now < due:
        return
    token_hash = hashlib.sha256(npsso.encode()).hexdigest()
    if cfg.get("blocked_token") == token_hash:
        return
    if cfg.get("retry_at") and now < cfg["retry_at"]:
        return
    _save_schedule({"last_auto_sync_date": local_now.date().isoformat(),
                    "last_auto_attempt_at": now})
    logger.info("Starting daily auto trophy sync (scheduled %s)",
                datetime.fromtimestamp(due).isoformat())
    auth_failed = False
    try:
        result = sync_trophies(npsso)
        if result.get("status") != "success":
            auth_failed = str(result.get("error", "")).startswith("NPSSO is no longer valid")
            raise RuntimeError(result.get("error") or "Sync failed")
    except Exception as exc:
        retry_count = cfg.get("retry_count", 0) + 1
        delay = (300, 900, 1800)[min(retry_count - 1, 2)]
        blocked = auth_failed or isinstance(exc, notifications.AUTH_ERRORS)
        _save_schedule({"retry_count": retry_count,
                        "retry_at": time.time() + delay,
                        "blocked_token": token_hash if blocked else None})
        logger.exception("Daily auto sync failed; %s",
                         "waiting for updated NPSSO" if blocked else f"retry in {delay}s")
        return
    finished = time.time()
    finished_local = datetime.fromtimestamp(finished)
    next_day = finished_local.date() + timedelta(days=finished_local.hour >= 23)
    _save_schedule({"last_auto_success_at": finished,
                    "next_sync_at": _evening(next_day),
                    "retry_at": None, "retry_count": 0, "blocked_token": None})
    logger.info("Daily auto sync done: +%d trophies, %d games",
                result.get("trophies_added", 0), result.get("games_updated", 0))


def _scheduler_loop() -> None:
    logger.info("Scheduler started (checking every 60s; missed runs catch up)")
    while True:
        # Let networking settle after boot before the first attempt.
        time.sleep(60)
        try:
            _scheduler_tick()
        except Exception:
            logger.exception("Scheduler error")
