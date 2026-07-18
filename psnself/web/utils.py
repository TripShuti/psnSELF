from __future__ import annotations

import re
import time
from datetime import date

from psnself import auth

RARITY_LABELS = {
    "ultra_rare": "Ultra Rare", "very_rare": "Very Rare",
    "rare": "Rare", "common": "Common",
}

RARITY_COLORS = {
    "ultra_rare": "plat", "very_rare": "gold", "rare": "silver",
}


def fmt_date(d: str | None) -> str:
    if not d:
        return "–"
    return d[8:10] + "/" + d[5:7]


def fmt_hms(total_seconds: int) -> str:
    h, rem = divmod(int(total_seconds or 0), 3600)
    m = rem // 60
    if h == 0 and m == 0:
        return "0m"
    if h == 0:
        return f"{m}m"
    return f"{h}h {m}m"


def _parse_play_time(raw: str) -> int | None:
    raw = raw.strip().lower()
    try:
        if "h" in raw and "m" in raw:
            m = re.match(r"(\d+(?:\.\d+)?)\s*h\s*(\d+)\s*m", raw)
            if m:
                return int(float(m.group(1)) * 3600 + int(m.group(2)) * 60)
        elif "h" in raw:
            h = float(raw.replace("h", ""))
            return int(h * 3600)
        elif "m" in raw:
            m = int(raw.replace("m", ""))
            return m * 60
        else:
            h = float(raw)
            return int(h * 3600)
    except (ValueError, AttributeError):
        return None


def _month_label(year: int, month: int) -> str:
    return date(year, month, 1).strftime("%B %Y")


def _prev_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def _auth_context() -> dict:
    cfg = auth.load_config()
    if cfg.get("npsso"):
        return {"authenticated": True, "online_id": cfg.get("online_id", "unknown"), "account_id": cfg.get("account_id", "")}
    return {"authenticated": False, "online_id": None, "account_id": None}


def _fmt_remaining(interval_hours: int | float, last_sync: float) -> str:
    if last_sync == 0:
        return "not yet"
    elapsed = time.time() - last_sync
    remaining = interval_hours * 3600 - elapsed
    if remaining <= 0:
        return "any minute"
    mins = int(remaining // 60)
    if mins < 60:
        return f"{mins}m"
    return f"{mins // 60}h {mins % 60}m"
