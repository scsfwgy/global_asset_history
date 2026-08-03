/**
 * Versioned feature-update notice.
 *
 * Releases live in /config/feature-updates.json. The last release is current,
 * and it is considered read only after the user confirms it.
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'gah-feature-update-seen-version';
  var CONFIG_PATH = '/config/feature-updates.json';
  var cachedConfig = null;

  function getSeenVersion() {
    try {
      return localStorage.getItem(STORAGE_KEY) || '';
    } catch (_) {
      return '';
    }
  }

  function rememberVersion(version) {
    try {
      localStorage.setItem(STORAGE_KEY, version);
    } catch (_) { /* localStorage unavailable — the notice may appear again */ }
  }

  function configUrl() {
    var assetVersion = window.__GAH_ASSET_VERSION__ || '';
    return assetVersion
      ? CONFIG_PATH + '?v=' + encodeURIComponent(assetVersion)
      : CONFIG_PATH;
  }

  function translated(key, params, fallback) {
    return typeof window.__ === 'function' ? window.__(key, params) : fallback;
  }

  function releaseItems(release, lang) {
    var languageKey = lang === 'en' ? 'en' : 'zh';
    var preferred = Array.isArray(release && release[languageKey]) ? release[languageKey] : null;
    var fallback = Array.isArray(release && release.zh)
      ? release.zh
      : (Array.isArray(release && release.en) ? release.en : []);
    return (preferred || fallback).filter(function (item) {
      return typeof item === 'string' && item.trim();
    }).map(function (item) {
      return item.trim();
    });
  }

  function validReleases(config, lang) {
    if (!Array.isArray(config)) return [];
    return config.map(function (release) {
      var date = typeof (release && release.date) === 'string' ? release.date.trim() : '';
      return {
        version: typeof (release && release.version) === 'number' && Number.isFinite(release.version)
          ? String(release.version)
          : '',
        date: /^\d{4}\.\d{2}\.\d{2}$/.test(date) ? date : '',
        items: releaseItems(release, lang)
      };
    }).filter(function (release) {
      return release.version && release.date && release.items.length;
    });
  }

  function appendItems(container, items) {
    var list = document.createElement('ul');
    list.className = 'feature-update-items';
    items.forEach(function (text) {
      var item = document.createElement('li');
      item.textContent = text;
      list.appendChild(item);
    });
    container.appendChild(list);
  }

  function openDialog(config) {
    var dialog = document.getElementById('featureUpdateDialog');
    var content = document.getElementById('featureUpdateList');
    var title = document.getElementById('featureUpdateTitle');
    var meta = document.getElementById('featureUpdateMeta');
    var historyButton = document.getElementById('featureUpdateHistory');
    var confirmButton = document.getElementById('featureUpdateConfirm');
    if (!dialog || !content || !title || !meta || !historyButton || !confirmButton) return;

    var lang = typeof window.__lang === 'function' ? window.__lang() : 'zh-CN';
    var releases = validReleases(config, lang);
    if (!releases.length) return;

    var latest = releases[releases.length - 1];

    function showLatest() {
      title.textContent = translated('featureUpdates.title', null, 'What\'s New');
      var latestMetaKey = latest.items.length === 1
        ? 'featureUpdates.latestMetaOne'
        : 'featureUpdates.latestMeta';
      meta.textContent = translated(
        latestMetaKey,
        { version: latest.version, date: latest.date, n: latest.items.length },
        'Version ' + latest.version + ' · ' + latest.date + ' · ' + latest.items.length
          + (latest.items.length === 1 ? ' update' : ' updates')
      );
      content.textContent = '';
      appendItems(content, latest.items);
      historyButton.textContent = translated('featureUpdates.history', null, 'View history');
      historyButton.setAttribute('aria-expanded', 'false');
      dialog.dataset.view = 'latest';
    }

    function showHistory() {
      title.textContent = translated('featureUpdates.historyTitle', null, 'Update history');
      meta.textContent = translated(
        'featureUpdates.historyMeta',
        { n: releases.length },
        releases.length + ' versions'
      );
      content.textContent = '';
      releases.slice().reverse().forEach(function (release) {
        var section = document.createElement('section');
        section.className = 'feature-update-release';
        var heading = document.createElement('h3');
        heading.textContent = translated(
          'featureUpdates.version',
          { version: release.version, date: release.date },
          'Version ' + release.version + ' · ' + release.date
        );
        section.appendChild(heading);
        appendItems(section, release.items);
        content.appendChild(section);
      });
      historyButton.textContent = translated('featureUpdates.backToLatest', null, 'Back to latest');
      historyButton.setAttribute('aria-expanded', 'true');
      dialog.dataset.view = 'history';
    }

    historyButton.onclick = function () {
      if (dialog.dataset.view === 'history') showLatest();
      else showHistory();
    };

    confirmButton.onclick = function () {
      rememberVersion(latest.version);
      if (typeof dialog.close === 'function') dialog.close();
      else dialog.removeAttribute('open');
    };

    dialog.dataset.version = latest.version;
    showLatest();
    if (typeof dialog.showModal === 'function') {
      dialog.showModal();
      try { dialog.focus({ preventScroll: true }); } catch (_) { dialog.focus(); }
    } else {
      dialog.setAttribute('open', '');
    }
  }

  function renderNotice(config) {
    cachedConfig = config;
    var lang = typeof window.__lang === 'function' ? window.__lang() : 'zh-CN';
    var releases = validReleases(config, lang);
    if (!releases.length) return;
    var latest = releases[releases.length - 1];
    if (getSeenVersion() === latest.version) return;
    openDialog(config);
  }

  function showFeatureUpdates() {
    if (cachedConfig) { openDialog(cachedConfig); return; }
    fetch(configUrl(), { headers: { Accept: 'application/json' } })
      .then(function (response) {
        if (!response.ok) throw new Error('feature update config unavailable');
        return response.json();
      })
      .then(function (config) {
        cachedConfig = config;
        openDialog(config);
      })
      .catch(function () { /* Optional notice: page functionality must remain unaffected. */ });
  }

  window.showFeatureUpdates = showFeatureUpdates;

  fetch(configUrl(), { headers: { Accept: 'application/json' } })
    .then(function (response) {
      if (!response.ok) throw new Error('feature update config unavailable');
      return response.json();
    })
    .then(renderNotice)
    .catch(function () { /* Optional notice: page functionality must remain unaffected. */ });
})();
