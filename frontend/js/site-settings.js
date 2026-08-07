/**
 * Shared header settings: theme / color-scheme / language toggles and the
 * settings dropdown. Loaded on every app page (price-change + etf-market) so
 * the header behaves identically site-wide. Requires i18n.js to be loaded
 * first (uses the global __()).
 *
 * Icons are driven by CSS state (`[data-theme]` / `[data-color-scheme]`), so
 * this module never touches icon textContent — theme/color switch by class.
 */
(function () {
  "use strict";

  // ─── Settings dropdown ───
  (function () {
    var btn = document.getElementById("headerSettingsBtn");
    var menu = document.getElementById("headerSettingsMenu");
    if (!btn || !menu) return;

    // 10s idle hint: pulse + rotate + ring glow (3 loops, 2s each → 6s total)
    setTimeout(function () {
      btn.classList.add("hint");
      setTimeout(function () {
        btn.classList.remove("hint");
      }, 6200);
    }, 10000);

    // Track clicks on tracked external links
    var TRACKED_LINKS = {
      "feishu_us_stock": 'a[href*="kcn9via7j7oq"]',
      "github": 'a[href*="github.com"]',
      "xiaohongshu": 'a[href*="xhslink.com"]',
      "tools24": 'a[href*="tools24.uk"]'
    };
    Object.keys(TRACKED_LINKS).forEach(function (name) {
      var link = menu.querySelector(TRACKED_LINKS[name]);
      if (link) {
        link.addEventListener("click", function () {
          fetch("/api/link-click", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: name }),
            keepalive: true
          }).catch(function () {});
        });
      }
    });

    function setOpen(open) {
      if (open) {
        menu.style.display = "block";
        var newLink = menu.querySelector('a[href*="kcn9via7j7oq"]');
        if (newLink) newLink.classList.add("highlight-link");
        history.pushState({ _settingsOpen: true, _prev: location.pathname }, "", "/settings");
        if (typeof _track === "function") _track("settings_click");
      } else {
        menu.style.display = "none";
        var prev = (history.state && history.state._prev) || "/";
        history.replaceState({}, "", prev);
      }
    }

    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      setOpen(menu.style.display !== "block");
    });

    document.addEventListener("click", function () {
      if (menu.style.display === "block") setOpen(false);
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && menu.style.display === "block") setOpen(false);
    });
    menu.addEventListener("click", function (e) {
      e.stopPropagation();
    });
  })();

  // ─── Theme switching ───
  (function () {
    var STORAGE_KEY = "global-asset-history-theme";
    var html = document.documentElement;
    var label = document.getElementById("settingsThemeLabel");

    function applyTheme(theme) {
      if (theme === "light") {
        html.setAttribute("data-theme", "light");
      } else {
        html.removeAttribute("data-theme");
      }
      if (label) label.textContent = theme === "light" ? __("settings.themeLight") : __("settings.theme");
    }

    // Initialize: stored override > system preference. Sun/moon icon state is
    // pure CSS, keyed off [data-theme], so no icon DOM update is needed here.
    var stored = null;
    try { stored = localStorage.getItem(STORAGE_KEY); } catch (_) {}
    if (stored === "light" || stored === "dark") {
      applyTheme(stored);
    } else {
      var sys = window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
      applyTheme(sys);
    }

    var toggle = document.getElementById("settingsThemeToggle");
    if (toggle) {
      toggle.addEventListener("click", function () {
        var next = html.getAttribute("data-theme") === "light" ? "dark" : "light";
        applyTheme(next);
        try { localStorage.setItem(STORAGE_KEY, next); } catch (_) {}
        if (typeof window._refreshCharts === "function") window._refreshCharts();
        if (typeof _track === "function") _track("settings_action", { action: "theme" });
      });
    }

    // Listen for system preference changes (only when no manual override)
    window.matchMedia("(prefers-color-scheme: light)").addEventListener("change", function (e) {
      var hasOverride = false;
      try { hasOverride = !!localStorage.getItem(STORAGE_KEY); } catch (_) {}
      if (!hasOverride) {
        applyTheme(e.matches ? "light" : "dark");
        if (typeof window._refreshCharts === "function") window._refreshCharts();
      }
    });
  })();

  // ─── Color scheme switching (green-up / red-up) ───
  (function () {
    var COLOR_SCHEME_KEY = "global-asset-history-color-scheme";
    var html = document.documentElement;
    var label = document.getElementById("settingsColorSchemeLabel");

    function applyColorScheme(scheme) {
      if (scheme === "red_up") {
        html.setAttribute("data-color-scheme", "red_up");
      } else {
        html.removeAttribute("data-color-scheme");
      }
      if (label) label.textContent = scheme === "red_up" ? __("settings.colorSchemeRedUp") : __("settings.colorScheme");
      // Refresh any visible charts
      if (typeof window._refreshCharts === "function") window._refreshCharts();
    }

    // Initialize: localStorage override > backend config (price-change.js init
    // calls window.applyColorScheme when there is no localStorage value).
    var stored = null;
    try { stored = localStorage.getItem(COLOR_SCHEME_KEY); } catch (_) {}
    if (stored === "green_up" || stored === "red_up") {
      applyColorScheme(stored);
    }

    var toggle = document.getElementById("settingsColorSchemeToggle");
    if (toggle) {
      toggle.addEventListener("click", function () {
        var next = html.getAttribute("data-color-scheme") === "red_up" ? "green_up" : "red_up";
        applyColorScheme(next);
        try { localStorage.setItem(COLOR_SCHEME_KEY, next); } catch (_) {}
        if (typeof _track === "function") _track("settings_action", { action: "colorscheme" });
      });
    }

    // Expose for use by other modules
    window.getColorScheme = function () {
      return html.getAttribute("data-color-scheme") || "green_up";
    };
    window.applyColorScheme = applyColorScheme;
    window.getDataColors = function () {
      var s = getComputedStyle(html);
      return {
        positive: s.getPropertyValue("--data-positive").trim() || "#30d158",
        negative: s.getPropertyValue("--data-negative").trim() || "#ff453a",
        positiveAlpha22: s.getPropertyValue("--data-positive-alpha-22").trim() || "rgba(48,209,88,0.22)",
        positiveAlpha88: s.getPropertyValue("--data-positive-alpha-88").trim() || "rgba(48,209,88,0.88)",
        negativeAlpha18: s.getPropertyValue("--data-negative-alpha-18").trim() || "rgba(255,69,58,0.18)"
      };
    };
  })();

  // ─── Language switching ───
  (function () {
    var toggle = document.getElementById("settingsLangRow");
    var label = document.getElementById("settingsLangLabel");
    var currentLang = typeof window.__lang === "function" ? __lang() : "zh-CN";

    if (label) label.textContent = currentLang === "en" ? "English" : "中文";

    if (toggle) {
      toggle.addEventListener("click", function () {
        var next = currentLang === "zh-CN" ? "en" : "zh-CN";
        if (typeof _track === "function") _track("settings_action", { action: "language" });
        if (typeof window.__switchLang === "function") {
          window.__switchLang(next);
        }
      });
    }
  })();

  // ─── Update log (row exists on the main page only) ───
  (function () {
    var row = document.getElementById("settingsUpdateLogRow");
    if (!row) return;
    row.addEventListener("click", function () {
      if (typeof window.showFeatureUpdates === "function") window.showFeatureUpdates();
    });
  })();
})();
