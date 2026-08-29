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
  var CHART_COLORS = [
    "#2997ff", "#ff9f0a", "#30d158", "#bf5af2",
    "#ff375f", "#64d2ff", "#ffd60a", "#ac8e68",
  ];

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

  function includeDividendReinvestment() {
    var input = $("scDividendReinvestment");
    return !input || input.checked;
  }

  function backtestEnabled() {
    var input = $("scBacktestEnabled");
    return Boolean(input && input.checked);
  }

  function updateOptionState() {
    var enabled = backtestEnabled();
    var dateField = $("scStartDateField");
    var dateInput = $("scStartDate");
    if (dateField) dateField.style.display = enabled ? "flex" : "none";
    if (dateInput) dateInput.required = enabled;

    var reinvested = includeDividendReinvestment();
    var methodology = $("scMethodologyCombined");
    var description = $("scCombinedDescription");
    var methodologyKey = reinvested
      ? "stockCompare.methodologyCombinedReinvested"
      : "stockCompare.methodologyCombined";
    var descriptionKey = reinvested
      ? "stockCompare.combinedDescriptionReinvested"
      : "stockCompare.combinedDescription";
    if (methodology) {
      methodology.setAttribute("data-i18n", methodologyKey);
      methodology.textContent = __(methodologyKey);
    }
    if (description) {
      description.setAttribute("data-i18n", descriptionKey);
      description.textContent = __(descriptionKey);
    }
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
      localStorage.setItem("gah_stock_compare_dividend_reinvestment", includeDividendReinvestment() ? "1" : "0");
      localStorage.setItem("gah_stock_compare_backtest", backtestEnabled() ? "1" : "0");
      localStorage.setItem("gah_stock_compare_start_date", ($("scStartDate") || {}).value || "");
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

  function renderAggregateTable(result) {
    var table = $("scAggregateTable");
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
        var combined = metricValue(result, year, symbol, "combined_annualized");
        var drawdown = metricValue(result, year, symbol, "max_drawdown");
        var combinedColor = cellColor(combined);
        var drawdownColor = cellColor(drawdown);
        var title = __("stockCompare.combinedAnnualized") + ": " + formatPct(combined)
          + " · " + __("stockCompare.maxDrawdown") + ": " + formatPct(drawdown);
        return "<td class=\"sc-aggregate-cell\" title=\"" + escapeHtml(title) + "\">"
          + "<span class=\"sc-aggregate-bg sc-aggregate-bg-return\" style=\"background:"
          + combinedColor.bg + ";\"></span>"
          + "<span class=\"sc-aggregate-bg sc-aggregate-bg-drawdown\" style=\"background:"
          + drawdownColor.bg + ";\"></span>"
          + "<span class=\"sc-aggregate-metric sc-aggregate-return\" style=\"color:"
          + combinedColor.text + ";\"><span class=\"sc-aggregate-label\">"
          + escapeHtml(__("stockCompare.aggregateCombined")) + "</span><span class=\"sc-aggregate-value\">"
          + escapeHtml(formatPct(combined)) + "</span></span>"
          + "<span class=\"sc-aggregate-metric sc-aggregate-drawdown\" style=\"color:"
          + drawdownColor.text + ";\"><span class=\"sc-aggregate-label\">"
          + escapeHtml(__("stockCompare.aggregateDrawdown")) + "</span><span class=\"sc-aggregate-value\">"
          + escapeHtml(formatPct(drawdown)) + "</span></span></td>";
      }).join("");
      return "<tr><th scope=\"row\">" + year + "</th>" + cells + "</tr>";
    }).join("");
  }

  function renderMetricTables(result) {
    renderAggregateTable(result);
    METRICS.forEach(function (metric) {
      renderMetricTable(result, metric);
    });
  }

  function formatChartNumber(value) {
    var number = Number(value);
    if (!Number.isFinite(number)) return "—";
    return (number > 0 ? "+" : "") + number.toFixed(Math.abs(number) >= 100 ? 0 : 1) + "%";
  }

  function nearestBacktestRow(rows, targetMs) {
    if (!rows.length) return null;
    var low = 0;
    var high = rows.length - 1;
    while (low < high) {
      var mid = Math.floor((low + high) / 2);
      if (rows[mid].dateMs < targetMs) low = mid + 1;
      else high = mid;
    }
    if (low > 0 && Math.abs(rows[low - 1].dateMs - targetMs) <= Math.abs(rows[low].dateMs - targetMs)) {
      return rows[low - 1];
    }
    return rows[low];
  }

  function renderBacktestChart(result) {
    var card = $("scBacktestCard");
    var chart = $("scBacktestChart");
    var legend = $("scBacktestLegend");
    var description = $("scBacktestDescription");
    var backtest = result.backtest;
    if (!card || !chart || !legend) return;
    if (!result.backtest_enabled || !backtest) {
      card.style.display = "none";
      chart.innerHTML = "";
      legend.innerHTML = "";
      return;
    }
    card.style.display = "block";
    if (description) {
      description.textContent = __(
        result.include_dividend_reinvestment
          ? "stockCompare.backtestDescriptionReinvested"
          : "stockCompare.backtestDescriptionCash",
        { date: backtest.start_date }
      );
    }

    var series = (result.symbols || []).map(function (symbol, index) {
      var rows = ((backtest.curves || {})[symbol] || []).filter(function (row) {
        return row && row.date && Number.isFinite(Number(row.total_return_pct));
      }).map(function (row) {
        return {
          date: row.date,
          dateMs: Date.parse(row.date + "T00:00:00Z"),
          total_return_pct: Number(row.total_return_pct),
        };
      });
      return { symbol: symbol, rows: rows, color: CHART_COLORS[index % CHART_COLORS.length] };
    }).filter(function (item) { return item.rows.length; });
    if (!series.length) {
      chart.innerHTML = "<div class=\"pc-empty\">" + escapeHtml(__("stockCompare.backtestNoData")) + "</div>";
      legend.innerHTML = "";
      return;
    }

    var allRows = [];
    series.forEach(function (item) { allRows = allRows.concat(item.rows); });
    var dateValues = allRows.map(function (row) { return row.dateMs; });
    var returnValues = allRows.map(function (row) { return Number(row.total_return_pct); }).concat([0]);
    var minDate = Math.min.apply(null, dateValues);
    var maxDate = Math.max.apply(null, dateValues);
    var minReturn = Math.min.apply(null, returnValues);
    var maxReturn = Math.max.apply(null, returnValues);
    var returnRange = maxReturn - minReturn || Math.max(Math.abs(maxReturn), 1);
    minReturn -= returnRange * 0.08;
    maxReturn += returnRange * 0.08;
    returnRange = maxReturn - minReturn || 1;

    var W = 760, H = 300;
    var PAD = { left: 60, right: 18, top: 18, bottom: 36 };
    var plotW = W - PAD.left - PAD.right;
    var plotH = H - PAD.top - PAD.bottom;
    var dateRange = maxDate - minDate || 1;
    var xPos = function (dateText) {
      return PAD.left + (Date.parse(dateText + "T00:00:00Z") - minDate) / dateRange * plotW;
    };
    var yPos = function (value) {
      return PAD.top + plotH - (Number(value) - minReturn) / returnRange * plotH;
    };
    var svg = "";
    for (var tick = 0; tick <= 4; tick += 1) {
      var tickValue = minReturn + returnRange * tick / 4;
      var tickY = yPos(tickValue);
      svg += "<line x1=\"" + PAD.left + "\" y1=\"" + tickY + "\" x2=\"" + (W - PAD.right)
        + "\" y2=\"" + tickY + "\" stroke=\"var(--apple-divider)\" stroke-width=\"1\"/>"
        + "<text x=\"" + (PAD.left - 8) + "\" y=\"" + (tickY + 4)
        + "\" text-anchor=\"end\" fill=\"var(--apple-text-tertiary)\" font-size=\"10\">"
        + escapeHtml(formatChartNumber(tickValue)) + "</text>";
    }
    for (var dateTick = 0; dateTick <= 4; dateTick += 1) {
      var tickDateValue = minDate + dateRange * dateTick / 4;
      var tickDate = new Date(tickDateValue);
      var tickX = PAD.left + plotW * dateTick / 4;
      var tickLabel = tickDate.getUTCFullYear() + "-" + String(tickDate.getUTCMonth() + 1).padStart(2, "0");
      svg += "<text x=\"" + tickX + "\" y=\"" + (H - 12)
        + "\" text-anchor=\"middle\" fill=\"var(--apple-text-tertiary)\" font-size=\"10\">"
        + tickLabel + "</text>";
    }
    var zeroY = yPos(0);
    if (zeroY >= PAD.top && zeroY <= H - PAD.bottom) {
      svg += "<line x1=\"" + PAD.left + "\" y1=\"" + zeroY + "\" x2=\"" + (W - PAD.right)
        + "\" y2=\"" + zeroY + "\" stroke=\"var(--apple-text-tertiary)\" stroke-dasharray=\"4,3\" opacity=\"0.65\"/>";
    }
    series.forEach(function (item) {
      var path = item.rows.map(function (row, index) {
        return (index ? "L" : "M") + xPos(row.date).toFixed(2) + " " + yPos(row.total_return_pct).toFixed(2);
      }).join(" ");
      svg += "<path d=\"" + path + "\" fill=\"none\" stroke=\"" + item.color
        + "\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><title>"
        + escapeHtml(item.symbol + ": " + formatChartNumber(item.rows[item.rows.length - 1].total_return_pct))
        + "</title></path>";
    });
    var tooltipHeight = 28 + series.length * 18;
    svg += "<rect id=\"scBacktestHoverPlot\" x=\"" + PAD.left + "\" y=\"" + PAD.top
      + "\" width=\"" + plotW + "\" height=\"" + plotH + "\" fill=\"transparent\" style=\"cursor:crosshair;\"/>"
      + "<g id=\"scBacktestTooltip\" style=\"display:none;pointer-events:none;\">"
      + "<line id=\"scBacktestTooltipGuide\" x1=\"0\" y1=\"" + PAD.top + "\" x2=\"0\" y2=\""
      + (PAD.top + plotH) + "\" stroke=\"var(--apple-text-tertiary)\" stroke-width=\"1\" stroke-dasharray=\"4,3\"/>"
      + "<g id=\"scBacktestTooltipDots\"></g>"
      + "<g id=\"scBacktestTooltipBox\"><rect width=\"190\" height=\"" + tooltipHeight
      + "\" rx=\"8\" fill=\"var(--apple-tooltip-bg, rgba(24,24,26,0.96))\" stroke=\"var(--apple-divider)\"/>"
      + "<g id=\"scBacktestTooltipRows\"></g></g></g>";
    chart.innerHTML = "<svg viewBox=\"0 0 " + W + " " + H
      + "\" role=\"img\" aria-label=\"" + escapeHtml(__("stockCompare.backtestChartTitle"))
      + "\" style=\"width:100%;height:auto;display:block;font-family:-apple-system,SF Pro Text,Helvetica,Arial,sans-serif;\">"
      + svg + "</svg>";
    var chartSvg = chart.querySelector("svg");
    var hoverPlot = chartSvg && chartSvg.querySelector("#scBacktestHoverPlot");
    var tooltip = chartSvg && chartSvg.querySelector("#scBacktestTooltip");
    var tooltipGuide = chartSvg && chartSvg.querySelector("#scBacktestTooltipGuide");
    var tooltipBox = chartSvg && chartSvg.querySelector("#scBacktestTooltipBox");
    var tooltipRows = chartSvg && chartSvg.querySelector("#scBacktestTooltipRows");
    var tooltipDots = chartSvg && chartSvg.querySelector("#scBacktestTooltipDots");
    if (hoverPlot && tooltip) {
      hoverPlot.addEventListener("pointermove", function (event) {
        var rect = chartSvg.getBoundingClientRect();
        if (!rect.width) return;
        var pointerX = Math.max(PAD.left, Math.min(W - PAD.right,
          (event.clientX - rect.left) / rect.width * W));
        var targetMs = minDate + (pointerX - PAD.left) / plotW * dateRange;
        var anchor = nearestBacktestRow(series[0].rows, targetMs);
        if (!anchor) return;
        var guideX = PAD.left + (anchor.dateMs - minDate) / dateRange * plotW;
        var rowMarkup = "<text x=\"10\" y=\"18\" fill=\"var(--apple-tooltip-text, #fff)\" font-size=\"11\" font-weight=\"600\">"
          + escapeHtml(anchor.date) + "</text>";
        var dotMarkup = "";
        series.forEach(function (item, index) {
          var row = nearestBacktestRow(item.rows, anchor.dateMs);
          if (!row) return;
          var rowY = 37 + index * 18;
          rowMarkup += "<rect x=\"10\" y=\"" + (rowY - 8) + "\" width=\"8\" height=\"3\" rx=\"1\" fill=\""
            + item.color + "\"/><text x=\"24\" y=\"" + (rowY - 5)
            + "\" fill=\"var(--apple-tooltip-text, #fff)\" font-size=\"10\">" + escapeHtml(item.symbol)
            + "</text><text x=\"180\" y=\"" + (rowY - 5)
            + "\" text-anchor=\"end\" fill=\"var(--apple-tooltip-text, #fff)\" font-size=\"10\">"
            + escapeHtml(formatChartNumber(row.total_return_pct)) + "</text>";
          dotMarkup += "<circle cx=\"" + guideX + "\" cy=\"" + yPos(row.total_return_pct)
            + "\" r=\"3.5\" fill=\"" + item.color + "\" stroke=\"var(--apple-bg)\" stroke-width=\"1.5\"/>";
        });
        var boxX = guideX + 12;
        if (boxX + 190 > W - PAD.right) boxX = guideX - 202;
        tooltipGuide.setAttribute("x1", String(guideX));
        tooltipGuide.setAttribute("x2", String(guideX));
        tooltipBox.setAttribute("transform", "translate(" + boxX + ", " + (PAD.top + 8) + ")");
        tooltipRows.innerHTML = rowMarkup;
        tooltipDots.innerHTML = dotMarkup;
        tooltip.style.display = "";
      });
      hoverPlot.addEventListener("pointerleave", function () { tooltip.style.display = "none"; });
    }
    legend.innerHTML = series.map(function (item) {
      var latest = item.rows[item.rows.length - 1];
      return "<span class=\"sc-backtest-legend-item\"><span class=\"sc-backtest-swatch\" style=\"background:"
        + item.color + "\"></span><strong>" + escapeHtml(item.symbol) + "</strong> "
        + escapeHtml(formatChartNumber(latest.total_return_pct)) + "</span>";
    }).join("");
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
    renderBacktestChart(result);
    setState("result");
  }

  async function queryComparison() {
    if (_loading) return;
    if (_symbols.length < 2) {
      showError(__("stockCompare.errorMinSymbols"));
      return;
    }
    var taxRate = getTaxRate();
    var reinvested = includeDividendReinvestment();
    var runBacktest = backtestEnabled();
    var startDate = ($("scStartDate") || {}).value || "";
    if (runBacktest && !startDate) {
      showError(__("stockCompare.errorStartDate"));
      if ($("scStartDate")) $("scStartDate").focus();
      return;
    }
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
        body: JSON.stringify({
          symbols: _symbols,
          tax_rate: taxRate,
          include_dividend_reinvestment: reinvested,
          backtest_enabled: runBacktest,
          start_date: runBacktest ? startDate : null,
        }),
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
    var reinvestmentInput = $("scDividendReinvestment");
    var backtestInput = $("scBacktestEnabled");
    var startDateInput = $("scStartDate");
    if (startDateInput) startDateInput.max = new Date().toISOString().slice(0, 10);
    try {
      var savedSymbols = localStorage.getItem("gah_stock_compare_symbols_v3");
      var savedTax = localStorage.getItem("gah_dividend_tax_rate");
      var savedReinvestment = localStorage.getItem("gah_stock_compare_dividend_reinvestment");
      var savedBacktest = localStorage.getItem("gah_stock_compare_backtest");
      var savedStartDate = localStorage.getItem("gah_stock_compare_start_date");
      if (savedSymbols) {
        _symbols = savedSymbols.split(",").map(function (symbol) {
          return symbol.trim().toUpperCase();
        }).filter(Boolean).slice(0, 8);
      }
      if (savedTax && taxInput) taxInput.value = savedTax;
      if (savedReinvestment !== null && reinvestmentInput) reinvestmentInput.checked = savedReinvestment !== "0";
      if (savedBacktest !== null && backtestInput) backtestInput.checked = savedBacktest === "1";
      if (startDateInput) startDateInput.value = savedStartDate || "2021-01-01";
    } catch (_) {}
    updateOptionState();
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
    reinvestmentInput.addEventListener("change", function () {
      updateOptionState();
      saveState();
    });
    backtestInput.addEventListener("change", function () {
      updateOptionState();
      saveState();
    });
    startDateInput.addEventListener("change", saveState);
    var observer = new MutationObserver(function (mutations) {
      if (_lastResult && mutations.some(function (mutation) {
        return mutation.attributeName === "data-color-scheme"
          || mutation.attributeName === "data-theme";
      })) {
        renderMetricTables(_lastResult);
        renderBacktestChart(_lastResult);
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
