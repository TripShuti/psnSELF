from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from psnself import auth, db
from psnself.web.services.friend_service import FriendService
from psnself.web.services.game_service import GameService
from psnself.web.template import templates
from psnself.web.utils import RARITY_COLORS, RARITY_LABELS, _auth_context, _parse_play_time

router = APIRouter()


@router.get("/game/{np_comm_id}", response_class=HTMLResponse)
def game_detail(request: Request, np_comm_id: str) -> HTMLResponse:
    conn = db.get_conn()
    gs = GameService(conn)
    fs = FriendService(conn)

    game = gs.get_game(np_comm_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    trophies = gs.get_trophies(np_comm_id)
    friend_comparison = fs.get_comparison(np_comm_id)
    game_stats = gs.get_game_stats(np_comm_id)
    periods = gs.get_play_time_periods(np_comm_id)

    return templates.TemplateResponse(request, "game_detail.html", {
        **_auth_context(), "active": "", "game": game, "trophies": trophies,
        "friend_comparison": friend_comparison,
        "game_stats": game_stats,
        **periods,
        "rarity_labels": RARITY_LABELS,
        "rarity_colors": RARITY_COLORS,
    })


@router.post("/game/{np_comm_id}/time")
async def set_game_time(request: Request, np_comm_id: str) -> HTMLResponse:
    config = auth.load_config()
    if not config.get("npsso"):
        return HTMLResponse('<span style="color: var(--err);">Not authenticated</span>', status_code=400)
    form = await request.form()
    raw = (form.get("hours") or "").strip()
    sec = _parse_play_time(raw)
    if sec is None or sec <= 0:
        return HTMLResponse('<span style="color: var(--err);">Invalid format. Use e.g. 25.5 or 2h 30m</span>')
    conn = db.get_conn()
    gs = GameService(conn)
    gs.set_manual_time(np_comm_id, sec)
    return HTMLResponse(
        f'<span style="color: var(--accent);">✓ Saved: {sec//3600}h {(sec%3600)//60:02d}m</span>'
    )
