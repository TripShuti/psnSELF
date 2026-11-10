from unittest.mock import Mock

import pytest
from psnawp_api.core.psnawp_exceptions import PSNAWPAuthenticationError

from psnself import auth, notifications
from psnself.sync import trophy_sync


@pytest.fixture
def configured(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "CONFIG_PATH", tmp_path / "config.json")
    auth.save_config({"npsso": "cookie", "telegram": {"enabled": True, "bot_token": "123:secret", "chat_id": "456"}})
    sender = Mock()
    monkeypatch.setattr(notifications, "send_telegram", sender)
    return sender


def test_alert_persists_and_resets_after_recovery(configured):
    error = PSNAWPAuthenticationError("expired")
    notifications.record_failure("cookie", error)
    notifications.record_failure("cookie", error)
    notifications.notify_pending()
    assert configured.call_count == 1
    assert notifications.load_state()["invalid"]
    notifications.record_success("cookie", trophies=True)
    assert notifications.load_state()["last_success"]
    assert not notifications.load_state()["invalid"]
    notifications.record_failure("cookie", error)
    assert configured.call_count == 2


def test_network_and_old_token_failures_do_not_alert(configured):
    notifications.record_failure("cookie", TimeoutError())
    notifications.record_failure("old-cookie", PSNAWPAuthenticationError("expired"))
    configured.assert_not_called()
    assert not notifications.load_state()


def test_failed_delivery_retries_with_backoff(configured, monkeypatch):
    configured.side_effect = RuntimeError("offline")
    notifications.record_failure("cookie", PSNAWPAuthenticationError("expired"))
    notifications.notify_pending()
    assert configured.call_count == 1
    assert not notifications.load_state().get("notified")
    configured.side_effect = None
    now = notifications.time.time()
    monkeypatch.setattr(notifications.time, "time", lambda: now + 301)
    notifications.notify_pending()
    assert configured.call_count == 2
    assert notifications.load_state()["notified"]


def test_sync_wrapper_reports_auth_failure(configured, monkeypatch):
    monkeypatch.setattr(trophy_sync, "_do_sync", Mock(side_effect=PSNAWPAuthenticationError("expired")))
    with pytest.raises(PSNAWPAuthenticationError):
        trophy_sync.sync_trophies("cookie")
    configured.assert_called_once()


def test_telegram_errors_hide_secrets(monkeypatch):
    monkeypatch.setattr(notifications, "urlopen", Mock(side_effect=ValueError("123:secret")))
    with pytest.raises(RuntimeError) as error:
        notifications.send_telegram({"bot_token": "123:secret", "chat_id": "456"}, "test")
    assert "secret" not in str(error.value)
