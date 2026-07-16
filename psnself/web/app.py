"""
psnTUI web dashboard — a read-only web frontend over the same SQLite
database the TUI and headless sync already use.
"""
from __future__ import annotations

import json
import re
import threading
import time
from calendar import Calendar
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from psnself import auth, db, sync

SCHEDULE_PATH = auth.get_config_path().parent / "schedule.json"

app = FastAPI(title="psnTUI web")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

TROPHY_COLOR_VAR = {
    "platinum": "plat", "gold": "gold", "silver": "silver", "bronze": "bronze",
}
RARITY_LABELS = {
    "ultra_rare": "Ultra Rare", "very_rare": "Very Rare",
    "rare": "Rare", "common": "Common",
}
RARITY_ORDER = ["ultra_rare", "very_rare", "rare", "common"]


def fmt_date(d: str | None) -> str:
    if not d:
        return "–"
    return d[8:10] + "/" + d[5:7]  # 2026-07-15 → 15/07


templates.env.filters["fmt_date"] = fmt_date


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
            m = re.match(r"(\d+)\s*h\s*(\d+)\s*m", raw)
            if m:
                return int(m.group(1)) * 3600 + int(m.group(2)) * 60
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
        return {"authenticated": True, "online_id": cfg.get("online_id", "unknown")}
    return {"authenticated": False, "online_id": None}


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
                    _run_trophy_sync(npsso)
                    _save_schedule({"last_trophy_sync": time.time()})
            if fi > 0:
                last = cfg.get("last_friends_sync", 0)
                if now - last >= fi * 3600:
                    print("[schedule] Starting friends sync…")
                    _run_friends_sync(npsso)
                    _save_schedule({"last_friends_sync": time.time()})
        except Exception as e:
            print(f"[schedule] Error: {e}")

@app.on_event("startup")
def _startup() -> None:
    if db.DB_PATH is None:
        from platformdirs import user_config_dir
        db.set_db_path(Path(user_config_dir("psnself")) / "trophies.db")
    db.init_db()
    threading.Thread(target=_scheduler_loop, daemon=True).start()


@app.get("/auth", response_class=HTMLResponse)
def auth_page(request: Request):
    sc = _load_schedule()
    ti = sc.get("trophy_interval_hours", 0)
    fi = sc.get("friends_interval_hours", 0)
    return templates.TemplateResponse(request, "auth.html", {
        **_auth_context(), "active": "auth",
        "trophy_interval": ti,
        "friends_interval": fi,
        "next_trophy": _fmt_remaining(ti, sc.get("last_trophy_sync", 0)) if ti > 0 else None,
        "next_friends": _fmt_remaining(fi, sc.get("last_friends_sync", 0)) if fi > 0 else None,
    })


@app.post("/auth")
async def auth_submit(request: Request):
    form = await request.form()
    npsso = (form.get("npsso") or "").strip()

    if len(npsso) != 64:
        return HTMLResponse('<span style="color: var(--err);">NPSSO must be exactly 64 characters</span>')

    online_id = auth.validate_npsso(npsso)
    if online_id is None:
        return HTMLResponse('<span style="color: var(--err);">Invalid NPSSO. Make sure you copied it correctly.</span>')

    auth.save_config({"npsso": npsso, "online_id": online_id})

    threading.Thread(target=_run_trophy_sync, args=(npsso,), daemon=True).start()
    threading.Thread(target=_run_friends_sync, args=(npsso,), daemon=True).start()

    return HTMLResponse(
        f'<span style="color: var(--accent);">Authenticated as {online_id}! '
        f'Sync started in background — reload in a few minutes.</span>'
    )


@app.post("/auth/schedule")
async def auth_schedule(request: Request):
    form = await request.form()
    ti = form.get("trophy_interval", "0").strip()
    fi = form.get("friends_interval", "0").strip()
    try:
        ti = max(0, int(ti))
        fi = max(0, int(fi))
    except (ValueError, TypeError):
        return HTMLResponse('<span style="color: var(--err);">Invalid interval value</span>')
    _save_schedule({"trophy_interval_hours": ti, "friends_interval_hours": fi})
    return HTMLResponse(
        f'<span style="color: var(--accent);">✓ Schedule saved'
        f'{" — next trophy sync in ~" + _fmt_remaining(ti, _load_schedule().get("last_trophy_sync", 0)) if ti > 0 else ""}'
        f'</span>'
    )

