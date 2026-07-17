from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from psnself import auth, db
from psnself import db_friends
from psnself.web.services.friend_service import FriendService
from psnself.web.template import templates
from psnself.web.utils import _auth_context

router = APIRouter()


@router.get("/friends", response_class=HTMLResponse)
def friends(request: Request) -> HTMLResponse:
    conn = db.get_conn()
    fs = FriendService(conn)
    rows = fs.get_leaderboard()
    label = fs.get_fetched_at_label()
    return templates.TemplateResponse(request, "friends.html", {
        **_auth_context(), "active": "friends",
        "friends": rows, "fetched_at_label": label,
    })


@router.get("/compare/{account_id}", response_class=HTMLResponse)
def friend_compare(request: Request, account_id: str) -> HTMLResponse:
    conn = db.get_conn()
    fs = FriendService(conn)
    cfg = auth.load_config()
    my_account_id = cfg.get("account_id", "")
    if my_account_id and account_id == my_account_id:
        raise HTTPException(status_code=400, detail="Cannot compare with yourself")

    friend = fs.get_raw_friend(account_id)
    if friend is None:
        raise HTTPException(status_code=404, detail="Friend not found")

    myself = fs.get_raw_level(my_account_id) if my_account_id else None
    if myself is None:
        myself = db_friends.get_raw_trophy_level_by_online_id(conn, cfg.get("online_id", ""))
    if myself is None:
        myself = {"trophy_level": None}

    games = fs.get_comparison_detail(account_id)

    return templates.TemplateResponse(request, "friend_compare.html", {
        **_auth_context(), "active": "", "friend": friend, "myself": myself, "games": games,
    })
