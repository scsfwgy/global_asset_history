/**
 * i18n — lightweight internationalisation engine.
 *
 * No dependencies.  Load this before all other application scripts so that
 * __() is available everywhere.
 *
 * Language resolution (first match wins):
 *   1. URL path prefix  — /en/yearly  →  en
 *   2. server-rendered initial language
 *   3. localStorage      — "gah-lang"
 *   4. navigator.language (first two chars)
 *   5. fallback          — "zh-CN"
 *
 * Usage:
 *   __("nav.yearlyReturns")                // plain lookup
 *   __("msg.items", { n: 5 })             // interpolation: {{n}} → 5
 *   <span data-i18n="nav.yearlyReturns"></span>   // auto-filled on DOM ready
 *   <input data-i18n-attr="placeholder|label.key">
 */

(function () {
  'use strict';

  const STORAGE_KEY = 'gah-lang';
  const SUPPORTED = ['zh-CN', 'en'];
  const DEFAULT_LANG = 'zh-CN';

  // ── State ──────────────────────────────────────────────────────────
  let _currentLang = DEFAULT_LANG;
  let _translations = {};   // the loaded locale dictionary

  // ── Helpers ────────────────────────────────────────────────────────

  function _detectLang() {
    // 1. URL prefix: /en/xxx or /zh/xxx
    var m = location.pathname.match(/^\/(en|zh)(?:\/|$)/);
    if (m) return m[1] === 'zh' ? 'zh-CN' : 'en';

    // 2. server-rendered initial language keeps body text aligned with SEO head.
    if (SUPPORTED.indexOf(window.__GAH_INITIAL_LANG__) !== -1) return window.__GAH_INITIAL_LANG__;

    // 3. localStorage
    try {
      var stored = localStorage.getItem(STORAGE_KEY);
      if (stored && SUPPORTED.indexOf(stored) !== -1) return stored;
    } catch (_) { /* localStorage unavailable */ }

    // 4. browser preference (only first two chars — "zh" → "zh-CN")
    var nav = navigator.language || '';
    if (nav.slice(0, 2) === 'zh') return 'zh-CN';
    if (nav.slice(0, 2) === 'en') return 'en';

    // 5. fallback
    return DEFAULT_LANG;
  }

  /**
   * Simple template interpolation: __("key", {name:"World"})
   * Placeholders in translations use {{name}} syntax.
   */
  function _interpolate(template, params) {
    if (!params || typeof params !== 'object') return template;
    return template.replace(/\{\{(\w+)\}\}/g, function (_, key) {
      return params.hasOwnProperty(key) ? String(params[key]) : '{{' + key + '}}';
    });
  }

  // ── Public API ─────────────────────────────────────────────────────

  /**
   * Translate a dotted key.  Returns the key itself (in brackets) when
   * the translation is missing so bugs are visible rather than silent.
   *
   *   __("nav.yearlyReturns")              → "历年涨跌幅"
   *   __("msg.count", { n: 3 })            → "共 3 项"
   *   __("missing.key")                    → "[missing.key]"
   */
  window.__ = function (key, params) {
    if (!key) return '';
    var parts = key.split('.');
    var val = _translations;
    for (var i = 0; i < parts.length; i++) {
      if (val == null) break;
      val = val[parts[i]];
    }
    if (typeof val !== 'string') return '[' + key + ']';
    return _interpolate(val, params);
  };

  /** Return the current language code ("zh-CN" | "en"). */
  window.__lang = function () {
    return _currentLang;
  };

  /** Return the list of supported languages. */
  window.__supportedLangs = function () {
    return SUPPORTED.slice();
  };

  /**
   * Switch language, persist, and reload the page at the correct URL.
   * If URL-prefix routing is active the page reloads to the new prefix;
   * otherwise it sets localStorage and reloads in place.
   */
  window.__switchLang = function (lang) {
    if (SUPPORTED.indexOf(lang) === -1) return;
    try { localStorage.setItem(STORAGE_KEY, lang); } catch (_) {}

    var short = lang === 'zh-CN' ? 'zh' : 'en';
    var path = location.pathname;
    var m = path.match(/^\/(en|zh)(\/|$)/);
    if (m) {
      // URL prefix exists — swap it
      path = '/' + short + path.slice(m[0].length - (m[2] ? 1 : 0));
    } else {
      // No prefix — insert one (keep the root path clean for zh which is default)
      path = '/' + short + (path === '/' ? '' : path);
    }
    // Preserve hash
    var hash = location.hash || '';
    location.href = path + hash;
  };

  /** Get the URL prefix for a given language (for building hreflang links). */
  window.__langPath = function (path, lang) {
    var short = lang === 'zh-CN' ? 'zh' : 'en';
    path = path || '/';
    return '/' + short + (path === '/' ? '' : path);
  };

  // ── Initialise ─────────────────────────────────────────────────────

  function _init() {
    _currentLang = _detectLang();

    // Build the locale script URL and load synchronously via XHR so that
    // translations are ready before any other script runs.  We use a
    // blocking synchronous XHR here because other scripts reference __()
    // at global scope evaluation time.
    var url = '/locales/' + _currentLang + '.json';
    try {
      var xhr = new XMLHttpRequest();
      xhr.open('GET', url, false); // synchronous — intentional
      xhr.send();
      if (xhr.status === 200) {
        _translations = JSON.parse(xhr.responseText);
      } else {
        console.warn('[i18n] Failed to load locale ' + _currentLang + ' (' + xhr.status + '), falling back to ' + DEFAULT_LANG);
        // Retry with default language
        if (_currentLang !== DEFAULT_LANG) {
          xhr.open('GET', '/locales/' + DEFAULT_LANG + '.json', false);
          xhr.send();
          if (xhr.status === 200) {
            _translations = JSON.parse(xhr.responseText);
          }
        }
      }
    } catch (e) {
      console.warn('[i18n] Could not load translations: ' + e.message);
    }

    // Set <html lang> early
    document.documentElement.lang = _currentLang;

    // Scan DOM for data-i18n attributes once the DOM is ready
    function _scanDOM() {
      // data-i18n="key" → set textContent
      var els = document.querySelectorAll('[data-i18n]');
      for (var i = 0; i < els.length; i++) {
        var el = els[i];
        var key = el.getAttribute('data-i18n');
        if (key) el.textContent = __(key);
      }

      // data-i18n-attr="attrName|key" → set attribute
      // Also supports data-i18n-attr-alt for a second attribute on the same node.
      var attrEls = document.querySelectorAll('[data-i18n-attr], [data-i18n-attr-alt]');
      for (var j = 0; j < attrEls.length; j++) {
        var ael = attrEls[j];
        ['data-i18n-attr', 'data-i18n-attr-alt'].forEach(function (attrSpecName) {
          var spec = ael.getAttribute(attrSpecName);
          if (!spec) return;
          var pipe = spec.indexOf('|');
          if (pipe === -1) return;
          var attrName = spec.slice(0, pipe);
          var attrKey = spec.slice(pipe + 1);
          ael.setAttribute(attrName, __(attrKey));
        });
      }

      // data-i18n-html="key" → set innerHTML (use sparingly!)
      var htmlEls = document.querySelectorAll('[data-i18n-html]');
      for (var k = 0; k < htmlEls.length; k++) {
        var hel = htmlEls[k];
        var hkey = hel.getAttribute('data-i18n-html');
        if (hkey) hel.innerHTML = __(hkey);
      }
    }

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', _scanDOM);
    } else {
      _scanDOM();
    }
  }

  _init();
})();
