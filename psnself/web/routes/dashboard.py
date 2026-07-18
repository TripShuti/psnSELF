from __future__ import annotations

import re
import threading
import time
from datetime import date
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from psnself import auth, db, sync
from psnself.web.services.friend_service import FriendService
from psnself.web.services.game_service import GameService
from psnself.web.services.stats_service import StatsService
from psnself.web.template import templates
from psnself.web.utils import RARITY_COLORS, RARITY_LABELS, _auth_context, _month_label, _prev_month, _next_month

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

router = APIRouter()

_sync_status: dict[str, Any] = {}
_sync_lock = threading.Lock()


def _bg_sync(npsso: str, kind: str) -> None:
    try:
        if kind == "trophy":
            result = sync.sync_trophies(npsso)
        else:
            result = sync.fetch_friends_leaderboard(npsso)
        with _sync_lock:
            _sync_status[kind] = {"running": False, "result": result, "error": None, "time": time.time()}
    except Exception as e:
        with _sync_lock:
            _sync_status[kind] = {"running": False, "result": None, "error": str(e), "time": time.time()}


def _start_sync(kind: str, npsso: str) -> str | None:
    with _sync_lock:
        st = _sync_status.get(kind, {})
        if st.get("running"):
            return "already running"
        _sync_status[kind] = {"running": True, "result": None, "error": None, "time": time.time()}
    threading.Thread(target=_bg_sync, args=(npsso, kind), daemon=True).start()
    return None


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    conn = db.get_conn()
    gs = GameService(conn)
    ss = StatsService(conn)
    fs = FriendService(conn)
    today = date.today()

    games = gs.get_games()
    recent = gs.get_recent(limit=8)
    heatmap = ss.build_heatmap(today)
    playtime = ss.get_playtime_summary(today)
    rarest = gs.get_rarest(limit=5)

    ac = _auth_context()
    self_stats = fs.get_by_account_id(ac.get("account_id", "")) if ac.get("account_id") else None

    has_no_time = any(g.play_seconds == 0 for g in games)

    return templates.TemplateResponse(request, "index.html", {
        **_auth_context(), "active": "dashboard",
        "games": games, "recent": recent, "heatmap": heatmap,
        "playtime": playtime,
        "rarest": rarest, "self_stats": self_stats,
        "today_year": today.year, "today_month": today.month,
        "has_no_time_games": has_no_time,
        "rarity_labels": RARITY_LABELS,
        "rarity_colors": RARITY_COLORS,
    })


@router.get("/partials/day/{date_str}", response_class=HTMLResponse)
def partial_day(request: Request, date_str: str) -> HTMLResponse:
    if not _DATE_RE.match(date_str):
        return HTMLResponse('<span style="color: var(--err);">Invalid date</span>', status_code=400)
    conn = db.get_conn()
    ss = StatsService(conn)
    trophies = ss.get_daily_counts(date_str)
    return templates.TemplateResponse(request, "partials/day_detail.html", {
        "date_str": date_str, "trophies": trophies,
    })


@router.get("/partials/calendar/{year}/{month}", response_class=HTMLResponse)
def partial_calendar(request: Request, year: int, month: int) -> HTMLResponse:
    conn = db.get_conn()
    ss = StatsService(conn)
    cells = ss.get_calendar_data(year, month)
    month_total = sum(c["seconds"] for c in cells if c is not None)
    py, pm = _prev_month(year, month)
    ny, nm = _next_month(year, month)
    return templates.TemplateResponse(request, "partials/calendar.html", {
        "cells": cells, "label": _month_label(year, month),
        "prev_year": py, "prev_month": pm, "next_year": ny, "next_month": nm,
        "month_total": month_total,
    })


@router.get("/partials/playday/{date_str}", response_class=HTMLResponse)
def partial_play_day(request: Request, date_str: str) -> HTMLResponse:
    if not _DATE_RE.match(date_str):
        return HTMLResponse('<span style="color: var(--err);">Invalid date</span>', status_code=400)
    conn = db.get_conn()
    ss = StatsService(conn)
    details = ss.get_play_day_details(date_str)
    return templates.TemplateResponse(request, "partials/calendar_day_detail.html", {
        "date_str": date_str, "details": details,
    })


