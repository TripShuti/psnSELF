from __future__ import annotations

import threading
import time
import re
from urllib.parse import urlsplit
from starlette.concurrency import run_in_threadpool

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from psnself import auth, sync, notifications
from psnself.web.scheduler import _load_schedule, _save_schedule
from psnself.web.template import templates
from psnself.web.utils import _auth_context

router = APIRouter()


@router.get("/auth", response_class=HTMLResponse)
def auth_page(request: Request) -> HTMLResponse:
    sc = _load_schedule()
    telegram = auth.load_config().get("telegram", {})
    return templates.TemplateResponse(request, "auth.html", {
        **_auth_context(), "active": "auth",
        "telegram": {k: v for k, v in telegram.items() if k != "bot_token"},
        "telegram_token_saved": bool(telegram.get("bot_token")),
        "daily_sync_enabled": sc.get("daily_sync_enabled", False),
        "last_auto_sync_date": sc.get("last_auto_sync_date"),
    })


@router.post("/auth")
async def auth_submit(request: Request) -> HTMLResponse:
    form = await request.form()
    npsso = str(form.get("npsso") or "").strip()

    if len(npsso) != 64:
        return HTMLResponse('<span style="color: var(--err);">NPSSO must be exactly 64 characters</span>')

    result = auth.validate_npsso(npsso)
    if result is None:
        return HTMLResponse('<span style="color: var(--err);">Invalid NPSSO. Make sure you copied it correctly.</span>')
    online_id, account_id = result

    cfg = auth.load_config()
    cfg.update({"npsso": npsso, "online_id": online_id, "account_id": account_id})
    auth.save_config(cfg)

    def _run_both():
        sync.sync_trophies(npsso)
        time.sleep(30)
        sync.fetch_friends_leaderboard(npsso)
    threading.Thread(target=_run_both, daemon=True).start()

    return HTMLResponse(
        f'<span style="color: var(--accent);">Authenticated as {online_id}! '
        f'Sync started in background — reload in a few minutes.</span>'
    )


@router.post("/auth/schedule")
async def auth_schedule(request: Request) -> HTMLResponse:
    form = await request.form()
    enabled = str(form.get("daily_sync_enabled", "0")).strip() in ("1", "true", "on")
    _save_schedule({"daily_sync_enabled": enabled})
    status = "enabled ✓ — runs daily between 23:00 and 00:00; missed runs resume automatically" if enabled else "disabled"
    return HTMLResponse(f'<span style="color: var(--accent);">✓ Auto sync {status}</span>')


@router.post("/auth/telegram")
async def telegram_settings(request: Request) -> HTMLResponse:
    form = await request.form()
    cfg = auth.load_config()
    previous = cfg.get("telegram", {})
    token = str(form.get("bot_token") or "").strip() or previous.get("bot_token", "")
    chat_id = str(form.get("chat_id") or "").strip()
    auth_url = str(form.get("auth_url") or "").strip()
    enabled = form.get("telegram_enabled") == "1"
    if token and not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]+", token):
        return HTMLResponse("Invalid bot token format.")
    if chat_id and not re.fullmatch(r"-?[0-9]+", chat_id):
        return HTMLResponse("Chat ID must be a number.")
    if auth_url and (urlsplit(auth_url).scheme not in ("http", "https") or not urlsplit(auth_url).netloc):
        return HTMLResponse("Authentication URL must start with http:// or https://.")
    if (enabled or form.get("action") == "test") and not (token and chat_id):
        return HTMLResponse("Enter a bot token and chat ID first.")
    settings = {"bot_token": token, "chat_id": chat_id, "auth_url": auth_url, "enabled": enabled}
    if form.get("action") == "test":
        try:
            await run_in_threadpool(notifications.send_telegram, settings, "psnSELF: Telegram notifications are working.")
        except RuntimeError as exc:
            return HTMLResponse(str(exc))
        return HTMLResponse("Test message sent. Click Save to store these settings.")
    cfg["telegram"] = settings
    auth.save_config(cfg)
    await run_in_threadpool(notifications.notify_pending)
    return HTMLResponse("Telegram settings saved.")
