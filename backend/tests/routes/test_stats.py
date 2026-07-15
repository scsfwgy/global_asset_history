"""Tests for visit counter, event tracking, and admin stats dashboard."""

import os

import pytest


class TestVisitCounter:
    """GET /api/visits and POST /api/visits/increment"""

    def test_get_visits_returns_count(self, client):
        resp = client.get("/api/visits")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "count" in data
        assert isinstance(data["count"], int)

    def test_get_visits_does_not_increment(self, client):
        before = client.get("/api/visits").get_json()["count"]
        after = client.get("/api/visits").get_json()["count"]
        # Reading should not change the count (file-based counter is stable)
        assert after == before

    def test_increment_increases_count(self, client):
        before = client.get("/api/visits").get_json()["count"]
        resp = client.post("/api/visits/increment")
        assert resp.status_code == 200
        after = resp.get_json()["count"]
        assert after == before + 1

    def test_anonymous_uuid_counts_unique_daily_users(self, client):
        import app as app_module

        first_uid = "11111111-1111-4111-8111-111111111111"
        second_uid = "22222222-2222-4222-8222-222222222222"

        first = client.post("/api/visits/increment", json={"anonymous_id": first_uid}).get_json()
        duplicate = client.post("/api/visits/increment", json={"anonymous_id": first_uid}).get_json()
        second = client.post("/api/visits/increment", json={"anonymous_id": second_uid}).get_json()

        assert first["unique_users_today"] == 1
        assert first["is_new_daily_user"] is True
        assert duplicate["unique_users_today"] == 1
        assert duplicate["is_new_daily_user"] is False
        assert second["unique_users_today"] == 2
        assert second["is_new_daily_user"] is True
        assert first_uid not in app_module._UNIQUE_VISITS_PATH.read_text()


class TestEventTracking:
    """POST /api/track for tab_view, ad_click, settings_click, settings_action"""

    def test_tab_view_valid(self, client):
        resp = client.post("/api/track",
                          json={"type": "tab_view", "tab": "heatmap"})
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

    def test_tab_view_unknown_tab(self, client):
        resp = client.post("/api/track",
                          json={"type": "tab_view", "tab": "nonexistent"})
        assert resp.status_code == 400

    def test_ad_click(self, client):
        resp = client.post("/api/track",
                          json={"type": "ad_click", "link": "value-investing"})
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

    def test_ad_click_no_link(self, client):
        resp = client.post("/api/track",
                          json={"type": "ad_click"})
        assert resp.status_code == 400

    def test_settings_click(self, client):
        resp = client.post("/api/track",
                          json={"type": "settings_click"})
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

    @pytest.mark.parametrize("action", ["theme", "colorscheme", "language"])
    def test_settings_action_valid(self, client, action):
        resp = client.post("/api/track",
                          json={"type": "settings_action", "action": action})
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

    def test_settings_action_unknown(self, client):
        resp = client.post("/api/track",
                          json={"type": "settings_action", "action": "bogus"})
        assert resp.status_code == 400

    def test_settings_action_missing(self, client):
        resp = client.post("/api/track",
                          json={"type": "settings_action"})
        assert resp.status_code == 400

    def test_unknown_event_type(self, client):
        resp = client.post("/api/track",
                          json={"type": "bogus"})
        assert resp.status_code == 400


class TestAdminStatsDashboard:
    """GET /api/stats — admin-only HTML dashboard"""

    FAKE_TOKEN = "test-admin-token-123"

    @pytest.fixture(autouse=True)
    def set_admin_token(self, monkeypatch):
        monkeypatch.setenv("WISH_ADMIN_TOKEN", self.FAKE_TOKEN)

    def test_stats_unauthorized_without_token(self, client):
        resp = client.get("/api/stats")
        assert resp.status_code == 401
        assert b"401" in resp.data

    def test_stats_unauthorized_with_wrong_token(self, client):
        resp = client.get("/api/stats?token=wrong")
        assert resp.status_code == 401

    def test_stats_authorized_with_correct_token(self, client):
        resp = client.get(f"/api/stats?token={self.FAKE_TOKEN}")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "GlobalAssetHistory" in html
        assert "总访问次数" in html
        assert "Tab 浏览" in html
        assert "广告位点击" in html
        assert "设置面板打开" in html
        assert "设置项操作" in html
        assert "每日唯一用户" in html
        assert "匿名 UUID 去重，仅保留最近 30 天" in html
        assert 'class="uv-chart"' in html

    def test_stats_shows_tracked_data(self, client):
        # Track some events first
        client.post("/api/track", json={"type": "tab_view", "tab": "yearly"})
        client.post("/api/track", json={"type": "tab_view", "tab": "yearly"})
        client.post("/api/track", json={"type": "ad_click", "link": "value-investing"})
        client.post("/api/track", json={"type": "settings_click"})

        resp = client.get(f"/api/stats?token={self.FAKE_TOKEN}")
        assert resp.status_code == 200
        # File-based counter should show the data since Redis is not configured in tests
        html = resp.get_data(as_text=True)
        # The dashboard should at least render without errors
        assert "<table>" in html

    def test_stats_dashboard_shows_unique_user_count(self, client):
        client.post("/api/visits/increment", json={"anonymous_id": "11111111-1111-4111-8111-111111111111"})
        client.post("/api/visits/increment", json={"anonymous_id": "22222222-2222-4222-8222-222222222222"})

        resp = client.get(f"/api/stats?token={self.FAKE_TOKEN}")
        html = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert '<div class="num">2</div><div class="label">今日用户</div>' in html
        assert "近30日用户天次" in html
