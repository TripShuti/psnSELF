from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from psnself import auth, db
from psnself.web.app import app


@pytest.fixture
def api(tmp_path, monkeypatch):
    old_path = db.DB_PATH
    monkeypatch.setenv('PSNSELF_API_KEY', 'local-test-key')
    monkeypatch.setattr(auth, 'CONFIG_PATH', tmp_path / 'config.json')
    monkeypatch.setattr('psnself.web.app._scheduler_loop', lambda: None)
    db.set_db_path(tmp_path / 'api.db')
    db.init_db()
    conn = db.get_conn()
    conn.executemany('INSERT INTO games (np_communication_id, title_name, platform, progress) VALUES (?, ?, ?, ?)', [
        ('NPWR001_00', 'Гра Україна', 'PS5', 42), ('NPWR002_00', 'Another Game', 'PS4', 0),
    ])
    conn.execute("INSERT INTO game_stats (np_communication_id, total_seconds, play_count, last_played) VALUES ('NPWR001_00', 288180, 12, '2026-10-18T10:00:00Z')")
    conn.commit()
    with TestClient(app) as client:
        yield client
    db.close_conn()
    db.set_db_path(old_path)


HEADERS = {'Authorization': 'Bearer local-test-key'}


def test_disabled_and_auth(api, monkeypatch):
    assert api.get('/api/v1/games').status_code == 401
    assert api.get('/api/v1/games', headers={'Authorization': 'Bearer wrong'}).status_code == 401
    monkeypatch.delenv('PSNSELF_API_KEY')
    assert api.get('/api/v1/games', headers=HEADERS).status_code == 503


def test_unicode_search_and_stats(api):
    response = api.get('/api/v1/games', params={'q': 'УКРАЇНА'}, headers=HEADERS)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['total'] == 1
    game = result['games'][0]
    assert game['id'] == 'NPWR001_00'
    assert game['playtime_seconds'] == 288180
    assert game['play_count'] == 12
    assert game['progress'] == 42
    assert 'npsso' not in response.text.lower()


def test_detail_missing_and_null_time(api):
    assert api.get('/api/v1/games/MISSING', headers=HEADERS).status_code == 404
    game = api.get('/api/v1/games/NPWR002_00', headers=HEADERS).json()
    assert game['playtime_seconds'] is None
    assert game['progress'] == 0


def test_pagination_and_query_safety(api):
    result = api.get('/api/v1/games?limit=1&offset=1', headers=HEADERS).json()
    assert result['total'] == 2 and len(result['games']) == 1
    assert api.get('/api/v1/games?limit=101', headers=HEADERS).status_code == 422
    assert api.get('/api/v1/games', params={'q': "' OR 1=1 --"}, headers=HEADERS).json()['total'] == 0


def test_sync_status_and_no_writes(api):
    assert api.get('/api/v1/status', headers=HEADERS).json() == {'api_version': 1, 'last_sync': None}
    assert api.post('/api/v1/games', json={}, headers=HEADERS).status_code == 405