def _fmt_remaining(interval_hours: int, last_sync: float) -> str:
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

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    conn = db.get_conn()
    games = db.get_games(conn)
    recent = db.get_recent_earned(conn, limit=10)

    # --- heatmap: same 11-week window as the TUI ---
    today = date.today()
    weeks_back = 10
    start_date = today - timedelta(weeks=weeks_back, days=today.weekday())
    since = start_date.isoformat()
    until = (today + timedelta(days=1)).isoformat()
    earned_rows = db.get_earned_by_date_range(conn, since, until)
    counts = {r["day"]: r["count"] for r in earned_rows}
    max_count = max(counts.values(), default=1)

    week_labels = [(start_date + timedelta(weeks=w)).strftime("%b %d") for w in range(weeks_back + 1)]
    rows = []
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for d_idx, day_name in enumerate(day_names):
        cells = []
        for w in range(weeks_back + 1):
            cell_date = start_date + timedelta(weeks=w, days=d_idx)
            if cell_date > today:
                cells.append({"count": None})
                continue
            count = counts.get(cell_date.isoformat(), 0)
            intensity = count / max_count if max_count else 0
            color = "#0d5a45" if count == 0 else (
                "#3abaa0" if intensity < 0.5 else "#00c8a0"
            )
            cells.append({"count": count, "date": cell_date.isoformat(), "color": color})
        rows.append((day_name, cells))
    heatmap = {"week_labels": week_labels, "rows": rows}

    # --- month comparison ---
    cur_count = db.get_earned_month(conn, today.year, today.month)
    py, pm = _prev_month(today.year, today.month)
    prev_count = db.get_earned_month(conn, py, pm)
    change = round(((cur_count - prev_count) / prev_count) * 100) if prev_count else (100 if cur_count else 0)
    month_compare = {
        "cur_label": date(today.year, today.month, 1).strftime("%B %Y"),
        "prev_label": date(py, pm, 1).strftime("%B %Y"),
        "cur_count": cur_count, "prev_count": prev_count, "change": change,
    }

    # --- play time ---
    day_start = today.isoformat()
    week_start = (today - timedelta(days=today.weekday())).isoformat()
    month_start = date(today.year, today.month, 1).isoformat()
    tomorrow = (today + timedelta(days=1)).isoformat()
    playtime = {
        "total": fmt_hms(db.get_total_play_time(conn)),
        "today": fmt_hms(db.get_total_play_delta(conn, day_start, tomorrow)),
        "week": fmt_hms(db.get_total_play_delta(conn, week_start, tomorrow)),
        "month": fmt_hms(db.get_total_play_delta(conn, month_start, tomorrow)),
    }

    # --- rarity distribution ---
    rows_r = conn.execute("""
        SELECT trophy_rarity, COUNT(*) as count FROM trophies
        WHERE earned = 1 AND trophy_rarity IS NOT NULL
        GROUP BY trophy_rarity
    """).fetchall()
    counts_r = {r["trophy_rarity"]: r["count"] for r in rows_r}
    total_r = sum(counts_r.values()) or 1
    max_r = max(counts_r.values(), default=1)
    rarity = []
    for key in RARITY_ORDER:
        c = counts_r.get(key, 0)
        rarity.append({
            "label": RARITY_LABELS[key], "count": c,
            "pct": round((c / total_r) * 100),
            "bar_pct": max(round((c / max_r) * 100), 2) if c else 0,
        })

    return templates.TemplateResponse(request, "index.html", {
        **_auth_context(), "active": "dashboard",
        "games": games, "recent": recent, "heatmap": heatmap,
        "month_compare": month_compare, "playtime": playtime, "rarity": rarity,
        "today_year": today.year, "today_month": today.month,
    })


@app.get("/partials/day/{date_str}", response_class=HTMLResponse)
def partial_day(request: Request, date_str: str):
    conn = db.get_conn()
    trophies = db.get_trophies_by_date(conn, date_str)
    return templates.TemplateResponse(request, "partials/day_detail.html", {
        "date_str": date_str, "trophies": trophies,
    })


@app.get("/partials/calendar/{year}/{month}", response_class=HTMLResponse)
def partial_calendar(request: Request, year: int, month: int):
    conn = db.get_conn()
    daily = db.get_daily_play_time(conn, year, month)
    cal = Calendar(firstweekday=0)  # Monday first, matches the TUI
    cells = []
    for day in cal.itermonthdates(year, month):
        if day.month != month:
            cells.append(None)
            continue
        secs = daily.get(day.isoformat(), 0)
        cells.append({
            "day": day.day, "date": day.isoformat(),
            "seconds": secs, "label": fmt_hms(secs) if secs else "",
        })
    py, pm = _prev_month(year, month)
    ny, nm = _next_month(year, month)
    return templates.TemplateResponse(request, "partials/calendar.html", {
        "cells": cells, "label": _month_label(year, month),
        "prev_year": py, "prev_month": pm, "next_year": ny, "next_month": nm,
    })


