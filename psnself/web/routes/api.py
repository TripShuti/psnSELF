"""Versioned, read-only integration API over the already-synced local database."""
from __future__ import annotations

import os
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from psnself import db

bearer = HTTPBearer(auto_error=False)


def require_api_key(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    expected = os.environ.get("PSNSELF_API_KEY", "").strip()
    if not expected:
        raise HTTPException(503, "Integration API is disabled: configure PSNSELF_API_KEY")
    if (credentials is None or credentials.scheme.lower() != "bearer"
            or not secrets.compare_digest(credentials.credentials.encode(), expected.encode())):
        raise HTTPException(401, "Invalid API key", headers={"WWW-Authenticate": "Bearer"})


router = APIRouter(prefix="/api/v1", tags=["Integration API"], dependencies=[Depends(require_api_key)])


# These queries intentionally omit NPSSO, credentials, friends and private config.
GAME_SELECT = """
SELECT g.np_communication_id AS id, g.np_title_id AS title_id,
       g.title_name AS name, g.title_icon_url AS cover_url, g.platform,
       g.progress, g.earned_bronze, g.earned_silver, g.earned_gold, g.earned_platinum,
       gs.total_seconds AS playtime_seconds, gs.play_count,
       gs.first_played, gs.last_played, g.updated_at
FROM games g LEFT JOIN game_stats gs ON gs.np_communication_id = g.np_communication_id
"""


@router.get("/games")
def search_games(
    q: Annotated[str, Query(max_length=200)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    # Casefold in Python gives predictable Unicode search with stock SQLite.
    needle = q.strip().casefold()
    conn = db.get_conn()
    rows = conn.execute(GAME_SELECT + " ORDER BY g.title_name COLLATE NOCASE, g.np_communication_id").fetchall()
    matches = [dict(row) for row in rows if needle in row["name"].casefold()]
    return {"games": matches[offset:offset + limit], "total": len(matches), "limit": limit, "offset": offset}


@router.get("/games/{game_id}")
def get_game(game_id: str) -> dict:
    row = db.get_conn().execute(GAME_SELECT + " WHERE g.np_communication_id = ?", (game_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Game not found in the synced PSN library")
    return dict(row)


@router.get("/status")
def sync_status() -> dict:
    row = db.get_conn().execute(
        "SELECT started_at, finished_at, status FROM sync_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return {"api_version": 1, "last_sync": dict(row) if row else None}
