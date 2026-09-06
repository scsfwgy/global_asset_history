"""Tests for visit counter, event tracking, and admin stats dashboard."""

import os
from unittest.mock import patch

import pytest

from service import visitor_stats


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

    def test_increment_can_record_initial_tab_in_same_request(self, client):
        import app as app_module

        with (
            patch.object(app_module.cache_store, "is_enabled", return_value=True),
            patch.object(app_module.cache_store, "cache_incr", return_value=7),
            patch.object(app_module.cache_store, "cache_hincrby") as mock_hincrby,
            patch.object(app_module, "_record_unique_visit", return_value=None),
        ):
            resp = client.post("/api/visits/increment", json={"tab": "heatmap"})

        assert resp.status_code == 200
        assert resp.get_json()["count"] == 7
        mock_hincrby.assert_called_once_with(app_module._TAB_VISITS_KEY, "heatmap")

    def test_increment_records_independent_language_dimensions(self, client):
        uid = "11111111-1111-4111-8111-111111111111"
        payload = {
            "anonymous_id": uid,
            "site_language": "zh-CN",
            "device_language": "en-US",
        }

        client.post("/api/visits/increment", json=payload)
        client.post("/api/visits/increment", json=payload)
        client.post("/api/visits/increment", json={**payload, "site_language": "en"})

        assert visitor_stats.get_language_stats() == {
            "site_language": {"zh-CN": 1, "zh-TW": 0, "en": 1},
            "device_language": {"en-US": 1},
        }


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


class TestTools24Tracking:
    """POST /api/tools24/track for page_view, download, google_play"""

    def test_page_view(self, client):
        resp = client.post("/api/tools24/track", json={"event": "page_view"})
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

    def test_download(self, client):
        resp = client.post("/api/tools24/track", json={"event": "download"})
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

    def test_google_play(self, client):
        resp = client.post("/api/tools24/track", json={"event": "google_play"})
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

    def test_unknown_event(self, client):
        resp = client.post("/api/tools24/track", json={"event": "bogus"})
        assert resp.status_code == 400

    def test_missing_event(self, client):
        resp = client.post("/api/tools24/track", json={})
        assert resp.status_code == 400

    def test_file_fallback_increments_independently(self, client):
        import app as app_module

        client.post("/api/tools24/track", json={"event": "download"})
        client.post("/api/tools24/track", json={"event": "download"})
        client.post("/api/tools24/track", json={"event": "page_view"})

        with app_module._tools24_stats_lock:
            data = app_module._read_tools24_stats()
        assert data == {"download": 2, "page_view": 1}



class TestVisitorStatsPages:
    def test_main_pages_load_visitor_stats(self, client):
        for path in ("/zh/yearly", "/en/yearly"):
            html = client.get(path).get_data(as_text=True)
            assert "/js/visitor-stats.js?v=" in html
            assert "gahRecordVisit" in html

    def test_etf_page_loads_visitor_stats(self, client):
        html = client.get("/zh/etf-market").get_data(as_text=True)

        assert "/js/visitor-stats.js?v=" in html
        assert 'gahRecordVisit("etf")' in html

    def test_excluded_pages_do_not_load_visitor_stats(self):
        import app as app_module

        for filename in ("landing.html", "health.html"):
            html = (app_module.FRONTEND_DIR / filename).read_text()
            assert "visitor-stats.js" not in html


class TestAdminStatsDashboard:
    FAKE_TOKEN = 'test-admin-token-123'

    @pytest.fixture(autouse=True)
    def set_admin_token(self, monkeypatch):
        monkeypatch.setenv('STATS_READ_TOKEN', self.FAKE_TOKEN)

    def read(self, client):
        response = client.get('/api/admin/stats', headers={'Authorization': 'Bearer ' + self.FAKE_TOKEN})
        assert response.status_code == 200
        return response.json['data']

    def test_old_dashboard_moves_to_hometools_without_forwarding_token(self, client):
        response = client.get('/api/stats?token=old-secret')
        assert response.status_code == 302
        assert response.headers['Location'] == 'https://www.tools24.uk/admin/sites?source=globalassets'

    def test_stats_dashboard_shows_unique_user_count(self, client):
        for uid in ('11111111-1111-4111-8111-111111111111', '22222222-2222-4222-8222-222222222222'):
            client.post('/api/visits/increment', json={'anonymous_id': uid})
        data = self.read(client)
        assert {row['label']: row['value'] for row in data['metrics']}['今日访客'] == 2
        assert data['dailyUsers'][-1]['users'] == 2

    def test_stats_dashboard_shows_tools24_stats(self, client):
        for event in ('page_view', 'download', 'google_play'):
            client.post('/api/tools24/track', json={'event': event})
        groups = self.read(client)['breakdowns']
        rows = next(g['rows'] for g in groups if g['label'] == '旧 Tools24 下载站 · 历史累计')
        assert {r['id']: r['value'] for r in rows} == {'page_view': 1, 'download': 1, 'google_play': 1}

    def test_independent_language_distributions_and_shares(self, client):
        for uid, lang, device in [('11111111-1111-4111-8111-111111111111','zh-CN','en-US'),
                                  ('11111111-1111-4111-8111-111111111111','en','en-US'),
                                  ('22222222-2222-4222-8222-222222222222','zh-CN','zh-TW')]:
            client.post('/api/visits/increment', json={'anonymous_id': uid, 'site_language': lang, 'device_language': device})
        groups = self.read(client)['breakdowns']
        site = next(g['rows'] for g in groups if g['label'].startswith('网站使用语言'))
        assert {r['id']: r['value'] for r in site} == {'zh-CN': 2, 'en': 1, 'zh-TW': 0}
        assert {r['id']: r['share'] for r in site}['zh-CN'] == 66.7
        device = next(g['rows'] for g in groups if g['label'].startswith('设备语言'))
        assert {r['id']: r['value'] for r in device} == {'en-US': 1, 'zh-TW': 1}
