"""
psnSELF — read-only web frontend over the SQLite database.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from psnself import db
from psnself.log import setup_logger
from psnself.web.routes.auth import router as auth_router
from psnself.web.routes.dashboard import router as dashboard_router
from psnself.web.routes.friends import router as friends_router
from psnself.web.routes.games import router as games_router
from psnself.web.scheduler import _scheduler_loop

LOGGER = setup_logger()

app = FastAPI(title="psnSELF")

app.include_router(dashboard_router)
app.include_router(auth_router)
app.include_router(games_router)
app.include_router(friends_router)

_HERE = Path(__file__).parent
app.mount("/static", StaticFiles(directory=str(_HERE / "static")), name="static")


@app.get("/favicon.ico")
def favicon() -> Response:
    return Response(status_code=204)


@app.on_event("startup")
def _startup() -> None:
    uvicorn_logger = logging.getLogger("uvicorn.access")
    uvicorn_logger.handlers.clear()
    uvicorn_logger.propagate = True
    if db.DB_PATH is None:
        from platformdirs import user_config_dir
        db.set_db_path(Path(user_config_dir("psnself")) / "trophies.db")
    db.init_db()
    LOGGER.info("psnSELF started — scheduler launching")
    threading.Thread(target=_scheduler_loop, daemon=True).start()
