from __future__ import annotations

import json
import time

from psnself import auth, sync

SCHEDULE_PATH = auth.get_config_path().parent / "schedule.json"


def _load_schedule() -> dict[str, int | float]:
    if SCHEDULE_PATH.exists():
        return json.loads(SCHEDULE_PATH.read_text())
    return {}


def _save_schedule(data: dict) -> None:
    existing = _load_schedule()
    existing.update(data)
    SCHEDULE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEDULE_PATH.write_text(json.dumps(existing, indent=2))


def _run_trophy_sync(npsso: str) -> dict:
    print("[web] Starting trophy sync…")
    result = sync.sync_trophies(npsso)
    print(f"[web] Trophy sync done: {result}")
    return result


def _run_friends_sync(npsso: str) -> dict:
    print("[web] Starting friends sync…")
    result = sync.fetch_friends_leaderboard(npsso)
    print(f"[web] Friends sync done: {result}")
    return result


def _scheduler_loop() -> None:
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
            now = time.time()
            if ti > 0:
                last = cfg.get("last_trophy_sync", 0)
                if now - last >= ti * 3600:
                    print("[schedule] Starting trophy sync…")
                    result = _run_trophy_sync(npsso)
                    if result.get("status") != "error":
                        _save_schedule({"last_trophy_sync": time.time()})
                    time.sleep(30)
            if fi > 0:
                last = cfg.get("last_friends_sync", 0)
                if now - last >= fi * 3600:
                    print("[schedule] Starting friends sync…")
                    result = _run_friends_sync(npsso)
                    if result.get("status") != "error":
                        _save_schedule({"last_friends_sync": time.time()})
        except Exception as e:
            print(f"[schedule] Error: {e}")
