from __future__ import annotations

import json
import random
import time
from datetime import datetime
from threading import Lock

from psnself import auth
from psnself.log import get_logger
from psnself.sync import sync_trophies

SCHEDULE_PATH = auth.get_config_path().parent / "schedule.json"

_schedule_lock = Lock()

logger = get_logger("scheduler")


def _load_schedule() -> dict:
    if SCHEDULE_PATH.exists():
        return json.loads(SCHEDULE_PATH.read_text())
    return {}


def _save_schedule(data: dict) -> None:
    existing = _load_schedule()
    existing.update(data)
    SCHEDULE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEDULE_PATH.write_text(json.dumps(existing, indent=2))


def _scheduler_loop() -> None:
    logger.info("Scheduler started (checking every 60s)")
    while True:
        time.sleep(60)
        try:
            cfg = _load_schedule()
            if not cfg.get("daily_sync_enabled", False):
                continue

            npsso = auth.load_config().get("npsso")
            if not npsso:
                continue

            now = datetime.now()
            if now.hour != 23:
                continue

            today_str = now.strftime("%Y-%m-%d")
            if cfg.get("last_auto_sync_date") == today_str:
                continue

            # Pick a random minute in 23:00-00:00 for today if not yet set
            scheduled_date = cfg.get("scheduled_date")
            target_minute = cfg.get("scheduled_minute")
            if scheduled_date != today_str or target_minute is None:
                target_minute = random.randint(0, 59)
                with _schedule_lock:
                    fresh = _load_schedule()
                    if fresh.get("last_auto_sync_date") == today_str:
                        continue
                    _save_schedule({"scheduled_minute": target_minute, "scheduled_date": today_str})
                    logger.info("Scheduled daily sync at 23:%02d for %s", target_minute, today_str)

            if now.minute < target_minute:
                continue

            with _schedule_lock:
                fresh = _load_schedule()
                if fresh.get("last_auto_sync_date") == today_str:
                    continue
                _save_schedule({"last_auto_sync_date": today_str, "scheduled_minute": None, "scheduled_date": None})

            logger.info("Starting daily auto trophy sync for %s", today_str)
            result = sync_trophies(npsso)

            if result.get("status") == "error":
                logger.error("Daily auto sync failed: %s", result.get("error"))
            else:
                logger.info(
                    "Daily auto sync done: +%d trophies, %d games",
                    result.get("trophies_added", 0), result.get("games_updated", 0),
                )
        except Exception as e:
            logger.error("Scheduler error: %s", e, exc_info=True)