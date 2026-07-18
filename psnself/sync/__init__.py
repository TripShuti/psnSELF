from __future__ import annotations

import hashlib
from datetime import datetime
from threading import Lock

from .. import auth, db
from ..log import get_logger
from .extractor import _normalize_name

__all__ = [
    "sync_lock",
    "sync_trophies",
    "fetch_friends_leaderboard",
    "_normalize_name",
    "write_sync_log",
]

sync_lock = Lock()

from .friends_sync import fetch_friends_leaderboard  # noqa: E402
from .trophy_sync import sync_trophies  # noqa: E402

logger = get_logger("sync")


def write_sync_log(warnings: list[str]) -> None:
    if not warnings:
        return
    log_path = (db.DB_PATH.parent if db.DB_PATH else auth.get_db_path().parent) / "sync.log"
    hash_path = log_path.with_suffix(".log.hash")
    new_hash = hashlib.sha256("".join(warnings).encode()).hexdigest()
    try:
        old_hash = hash_path.read_text().strip()
        if old_hash == new_hash:
            return
    except (OSError, FileNotFoundError):
        pass
    for w in warnings:
        logger.warning("Sync warning: %s", w)
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