@router.get("/partials/playrange/{since}/{until}", response_class=HTMLResponse)
def partial_play_range(request: Request, since: str, until: str) -> HTMLResponse:
    if not _DATE_RE.match(since) or not _DATE_RE.match(until):
        return HTMLResponse('<span style="color: var(--err);">Invalid date</span>', status_code=400)
    conn = db.get_conn()
    ss = StatsService(conn)
    details = ss.get_range_play_details(since, until)
    return templates.TemplateResponse(request, "partials/calendar_day_detail.html", {
        "date_str": f"{since} – {until}", "details": details,
    })


@router.post("/sync")
def trigger_sync(request: Request) -> HTMLResponse:
    config = auth.load_config()
    if not config.get("npsso"):
        return HTMLResponse(
            '<span style="color: var(--err);">Not authenticated</span>',
            status_code=400,
        )
    err = _start_sync("trophy", config["npsso"])
    if err:
        return HTMLResponse('<span style="color: var(--fg-dim);">⏳ Sync already in progress</span>')
    return HTMLResponse(
        '<span style="color: var(--accent);">Sync started…</span>'
        '<span hx-get="/sync-poll" hx-trigger="every 2s" hx-target="#sync-msg" hx-swap="innerHTML"></span>'
    )


@router.get("/sync-poll")
def sync_poll(request: Request) -> HTMLResponse:
    with _sync_lock:
        st = _sync_status.get("trophy", {})
        if st.get("running"):
            return HTMLResponse(
                '<span style="color: var(--fg-dim);">⏳ Syncing…</span>'
                '<span hx-get="/sync-poll" hx-trigger="every 2s" hx-target="#sync-msg" hx-swap="innerHTML"></span>'
            )
        result = st.get("result")
        error = st.get("error")
        _sync_status.pop("trophy", None)
    if error:
        return HTMLResponse(f'<span style="color: var(--err);">Failed: {error}</span>')
    if result:
        if result.get("status") == "error":
            return HTMLResponse(f'<span style="color: var(--err);">Failed: {result["error"]}</span>')
        msg = f'✓ Completed: +{result["trophies_added"]} trophies, {result["games_updated"]} games'
        if result.get("warnings"):
            msg += f'<br><span style="color: var(--fg-dim);">⚠ {len(result["warnings"])} warnings (no play time data)</span>'
        return HTMLResponse(f'<span style="color: var(--accent);">{msg}</span>')
    return HTMLResponse('<span style="color: var(--fg-dim);">Waiting…</span>')


@router.post("/sync-friends")
def trigger_sync_friends(request: Request) -> HTMLResponse:
    config = auth.load_config()
    if not config.get("npsso"):
        return HTMLResponse(
            '<span style="color: var(--err);">Not authenticated</span>',
            status_code=400,
        )
    err = _start_sync("friends", config["npsso"])
    if err:
        return HTMLResponse('<span style="color: var(--fg-dim);">⏳ Sync already in progress</span>')
    return HTMLResponse(
        '<span style="color: var(--accent);">Syncing friends…</span>'
        '<span hx-get="/sync-friends-poll" hx-trigger="every 2s" hx-target="#friends-sync-msg" hx-swap="innerHTML"></span>'
    )


@router.get("/sync-friends-poll")
def sync_friends_poll(request: Request) -> HTMLResponse:
    with _sync_lock:
        st = _sync_status.get("friends", {})
        if st.get("running"):
            return HTMLResponse(
                '<span style="color: var(--fg-dim);">⏳ Syncing…</span>'
                '<span hx-get="/sync-friends-poll" hx-trigger="every 2s" hx-target="#friends-sync-msg" hx-swap="innerHTML"></span>'
            )
        result = st.get("result")
        error = st.get("error")
        _sync_status.pop("friends", None)
    if error:
        return HTMLResponse(f'<span style="color: var(--err);">Failed: {error}</span>')
    if result:
        return HTMLResponse(
            f'<span style="color: var(--accent);">'
            f'✓ Completed: {result["processed"]} friends, {result["games_stored"]} games'
            f'</span>'
        )
    return HTMLResponse('<span style="color: var(--fg-dim);">Waiting…</span>')
