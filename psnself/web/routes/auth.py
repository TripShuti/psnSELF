from __future__ import annotations

import threading
import time

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from psnself import auth, sync
from psnself.web.scheduler import _load_schedule, _save_schedule
from psnself.web.template import templates
from psnself.web.utils import _auth_context

router = APIRouter()


@router.get("/auth", response_class=HTMLResponse)
def auth_page(request: Request) -> HTMLResponse:
    sc = _load_schedule()
    return templates.TemplateResponse(request, "auth.html", {
        **_auth_context(), "active": "auth",
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
    status = "enabled ✓ — runs daily between 23:00 and 00:00 (random minute)" if enabled else "disabled"
    return HTMLResponse(f'<span style="color: var(--accent);">✓ Auto sync {status}</span>')
