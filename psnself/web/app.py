"""
psnSELF — read-only web frontend over the SQLite database.
"""
from __future__ import annotations

import asyncio
import logging
import time
import threading
from collections import Counter
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import Response

from psnself import db
from psnself.log import setup_logger
from psnself.web.routes.api import router as api_router
from psnself.web.routes.auth import router as auth_router
from psnself.web.routes.dashboard import router as dashboard_router
from psnself.web.routes.friends import router as friends_router
from psnself.web.routes.games import router as games_router
from psnself.web.scheduler import _scheduler_loop

LOGGER = setup_logger()

app = FastAPI(title="psnSELF")

app.include_router(api_router)
app.include_router(dashboard_router)
app.include_router(auth_router)
app.include_router(games_router)
app.include_router(friends_router)

_API_BURST_IDLE_SECONDS = 1.0
_api_bursts: dict[str, dict] = {}
_api_burst_tasks: dict[str, asyncio.Task] = {}
_api_burst_lock = asyncio.Lock()


def _api_route(path: str) -> str:
    # Collapse per-game detail paths so summaries stay compact.
    if path.startswith("/api/v1/games/"):
        return "/api/v1/games/{id}"
    return path


async def _flush_api_burst(client_key: str) -> None:
    try:
        await asyncio.sleep(_API_BURST_IDLE_SECONDS)
        async with _api_burst_lock:
            burst = _api_bursts.pop(client_key, None)
            _api_burst_tasks.pop(client_key, None)
        if not burst:
            return
        routes = ", ".join(
            f"{route} x{count}" for route, count in sorted(burst["routes"].items())
        )
        elapsed = (burst["last"] - burst["first"]) * 1000
        LOGGER.info(
            "API summary: %d requests, %d responses, %d bytes, %d errors, %.0fms; %s",
            burst["count"], burst["responses"], burst["bytes"],
            burst["errors"], elapsed, routes,
        )
    except asyncio.CancelledError:
        return


async def _record_api_response(request: Request, response, elapsed_ms: float) -> None:
    client_key = request.client.host if request.client else "unknown"
    now = time.monotonic()
    try:
        response_bytes = int(response.headers.get("content-length", "0"))
    except ValueError:
        response_bytes = 0
    async with _api_burst_lock:
        burst = _api_bursts.setdefault(client_key, {
            "first": now, "last": now, "count": 0, "responses": 0,
            "bytes": 0, "errors": 0, "routes": Counter(),
        })
        burst["last"] = now
        burst["count"] += 1
        burst["responses"] += 1
        burst["bytes"] += response_bytes
        burst["errors"] += response.status_code >= 400
        burst["routes"][_api_route(request.url.path)] += 1
        old_task = _api_burst_tasks.get(client_key)
        if old_task:
            old_task.cancel()
        _api_burst_tasks[client_key] = asyncio.create_task(_flush_api_burst(client_key))


@app.middleware("http")
async def concise_access_log(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        LOGGER.exception("HTTP %s %s failed", request.method, request.url.path)
        raise
    elapsed_ms = (time.perf_counter() - started) * 1000
    if request.url.path.startswith("/api/"):
        await _record_api_response(request, response, elapsed_ms)
    else:
        LOGGER.info("HTTP %s %s %d %.1fms", request.method, request.url.path,
                    response.status_code, elapsed_ms)
    return response

@app.get("/favicon.ico")
def favicon() -> Response:
    return Response(status_code=204)


@app.on_event("startup")
def _startup() -> None:
    logging.getLogger("uvicorn.access").disabled = True
    if db.DB_PATH is None:
        from platformdirs import user_config_dir
        db.set_db_path(Path(user_config_dir("psnself")) / "trophies.db")
    db.init_db()
    LOGGER.info("psnSELF started — scheduler launching")
    threading.Thread(target=_scheduler_loop, daemon=True).start()
