from __future__ import annotations

import hashlib
from datetime import datetime
from threading import Lock

from .. import db
from .extractor import _normalize_name

_sync_lock = Lock()

from .trophy_sync import sync_trophies
from .friends_sync import fetch_friends_leaderboard


def write_sync_log(warnings: list[str]) -> None:
    if not warnings:
        return
    log_path = db.DB_PATH.parent / "sync.log"
    hash_path = log_path.with_suffix(".log.hash")
    new_hash = hashlib.sha256("".join(warnings).encode()).hexdigest()
    try:
        old_hash = hash_path.read_text().strip()
        if old_hash == new_hash:
            return
    except (OSError, FileNotFoundError):
        pass
    now = datetime.now().isoformat(timespec="seconds")
    lines = [f"[{now}] Sync warnings ({len(warnings)}):"]
    for w in warnings:
        lines.append(f"  ⚠ {w}")
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n\n")
        hash_path.write_text(new_hash)
    except OSError:
        pass
