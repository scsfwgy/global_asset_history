/**
 * Versioned investment-guide notices.
 *
 * Each notice is shown until it is dismissed, then remembered independently.
 * Content is structured so link text is rendered as a DOM node, never HTML.
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'gah-knowledge-notice-seen-version';
  var CONFIG_PATH = '/config/knowledge-notices.json';

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

  function validUrl(value) {
    try {
      var url = new URL(value);
      return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : '';
    } catch (_) {
      return '';
    }
  }

  function localizedText(value, lang) {
    var languageKey = languageFor(lang);
    var preferred = value && typeof value[languageKey] === 'string' ? value[languageKey].trim() : '';
    if (preferred) return preferred;
    var fallback = value && typeof value.zh === 'string' ? value.zh.trim() : '';
    return fallback || (value && typeof value.en === 'string' ? value.en.trim() : '');
  }

  function languageFor(lang) {
    return lang === 'zh' || lang === 'zh-CN' || lang === 'zh-TW' ? 'zh' : 'en';
  }

  function noticeItems(release, lang) {
    var languageKey = languageFor(lang);
    var preferred = Array.isArray(release && release[languageKey]) ? release[languageKey] : null;
    var fallback = Array.isArray(release && release.zh)
      ? release.zh
      : (Array.isArray(release && release.en) ? release.en : []);
    return (preferred || fallback).map(function (item) {
      var text = typeof (item && item.text) === 'string' ? item.text : '';
      var link = item && item.link;
      var label = typeof (link && link.label) === 'string' ? link.label.trim() : '';
      var href = validUrl(link && link.href);
      return text.trim() || (label && href) ? { text: text, label: label, href: href } : null;
    }).filter(Boolean);
  }

  function validNotices(config, lang) {
    if (!Array.isArray(config)) return [];
    return config.map(function (release) {
      var date = typeof (release && release.date) === 'string' ? release.date.trim() : '';
      return {
        version: typeof (release && release.version) === 'number' && Number.isFinite(release.version)
          ? String(release.version)
          : '',
        date: /^\d{4}\.\d{2}\.\d{2}$/.test(date) ? date : '',
        title: localizedText(release && release.title, lang),
        items: noticeItems(release, lang)
      };
    }).filter(function (release) {
      return release.version && release.date && release.items.length;
    });
  }

  function appendItems(container, items) {
    var list = document.createElement('ul');
    list.className = 'knowledge-notice-items';
    items.forEach(function (item) {
      var entry = document.createElement('li');
      entry.appendChild(document.createTextNode(item.text));
      if (item.label && item.href) {
        var link = document.createElement('a');
        link.href = item.href;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        link.textContent = item.label;
        entry.appendChild(link);
      }
      list.appendChild(entry);
    });
    container.appendChild(list);
  }

  function enqueueNotice(show) {
    if (typeof window.gahEnqueueNotice === 'function') {
      window.gahEnqueueNotice(show, { priority: 1, delayMs: 5000 });
    } else {
      show(function () {});
    }
  }

  function openDialog(config, done) {
    var dialog = document.getElementById('knowledgeNoticeDialog');
    var content = document.getElementById('knowledgeNoticeList');
    var title = document.getElementById('knowledgeNoticeTitle');
    var meta = document.getElementById('knowledgeNoticeMeta');
    var confirmButton = document.getElementById('knowledgeNoticeConfirm');
    if (!dialog || !content || !title || !meta || !confirmButton) { done(); return; }

    var lang = typeof window.__lang === 'function' ? window.__lang() : 'en';
    var notices = validNotices(config, lang);
    if (!notices.length) { done(); return; }

    var latest = notices[notices.length - 1];
    var settled = false;
    function finish() {
      if (settled) return;
      settled = true;
      done();
    }

    title.textContent = latest.title || translated('knowledgeNotice.title', null, 'Investment Guide');
    meta.textContent = translated(
      'knowledgeNotice.meta',
      { version: latest.version, date: latest.date },
      'Version ' + latest.version + ' · ' + latest.date
    );
    content.textContent = '';
    appendItems(content, latest.items);
    confirmButton.textContent = translated('knowledgeNotice.confirm', null, 'Got it');
    confirmButton.onclick = function () {
      rememberVersion(latest.version);
      if (typeof dialog.close === 'function') dialog.close();
      else { dialog.removeAttribute('open'); finish(); }
    };
    dialog.addEventListener('close', finish, { once: true });

    if (typeof dialog.showModal === 'function') {
      dialog.showModal();
      try { dialog.focus({ preventScroll: true }); } catch (_) { dialog.focus(); }
    } else {
      dialog.setAttribute('open', '');
    }
  }

  function renderNotice(config) {
    var lang = typeof window.__lang === 'function' ? window.__lang() : 'en';
    var notices = validNotices(config, lang);
    if (!notices.length) return;
    var latest = notices[notices.length - 1];
    if (getSeenVersion() === latest.version) return;
    enqueueNotice(function (done) { openDialog(config, done); });
  }

  fetch(configUrl(), { headers: { Accept: 'application/json' } })
    .then(function (response) {
      if (!response.ok) throw new Error('knowledge notice config unavailable');
      return response.json();
    })
    .then(renderNotice)
    .catch(function () { /* Optional notice: page functionality must remain unaffected. */ });
})();
