from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from pyrate_limiter import Rate

ProgressCB = Optional[Callable[[int, int, str], None]]
_DEFAULT_RATE_LIMIT = Rate(1, 3)

from psnawp_api.core.request_builder import RequestBuilder
from psnawp_api.models.trophies import PlatformType

REQUEST_TIMEOUT = 60
_request_patch_applied = False

_RE_TM = re.compile(r"[™®]")
_RE_NEWLINE = re.compile(r"[\u000a\u000d]")
_RE_SUFFIX = re.compile(r"\s+trophies$", re.IGNORECASE)
_RE_WS = re.compile(r"\s+")


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_date_utc(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    return _ensure_utc(dt)


# Monkey-patch psnawp's RequestBuilder to add a default timeout.
# psnawp does not set timeouts, causing requests to hang indefinitely.
# This is a known workaround; if psnawp ever adds native timeout support
# this patch can be removed.
def _ensure_request_timeout() -> None:
    global _request_patch_applied
    if _request_patch_applied:
        return
    _orig_request = RequestBuilder.request
    def _patched_request(self, method, **kwargs):
        kwargs.setdefault("timeout", REQUEST_TIMEOUT)
        return _orig_request(self, method, **kwargs)
    RequestBuilder.request = _patched_request
    _request_patch_applied = True


def _extract_game_data(title: Any) -> dict:
    platform = list(title.title_platform)[0].value if title.title_platform else None
    return {
        "np_communication_id": title.np_communication_id,
        "np_title_id": title.np_title_id,
        "title_name": title.title_name,
        "title_icon_url": title.title_icon_url,
        "platform": platform,
        "defined_bronze": title.defined_trophies.bronze,
        "defined_silver": title.defined_trophies.silver,
        "defined_gold": title.defined_trophies.gold,
        "defined_platinum": title.defined_trophies.platinum,
        "earned_bronze": title.earned_trophies.bronze,
        "earned_silver": title.earned_trophies.silver,
        "earned_gold": title.earned_trophies.gold,
        "earned_platinum": title.earned_trophies.platinum,
        "progress": title.progress,
        "last_updated_datetime": (
            title.last_updated_datetime.isoformat()
            if title.last_updated_datetime
            else None
        ),
    }


def _extract_trophy_data(np_comm_id: str, trophy: Any) -> dict:
    return {
        "np_communication_id": np_comm_id,
        "trophy_id": trophy.trophy_id,
        "trophy_name": trophy.trophy_name,
        "trophy_detail": trophy.trophy_detail,
        "trophy_type": trophy.trophy_type.value.lower() if trophy.trophy_type else None,
        "trophy_icon_url": trophy.trophy_icon_url,
        "trophy_hidden": bool(trophy.trophy_hidden),
        "trophy_group_id": trophy.trophy_group_id or "default",
        "earned": bool(trophy.earned) if hasattr(trophy, "earned") else False,
        "earned_date_time": (
            trophy.earned_date_time.isoformat()
            if hasattr(trophy, "earned_date_time") and trophy.earned_date_time
            else None
        ),
        "trophy_rarity": (
            trophy.trophy_rarity.name.lower()
            if hasattr(trophy, "trophy_rarity") and trophy.trophy_rarity
            else None
        ),
        "trophy_earn_rate": (
            float(trophy.trophy_earn_rate)
            if hasattr(trophy, "trophy_earn_rate") and trophy.trophy_earn_rate is not None
            else None
        ),
        "progress": (
            int(trophy.progress)
            if hasattr(trophy, "progress") and trophy.progress is not None
            else None
        ),
        "progress_rate": (
            int(trophy.progress_rate)
            if hasattr(trophy, "progress_rate") and trophy.progress_rate is not None
            else None
        ),
    }


def _get_platform(title: Any) -> PlatformType:
    if title.title_platform:
        return list(title.title_platform)[0]
    return PlatformType.PS4


def _normalize_name(name: str) -> str:
    s = _RE_NEWLINE.sub("", name)
    s = s.replace("\u2019", "'").replace("\u2018", "'")
    s = _RE_TM.sub("", s)
    s = _RE_SUFFIX.sub("", s)
    s = _RE_WS.sub(" ", s)
    return s.strip().lower()
