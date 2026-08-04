/**
 * Recent-queries history for the research tools (detail / backtest / crash /
 * download). Each tool keeps its own localStorage list of {symbol, name, type}
 * capped at HISTORY_MAX entries, most-recent-first, deduped by symbol+type.
 *
 * Human-readable names are resolved asynchronously through the symbol-search
 * endpoint when a record is saved without one (the downstream APIs only echo
 * the symbol). Clicking a rendered record is intentionally side-effect free
 * except for refilling the caller's inputs — the caller wires that via the
 * onPick callback.
 */

(function () {
  "use strict";

  var HISTORY_MAX = 10;
  var _binds = []; // { key, container, onPick }

  function _escape(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function _load(key) {
    try {
      var raw = JSON.parse(localStorage.getItem(key) || "[]");
      return Array.isArray(raw) ? raw : [];
    } catch (_) {
      return [];
    }
  }

  function _save(key, list) {
    try {
      localStorage.setItem(key, JSON.stringify(list.slice(0, HISTORY_MAX)));
    } catch (_) { /* localStorage unavailable — keep the current session */ }
  }

  function _same(rec, symbol, type) {
    return String(rec.symbol || "").toUpperCase() === symbol
      && String(rec.type || "stock") === type;
  }

  function _render(key) {
    var list = _load(key);
    _binds.forEach(function (bind) {
      if (bind.key !== key || !bind.container) return;
      if (!list.length) {
        bind.container.innerHTML = "";
        return;
      }
      var items = list.map(function (rec, i) {
        var name = String(rec.name || "").trim();
        var nameHtml = name
          ? '<span class="gah-history-name">' + _escape(name) + '</span>'
          : "";
        return '<button type="button" class="gah-history-item" data-idx="' + i + '">'
          + '<span class="gah-history-symbol">' + _escape(rec.symbol) + '</span>'
          + nameHtml
          + '</button>';
      }).join("");
      bind.container.innerHTML =
        '<div class="gah-history-head">'
        + '<span class="gah-history-title">' + __("historyRecords.title") + '</span>'
        + '<button type="button" class="gah-history-clear">' + __("historyRecords.clear") + '</button>'
        + '</div>'
        + '<div class="gah-history-list">' + items + '</div>';
    });
  }

  function _resolveName(symbol, type, cb) {
    if (typeof SYMBOL_SEARCH_ENDPOINT === "undefined") { cb(""); return; }
    var url = SYMBOL_SEARCH_ENDPOINT + "?q=" + encodeURIComponent(symbol)
      + "&type=" + encodeURIComponent(type || "stock");
    fetch(url)
      .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status)); })
      .then(function (payload) {
        var results = (payload && payload.results) || [];
        var target = String(symbol || "").toUpperCase();
        var hit = results.find(function (x) {
          return String(x.symbol || "").toUpperCase() === target;
        }) || results[0];
        cb(hit ? String(hit.name || "") : "");
      })
      .catch(function () { cb(""); });
  }

  /** Add (or move to front of) a history record for key. */
  function _upsert(key, record) {
    var symbol = String(record.symbol || "").trim().toUpperCase();
    var type = String(record.type || "stock");
    if (!symbol) return;
    var list = _load(key);
    var existing = list.find(function (r) { return _same(r, symbol, type); });
    var name = String(record.name || "").trim();
    if (!name && existing) name = String(existing.name || "").trim();
    var next = { symbol: symbol, name: name, type: type };
    _save(key, [next].concat(list.filter(function (r) { return !_same(r, symbol, type); })));
    _render(key);
    if (!name) {
      _resolveName(symbol, type, function (resolved) {
        if (!resolved) return;
        var list2 = _load(key);
        var hit = list2.find(function (r) { return _same(r, symbol, type); });
        if (hit && !String(hit.name || "").trim()) {
          hit.name = resolved;
          _save(key, list2);
          _render(key);
        }
      });
    }
  }

  window.gahHistoryRecord = _upsert;

  /** Render the history list for key into container; onPick(record) on click. */
  window.gahHistoryBind = function (key, container, onPick) {
    if (!container) return;
    _binds.push({ key: key, container: container, onPick: onPick });
    _render(key);
    container.addEventListener("click", function (event) {
      if (event.target.closest(".gah-history-clear")) {
        _save(key, []);
        _render(key);
        return;
      }
      var item = event.target.closest(".gah-history-item");
      if (!item || !onPick) return;
      var rec = _load(key)[parseInt(item.getAttribute("data-idx"), 10)];
      if (rec) onPick(rec);
    });
  };
})();
