(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const MONTHS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
  const DAYS = Array.from({ length: 31 }, (_, i) => i + 1);
  var _barChartCollapsed = false;
  var _overviewCollapsed = false;
  var _paramsCollapsed = false;
  var _barChartHeight = 220;
  var _lastBarChartResult = null;
  var _lastStockHistoryResult = null;
  var _stockHistoryCache = null;
  var _pendingYear = "";
  var _resizeRenderFrame = null;

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function formatPct(value, digits) {
    if (value == null || !Number.isFinite(Number(value))) return "—";
    const num = Number(value);
    const sign = num > 0 ? "+" : "";
    return sign + num.toFixed(digits == null ? 2 : digits) + "%";
  }

  function formatUnsignedPct(value, digits) {
    if (value == null || !Number.isFinite(Number(value))) return "—";
    return Number(value).toFixed(digits == null ? 2 : digits) + "%";
  }

  function formatPrice(value) {
    if (value == null || !Number.isFinite(Number(value))) return "—";
    var num = Number(value);
    var absolute = Math.abs(num);
    var digits = absolute < 1 ? 6 : (absolute < 100 ? 4 : 2);
    return new Intl.NumberFormat(document.documentElement.lang || undefined, {
      minimumFractionDigits: 0,
      maximumFractionDigits: digits,
    }).format(num);
  }

  function formatNumber(value, digits) {
    if (value == null || !Number.isFinite(Number(value))) return "—";
    return new Intl.NumberFormat(document.documentElement.lang || undefined, {
      minimumFractionDigits: 0,
      maximumFractionDigits: digits == null ? 2 : digits,
    }).format(Number(value));
  }

  function formatCompactNumber(value, currency) {
    if (value == null || !Number.isFinite(Number(value))) return "—";
    var options = {
      notation: "compact",
      compactDisplay: "short",
      maximumFractionDigits: 2,
    };
    if (currency) {
      options.style = "currency";
      options.currency = currency;
      options.currencyDisplay = "narrowSymbol";
    }
    try {
      return new Intl.NumberFormat(
        document.documentElement.lang || undefined,
        options
      ).format(Number(value));
    } catch (_) {
      return formatNumber(value, 0) + (currency ? " " + currency : "");
    }
  }

  function formatRatio(value) {
    if (value == null || !Number.isFinite(Number(value))) return "—";
    return formatNumber(value, 2) + "×";
  }

  function formatDividend(value) {
    if (value == null || !Number.isFinite(Number(value))) return "—";
    return "$" + new Intl.NumberFormat(document.documentElement.lang || undefined, {
      minimumFractionDigits: 0,
      maximumFractionDigits: 6,
    }).format(Number(value));
  }

  function formatDateTime(value) {
    if (!value) return "—";
    var parsed = new Date(value);
    if (!Number.isFinite(parsed.getTime())) return String(value);
    return new Intl.DateTimeFormat(document.documentElement.lang || undefined, {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }).format(parsed);
  }

  function valueTone(value, inverse) {
    if (value == null || !Number.isFinite(Number(value)) || Number(value) === 0) return "";
    var positive = Number(value) > 0;
    if (inverse) positive = !positive;
    return positive ? " is-positive" : " is-negative";
  }

  function cellColor(value, min, max) {
    const isRedUp = (typeof window.getColorScheme === "function" && window.getColorScheme() === "red_up");
    const posHue = isRedUp ? 4 : 142;
    const negHue = isRedUp ? 142 : 4;
    const num = Number(value);
    if (!Number.isFinite(num)) {
      return { bg: "transparent", text: "var(--apple-text-tertiary)" };
    }
    if (num > 0) {
      const intensity = Math.min(num / Math.max(max, 1), 1);
      const lightness = 88 - intensity * 53;
      const saturation = 55 + intensity * 30;
      const alpha = Math.min(0.18 + intensity * 0.72, 0.95);
      return {
        bg: `hsla(${posHue}, ${Math.round(saturation)}%, ${Math.round(lightness)}%, ${alpha.toFixed(3)})`,
        text: lightness < 50 ? "#fff" : "var(--data-positive)",
      };
    }
    if (num < 0) {
      const intensity = Math.min(Math.abs(num) / Math.max(Math.abs(min), 1), 1);
      const lightness = 88 - intensity * 53;
      const saturation = 55 + intensity * 30;
      const alpha = Math.min(0.18 + intensity * 0.72, 0.95);
      return {
        bg: `hsla(${negHue}, ${Math.round(saturation)}%, ${Math.round(lightness)}%, ${alpha.toFixed(3)})`,
        text: lightness < 50 ? "#fff" : "var(--data-negative)",
      };
    }
    return { bg: "transparent", text: "var(--apple-text-secondary)" };
  }

  function showError(message) {
    const el = $("pdError");
    if (!el) return;
    el.style.display = message ? "block" : "none";
    el.textContent = message || "";
  }

  function setLoading(on) {
    const el = $("pdLoading");
    if (el) el.style.display = on ? "flex" : "none";
  }

  function setResultVisible(hasResult) {
    const empty = $("pdEmpty");
    const result = $("pdResult");
    if (empty) empty.style.display = hasResult ? "none" : "block";
    if (result) result.style.display = hasResult ? "block" : "none";
  }

  function getColorRange() {
    const min = Number($("pdMinRange")?.value || -50);
    const max = Number($("pdMaxRange")?.value || 50);
    return { min, max };
  }

  function buildYearSelector(years) {
    const sel = $("pdYearSelect");
    if (!sel) return;
    var selected = sel.value;
    sel.innerHTML = '<option value="">' + __("detail.allYears") + '</option>';
    years.forEach(function (y) {
      var opt = document.createElement("option");
      opt.value = y;
      opt.textContent = y;
      sel.appendChild(opt);
    });
    // restore previous selection if still valid
    if (selected && years.indexOf(Number(selected)) !== -1) {
      sel.value = selected;
    }
  }

  function renderYearlyTable(result) {
    var head = $("pdTableHead");
    var body = $("pdTableBody");
    if (!head || !body) return;
    var tableTitle = $("pdTableTitle");
    if (tableTitle) tableTitle.textContent = __("detail.returnCalendarTitle");

    var range = getColorRange();
    var monthHead = MONTHS.map(function (m) { return "<th>" + __("yearly.monthLabel", { m: m }) + "</th>"; }).join("");
    var statColHead = '<th class="pd-stat-col">' + __("detail.avg") + '</th>'
      + '<th class="pd-stat-col">' + __("detail.median") + '</th>'
      + '<th class="pd-stat-col">' + __("detail.winRate") + '</th>';
    head.innerHTML = '<tr><th>' + __("yearly.colYear") + '</th>' + monthHead + '<th>' + __("yearly.annualTotal") + '</th>' + statColHead + '</tr>';

    var rowsHtml = (result.rows || []).map(function (row) {
      var monthMap = {};
      (row.months || []).forEach(function (m) { monthMap[m.month] = m.return; });
      var monthCells = MONTHS.map(function (month) {
        var value = monthMap[month];
        var color = cellColor(value, range.min, range.max);
        return '<td style="background:' + color.bg + ';color:' + color.text + ';" title="' + row.year + '-' + String(month).padStart(2, "0") + ' ' + formatPct(value) + '">' + formatPct(value) + '</td>';
      }).join("");
      var annualColor = cellColor(row.annual_return, range.min, range.max);
      var rs = row.row_stats || {};
      return '<tr><td>' + row.year + '</td>' + monthCells
        + '<td style="background:' + annualColor.bg + ';color:' + annualColor.text + ';font-weight:700;">' + formatPct(row.annual_return) + '</td>'
        + '<td class="pd-stat-col" style="background:' + cellColor(rs.avg, range.min, range.max).bg + ';color:' + cellColor(rs.avg, range.min, range.max).text + ';">' + formatPct(rs.avg) + '</td>'
        + '<td class="pd-stat-col" style="background:' + cellColor(rs.median, range.min, range.max).bg + ';color:' + cellColor(rs.median, range.min, range.max).text + ';">' + formatPct(rs.median) + '</td>'
        + '<td class="pd-stat-col">' + formatUnsignedPct(rs.win_rate, 1) + '</td></tr>';
    });

    // Aggregate rows across years for each calendar month.
    var stats = result.stats || [];
    var byMonth = {};
    stats.forEach(function (s) { byMonth[s.month] = s; });

    function statRow(label, field, formatter, useReturnColor) {
      var cells = MONTHS.map(function (month) {
        var stat = byMonth[month] || {};
        var value = stat[field];
        var color = useReturnColor === false
          ? { bg: "transparent", text: "var(--apple-text-secondary)" }
          : cellColor(value, range.min, range.max);
        return '<td style="background:' + color.bg + ';color:' + color.text + ';">' + formatter(value) + '</td>';
      }).join("");
      return '<tr class="pd-stat-row"><td>' + escapeHtml(label) + '</td>' + cells + '<td>—</td><td>—</td><td>—</td><td>—</td></tr>';
    }

    rowsHtml.push(statRow(__("detail.avg"), "avg", function (v) { return formatPct(v); }));
    rowsHtml.push(statRow(__("detail.median"), "median", function (v) { return formatPct(v); }));
    rowsHtml.push(statRow(__("detail.winRate"), "win_rate", function (v) {
      return formatUnsignedPct(v, 1);
    }, false));
    rowsHtml.push(statRow(__("detail.sampleCount"), "count", function (v) {
      return v == null ? "—" : String(v);
    }, false));
    body.innerHTML = rowsHtml.join("");
  }

  function renderDailyTable(result) {
    var head = $("pdTableHead");
    var body = $("pdTableBody");
    if (!head || !body) return;
    var tableTitle = $("pdTableTitle");
    if (tableTitle) {
      tableTitle.textContent = __("detail.dailyReturnCalendarTitle", { year: result.year });
    }

    var range = getColorRange();
    var monthHead = MONTHS.map(function (m) { return "<th>" + __("yearly.monthLabel", { m: m }) + "</th>"; }).join("");
    var statColHead = '<th class="pd-stat-col">' + __("detail.avg") + '</th>'
      + '<th class="pd-stat-col">' + __("detail.median") + '</th>'
      + '<th class="pd-stat-col">' + __("detail.winRate") + '</th>';
    head.innerHTML = '<tr><th>' + __("detail.day") + '</th>' + monthHead + statColHead + '</tr>';

    var dailyRows = result.daily_rows || [];
    var rowsHtml = dailyRows.map(function (row) {
      var monthMap = {};
      (row.months || []).forEach(function (m) { monthMap[m.month] = m.return; });
      var monthCells = MONTHS.map(function (month) {
        var value = monthMap[month];
        var color = cellColor(value, range.min, range.max);
        var title = result.year + '-' + String(month).padStart(2, "0") + '-' + String(row.day).padStart(2, "0") + ' ' + formatPct(value);
        return '<td style="background:' + color.bg + ';color:' + color.text + ';" title="' + title + '">' + formatPct(value) + '</td>';
      }).join("");
      var rs = row.row_stats || {};
      return '<tr><td>' + row.day + '</td>' + monthCells
        + '<td class="pd-stat-col" style="background:' + cellColor(rs.avg, range.min, range.max).bg + ';color:' + cellColor(rs.avg, range.min, range.max).text + ';">' + formatPct(rs.avg) + '</td>'
        + '<td class="pd-stat-col" style="background:' + cellColor(rs.median, range.min, range.max).bg + ';color:' + cellColor(rs.median, range.min, range.max).text + ';">' + formatPct(rs.median) + '</td>'
        + '<td class="pd-stat-col">' + formatUnsignedPct(rs.win_rate, 1) + '</td></tr>';
    });

    // Aggregate rows across days for each calendar month.
    var stats = result.stats || [];
    var byMonth = {};
    stats.forEach(function (s) { byMonth[s.month] = s; });

    function statRow(label, field, formatter, useReturnColor) {
      var cells = MONTHS.map(function (month) {
        var stat = byMonth[month] || {};
        var value = stat[field];
        var color = useReturnColor === false
          ? { bg: "transparent", text: "var(--apple-text-secondary)" }
          : cellColor(value, range.min, range.max);
        return '<td style="background:' + color.bg + ';color:' + color.text + ';">' + formatter(value) + '</td>';
      }).join("");
      return '<tr class="pd-stat-row"><td>' + escapeHtml(label) + '</td>' + cells + '<td>—</td><td>—</td><td>—</td></tr>';
    }

    rowsHtml.push(statRow(__("detail.avg"), "avg", function (v) { return formatPct(v); }));
    rowsHtml.push(statRow(__("detail.median"), "median", function (v) { return formatPct(v); }));
    rowsHtml.push(statRow(__("detail.winRate"), "win_rate", function (v) {
      return formatUnsignedPct(v, 1);
    }, false));
    rowsHtml.push(statRow(__("detail.sampleCount"), "count", function (v) {
      return v == null ? "—" : String(v);
    }, false));
    body.innerHTML = rowsHtml.join("");
  }

  function renderSummary(result) {
    var headerEl = $("pdAssetHeader");
    var basisNote = $("pdReturnBasisNote");
    var summaryEl = $("pdSummary");
    var historyStatsEl = $("pdHistoryStats");
    if (!summaryEl || !headerEl || !historyStatsEl) return;
    var summary = result.summary || {};
    var overview = result.overview || {};
    var best = summary.best_month;
    var worst = summary.worst_month;
    var source = result.meta && result.meta.source ? result.meta.source : result.source;
    var fundamentals = result.fundamentals || {};
    var typeLabels = {
      stock: __("yearly.assetTypeStock"),
      crypto: __("yearly.assetTypeCrypto"),
      cn_stock: __("yearly.assetTypeCnStock"),
    };
    var coverage = overview.first_date && overview.latest_date
      ? overview.first_date + " → " + overview.latest_date
      : "—";
    headerEl.innerHTML = '<div><div class="pd-asset-symbol-row"><span class="pd-asset-symbol">'
      + escapeHtml(result.symbol || overview.symbol || "—") + '</span><span class="pd-asset-type">'
      + escapeHtml(typeLabels[result.type] || result.type || "—") + '</span></div>'
      + (fundamentals.name
        ? '<div class="pd-asset-name">' + escapeHtml(fundamentals.name) + '</div>'
        : "")
      + '<div class="pd-asset-meta">' + escapeHtml(__("detail.coverage")) + " · "
      + escapeHtml(coverage) + "<br>" + escapeHtml(__("detail.summarySource")) + " · "
      + escapeHtml(source || "—") + " · " + escapeHtml(__("detail.updatedAt")) + " "
      + escapeHtml(formatDateTime(overview.updated_at)) + '</div></div>'
      + '<div class="pd-asset-price-wrap"><div class="pd-asset-price-label">'
      + escapeHtml(__("detail.latestClose")) + " · " + escapeHtml(overview.latest_date || "—")
      + '</div><div class="pd-asset-price">' + escapeHtml(formatPrice(overview.latest_price))
      + '</div></div>';

    if (basisNote) {
      basisNote.textContent = __(
        result.type === "stock" ? "detail.returnBasisStock" : "detail.returnBasisAdjusted"
      );
    }

    var cards = [
      {
        label: __("detail.ytdReturn"),
        value: formatPct(overview.ytd_return),
        tone: valueTone(overview.ytd_return),
        meta: overview.current_year_is_ytd ? "YTD" : "",
      },
      {
        label: __("detail.oneYearReturn"),
        value: formatPct(overview.one_year_return),
        tone: valueTone(overview.one_year_return),
      },
      {
        label: __("detail.cagr3y"),
        value: formatPct(overview.cagr_3y),
        tone: valueTone(overview.cagr_3y),
      },
      {
        label: __("detail.cagr5y"),
        value: formatPct(overview.cagr_5y),
        tone: valueTone(overview.cagr_5y),
      },
      {
        label: __("detail.cagr10y"),
        value: formatPct(overview.cagr_10y),
        tone: valueTone(overview.cagr_10y),
      },
      {
        label: __("detail.volatility1y"),
        value: formatUnsignedPct(overview.annualized_volatility_1y),
      },
      {
        label: __("detail.currentDrawdown"),
        value: formatPct(overview.current_drawdown),
        tone: valueTone(overview.current_drawdown),
        meta: overview.all_time_high_date
          ? __("detail.athDate", { date: overview.all_time_high_date })
          : "",
      },
      {
        label: __("detail.historicalMaxDrawdown"),
        value: formatPct(overview.max_drawdown),
        tone: valueTone(overview.max_drawdown),
        meta: overview.max_drawdown_peak_date && overview.max_drawdown_trough_date
          ? __("detail.drawdownPeriod", {
            peak: overview.max_drawdown_peak_date,
            trough: overview.max_drawdown_trough_date,
          })
          : "",
      },
      {
        label: __("detail.maxDrawdownRecovery"),
        value: overview.max_drawdown_recovery_trading_days != null
          ? __("detail.tradingDays", { days: overview.max_drawdown_recovery_trading_days })
          : __("detail.notRecovered"),
        meta: overview.max_drawdown_recovery_date || "",
      },
    ];
    summaryEl.innerHTML = cards.map(function (card) {
      return '<div class="pd-summary-card"><div class="pd-summary-label">'
        + escapeHtml(card.label) + '</div><div class="pd-summary-value' + (card.tone || "")
        + '">' + escapeHtml(card.value) + '</div><div class="pd-summary-meta">'
        + escapeHtml(card.meta || "") + '</div></div>';
    }).join("");

    var bestYear = overview.best_year;
    var worstYear = overview.worst_year;
    var historyStats = result.mode === "daily"
      ? [
        [__("detail.summarySelectedYear"), result.year],
        [__("detail.summaryYears"), (result.years || []).length],
      ]
      : [
        [__("detail.summaryYears"), summary.year_count != null ? summary.year_count : "—"],
        [__("detail.summaryAvgYear"), formatPct(summary.avg_yearly_return)],
        [__("detail.summaryMedianYear"), formatPct(summary.median_yearly_return)],
        [__("detail.summaryWinRate"), formatUnsignedPct(summary.yearly_win_rate, 1)],
        [
          __("detail.summaryBestYear"),
          bestYear ? bestYear.year + " " + formatPct(bestYear.return) : "—",
        ],
        [
          __("detail.summaryWorstYear"),
          worstYear ? worstYear.year + " " + formatPct(worstYear.return) : "—",
        ],
        [
          __("detail.summaryBestMonth"),
          best ? best.year + "-" + String(best.month).padStart(2, "0") + " " + formatPct(best.return) : "—",
        ],
        [
          __("detail.summaryWorstMonth"),
          worst ? worst.year + "-" + String(worst.month).padStart(2, "0") + " " + formatPct(worst.return) : "—",
        ],
      ];
    historyStatsEl.innerHTML = historyStats.map(function (pair) {
      return '<span class="pd-history-stat"><span>' + escapeHtml(pair[0])
        + '</span><strong>' + escapeHtml(pair[1]) + '</strong></span>';
    }).join("");
  }

  function renderAnalysisCards(host, cards) {
    if (!host) return;
    host.innerHTML = cards.filter(function (card) {
      return card.available !== false;
    }).map(function (card) {
      return '<div class="pd-analysis-card"><div class="pd-analysis-label">'
        + escapeHtml(card.label) + '</div><div class="pd-analysis-value'
        + (card.tone || "") + '">' + escapeHtml(card.value)
        + '</div><div class="pd-analysis-meta">'
        + escapeHtml(card.meta || "") + '</div></div>';
    }).join("");
  }

  function renderQuality(result) {
    var section = $("pdQualitySection");
    var grid = $("pdQualityGrid");
    var note = $("pdQualityNote");
    if (!section || !grid || !note) return;
    var quality = result.quality || {};
    if (!quality.daily_observations) {
      section.style.display = "none";
      return;
    }
    var bestDay = quality.best_day_1y;
    var worstDay = quality.worst_day_1y;
    var bestRolling = quality.rolling_1y_best;
    var worstRolling = quality.rolling_1y_worst;
    var cards = [
      {
        label: __("detail.dailyWinRate"),
        value: formatUnsignedPct(quality.daily_win_rate, 1),
        meta: __("detail.observationCount", { count: quality.daily_observations }),
      },
      {
        label: __("detail.downsideVolatility1y"),
        value: formatUnsignedPct(quality.downside_volatility_1y),
        available: quality.downside_volatility_1y != null,
      },
      {
        label: __("detail.sortinoRatio1y"),
        value: formatNumber(quality.sortino_ratio_1y, 2),
        tone: valueTone(quality.sortino_ratio_1y),
        meta: __("detail.sortinoTarget"),
        available: quality.sortino_ratio_1y != null,
      },
      {
        label: __("detail.bestDay1y"),
        value: bestDay ? formatPct(bestDay.return) : "—",
        tone: bestDay ? valueTone(bestDay.return) : "",
        meta: bestDay ? bestDay.date : "",
        available: !!bestDay,
      },
      {
        label: __("detail.worstDay1y"),
        value: worstDay ? formatPct(worstDay.return) : "—",
        tone: worstDay ? valueTone(worstDay.return) : "",
        meta: worstDay ? worstDay.date : "",
        available: !!worstDay,
      },
      {
        label: __("detail.rolling1yWinRate"),
        value: formatUnsignedPct(quality.rolling_1y_win_rate, 1),
        meta: __("detail.rollingObservationCount", {
          count: quality.rolling_1y_observations,
        }),
        available: quality.rolling_1y_win_rate != null,
      },
      {
        label: __("detail.rolling1yMedian"),
        value: formatPct(quality.rolling_1y_median),
        tone: valueTone(quality.rolling_1y_median),
        available: quality.rolling_1y_median != null,
      },
      {
        label: __("detail.rolling1yBest"),
        value: bestRolling ? formatPct(bestRolling.return) : "—",
        tone: bestRolling ? valueTone(bestRolling.return) : "",
        meta: bestRolling
          ? bestRolling.start_date + " → " + bestRolling.end_date
          : "",
        available: !!bestRolling,
      },
      {
        label: __("detail.rolling1yWorst"),
        value: worstRolling ? formatPct(worstRolling.return) : "—",
        tone: worstRolling ? valueTone(worstRolling.return) : "",
        meta: worstRolling
          ? worstRolling.start_date + " → " + worstRolling.end_date
          : "",
        available: !!worstRolling,
      },
    ];
    renderAnalysisCards(grid, cards);
    note.textContent = __("detail.qualityNote");
    section.style.display = grid.childElementCount ? "block" : "none";
  }

  function renderFundamentals(result) {
    var section = $("pdFundamentalsSection");
    var grid = $("pdFundamentalsGrid");
    var note = $("pdFundamentalsNote");
    if (!section || !grid || !note) return;
    var data = result.fundamentals || {};
    if (!data.available) {
      section.style.display = "none";
      return;
    }
    var currency = data.currency || "USD";
    var isEtf = String(data.quote_type || "").toUpperCase() === "ETF";
    var cards = [
      {
        label: __(isEtf && data.total_assets != null
          ? "detail.totalAssets"
          : "detail.marketCap"),
        value: formatCompactNumber(
          isEtf && data.total_assets != null ? data.total_assets : data.market_cap,
          currency
        ),
        available: (isEtf && data.total_assets != null) || data.market_cap != null,
      },
      {
        label: __("detail.trailingPe"),
        value: formatRatio(data.trailing_pe),
        available: data.trailing_pe != null,
      },
      {
        label: __("detail.forwardPe"),
        value: formatRatio(data.forward_pe),
        available: data.forward_pe != null,
      },
      {
        label: __("detail.priceToBook"),
        value: formatRatio(data.price_to_book),
        available: data.price_to_book != null,
      },
      {
        label: __("detail.epsTtm"),
        value: formatNumber(data.eps_ttm, 3) + " " + currency,
        available: data.eps_ttm != null,
      },
      {
        label: __("detail.epsForward"),
        value: formatNumber(data.eps_forward, 3) + " " + currency,
        available: data.eps_forward != null,
      },
      {
        label: __("detail.dividendYield"),
        value: formatUnsignedPct(data.dividend_yield),
        available: data.dividend_yield != null,
      },
      {
        label: __("detail.dividendPerShareTtm"),
        value: formatNumber(data.dividend_per_share_ttm, 4) + " " + currency,
        available: data.dividend_per_share_ttm != null,
      },
      {
        label: __("detail.beta"),
        value: formatNumber(data.beta, 2),
        available: data.beta != null,
      },
      {
        label: __("detail.fiftyTwoWeekRange"),
        value: formatPrice(data.fifty_two_week_low) + " – "
          + formatPrice(data.fifty_two_week_high),
        meta: data.position_in_52w_range != null
          ? __("detail.rangePosition", {
            position: formatUnsignedPct(data.position_in_52w_range, 1),
          })
          : "",
        available: data.fifty_two_week_low != null
          && data.fifty_two_week_high != null,
      },
      {
        label: __("detail.distanceTo52wHigh"),
        value: formatPct(data.distance_to_52w_high),
        tone: valueTone(data.distance_to_52w_high),
        available: data.distance_to_52w_high != null,
      },
      {
        label: __("detail.averageVolume3m"),
        value: formatCompactNumber(data.average_volume_3m),
        available: data.average_volume_3m != null,
      },
      {
        label: __("detail.sharesOutstanding"),
        value: formatCompactNumber(data.shares_outstanding),
        available: data.shares_outstanding != null,
      },
      {
        label: __("detail.expenseRatio"),
        value: formatUnsignedPct(data.expense_ratio),
        available: data.expense_ratio != null,
      },
      {
        label: __("detail.etfYtdReturn"),
        value: formatPct(data.ytd_return),
        tone: valueTone(data.ytd_return),
        available: data.ytd_return != null,
      },
      {
        label: __("detail.etfThreeYearReturn"),
        value: formatPct(data.three_year_return),
        tone: valueTone(data.three_year_return),
        available: data.three_year_return != null,
      },
      {
        label: __("detail.etfFiveYearReturn"),
        value: formatPct(data.five_year_average_return),
        tone: valueTone(data.five_year_average_return),
        available: data.five_year_average_return != null,
      },
    ];
    renderAnalysisCards(grid, cards);
    var snapshot = data.snapshot_at ? formatDateTime(data.snapshot_at) : "—";
    note.textContent = __("detail.fundamentalsNote", {
      source: data.source || "Yahoo",
      time: snapshot,
    });
    section.style.display = grid.childElementCount ? "block" : "none";
  }

  function hideStockHistory(clearCache) {
    var section = $("pdStockHistory");
    if (section) section.style.display = "none";
    _lastStockHistoryResult = null;
    if (clearCache) _stockHistoryCache = null;
  }

  function getDividendTaxRate() {
    var input = $("pdDividendTaxRate");
    var rawValue = input?.value;
    if (rawValue == null || String(rawValue).trim() === "") return 30;
    var value = Number(rawValue);
    if (!Number.isFinite(value)) return 30;
    return Math.max(0, Math.min(100, value));
  }

  function renderStockHistory(result) {
    var section = $("pdStockHistory");
    var body = $("pdStockHistoryBody");
    var tables = result && result.stock_tables;
    if (!section || !body) return;
    if (result.type !== "stock") {
      hideStockHistory(true);
      return;
    }
    if (tables) {
      _stockHistoryCache = {
        symbol: result.symbol,
        type: result.type,
        tables: tables,
      };
    } else if (
      _stockHistoryCache
      && _stockHistoryCache.symbol === result.symbol
      && _stockHistoryCache.type === result.type
    ) {
      tables = _stockHistoryCache.tables;
    }
    if (!tables) {
      hideStockHistory(false);
      return;
    }
    _lastStockHistoryResult = Object.assign({}, result, { stock_tables: tables });

    var range = getColorRange();
    var taxRate = getDividendTaxRate();
    var rows = (tables.rows || []).map(function (row) {
      var totalDividend = Number(row.total_dividend_per_share) || 0;
      var afterTaxDividend = totalDividend * (1 - taxRate / 100);
      var dividendBasis = Number(row.dividend_yield_basis_price);
      var dividendYieldAfterTax = Number.isFinite(dividendBasis) && dividendBasis > 0
        ? afterTaxDividend / dividendBasis * 100
        : null;
      var combinedAnnualized = row.annual_return != null && dividendYieldAfterTax != null
        ? Number(row.annual_return) + dividendYieldAfterTax
        : null;
      var combinedColor = cellColor(combinedAnnualized, range.min, range.max);
      var returnColor = cellColor(row.annual_return, range.min, range.max);
      var dividendYieldColor = cellColor(dividendYieldAfterTax, range.min, range.max);
      var drawdownColor = cellColor(row.max_drawdown, range.min, range.max);
      var runupColor = cellColor(row.max_runup, range.min, range.max);
      var payments = (row.dividend_payments || []).map(function (payment) {
        return '<div class="pd-dividend-payment">'
          + escapeHtml(payment.date) + " · " + escapeHtml(formatDividend(payment.amount))
          + '</div>';
      }).join("");
      return '<tr><td>' + escapeHtml(row.year) + '</td><td style="background:'
        + combinedColor.bg + ';color:' + combinedColor.text + ';font-weight:700;">'
        + escapeHtml(formatPct(combinedAnnualized)) + '</td><td style="background:'
        + returnColor.bg + ';color:' + returnColor.text + ';font-weight:600;">'
        + escapeHtml(formatPct(row.annual_return)) + '</td><td style="background:'
        + dividendYieldColor.bg + ';color:' + dividendYieldColor.text + ';font-weight:600;">'
        + escapeHtml(formatPct(dividendYieldAfterTax)) + '</td><td style="background:'
        + drawdownColor.bg + ';color:' + drawdownColor.text + ';font-weight:600;">'
        + escapeHtml(formatPct(row.max_drawdown)) + '</td><td style="background:'
        + runupColor.bg + ';color:' + runupColor.text
        + ';font-weight:600;">' + escapeHtml(formatPct(row.max_runup))
        + '</td><td>' + escapeHtml(row.payment_count || 0)
        + '</td><td>' + (payments || "—")
        + '</td><td style="font-weight:600;">' + escapeHtml(formatDividend(totalDividend))
        + '</td><td style="font-weight:600;">' + escapeHtml(formatDividend(afterTaxDividend))
        + '</td></tr>';
    });
    body.innerHTML = rows.length
      ? rows.join("")
      : '<tr><td class="pd-history-empty" colspan="10">'
        + escapeHtml(__("detail.noHistoryData")) + '</td></tr>';

    section.style.display = "block";
  }

  function barChartPoints(result) {
    if (result.mode === "daily") {
      var monthlyByNumber = {};
      (result.monthly_returns || []).forEach(function (item) {
        monthlyByNumber[Number(item.month)] = item;
      });
      return MONTHS.map(function (month) {
        var item = monthlyByNumber[month] || {};
        return {
          label: __("yearly.monthLabel", { m: month }),
          value: item.return,
          maxDailyGain: item.max_daily_gain,
          maxDailyLoss: item.max_daily_loss,
          candle: item.candle,
        };
      });
    }

    return (result.rows || []).slice().sort(function (a, b) {
      return Number(a.year) - Number(b.year);
    }).map(function (row) {
      return {
        label: String(row.year),
        value: row.annual_return,
        maxDailyGain: row.max_daily_gain,
        maxDailyLoss: row.max_daily_loss,
        candle: row.candle,
      };
    });
  }

  function chartDetailText(point) {
    var parts = [
      point.label,
      __("detail.chartCloseReturn") + " " + formatPct(point.value),
    ];
    if (point.maxDailyGain) {
      parts.push(__("detail.chartMaxDailyGain") + " " + formatPct(point.maxDailyGain.return)
        + " · " + point.maxDailyGain.date);
    }
    if (point.maxDailyLoss) {
      parts.push(__("detail.chartMaxDailyLoss") + " " + formatPct(point.maxDailyLoss.return)
        + " · " + point.maxDailyLoss.date);
    }
    if (point.candle) {
      parts.push(__("detail.chartOhlcReturn") + " "
        + [
          point.candle.high_return,
          point.candle.open_return,
          point.candle.low_return,
          point.candle.close_return,
        ].map(formatPct).join(" / "));
      parts.push(__("detail.chartOhlcPrice") + " "
        + [point.candle.high, point.candle.open, point.candle.low, point.candle.close]
          .map(formatPrice).join(" / "));
      parts.push(__("detail.chartAmplitude") + " " + formatPrice(point.candle.amplitude));
      parts.push(__("detail.chartAmplitudePercent") + " "
        + formatUnsignedPct(point.candle.amplitude_percent));
    }
    return parts.join("；");
  }

  function attachBarChartTooltips(host, points) {
    var tooltip = host.querySelector(".pd-chart-tooltip");
    var marks = host.querySelectorAll(".pd-range-mark");
    if (!tooltip) return;

    function hide() {
      tooltip.hidden = true;
    }

    function position(mark) {
      var markRect = mark.getBoundingClientRect();
      var tipRect = tooltip.getBoundingClientRect();
      var left = markRect.left + markRect.width / 2 - tipRect.width / 2;
      var top = markRect.top - tipRect.height - 8;
      left = Math.max(8, Math.min(left, window.innerWidth - tipRect.width - 8));
      if (top < 8) top = markRect.bottom + 8;
      tooltip.style.left = Math.round(left) + "px";
      tooltip.style.top = Math.round(top) + "px";
    }

    function show(mark, point) {
      var candle = point.candle || {};
      var closeTone = Number(point.value) > 0
        ? " is-positive"
        : (Number(point.value) < 0 ? " is-negative" : "");
      var ohlcLabels = [
        __("detail.chartHighShort"),
        __("detail.chartOpenShort"),
        __("detail.chartLowShort"),
        __("detail.chartCloseShort"),
      ];

      function matrix(label, values, formatter, colorValues) {
        var cells = ohlcLabels.map(function (item, index) {
          var tone = "";
          if (colorValues) {
            tone = Number(values[index]) > 0
              ? " is-positive"
              : (Number(values[index]) < 0 ? " is-negative" : "");
          }
          return '<div class="pd-chart-tooltip-cell"><span>' + escapeHtml(item)
            + '</span><strong class="' + tone.trim() + '">'
            + escapeHtml(formatter(values[index])) + '</strong></div>';
        }).join("");
        return '<div class="pd-chart-tooltip-section"><div class="pd-chart-tooltip-section-label">'
          + escapeHtml(label) + '</div><div class="pd-chart-tooltip-matrix">'
          + cells + '</div></div>';
      }

      var rows = [
        '<div class="pd-chart-tooltip-row pd-chart-tooltip-close"><span>'
          + '<i class="pd-return-dot' + closeTone + '" aria-hidden="true"></i>'
          + escapeHtml(__("detail.chartCloseReturn")) + '</span><strong class="' + closeTone.trim() + '">'
          + escapeHtml(formatPct(point.value)) + '</strong></div>',
        '<div class="pd-chart-tooltip-row"><span>' + escapeHtml(__("detail.chartMaxDailyGain")) + '</span><strong>'
          + escapeHtml(point.maxDailyGain
            ? formatPct(point.maxDailyGain.return) + " · " + point.maxDailyGain.date
            : "—") + '</strong></div>',
        '<div class="pd-chart-tooltip-row"><span>' + escapeHtml(__("detail.chartMaxDailyLoss")) + '</span><strong>'
          + escapeHtml(point.maxDailyLoss
            ? formatPct(point.maxDailyLoss.return) + " · " + point.maxDailyLoss.date
            : "—") + '</strong></div>',
        '<div class="pd-chart-tooltip-row"><span>' + escapeHtml(__("detail.chartAmplitude")) + '</span><strong>'
          + escapeHtml(formatPrice(candle.amplitude)) + '</strong></div>',
        '<div class="pd-chart-tooltip-row"><span>' + escapeHtml(__("detail.chartAmplitudePercent")) + '</span><strong>'
          + escapeHtml(formatUnsignedPct(candle.amplitude_percent)) + '</strong></div>',
        matrix(
          __("detail.chartOhlcReturn"),
          [candle.high_return, candle.open_return, candle.low_return, candle.close_return],
          formatPct,
          true
        ),
        matrix(
          __("detail.chartOhlcPrice"),
          [candle.high, candle.open, candle.low, candle.close],
          formatPrice,
          false
        ),
      ];
      tooltip.innerHTML = rows.join("");
      tooltip.hidden = false;
      position(mark);
    }

    marks.forEach(function (mark) {
      var point = points[Number(mark.dataset.pointIndex)];
      if (!point) return;
      mark.addEventListener("mouseenter", function () { show(mark, point); });
      mark.addEventListener("mousemove", function () { position(mark); });
      mark.addEventListener("mouseleave", hide);
      mark.addEventListener("focus", function () { show(mark, point); });
      mark.addEventListener("blur", hide);
      mark.addEventListener("click", function () {
        mark.focus();
        show(mark, point);
      });
    });
    host.onpointerleave = hide;
    host.onscroll = hide;
  }

  function scrollBarChartToLatest() {
    var host = $("pdBarChart");
    if (!host || _barChartCollapsed) return;
    window.requestAnimationFrame(function () {
      host.scrollLeft = host.scrollWidth - host.clientWidth;
    });
  }

  function setBarChartCollapsed(collapsed) {
    var card = $("pdBarChartCard");
    var host = $("pdBarChart");
    var toggle = $("pdBarChartToggle");
    var resizeHandle = $("pdBarChartResizeHandle");
    _barChartCollapsed = Boolean(collapsed);
    if (card) card.classList.toggle("is-collapsed", _barChartCollapsed);
    if (host) host.style.display = _barChartCollapsed ? "none" : "block";
    if (resizeHandle) {
      var canResize = resizeHandle.dataset.enabled === "true";
      resizeHandle.style.display = !_barChartCollapsed && canResize ? "flex" : "none";
    }
    if (toggle) {
      toggle.textContent = __(_barChartCollapsed ? "detail.expandChart" : "detail.collapseChart");
      toggle.setAttribute("aria-expanded", String(!_barChartCollapsed));
    }
    if (!_barChartCollapsed) scrollBarChartToLatest();
  }

  function resizeBarChart(height) {
    var nextHeight = Math.max(180, Math.min(480, Math.round(height)));
    if (nextHeight === _barChartHeight) return;
    _barChartHeight = nextHeight;
    var handle = $("pdBarChartResizeHandle");
    if (handle) handle.setAttribute("aria-valuenow", String(nextHeight));
    if (!_lastBarChartResult) return;
    if (_resizeRenderFrame) window.cancelAnimationFrame(_resizeRenderFrame);
    _resizeRenderFrame = window.requestAnimationFrame(function () {
      _resizeRenderFrame = null;
      renderBarChart(_lastBarChartResult);
    });
  }

  function setParamsCollapsed(collapsed) {
    var panel = $("pdParamsPanel");
    var toggle = $("pdParamsToggle");
    _paramsCollapsed = Boolean(collapsed);
    if (panel) panel.style.display = _paramsCollapsed ? "none" : "block";
    if (toggle) {
      toggle.textContent = __(_paramsCollapsed ? "detail.expandParams" : "detail.collapseParams");
      toggle.setAttribute("aria-expanded", String(!_paramsCollapsed));
    }
  }

  function setOverviewCollapsed(collapsed) {
    var panel = $("pdOverviewPanel");
    var toggle = $("pdOverviewToggle");
    _overviewCollapsed = Boolean(collapsed);
    if (panel) panel.style.display = _overviewCollapsed ? "none" : "block";
    if (toggle) {
      toggle.textContent = __(
        _overviewCollapsed ? "detail.expandOverview" : "detail.collapseOverview"
      );
      toggle.setAttribute("aria-expanded", String(!_overviewCollapsed));
    }
  }

  function renderBarChart(result) {
    var card = $("pdBarChartCard");
    var title = $("pdBarChartTitle");
    var host = $("pdBarChart");
    if (!card || !title || !host) return;
    _lastBarChartResult = result;

    var points = barChartPoints(result);
    var finiteValues = [];
    points.forEach(function (point) {
      var candle = point.candle || {};
      [candle.open_return, candle.high_return, candle.low_return, candle.close_return].forEach(function (value) {
        if (value != null && Number.isFinite(Number(value))) finiteValues.push(Number(value));
      });
    });
    if (!points.length || !finiteValues.length) {
      card.style.display = "none";
      host.innerHTML = "";
      return;
    }

    title.textContent = result.mode === "daily"
      ? __("detail.chartMonthlyTitle", { year: result.year })
      : __("detail.chartYearlyTitle");

    var panel = host.closest(".pc-monthly");
    var panelStyle = panel ? window.getComputedStyle(panel) : null;
    var panelInnerW = panel ? panel.clientWidth
      - parseFloat(panelStyle.paddingLeft || 0)
      - parseFloat(panelStyle.paddingRight || 0) : 0;
    var availableW = Math.floor(panelInnerW - 22);
    var intrinsicW = points.length * 34 + 62;
    var spreadsToFill = availableW >= intrinsicW;
    var W = Math.max(470, availableW, intrinsicW);
    var H = _barChartHeight;
    var pad = { top: 22, right: 10, bottom: 30, left: 48 };
    var plotW = W - pad.left - pad.right;
    var plotH = H - pad.top - pad.bottom;
    var zeroY = pad.top + plotH / 2;
    var maxAbs = Math.max.apply(null, finiteValues.map(function (value) { return Math.abs(value); }));
    maxAbs = maxAbs || 1;
    var halfPlotH = plotH / 2 - 10;
    var slotW = plotW / points.length;
    var barW = spreadsToFill
      ? Math.max(16, Math.min(42, slotW * 0.55))
      : Math.max(12, Math.min(28, slotW * 0.78));
    var parts = [];

    [1, 0.5, 0, -0.5, -1].forEach(function (ratio) {
      var y = zeroY - ratio * halfPlotH;
      var value = ratio * maxAbs;
      var isZero = ratio === 0;
      parts.push('<line x1="' + pad.left + '" y1="' + y.toFixed(1) + '" x2="' + (W - pad.right) + '" y2="' + y.toFixed(1)
        + '" stroke="' + (isZero ? 'var(--apple-blue)' : 'var(--apple-divider)')
        + '" stroke-width="1"' + (isZero ? ' stroke-dasharray="6,4" opacity="0.55"' : ' stroke-dasharray="3,3"') + '/>');
      parts.push('<text x="' + (pad.left - 7) + '" y="' + (y + 4).toFixed(1)
        + '" text-anchor="end" fill="' + (isZero ? 'var(--apple-blue)' : 'var(--apple-text-tertiary)')
        + '" opacity="' + (isZero ? '0.8' : '1') + '" font-size="10">' + formatPct(value, 1) + '</text>');
    });

    points.forEach(function (point, index) {
      var value = Number(point.value);
      var candle = point.candle || {};
      var openReturn = Number(candle.open_return);
      var highReturn = Number(candle.high_return);
      var lowReturn = Number(candle.low_return);
      var closeReturn = Number(candle.close_return);
      var hasCandle = [openReturn, highReturn, lowReturn, closeReturn].every(Number.isFinite);
      var x = pad.left + index * slotW + (slotW - barW) / 2;
      var centerX = x + barW / 2;
      var label = escapeHtml(point.label);
      var hitX = pad.left + index * slotW;
      var ariaLabel = escapeHtml(chartDetailText(point));
      parts.push('<g class="pd-range-mark" data-point-index="' + index + '" tabindex="0" role="img" aria-label="' + ariaLabel + '">');
      parts.push('<rect x="' + hitX.toFixed(1) + '" y="' + pad.top + '" width="' + slotW.toFixed(1)
        + '" height="' + plotH.toFixed(1) + '" fill="transparent"/>');

      if (hasCandle) {
        var yHigh = zeroY - (highReturn / maxAbs) * halfPlotH;
        var yLow = zeroY - (lowReturn / maxAbs) * halfPlotH;
        var yOpen = zeroY - (openReturn / maxAbs) * halfPlotH;
        var yClose = zeroY - (closeReturn / maxAbs) * halfPlotH;
        var candleUp = closeReturn >= openReturn;
        var color = candleUp ? "var(--data-positive)" : "var(--data-negative)";
        var bodyY = Math.min(yOpen, yClose);
        var bodyHeight = Math.abs(yOpen - yClose);
        parts.push('<line x1="' + centerX.toFixed(1) + '" y1="' + yHigh.toFixed(1)
          + '" x2="' + centerX.toFixed(1) + '" y2="' + yLow.toFixed(1)
          + '" stroke="' + color + '" stroke-width="1.5"/>');
        if (bodyHeight < 1) {
          parts.push('<line class="pd-candle-body" x1="' + x.toFixed(1)
            + '" y1="' + ((yOpen + yClose) / 2).toFixed(1)
            + '" x2="' + (x + barW).toFixed(1)
            + '" y2="' + ((yOpen + yClose) / 2).toFixed(1)
            + '" stroke="' + color + '" stroke-width="1.5"/>');
        } else {
          parts.push('<rect class="pd-candle-body" x="' + x.toFixed(1) + '" y="' + bodyY.toFixed(1)
            + '" width="' + barW.toFixed(1) + '" height="' + bodyHeight.toFixed(1)
            + '" rx="2" fill="' + color + '" opacity="0.9"/>');
        }
        if (point.value != null && Number.isFinite(value)) {
          var textY = closeReturn >= 0 ? yHigh - 6 : yLow + 13;
          parts.push('<text x="' + centerX.toFixed(1) + '" y="' + textY.toFixed(1)
            + '" text-anchor="middle" fill="' + color + '" font-size="9" font-weight="600">'
            + escapeHtml(formatPct(value, 1)) + '</text>');
        }
      }
      parts.push('</g>');
      parts.push('<text x="' + centerX.toFixed(1) + '" y="' + (H - 14)
        + '" text-anchor="middle" fill="var(--apple-text-tertiary)" font-size="10">' + label + '</text>');
    });

    host.innerHTML = '<svg viewBox="0 0 ' + W + ' ' + H + '" width="' + W + '" height="' + H + '" role="img" aria-label="'
      + escapeHtml(__("detail.chartAriaLabel"))
      + '" style="width:' + W + 'px;height:' + H + 'px;font-family:-apple-system,SF Pro Text,Helvetica,Arial,sans-serif;">'
      + parts.join("") + '</svg><div class="pd-chart-tooltip" role="tooltip" hidden></div>';
    attachBarChartTooltips(host, points);
    var resizeHandle = $("pdBarChartResizeHandle");
    if (resizeHandle) {
      resizeHandle.dataset.enabled = "true";
      resizeHandle.setAttribute("aria-valuenow", String(_barChartHeight));
    }
    card.style.display = "block";
    setBarChartCollapsed(_barChartCollapsed);
  }

  async function queryDetail() {
    var symbolInput = $("pdSymbolInput");
    var typeSelect = $("pdTypeSelect");
    var yearSelect = $("pdYearSelect");
    var symbol = (symbolInput?.value || "").trim().toUpperCase();
    var type = typeSelect?.value || "stock";
    var year = _pendingYear || yearSelect?.value || "";
    if (!symbol) {
      showError(__("detail.errorNoSymbol"));
      setResultVisible(false);
      return;
    }

    try {
      localStorage.setItem("gah_detail_state", JSON.stringify({
        symbol: symbol,
        type: type,
        year: year,
        minRange: $("pdMinRange")?.value || "-50",
        maxRange: $("pdMaxRange")?.value || "50",
      }));
    } catch (_) {}

    showError(null);
    setLoading(true);
    setResultVisible(false);
    var canReuseStockHistory = (
      _stockHistoryCache
      && _stockHistoryCache.symbol === symbol
      && _stockHistoryCache.type === type
    );
    hideStockHistory(!canReuseStockHistory);

    try {
      var body = { symbol: symbol, type: type };
      if (year) body.year = parseInt(year, 10);
      if (year && type === "stock") {
        body.include_stock_history = !canReuseStockHistory;
      }
      var resp = await fetch(DETAIL_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      var result = await resp.json().catch(function () { return {}; });
      if (!resp.ok) {
        throw new Error(result.error || "HTTP " + resp.status);
      }
      buildYearSelector(result.years || []);
      if (result.year != null && $("pdYearSelect")) {
        $("pdYearSelect").value = String(result.year);
      }
      _pendingYear = "";
      renderSummary(result);
      renderQuality(result);
      renderFundamentals(result);
      renderBarChart(result);
      if (result.mode === "daily") {
        renderDailyTable(result);
      } else {
        renderYearlyTable(result);
      }
      renderStockHistory(result);
      setResultVisible(true);
      var nextUrl = new URL(window.location.href);
      nextUrl.searchParams.set("symbol", symbol);
      nextUrl.searchParams.set("type", type);
      if (result.year != null) {
        nextUrl.searchParams.set("year", String(result.year));
      } else {
        nextUrl.searchParams.delete("year");
      }
      history.replaceState(
        { tab: "detail", symbol: symbol, type: type, year: result.year || null },
        "",
        nextUrl.pathname + nextUrl.search
      );
    } catch (err) {
      showError(__("detail.errorRequest") + " " + err.message);
      setResultVisible(false);
    } finally {
      setLoading(false);
    }
  }

  function restoreState() {
    try {
      var raw = localStorage.getItem("gah_detail_state");
      if (!raw) return;
      var state = JSON.parse(raw);
      if (state.symbol && $("pdSymbolInput")) $("pdSymbolInput").value = state.symbol;
      if (state.type && $("pdTypeSelect")) $("pdTypeSelect").value = state.type;
      if (state.minRange && $("pdMinRange")) $("pdMinRange").value = state.minRange;
      if (state.maxRange && $("pdMaxRange")) $("pdMaxRange").value = state.maxRange;
    } catch (_) {}
  }

  function init() {
    var btn = $("pdQueryBtn");
    var input = $("pdSymbolInput");
    var typeSelect = $("pdTypeSelect");
    var dividendTaxInput = $("pdDividendTaxRate");
    if (!btn || !input) return;
    restoreState();
    var params = new URLSearchParams(window.location.search);
    var linkedSymbol = (params.get("symbol") || "").trim().toUpperCase();
    if (linkedSymbol) {
      input.value = linkedSymbol;
      if ($("pdTypeSelect") && params.get("type")) $("pdTypeSelect").value = params.get("type");
      var linkedYear = params.get("year");
      _pendingYear = linkedYear && /^\d{4}$/.test(linkedYear) ? linkedYear : "";
    }
    btn.addEventListener("click", queryDetail);
    if (typeSelect) {
      typeSelect.addEventListener("change", function () {
        if (typeSelect.value !== "stock") hideStockHistory(true);
      });
    }
    if (dividendTaxInput) {
      try {
        var savedTaxRate = localStorage.getItem("gah_dividend_tax_rate");
        if (savedTaxRate != null && savedTaxRate !== "") {
          dividendTaxInput.value = savedTaxRate;
        }
      } catch (_) {}
      dividendTaxInput.addEventListener("input", function () {
        var taxRate = getDividendTaxRate();
        try {
          localStorage.setItem("gah_dividend_tax_rate", String(taxRate));
        } catch (_) {}
        if (_lastStockHistoryResult) renderStockHistory(_lastStockHistoryResult);
      });
      dividendTaxInput.addEventListener("change", function () {
        dividendTaxInput.value = String(getDividendTaxRate());
      });
    }
    var chartToggle = $("pdBarChartToggle");
    if (chartToggle) {
      chartToggle.addEventListener("click", function () {
        setBarChartCollapsed(!_barChartCollapsed);
      });
    }
    var paramsToggle = $("pdParamsToggle");
    if (paramsToggle) {
      paramsToggle.addEventListener("click", function () {
        setParamsCollapsed(!_paramsCollapsed);
      });
    }
    var overviewToggle = $("pdOverviewToggle");
    if (overviewToggle) {
      overviewToggle.addEventListener("click", function () {
        setOverviewCollapsed(!_overviewCollapsed);
      });
    }
    var resizeHandle = $("pdBarChartResizeHandle");
    if (resizeHandle) {
      var dragStartY = 0;
      var dragStartHeight = 0;
      var activePointerId = null;
      resizeHandle.addEventListener("pointerdown", function (event) {
        if (resizeHandle.dataset.enabled !== "true") return;
        activePointerId = event.pointerId;
        dragStartY = event.clientY;
        dragStartHeight = _barChartHeight;
        resizeHandle.classList.add("is-dragging");
        resizeHandle.setPointerCapture(event.pointerId);
        event.preventDefault();
      });
      resizeHandle.addEventListener("pointermove", function (event) {
        if (event.pointerId !== activePointerId) return;
        resizeBarChart(dragStartHeight + event.clientY - dragStartY);
      });
      function stopResize(event) {
        if (event.pointerId !== activePointerId) return;
        resizeHandle.classList.remove("is-dragging");
        activePointerId = null;
      }
      resizeHandle.addEventListener("pointerup", stopResize);
      resizeHandle.addEventListener("pointercancel", stopResize);
      resizeHandle.addEventListener("keydown", function (event) {
        if (resizeHandle.dataset.enabled !== "true") return;
        if (event.key === "ArrowUp") {
          resizeBarChart(_barChartHeight - 20);
          event.preventDefault();
        } else if (event.key === "ArrowDown") {
          resizeBarChart(_barChartHeight + 20);
          event.preventDefault();
        }
      });
    }
    input.addEventListener("keydown", function (event) {
      if (event.key === "Enter") queryDetail();
    });
    ["pdMinRange", "pdMaxRange"].forEach(function (id) {
      var el = $(id);
      if (el) el.addEventListener("keydown", function (event) {
        if (event.key === "Enter") queryDetail();
      });
    });
    // re-query on year change
    var yearSel = $("pdYearSelect");
    if (yearSel) {
      yearSel.addEventListener("change", function () {
        if ($("pdSymbolInput") && $("pdSymbolInput").value.trim()) {
          queryDetail();
        }
      });
    }
    if (linkedSymbol) queryDetail();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
