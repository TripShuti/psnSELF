"""Persistent authentication health and optional Telegram alerts."""
from __future__ import annotations

import json
import time
from threading import RLock
from urllib.request import Request, urlopen

from psnawp_api.core.psnawp_exceptions import (
    PSNAWPAuthenticationError, PSNAWPInvalidTokenError, PSNAWPUnauthorizedError,
)

from . import auth
from .log import get_logger

AUTH_ERRORS = (PSNAWPAuthenticationError, PSNAWPInvalidTokenError, PSNAWPUnauthorizedError)
_lock = RLock()
logger = get_logger("notifications")


def load_state() -> dict:
    path = auth.get_config_path().parent / "auth-health.json"
    return json.loads(path.read_text()) if path.exists() else {}


def _save_state(state: dict) -> None:
    path = auth.get_config_path().parent / "auth-health.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state))
    temporary.replace(path)


def send_telegram(settings: dict, message: str) -> None:
    """Do not propagate remote errors: they can contain the bot token."""
    try:
        request = Request(
            f'https://api.telegram.org/bot{settings["bot_token"]}/sendMessage',
            data=json.dumps({"chat_id": settings["chat_id"], "text": message}).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urlopen(request, timeout=10) as response:
            if not json.load(response).get("ok"):
                raise ValueError("Telegram rejected message")
    except Exception:
        raise RuntimeError("Telegram delivery failed. Check bot token, chat ID and connection.") from None


def notify_pending() -> None:
    with _lock:
        state = load_state()
        settings = auth.load_config().get("telegram", {})
        if not state.get("invalid") or state.get("notified") or not settings.get("enabled"):
            return
        if time.time() - state.get("last_attempt", 0) < 300:
            return
        state["last_attempt"] = time.time()
        _save_state(state)
        message = "psnSELF: NPSSO is no longer valid. Sync cannot continue. Update NPSSO on the authentication page."
        if settings.get("auth_url"):
            message += "\n" + settings["auth_url"]
        try:
            send_telegram(settings, message)
        except RuntimeError:
            logger.warning("Telegram alert delivery failed; will retry")
            return
        state["notified"] = True
        _save_state(state)
        logger.info("Telegram NPSSO alert delivered")


def record_failure(npsso: str, error: Exception) -> None:
    if not isinstance(error, AUTH_ERRORS):
        return
    with _lock:
        if auth.load_config().get("npsso") != npsso:
            return
        state = load_state()
        was_invalid = state.get("invalid", False)
        state["invalid"] = True
        _save_state(state)
        if not was_invalid:
            logger.warning("NPSSO rejected by PlayStation; authentication needs renewal")
        notify_pending()


def record_success(npsso: str, *, trophies: bool = False) -> None:
    with _lock:
        if auth.load_config().get("npsso") != npsso:
            return
        state = load_state()
        was_invalid = state.get("invalid", False)
        state.update(invalid=False, notified=False, last_attempt=0)
        if trophies:
            state["last_success"] = time.time()
        _save_state(state)
        if was_invalid:
            logger.info("NPSSO authentication recovered")
