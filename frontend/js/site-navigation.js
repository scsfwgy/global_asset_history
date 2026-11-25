/** Shared desktop sidebar and mobile drawer. Loaded in the head to restore width before paint. */
(function () {
  'use strict';
  var key = 'gah-sidebar-mode';
  var modes = ['expanded', 'compact', 'immersive'];
  var mode = 'expanded';
  try { mode = localStorage.getItem(key) || mode; } catch (_) { /* Session-only when storage is blocked. */ }
  if (modes.indexOf(mode) === -1) mode = 'expanded';
  document.documentElement.dataset.sidebarMode = mode;

  document.addEventListener('DOMContentLoaded', function () {
    var sidebar = document.getElementById('siteSidebar');
    var content = document.getElementById('mainContent');
    if (!sidebar || !content) return;
    var toggle = document.getElementById('sidebarToggle');
    var restore = document.getElementById('sidebarRestore');
    var mobileToggle = document.getElementById('mobileMenuToggle');
    var scrim = document.getElementById('sidebarScrim');
    var mobile = window.matchMedia('(max-width: 768px)');
    var open = false;
    var previousFocus = null;

    function label(button, name) {
      button.setAttribute('aria-label', __('nav.' + name));
      button.title = __('nav.' + name);
      button.removeAttribute('data-i18n-attr');
    }
    function closeSettings() {
      if (typeof window.gahCloseSettings === 'function') window.gahCloseSettings();
    }
    function sync() {
      var hidden = mobile.matches ? !open : mode === 'immersive';
      sidebar.inert = hidden;
      sidebar.setAttribute('aria-hidden', String(hidden));
      toggle.setAttribute('aria-expanded', String(mobile.matches ? open : mode === 'expanded'));
      mobileToggle.setAttribute('aria-expanded', String(open));
      content.inert = mobile.matches && open;
      document.body.classList.toggle('mobile-menu-open', mobile.matches && open);
      label(toggle, mobile.matches ? 'closeMenu' : (mode === 'expanded' ? 'collapse' : 'hide'));
      label(restore, 'expand');
    }
    function setMobileOpen(value, returnFocus) {
      if (value) previousFocus = document.activeElement;
      else closeSettings();
      open = value && mobile.matches;
      sidebar.classList.toggle('mobile-open', open);
      sync();
      if (open) toggle.focus();
      else if (returnFocus !== false && previousFocus && previousFocus.isConnected) previousFocus.focus();
    }
    function setMode(value, keepSettings) {
      if (!keepSettings) closeSettings();
      mode = value;
      document.documentElement.dataset.sidebarMode = mode;
      try { localStorage.setItem(key, mode); } catch (_) { /* Keep the selection for this page. */ }
      sync();
      if (mode === 'immersive') restore.focus();
      else toggle.focus();
    }
    toggle.addEventListener('click', function () {
      if (mobile.matches) setMobileOpen(false);
      else setMode(modes[(modes.indexOf(mode) + 1) % modes.length]);
    });
    restore.addEventListener('click', function () { setMode('expanded'); });
    mobileToggle.addEventListener('click', function () { setMobileOpen(!open); });
    scrim.addEventListener('click', function () { setMobileOpen(false); });
    sidebar.querySelectorAll('.tab-btn, .header-quick-link, .site-brand-name').forEach(function (link) {
      link.addEventListener('click', function () { if (mobile.matches) setMobileOpen(false); });
    });
    mobile.addEventListener('change', function () {
      setMobileOpen(false, false);
      // Do not leave keyboard focus inside a drawer hidden by a breakpoint change.
      if (sidebar.contains(document.activeElement) && sidebar.inert) {
        (mobile.matches ? mobileToggle : restore).focus();
      }
    });
    document.addEventListener('keydown', function (event) {
      if (event.defaultPrevented || !mobile.matches || !open || document.querySelector('dialog[open]')) return;
      if (event.key === 'Escape') {
        var menu = document.getElementById('headerSettingsMenu');
        if (menu && menu.style.display === 'block') return;
        event.preventDefault();
        setMobileOpen(false);
      }
      if (event.key === 'Tab') {
        var items = Array.from(sidebar.querySelectorAll('a[href], button, [tabindex="0"]'))
          .filter(function (item) { return !item.disabled && item.getClientRects().length; });
        var first = items[0], last = items[items.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    });
    window.gahCloseNavigation = function () { setMobileOpen(false, false); };
    window.gahOpenNavigation = function () {
      if (mobile.matches) setMobileOpen(true);
      else if (mode === 'immersive') setMode('expanded', true);
    };
    sync();
    if (/\/settings\/?$/.test(location.pathname)) {
      window.gahOpenNavigation();
      document.getElementById('headerSettingsBtn').setAttribute('aria-expanded', 'true');
    }

    // Width changes from navigation do not emit a window resize event.
    if (typeof ResizeObserver !== 'undefined') {
      var width = -1;
      var frame;
      new ResizeObserver(function (entries) {
        var next = entries[0].contentRect.width;
        if (next === width) return;
        width = next;
        cancelAnimationFrame(frame);
        frame = requestAnimationFrame(function () { window.dispatchEvent(new Event('gah:layout')); });
      }).observe(content);
    }
  });
})();
