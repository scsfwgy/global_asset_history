(function () {
  "use strict";

  var DEFAULT_SYMBOLS = ["SPY", "QQQ", "SCHD", "VGT", "SMH", "AAPL", "GOOGL"];
  var QUICK_SYMBOLS = [
    "SCHD", "SPY", "VOO", "QQQ", "QQQM", "VGT", "XLK", "SMH", "SOXX",
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
  ];
  var QUICK_NAMES = {
    AAPL: "Apple 苹果",
    MSFT: "Microsoft 微软",
    NVDA: "NVIDIA 英伟达",
    AMZN: "Amazon 亚马逊",
    GOOGL: "Alphabet 谷歌",
    META: "Meta Platforms",
    TSLA: "Tesla 特斯拉",
    "BRK.B": "Berkshire Hathaway 伯克希尔",
    JPM: "JPMorgan Chase 摩根大通",
    V: "Visa",
    SCHD: "Schwab US Dividend Equity ETF",
    SPY: "SPDR S&P 500 ETF",
    VOO: "Vanguard S&P 500 ETF",
    QQQ: "Invesco Nasdaq 100 ETF",
    QQQM: "Invesco Nasdaq 100 ETF",
    VGT: "Vanguard Information Technology ETF",
    XLK: "Technology Select Sector SPDR Fund",
    SMH: "VanEck Semiconductor ETF",
    SOXX: "iShares Semiconductor ETF",
  };
  var METRICS = [
    { key: "combined_annualized", tableId: "scCombinedTable" },
    { key: "max_drawdown", tableId: "scDrawdownTable" },
    { key: "dividend_yield_after_tax", tableId: "scDividendTable" },
    { key: "annual_return", tableId: "scReturnTable" },
  ];

  var _symbols = DEFAULT_SYMBOLS.slice();
  var _searchIndex = [];
  var _suggestions = [];
  var _activeSuggestion = -1;
  var _loaded = false;
  var _loading = false;
  var _lastResult = null;
  var _paramsCollapsed = false;

  function $(id) {
    return document.getElementById(id);
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function formatPct(value) {
    if (value == null || !Number.isFinite(Number(value))) return "—";
    var number = Number(value);
    return (number > 0 ? "+" : "") + number.toFixed(2) + "%";
  }

  function cellColor(value) {
    var isRedUp = typeof window.getColorScheme === "function"
      && window.getColorScheme() === "red_up";
    var positiveHue = isRedUp ? 4 : 142;
    var negativeHue = isRedUp ? 142 : 4;
    var number = Number(value);
    if (!Number.isFinite(number)) {
      return { bg: "transparent", text: "var(--apple-text-tertiary)" };
    }
    var intensity = Math.min(Math.abs(number) / 50, 1);
    if (number > 0) {
      return {
        bg: "hsla(" + positiveHue + ", 68%, 72%, " + (0.18 + intensity * 0.55).toFixed(3) + ")",
        text: intensity > 0.7 ? "#fff" : "var(--data-positive)",
      };
    }
    if (number < 0) {
      return {
        bg: "hsla(" + negativeHue + ", 72%, 70%, " + (0.18 + intensity * 0.55).toFixed(3) + ")",
        text: intensity > 0.7 ? "#fff" : "var(--data-negative)",
      };
    }
    return { bg: "transparent", text: "var(--apple-text-secondary)" };
  }

  function getTaxRate() {
    var input = $("scTaxRate");
    if (!input || String(input.value).trim() === "") return 30;
    var value = Number(input.value);
    if (!Number.isFinite(value)) return 30;
    return Math.max(0, Math.min(100, value));
  }

  function setState(name) {
    var loading = $("scLoading");
    var empty = $("scEmpty");
    var result = $("scResult");
    if (loading) loading.style.display = name === "loading" ? "flex" : "none";
    if (empty) empty.style.display = name === "empty" ? "block" : "none";
    if (result) result.style.display = name === "result" ? "block" : "none";
  }

  function showError(message) {
    var error = $("scError");
    if (!error) return;
    error.textContent = message || "";
    error.style.display = message ? "block" : "none";
  }

  function saveState() {
    try {
      localStorage.setItem("gah_stock_compare_symbols_v3", _symbols.join(","));
      localStorage.setItem("gah_dividend_tax_rate", String(getTaxRate()));
    } catch (_) {}
  }

  function renderTags() {
    var tags = $("scTags");
    if (!tags) return;
    if (!_symbols.length) {
      tags.innerHTML = "<span class=\"sc-tags-empty\">" + escapeHtml(__("stockCompare.noSymbols")) + "</span>";
      syncQuickPickState();
      return;
    }
    tags.innerHTML = _symbols.map(function (symbol, index) {
      var match = _searchIndex.find(function (item) { return item.code === symbol; });
      return "<span class=\"pc-tag\"><strong>" + escapeHtml(symbol) + "</strong>"
        + (match && match.name ? "<span class=\"sc-tag-name\">" + escapeHtml(match.name) + "</span>" : "")
        + "<button type=\"button\" class=\"sc-tag-remove\" data-index=\"" + index
        + "\" aria-label=\"" + escapeHtml(__("stockCompare.removeSymbol", { symbol: symbol })) + "\">×</button></span>";
    }).join("");
    tags.querySelectorAll(".sc-tag-remove").forEach(function (button) {
      button.addEventListener("click", function () {
        _symbols.splice(Number(button.dataset.index), 1);
        renderTags();
        saveState();
      });
    });
    syncQuickPickState();
  }

  function addSymbol(rawSymbol) {
    var symbol = String(rawSymbol || "").trim().toUpperCase();
    if (!symbol) return false;
    if (_symbols.indexOf(symbol) !== -1) {
      showError(__("stockCompare.errorDuplicate"));
      return false;
    }
    if (_symbols.length >= 8) {
      showError(__("stockCompare.errorMaxSymbols"));
      return false;
    }
    _symbols.push(symbol);
    var input = $("scSymbolInput");
    if (input) {
      input.value = "";
      input.focus();
    }
    showSuggestions([]);
    showError("");
    renderTags();
    saveState();
    return true;
  }

  function clearSymbols() {
    _symbols = [];
    renderTags();
    saveState();
    showError("");
  }

  function syncQuickPickState() {
    var container = $("scQuickPicks");
    if (!container) return;
    container.querySelectorAll(".sc-quick-chip").forEach(function (button) {
      var selected = _symbols.indexOf(button.dataset.symbol) !== -1;
      button.classList.toggle("selected", selected);
      button.setAttribute("aria-pressed", selected ? "true" : "false");
    });
  }

  function renderQuickPicks() {
    var container = $("scQuickPicks");
    if (!container) return;
    container.innerHTML = "<div class=\"sc-quick-heading\">" + escapeHtml(__("stockCompare.quickAdd")) + "</div>"
      + QUICK_SYMBOLS.map(function (symbol) {
        return "<button type=\"button\" class=\"pc-preset-chip sc-quick-chip\" data-symbol=\""
          + escapeHtml(symbol) + "\" aria-pressed=\"false\">" + escapeHtml(symbol) + "</button>";
      }).join("");
    container.querySelectorAll(".sc-quick-chip").forEach(function (button) {
      button.addEventListener("click", function () {
        if (_symbols.indexOf(button.dataset.symbol) === -1) {
          addSymbol(button.dataset.symbol);
        }
      });
    });
    syncQuickPickState();
  }

  function showSuggestions(items) {
    var dropdown = $("scSuggestions");
    if (!dropdown) return;
    _suggestions = items;
    _activeSuggestion = -1;
    dropdown.innerHTML = items.map(function (item, index) {
      return "<button type=\"button\" class=\"pc-ac-item\" data-index=\"" + index + "\">"
        + "<span class=\"ac-code\">" + escapeHtml(item.code) + "</span>"
        + (item.name ? "<span class=\"ac-name\">" + escapeHtml(item.name) + "</span>" : "")
        + "</button>";
    }).join("");
    dropdown.style.display = items.length ? "block" : "none";
    dropdown.querySelectorAll(".pc-ac-item").forEach(function (button) {
      button.addEventListener("click", function () {
        addSymbol(_suggestions[Number(button.dataset.index)].code);
      });
    });
  }

  function searchSymbols(query) {
    var normalized = String(query || "").trim().toLowerCase();
    if (!normalized) return [];
    return _searchIndex.filter(function (item) {
      return item.code.toLowerCase().indexOf(normalized) !== -1
        || (item.name && item.name.toLowerCase().indexOf(normalized) !== -1);
    }).slice(0, 8);
  }

  function highlightSuggestion() {
    var dropdown = $("scSuggestions");
    if (!dropdown) return;
    dropdown.querySelectorAll(".pc-ac-item").forEach(function (item, index) {
      item.classList.toggle("active", index === _activeSuggestion);
    });
  }

  async function loadSearchIndex() {
    try {
      var config = typeof window.gahLoadConfig === "function"
        ? await window.gahLoadConfig()
        : await fetch(CONFIG_ENDPOINT).then(function (response) { return response.json(); });
      var seen = {};
      (config.presets || []).forEach(function (preset) {
        (preset.symbols || []).forEach(function (item) {
          if (item.type !== "stock") return;
          var code = String(item.symbol || "").toUpperCase();
          if (!code || seen[code]) return;
          seen[code] = true;
          _searchIndex.push({ code: code, name: item.name || QUICK_NAMES[code] || "" });
        });
      });
      renderTags();
    } catch (_) {
      _searchIndex = QUICK_SYMBOLS.map(function (code) {
        return { code: code, name: QUICK_NAMES[code] || "" };
      });
    }
  }

  function metricValue(result, year, symbol, key) {
    return ((((result || {}).data || {})[String(year)] || {})[symbol] || {})[key];
  }

  function renderMetricTable(result, metric) {
    var table = $(metric.tableId);
    if (!table) return;
    var symbols = result.symbols || [];
    var years = result.years || [];
    var head = table.querySelector("thead");
    var body = table.querySelector("tbody");
    head.innerHTML = "<tr><th scope=\"col\">" + escapeHtml(__("stockCompare.year")) + "</th>"
      + symbols.map(function (symbol) {
        return "<th scope=\"col\">" + escapeHtml(symbol) + "</th>";
      }).join("") + "</tr>";
    body.innerHTML = years.map(function (year) {
      var cells = symbols.map(function (symbol) {
        var value = metricValue(result, year, symbol, metric.key);
        var color = cellColor(value);
        return "<td style=\"background:" + color.bg + ";color:" + color.text
          + ";font-weight:600;\">" + escapeHtml(formatPct(value)) + "</td>";
      }).join("");
      return "<tr><th scope=\"row\">" + year + "</th>" + cells + "</tr>";
    }).join("");
  }

  function renderMetricTables(result) {
    METRICS.forEach(function (metric) {
      renderMetricTable(result, metric);
    });
  }

  function renderResult(result) {
    _lastResult = result;
    _symbols = (result.symbols || []).slice();
    renderTags();
    var meta = result.meta || {};
    var errors = _symbols.filter(function (symbol) {
      return (meta[symbol] || {}).error;
    }).map(function (symbol) {
      return symbol + ": " + meta[symbol].error;
    });
    var warning = $("scWarnings");
    if (warning) {
      warning.textContent = errors.length
        ? __("stockCompare.partialError", { errors: errors.join(" · ") })
        : "";
      warning.style.display = errors.length ? "block" : "none";
    }
    renderMetricTables(result);
    setState("result");
  }

  async function queryComparison() {
    if (_loading) return;
    if (_symbols.length < 2) {
      showError(__("stockCompare.errorMinSymbols"));
      return;
    }
    var taxRate = getTaxRate();
    var taxInput = $("scTaxRate");
    if (taxInput) taxInput.value = String(taxRate);
    showError("");
    setState("loading");
    _loading = true;
    saveState();
    try {
      var response = await fetch(STOCK_COMPARE_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbols: _symbols, tax_rate: taxRate }),
      });
      var payload = await response.json().catch(function () { return {}; });
      if (!response.ok) throw new Error(payload.error || ("HTTP " + response.status));
      _loaded = true;
      renderResult(payload);
    } catch (error) {
      showError(__("stockCompare.errorRequest") + " " + error.message);
      setState(_lastResult ? "result" : "empty");
    } finally {
      _loading = false;
    }
  }

  function activate() {
    if (!_loaded && !_loading) setState("empty");
  }

  function setParamsCollapsed(collapsed) {
    var panel = $("scParamsPanel");
    var toggle = $("scParamsToggle");
    _paramsCollapsed = Boolean(collapsed);
    if (panel) panel.style.display = _paramsCollapsed ? "none" : "block";
    if (toggle) {
      toggle.textContent = __(_paramsCollapsed ? "detail.expandParams" : "detail.collapseParams");
      toggle.setAttribute("aria-expanded", String(!_paramsCollapsed));
    }
  }

  function init() {
    var input = $("scSymbolInput");
    var taxInput = $("scTaxRate");
    try {
      var savedSymbols = localStorage.getItem("gah_stock_compare_symbols_v3");
      var savedTax = localStorage.getItem("gah_dividend_tax_rate");
      if (savedSymbols) {
        _symbols = savedSymbols.split(",").map(function (symbol) {
          return symbol.trim().toUpperCase();
        }).filter(Boolean).slice(0, 8);
      }
      if (savedTax && taxInput) taxInput.value = savedTax;
    } catch (_) {}
    renderTags();
    renderQuickPicks();
    loadSearchIndex();

    $("scAddBtn").addEventListener("click", function () {
      addSymbol(input.value);
    });
    $("scClearBtn").addEventListener("click", clearSymbols);
    $("scQueryBtn").addEventListener("click", queryComparison);
    $("scParamsToggle").addEventListener("click", function () {
      setParamsCollapsed(!_paramsCollapsed);
    });
    input.addEventListener("input", function () {
      showSuggestions(searchSymbols(input.value));
    });
    input.addEventListener("focus", function () {
      showSuggestions(searchSymbols(input.value));
    });
    input.addEventListener("keydown", function (event) {
      if (event.key === "ArrowDown" && _suggestions.length) {
        event.preventDefault();
        _activeSuggestion = Math.min(_activeSuggestion + 1, _suggestions.length - 1);
        highlightSuggestion();
      } else if (event.key === "ArrowUp" && _suggestions.length) {
        event.preventDefault();
        _activeSuggestion = Math.max(_activeSuggestion - 1, 0);
        highlightSuggestion();
      } else if (event.key === "Enter") {
        event.preventDefault();
        addSymbol(_activeSuggestion >= 0 ? _suggestions[_activeSuggestion].code : input.value);
      } else if (event.key === "Escape") {
        showSuggestions([]);
      }
    });
    document.addEventListener("click", function (event) {
      var search = $("scSymbolSearch");
      if (search && !search.contains(event.target)) showSuggestions([]);
    });
    taxInput.addEventListener("change", function () {
      taxInput.value = String(getTaxRate());
      if (_loaded) queryComparison();
    });
    var observer = new MutationObserver(function (mutations) {
      if (_lastResult && mutations.some(function (mutation) {
        return mutation.attributeName === "data-color-scheme"
          || mutation.attributeName === "data-theme";
      })) {
        renderMetricTables(_lastResult);
      }
    });
    observer.observe(document.documentElement, { attributes: true });
  }

  window._stockCompareActivate = activate;
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
