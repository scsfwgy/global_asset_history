"""Integration checks for the versioned feature-update notice."""

import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_feature_update_config_is_a_bilingual_release_list():
    releases = json.loads(_source("frontend/config/feature-updates.json"))

    assert isinstance(releases, list)
    assert releases
    assert len({release["version"] for release in releases}) == len(releases)
    for release in releases:
        assert isinstance(release["version"], int) and release["version"] > 0
        assert datetime.strptime(release["date"], "%Y.%m.%d")
        assert release["zh"]
        assert release["en"]
        assert all(isinstance(item, str) and item.strip() for item in release["zh"])
        assert all(isinstance(item, str) and item.strip() for item in release["en"])


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

    assert "'/config/feature-updates.json'" in script
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


def test_feature_update_config_is_served_with_the_frontend_cache_policy():
    from app import app as flask_app

    flask_app.config["TESTING"] = True
    client = flask_app.test_client()
    configured_releases = json.loads(_source("frontend/config/feature-updates.json"))
    page = client.get("/zh/heatmap")
    version = page.headers["X-Frontend-Version"]

    unversioned = client.get("/config/feature-updates.json")
    assert unversioned.status_code == 200
    assert unversioned.get_json() == configured_releases
    assert unversioned.headers["Cache-Control"] == "no-cache, max-age=0, must-revalidate"

    versioned = client.get(f"/config/feature-updates.json?v={version}")
    assert versioned.status_code == 200
    assert versioned.get_json() == configured_releases
    assert versioned.headers["Cache-Control"] == "public, max-age=31536000, immutable"


def test_versioned_knowledge_notice_supports_safe_clickable_links_and_once_only_display():
    notices = json.loads(_source("frontend/config/knowledge-notices.json"))
    page = _source("frontend/price-change.html")
    script = _source("frontend/js/knowledge-notices.js")
    zh = json.loads(_source("frontend/locales/zh-CN.json"))["knowledgeNotice"]
    en = json.loads(_source("frontend/locales/en.json"))["knowledgeNotice"]

    assert isinstance(notices, list) and notices
    assert len({notice.get("version") for notice in notices}) == len(notices)
    for notice in notices:
        assert isinstance(notice.get("version"), int) and notice["version"] > 0
        assert datetime.strptime(notice.get("date", ""), "%Y.%m.%d")
        assert isinstance(notice.get("title"), dict)
        assert all(isinstance(notice["title"].get(lang), str) and notice["title"][lang].strip()
                   for lang in ("zh", "en"))
        for lang in ("zh", "en"):
            items = notice.get(lang)
            assert isinstance(items, list) and items
            for item in items:
                assert isinstance(item, dict)
                text = item.get("text")
                link = item.get("link")
                assert (isinstance(text, str) and text.strip()) or isinstance(link, dict)
                if link is not None:
                    assert isinstance(link.get("label"), str) and link["label"].strip()
                    assert isinstance(link.get("href"), str)
                    assert link["href"].startswith(("https://", "http://"))
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


def test_knowledge_notice_config_is_served_with_the_frontend_cache_policy():
    from app import app as flask_app

    flask_app.config["TESTING"] = True
    client = flask_app.test_client()
    configured_notices = json.loads(_source("frontend/config/knowledge-notices.json"))
    page = client.get("/zh/heatmap")
    version = page.headers["X-Frontend-Version"]

    assert f'src="/js/knowledge-notices.js?v={version}"' in page.get_data(as_text=True)

    unversioned = client.get("/config/knowledge-notices.json")
    assert unversioned.status_code == 200
    assert unversioned.get_json() == configured_notices
    assert unversioned.headers["Cache-Control"] == "no-cache, max-age=0, must-revalidate"

    versioned = client.get(f"/config/knowledge-notices.json?v={version}")
    assert versioned.status_code == 200
    assert versioned.get_json() == configured_notices
    assert versioned.headers["Cache-Control"] == "public, max-age=31536000, immutable"
