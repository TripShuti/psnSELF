from unittest.mock import Mock

from psnself import auth, notifications
from tests.test_routes import client  # noqa: F401


def test_save_and_render_without_exposing_token(client):
    response = client.post('/auth/telegram', data={
        'bot_token': '123:secret', 'chat_id': '456', 'telegram_enabled': '1',
    })
    assert 'saved' in response.text
    assert auth.load_config()['telegram']['enabled']
    page = client.get('/auth')
    assert 'secret' not in page.text
    assert 'Token saved' in page.text
    client.post('/auth/telegram', data={'chat_id': '789'})
    settings = auth.load_config()['telegram']
    assert settings['bot_token'] == '123:secret'
    assert settings['chat_id'] == '789'
    assert not settings['enabled']


def test_test_message_uses_entered_settings_without_saving(client, monkeypatch):
    sender = Mock()
    monkeypatch.setattr(notifications, 'send_telegram', sender)
    response = client.post('/auth/telegram', data={
        'action': 'test', 'bot_token': '123:secret', 'chat_id': '456',
    })
    assert 'Test message sent' in response.text
    assert sender.call_args.args[0]['chat_id'] == '456'
    assert not auth.load_config().get('telegram')


def test_invalid_configuration_and_banner(client):
    response = client.post('/auth/telegram', data={'telegram_enabled': '1'})
    assert 'first' in response.text
    auth.save_config({'npsso': 'cookie'})
    notifications.record_failure('cookie', notifications.AUTH_ERRORS[0]('expired'))
    page = client.get('/')
    assert 'NPSSO is no longer valid' in page.text
    assert 'Update NPSSO' in page.text
