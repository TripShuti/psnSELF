from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from psnself import auth, db
from psnself.web.app import app


@pytest.fixture
def client():
    old_db_path = db.DB_PATH
    old_config = auth.CONFIG_PATH
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            db_path = tmp / "trophies.db"
            auth.CONFIG_PATH = tmp / "config.json"
            auth.DB_PATH = db_path
            db.set_db_path(db_path)
            db.init_db()

            with TestClient(app) as c:
                yield c
    finally:
        db.close_conn()
        db.set_db_path(old_db_path)
        auth.CONFIG_PATH = old_config


class TestDashboard:
    def test_dashboard_returns_200(self, client: TestClient) -> None:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_dashboard_contains_title(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "Dashboard" in resp.text


class TestAuth:
    def test_auth_page_returns_200(self, client: TestClient) -> None:
        resp = client.get("/auth")
        assert resp.status_code == 200

    def test_auth_submit_rejects_short_npsso(self, client: TestClient) -> None:
        resp = client.post("/auth", data={"npsso": "short"})
        assert resp.status_code == 200
        assert "exactly 64 characters" in resp.text


class TestGameRoutes:
    def test_game_detail_404(self, client: TestClient) -> None:
        resp = client.get("/game/NONEXIST")
        assert resp.status_code == 404

    def test_game_detail_with_data(self, client: TestClient) -> None:
        conn = db.get_conn()
        conn.execute("""
            INSERT INTO games (np_communication_id, title_name, platform,
                defined_bronze, defined_silver, defined_gold, defined_platinum,
                earned_bronze, earned_silver, earned_gold, earned_platinum,
                progress, updated_at)
            VALUES ('NPWR001', 'Test Game', 'PS5',
                50, 20, 5, 1, 10, 5, 1, 0, 30, datetime('now'))
        """)
        conn.commit()
        resp = client.get("/game/NPWR001")
        assert resp.status_code == 200
        assert "Test Game" in resp.text


class TestFriends:
    def test_friends_returns_200(self, client: TestClient) -> None:
        resp = client.get("/friends")
        assert resp.status_code == 200


class TestSync:
    def test_sync_without_auth_returns_400(self, client: TestClient) -> None:
        resp = client.post("/sync")
        assert resp.status_code == 400

    def test_sync_friends_without_auth_returns_400(self, client: TestClient) -> None:
        resp = client.post("/sync-friends")
        assert resp.status_code == 400