@app.get("/partials/playday/{date_str}", response_class=HTMLResponse)
def partial_play_day(request: Request, date_str: str):
    conn = db.get_conn()
    raw = db.get_daily_play_details(conn, date_str)
    details = [{"title_name": r["title_name"], "label": fmt_hms(r["delta_seconds"])} for r in raw]
    return templates.TemplateResponse(request, "partials/calendar_day_detail.html", {
        "date_str": date_str, "details": details,
    })


@app.get("/friends", response_class=HTMLResponse)
def friends(request: Request):
    conn = db.get_conn()
    rows = db.get_friends_leaderboard(conn)
    fetched_at = db.get_friends_fetched_at(conn)
    label = "Never refreshed — press l then r in the TUI"
    if fetched_at:
        dt = datetime.fromisoformat(fetched_at)
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        mins = int((now - dt).total_seconds() // 60)
        label = f"Last updated {mins} min ago" if mins < 60 else f"Last updated {mins // 60}h ago"
    return templates.TemplateResponse(request, "friends.html", {
        **_auth_context(), "active": "friends",
        "friends": rows, "fetched_at_label": label,
    })


@app.post("/sync")
def trigger_sync(request: Request):
    config = auth.load_config()
    if not config.get("npsso"):
        return HTMLResponse(
            '<span style="color: var(--err);">Not authenticated</span>',
            status_code=400,
        )
    result = _run_trophy_sync(config["npsso"])
    if result["status"] == "error":
        return HTMLResponse(f'<span style="color: var(--err);">Failed: {result["error"]}</span>')
    msg = f'✓ Completed: +{result["trophies_added"]} trophies, {result["games_updated"]} games'
    if result.get("warnings"):
        msg += f'<br><span style="color: var(--fg-dim);">⚠ {len(result["warnings"])} warnings (no play time data)</span>'
    return HTMLResponse(f'<span style="color: var(--accent);">{msg}</span>')


@app.post("/sync-friends")
def trigger_sync_friends(request: Request):
    config = auth.load_config()
    if not config.get("npsso"):
        return HTMLResponse(
            '<span style="color: var(--err);">Not authenticated</span>',
            status_code=400,
        )
    result = _run_friends_sync(config["npsso"])
    return HTMLResponse(
        f'<span style="color: var(--accent);">'
        f'✓ Completed: {result["processed"]} friends, {result["games_stored"]} games'
        f'</span>'
    )


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


@app.get("/game/{np_comm_id}", response_class=HTMLResponse)
def game_detail(request: Request, np_comm_id: str):
    conn = db.get_conn()
    game = db.get_game(conn, np_comm_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    trophies = db.get_trophies(conn, np_comm_id)
    friend_comparison = db.get_friend_game_comparison(conn, np_comm_id)
    game_stats = db.get_game_stats(conn, np_comm_id)
    today = date.today()
    today_sec = db.get_play_time(conn, np_comm_id, today.isoformat(), today.isoformat())
    week_start = today - timedelta(days=today.weekday())
    week_sec = db.get_play_time(conn, np_comm_id, week_start.isoformat(), today.isoformat())
    month_sec = db.get_play_time(conn, np_comm_id, today.replace(day=1).isoformat(), today.isoformat())
    return templates.TemplateResponse(request, "game_detail.html", {
        **_auth_context(), "game": game, "trophies": trophies,
        "friend_comparison": friend_comparison,
        "game_stats": game_stats,
        "today_sec": today_sec, "week_sec": week_sec, "month_sec": month_sec,
    })


@app.post("/game/{np_comm_id}/time")
async def set_game_time(request: Request, np_comm_id: str):
    config = auth.load_config()
    if not config.get("npsso"):
        return HTMLResponse('<span style="color: var(--err);">Not authenticated</span>', status_code=400)
    form = await request.form()
    raw = (form.get("hours") or "").strip()
    sec = _parse_play_time(raw)
    if sec is None or sec <= 0:
        return HTMLResponse('<span style="color: var(--err);">Invalid format. Use e.g. 25.5 or 2h 30m</span>')
    conn = db.get_conn()
    db.set_manual_play_time(conn, np_comm_id, sec)
    conn.commit()
    return HTMLResponse(
        f'<span style="color: var(--accent);">✓ Saved: {sec//3600}h {(sec%3600)//60:02d}m</span>'
    )
