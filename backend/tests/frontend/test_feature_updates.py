"""Integration checks for the versioned feature-update notice."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_local_notice_config_files_are_removed():
    assert not (ROOT / 'frontend/config/feature-updates.json').exists()
    assert not (ROOT / 'frontend/config/knowledge-notices.json').exists()


def test_feature_update_dialog_and_history_controls_are_wired_into_the_main_page():
    page = _source("frontend/price-change.html")
    zh = json.loads(_source("frontend/locales/zh-CN.json"))["featureUpdates"]
    en = json.loads(_source("frontend/locales/en.json"))["featureUpdates"]

    assert 'id="featureUpdateDialog"' in page
    assert 'id="featureUpdateList"' in page
    assert 'id="featureUpdateHistory"' in page
    assert 'id="featureUpdateConfirm"' in page
    assert 'data-i18n="featureUpdates.history"' in page
    assert 'data-i18n="featureUpdates.confirm"' in page
    assert 'src="/js/feature-updates.js"' in page
    assert page.index('src="/js/i18n.js"') < page.index('src="/js/feature-updates.js"')
    expected_keys = {
        "title",
        "historyTitle",
        "version",
        "latestMetaOne",
        "latestMeta",
        "historyMeta",
        "history",
        "backToLatest",
        "confirm",
    }
    assert expected_keys <= zh.keys()
    assert expected_keys <= en.keys()


def test_settings_menu_opens_the_update_dialog_on_demand():
    page = _source("frontend/price-change.html")
    settings_js = _source("frontend/js/site-settings.js")
    script = _source("frontend/js/feature-updates.js")
    zh = json.loads(_source("frontend/locales/zh-CN.json"))["settings"]
    en = json.loads(_source("frontend/locales/en.json"))["settings"]

    # The row markup stays on the page; the click wiring moved to the shared
    # site-settings.js module (also loaded by the standalone ETF page).
    assert 'id="settingsUpdateLogRow"' in page
    assert 'data-i18n="settings.updateLog"' in page
    assert 'document.getElementById("settingsUpdateLogRow")' in settings_js
    assert 'row.addEventListener("click"' in settings_js
    assert 'window.showFeatureUpdates === "function"' in settings_js
    assert "window.showFeatureUpdates = showFeatureUpdates" in script
    assert zh["updateLog"] == "更新日志"
    assert en["updateLog"] == "Update Log"


def test_settings_feature_list_ui_and_copy_are_removed():
    page = _source("frontend/price-change.html")
    zh_settings = json.loads(_source("frontend/locales/zh-CN.json"))["settings"]
    en_settings = json.loads(_source("frontend/locales/en.json"))["settings"]

    assert 'id="settingsFeatureListBtn"' not in page
    assert 'id="featureListDialog"' not in page
    assert "feature-list-" not in page
    assert not any(key.startswith("feature") for key in zh_settings)
    assert not any(key.startswith("feature") for key in en_settings)


def test_feature_update_script_uses_last_release_and_confirms_once():
    script = _source("frontend/js/feature-updates.js")

    assert "'/api/site-config/feature-updates'" in script
    assert "'gah-feature-update-seen-version'" in script
    assert "if (!Array.isArray(config)) return [];" in script
    assert "languageKey = lang === 'en' ? 'en' : 'zh'" in script
    assert "Number.isFinite(release.version)" in script
    assert r"/^\d{4}\.\d{2}\.\d{2}$/" in script
    assert "release.version && release.date && release.items.length" in script
    assert "if (!releases.length) return;" in script
    assert "releases[releases.length - 1]" in script
    assert "latest.items.length === 1" in script
    assert "getSeenVersion() === latest.version" in script
    assert "rememberVersion(latest.version)" in script
    assert "historyButton.onclick" in script
    assert "releases.slice().reverse()" in script
    assert "dialog.focus({ preventScroll: true })" in script
    assert "initialFeatureNoticePending" in script
    assert "noticeQueue.sort" in script


def test_feature_update_feed_is_dynamic_and_never_cached(monkeypatch):
    from app import app as flask_app
    from service import site_config
    releases = [{'version': 1, 'date': '2026.01.01', 'zh': ['测试'], 'en': ['Test']}]
    monkeypatch.setattr(site_config, 'read', lambda kind: {'enabled': True, 'items': releases})
    client = flask_app.test_client()
    for url in ('/api/site-config/feature-updates', '/api/site-config/feature-updates?v=old'):
        response = client.get(url)
        assert response.json == releases
        assert response.headers['Cache-Control'] == 'no-store'
    assert client.get('/config/feature-updates.json').status_code == 404


def test_versioned_knowledge_notice_supports_safe_clickable_links_and_once_only_display():
    page = _source("frontend/price-change.html")
    script = _source("frontend/js/knowledge-notices.js")
    zh = json.loads(_source("frontend/locales/zh-CN.json"))["knowledgeNotice"]
    en = json.loads(_source("frontend/locales/en.json"))["knowledgeNotice"]

    assert 'id="knowledgeNoticeDialog"' in page
    assert 'id="knowledgeNoticeList"' in page
    assert 'id="knowledgeNoticeConfirm"' in page
    assert 'src="/js/knowledge-notices.js"' in page
    assert page.index('src="/js/i18n.js"') < page.index('src="/js/feature-updates.js"')
    assert page.index('src="/js/feature-updates.js"') < page.index('src="/js/knowledge-notices.js"')
    assert "'gah-knowledge-notice-seen-version'" in script
    assert "new URL(value)" in script
    assert "url.protocol === 'https:' || url.protocol === 'http:'" in script
    assert "link.target = '_blank'" in script
    assert "link.rel = 'noopener noreferrer'" in script
    assert "text.trim() || (label && href)" in script
    assert "if (item.label && item.href)" in script
    assert "localizedText(release && release.title, lang)" in script
    assert "return lang === 'zh' || lang === 'zh-CN' || lang === 'zh-TW' ? 'zh' : 'en';" in script
    assert "window.gahEnqueueNotice(show, { priority: 1, delayMs: 5000 });" in script
    assert "latest.title || translated('knowledgeNotice.title'" in script
    assert "getSeenVersion() === latest.version" in script
    assert "rememberVersion(latest.version)" in script
    assert {"title", "meta", "confirm"} <= zh.keys()
    assert {"title", "meta", "confirm"} <= en.keys()


def test_knowledge_notice_feed_is_dynamic_and_never_cached(monkeypatch):
    from app import app as flask_app
    from service import site_config
    notices = [{'version': 1, 'date': '2026.01.01', 'title': {'zh': '公告', 'en': 'Notice'},
                'zh': [{'text': '测试'}], 'en': [{'text': 'Test'}]}]
    monkeypatch.setattr(site_config, 'read', lambda kind: {'enabled': True, 'items': notices})
    client = flask_app.test_client()
    for url in ('/api/site-config/knowledge-notices', '/api/site-config/knowledge-notices?v=old'):
        response = client.get(url)
        assert response.json == notices
        assert response.headers['Cache-Control'] == 'no-store'
    assert client.get('/config/knowledge-notices.json').status_code == 404
    assert "'/api/site-config/knowledge-notices'" in _source('frontend/js/knowledge-notices.js')
