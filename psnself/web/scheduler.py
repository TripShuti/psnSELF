from __future__ import annotations

import json
import time

from psnself import auth
from psnself.log import get_logger
from psnself.sync import sync_lock, sync_trophies, fetch_friends_leaderboard

SCHEDULE_PATH = auth.get_config_path().parent / "schedule.json"

logger = get_logger("scheduler")


def _load_schedule() -> dict[str, int | float]:
    if SCHEDULE_PATH.exists():
        return json.loads(SCHEDULE_PATH.read_text())
    return {}


def _save_schedule(data: dict) -> None:
    existing = _load_schedule()
    existing.update(data)
    SCHEDULE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEDULE_PATH.write_text(json.dumps(existing, indent=2))


def _need_sync(cfg: dict, key: str, interval_hours: int | float) -> bool:
    if interval_hours <= 0:
        return False
    last = cfg.get(key, 0)
    return time.time() - last >= interval_hours * 3600


def _check_and_sync(npsso: str, key: str, interval_hours: int | float,
                     sync_fn, label: str) -> None:
    if interval_hours <= 0:
        return
    with sync_lock:
        fresh = _load_schedule()
        last = fresh.get(key, 0)
        if time.time() - last < interval_hours * 3600:
            return
        logger.info(
            "Starting %s sync (interval=%dh, last=%s)",
            label, interval_hours,
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last)) if last else "never",
        )

    result = sync_fn(npsso)

    if result.get("status") != "error":
        with sync_lock:
            fresh = _load_schedule()
            if time.time() - fresh.get(key, 0) >= interval_hours * 3600:
                _save_schedule({key: time.time()})
                logger.info("%s sync saved at %s", label.capitalize(), key)


def _scheduler_loop() -> None:
    logger.info("Scheduler started (checking every 60s)")
    while True:
        time.sleep(60)
        try:
            cfg = _load_schedule()
            ti = cfg.get("trophy_interval_hours", 0)
            fi = cfg.get("friends_interval_hours", 0)
            if ti == 0 and fi == 0:
                continue
            npsso = auth.load_config().get("npsso")
            if not npsso:
                continue
            if _need_sync(cfg, "last_trophy_sync", ti):
                _check_and_sync(npsso, "last_trophy_sync", ti,
                                 sync_trophies, "trophy")
            if _need_sync(cfg, "last_friends_sync", fi):
                _check_and_sync(npsso, "last_friends_sync", fi,
                                 fetch_friends_leaderboard, "friends")
        except Exception as e:
            logger.error("Scheduler error: %s", e, exc_info=True)
