from __future__ import annotations

import threading
import time

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from psnself import auth
from psnself.web.scheduler import _load_schedule, _run_friends_sync, _run_trophy_sync, _save_schedule
from psnself.web.template import templates
from psnself.web.utils import _auth_context, _fmt_remaining

router = APIRouter()


@router.get("/auth", response_class=HTMLResponse)
def auth_page(request: Request) -> HTMLResponse:
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


@router.post("/auth")
async def auth_submit(request: Request) -> HTMLResponse:
    form = await request.form()
    npsso = (form.get("npsso") or "").strip()

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
        _run_trophy_sync(npsso)
        time.sleep(30)
        _run_friends_sync(npsso)
    threading.Thread(target=_run_both, daemon=True).start()

    return HTMLResponse(
        f'<span style="color: var(--accent);">Authenticated as {online_id}! '
        f'Sync started in background — reload in a few minutes.</span>'
    )


@router.post("/auth/schedule")
async def auth_schedule(request: Request) -> HTMLResponse:
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
