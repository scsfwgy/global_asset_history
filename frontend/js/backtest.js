/** Backtest controls, chart, and result table. */

const BACKTEST_SYMBOL_STORAGE_KEY = "gah_backtest_symbol";
let _btCurrency = "USD";

const GLOBAL_STOCK_CURRENCIES = [
  [".TWO", "TWD"], [".KS", "KRW"], [".KQ", "KRW"], [".TW", "TWD"],
  [".NS", "INR"], [".BO", "INR"], [".SI", "SGD"], [".AX", "AUD"],
  [".TO", "CAD"], [".V", "CAD"], [".L", "GBp"], [".DE", "EUR"],
  [".AS", "EUR"], [".PA", "EUR"], [".SW", "CHF"], [".CO", "DKK"],
  [".SA", "BRL"], [".SR", "SAR"], [".T", "JPY"],
];

function backtestCurrencyForType(type, symbol) {
  if (type === "global_stock") {
    var cleanSymbol = String(symbol || "").trim().toUpperCase();
    var match = GLOBAL_STOCK_CURRENCIES.find(function (item) {
      return cleanSymbol.endsWith(item[0]);
    });
    return match ? match[1] : "USD";
  }
  return type === "hk_stock" ? "HKD"
    : type === "cn_stock" ? "CNY"
      : type === "crypto" ? "USDT"
        : "USD";
}

function syncBacktestCurrency(type, currency) {
  _btCurrency = currency || backtestCurrencyForType(
    type || btTypeSelect?.value || "stock",
    btSymbolInput?.value || ""
  );
  var label = document.getElementById("pcBtCurrency");
  if (label) label.textContent = _btCurrency;
}

function saveBacktestSymbol(symbol, type) {
  try {
    localStorage.setItem(BACKTEST_SYMBOL_STORAGE_KEY, JSON.stringify({
      symbol: symbol,
      type: type,
    }));
  } catch (_) { /* localStorage unavailable — keep the current form value */ }
}

function restoreBacktestSymbol() {
  try {
    var raw = localStorage.getItem(BACKTEST_SYMBOL_STORAGE_KEY);
    if (!raw) return false;
    var state = JSON.parse(raw);
    var type = state && state.type;
    var symbol = normalizeAssetSymbol(state && state.symbol || "", type);
    if (!symbol) return false;
    if (btSymbolInput) btSymbolInput.value = symbol;
    if (btTypeSelect && ["stock", "hk_stock", "global_stock", "crypto", "cn_stock"].indexOf(type) !== -1) {
      btTypeSelect.value = type;
    }
    syncBacktestCurrency(type);
    return true;
  } catch (_) {
    return false;
  }
}

function initBacktestSymbolPersistence() {
  restoreBacktestSymbol();
  syncBacktestCurrency(btTypeSelect?.value || "stock");

  function saveCurrentPreference() {
    var type = btTypeSelect?.value || "stock";
    var symbol = normalizeAssetSymbol(btSymbolInput?.value || "", type);
    if (symbol) saveBacktestSymbol(symbol, type);
    syncBacktestCurrency(type);
  }

  if (btSymbolInput) btSymbolInput.addEventListener("input", saveCurrentPreference);
  if (btTypeSelect) btTypeSelect.addEventListener("change", saveCurrentPreference);

  if (typeof gahHistoryBind === "function") {
    gahHistoryBind("gah_backtest_history", document.getElementById("btHistory"), function (rec) {
      if (btSymbolInput) btSymbolInput.value = rec.symbol;
      if (btTypeSelect) btTypeSelect.value = rec.type;
    });
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initBacktestSymbolPersistence);
} else {
  initBacktestSymbolPersistence();
}

function getChartColors() {
  const s = getComputedStyle(document.documentElement);
  return {
    invested: s.getPropertyValue('--apple-chart-invested').trim() || 'rgba(255,255,255,0.55)',
    guide: s.getPropertyValue('--apple-chart-guide').trim() || 'rgba(255,255,255,0.18)',
    tooltipBg: s.getPropertyValue('--apple-tooltip-bg').trim() || 'rgba(24,24,26,0.96)',
    tooltipBorder: s.getPropertyValue('--apple-tooltip-border').trim() || 'rgba(255,255,255,0.12)',
    tooltipText: s.getPropertyValue('--apple-tooltip-text').trim() || '#fff',
    positive: s.getPropertyValue('--data-positive').trim() || '#30d158',
    negative: s.getPropertyValue('--data-negative').trim() || '#ff453a',
    positiveAlpha22: s.getPropertyValue('--data-positive-alpha-22').trim() || 'rgba(48,209,88,0.22)',
    positiveAlpha88: s.getPropertyValue('--data-positive-alpha-88').trim() || 'rgba(48,209,88,0.88)',
    negativeAlpha18: s.getPropertyValue('--data-negative-alpha-18').trim() || 'rgba(255,69,58,0.18)',
  };
}

function getBacktestSampleSize() {
  const raw = parseInt(btSampleSize?.value, 10);
  return Number.isFinite(raw) ? Math.max(BACKTEST_MIN_SAMPLE, raw) : BACKTEST_DEFAULT_SAMPLE;
}

function getBacktestAnimMs() {
  const raw = parseFloat(btAnimSeconds?.value);
  if (!Number.isFinite(raw) || raw < 0) return 5000;
  return raw * 1000;
}

function getCompareAnimMs() {
  const raw = parseFloat($("pcBtCompareAnim")?.value);
  if (!Number.isFinite(raw) || raw < 0) return 20000;
  return raw * 1000;
}

function sampleEvenly(items, maxPoints) {
  if (!Array.isArray(items) || items.length <= maxPoints) return items || [];
  const sampled = [];
  const lastIndex = items.length - 1;
  for (let i = 0; i < maxPoints; i++) {
    const idx = Math.round((i * lastIndex) / Math.max(1, maxPoints - 1));
    sampled.push(items[idx]);
  }
  return sampled;
}

// Shared chart geometry and styling. Detail, compare, page SVG, and recorded
// SVG all use these tokens so axes do not drift as each view evolves.
var BT_GRID_STROKE = 'stroke-width="0.35" opacity="0.45"';
var BT_AXIS_FONT = 9;
var BT_AXIS_LINE_STROKE = 0.6;
var BT_AXIS_LINE_OPACITY = 0.65;
var BT_PRIMARY_LINE_STROKE = 1.8;
var BT_SECONDARY_LINE_STROKE = 1.4;

function btDateMs(value) {
  var ms = Date.parse(String(value || "") + "T00:00:00Z");
  return Number.isFinite(ms) ? ms : NaN;
}

function formatBtDateTick(ms) {
  return new Date(ms).toISOString().slice(0, 7);
}

function buildBtDateTicks(minMs, maxMs, count) {
  if (!Number.isFinite(minMs) || !Number.isFinite(maxMs)) return [];
  if (minMs === maxMs || count <= 1) return [{ ms: minMs, label: formatBtDateTick(minMs) }];
  var ticks = [];
  for (var i = 0; i < count; i++) {
    var ms = minMs + ((maxMs - minMs) * i) / (count - 1);
    var label = formatBtDateTick(ms);
    if (!ticks.length || ticks[ticks.length - 1].label !== label) ticks.push({ ms: ms, label: label });
  }
  return ticks;
}

function estimateBtTextWidth(text, fontSize) {
  return Array.from(String(text || "")).reduce(function (sum, ch) {
    return sum + (/[^\u0000-\u00ff]/.test(ch) ? 1 : 0.6) * fontSize;
  }, 0);
}

function buildBtChartPadding(yLabels, fontSize, portrait) {
  var widest = yLabels.reduce(function (max, label) {
    return Math.max(max, estimateBtTextWidth(label, fontSize));
  }, 0);
  return {
    top: Math.max(10, Math.ceil(fontSize * 0.9)),
    right: portrait ? 16 : 20,
    bottom: Math.ceil(fontSize + 18),
    left: Math.max(portrait ? 48 : 44, Math.ceil(widest + 10)),
  };
}

function buildBtAxes(config) {
  var yGrid = "", yLabels = "";
  config.yValues.forEach(function (v) {
    var y = config.yPos(v);
    yGrid += `<line x1="${config.PAD.left}" y1="${y}" x2="${config.W - config.PAD.right}" y2="${y}" stroke="${config.gridColor}" ${BT_GRID_STROKE}/>`;
    yLabels += `<text x="${config.PAD.left - 6}" y="${y + config.fontSize * 0.35}" text-anchor="end" fill="${config.labelColor}" font-size="${config.fontSize}">${config.formatY(v)}</text>`;
  });

  var plotBottom = config.H - config.PAD.bottom;
  var axisLines = `<line x1="${config.PAD.left}" y1="${config.PAD.top}" x2="${config.PAD.left}" y2="${plotBottom}" stroke="${config.axisColor}" stroke-width="${BT_AXIS_LINE_STROKE}" opacity="${BT_AXIS_LINE_OPACITY}"/>` +
    `<line x1="${config.PAD.left}" y1="${plotBottom}" x2="${config.W - config.PAD.right}" y2="${plotBottom}" stroke="${config.axisColor}" stroke-width="${BT_AXIS_LINE_STROKE}" opacity="${BT_AXIS_LINE_OPACITY}"/>`;

  var xLabels = config.xTicks.map(function (tick, index) {
    var anchor = index === 0 ? "start" : (index === config.xTicks.length - 1 ? "end" : "middle");
    return `<text x="${config.xPosMs(tick.ms)}" y="${config.H - 5}" text-anchor="${anchor}" fill="${config.labelColor}" font-size="${config.fontSize}">${escapeHtml(tick.label)}</text>`;
  }).join("");

  return { grid: yGrid, labels: yLabels + xLabels, lines: axisLines };
}

function interpolateBtPointAtX(points, x) {
  if (!points || !points.length || x < points[0].x) return null;
  if (points.length === 1 || x >= points[points.length - 1].x) return points[points.length - 1];
  var low = 0, high = points.length - 1;
  while (low + 1 < high) {
    var mid = Math.floor((low + high) / 2);
    if (points[mid].x <= x) low = mid;
    else high = mid;
  }
  var left = points[low], right = points[high];
  var ratio = (x - left.x) / Math.max(0.000001, right.x - left.x);
  return {
    x: x,
    y: left.y + (right.y - left.y) * ratio,
    value: left.value + (right.value - left.value) * ratio,
    profit: left.profit + (right.profit - left.profit) * ratio,
    dateMs: left.dateMs + (right.dateMs - left.dateMs) * ratio,
  };
}

let _btCashflows = [];
let _btEquityByDate = {};
let _btPage = 1;
let _btPageSize = 20;

// Series visibility, shared by the advanced-panel checkboxes and the chart legend.
let _btVisibleSeries = { asset: true, invested: true, profit: true };
const BT_SERIES_NAMES = ["asset", "invested", "profit"];

function btSetSeriesVisible(name, visible) {
  const svgEl = $("btChart")?.querySelector("svg");
  const g = svgEl?.querySelector("#btSeries-" + name);
  if (g) g.style.display = visible ? "" : "none";
  const pulse = svgEl?.querySelector("#btPulse-" + name);
  if (pulse) pulse.style.display = visible ? "" : "none";
  const chip = document.querySelector('.bt-legend-chip[data-series="' + name + '"]');
  if (chip) chip.style.display = visible ? "" : "none";
  const cb = document.getElementById("btShow" + name.charAt(0).toUpperCase() + name.slice(1));
  if (cb) cb.checked = visible;
}

function btToggleSeries(name, visible) {
  if (!visible && BT_SERIES_NAMES.filter((n) => n !== name && _btVisibleSeries[n]).length === 0) {
    btSetSeriesVisible(name, true); // keep at least one series visible
    return;
  }
  _btVisibleSeries[name] = visible;
  btSetSeriesVisible(name, visible);
}

function formatBtMoney(value, signed) {
  const number = Number(value) || 0;
  let amount;
  try {
    amount = new Intl.NumberFormat(
      typeof __lang === "function" ? __lang() : undefined,
      {
        style: "currency",
        currency: _btCurrency,
        currencyDisplay: "narrowSymbol",
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }
    ).format(Math.abs(number));
  } catch (_) {
    amount = Math.abs(number).toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }) + " " + _btCurrency;
  }
  const sign = signed ? (number > 0 ? "+" : number < 0 ? "-" : "") : (number < 0 ? "-" : "");
  return `${sign}${amount}`;
}

function formatBtAxisMoney(value) {
  try {
    return new Intl.NumberFormat(
      typeof __lang === "function" ? __lang() : undefined,
      {
        style: "currency",
        currency: _btCurrency,
        currencyDisplay: "narrowSymbol",
        notation: "compact",
        maximumFractionDigits: 1,
      }
    ).format(Number(value) || 0);
  } catch (_) {
    return (Number(value) || 0).toLocaleString(undefined, {
      notation: "compact",
      maximumFractionDigits: 1,
    }) + " " + _btCurrency;
  }
}

function formatBtNumber(value, maximumFractionDigits) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return number.toLocaleString(
    typeof __lang === "function" ? __lang() : undefined,
    { minimumFractionDigits: 0, maximumFractionDigits }
  );
}

// Currency-free formatting: multi-currency compare must not show a single currency symbol.
function formatBtPlainNumber(value, digits) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  const d = digits == null ? 2 : digits;
  return number.toLocaleString(
    typeof __lang === "function" ? __lang() : undefined,
    { minimumFractionDigits: d, maximumFractionDigits: d }
  );
}

function formatBtPlainMoney(value) {
  return "$" + formatBtPlainAxis(value);
}

function formatBtPlainAxis(value) {
  const number = Number(value) || 0;
  return number.toLocaleString(
    typeof __lang === "function" ? __lang() : undefined,
    { notation: "compact", maximumFractionDigits: 1 }
  );
}

function renderBacktestCashflowPage() {
  const total = _btCashflows.length;
  const totalPages = Math.max(1, Math.ceil(total / _btPageSize));
  _btPage = Math.max(1, Math.min(_btPage, totalPages));
  const start = (_btPage - 1) * _btPageSize;
  const rows = _btCashflows.slice(start, start + _btPageSize);

  btBody.innerHTML = rows.map((row) => {
    const point = _btEquityByDate[row.date];
    const profit = point ? point.value - point.invested : null;
    const profitClass = profit == null ? "" : profit >= 0 ? "bt-val-positive" : "bt-val-negative";
    return `
      <tr>
        <td>${escapeHtml(row.date)}</td>
        <td>${__(row.kind === "initial" ? "backtest.kindInitial" : "backtest.kindRecurring")}</td>
        <td>${formatBtMoney(row.amount)}</td>
        <td>${formatBtMoney(row.price)}</td>
        <td>${formatBtNumber(row.units, 6)}</td>
        <td>${formatBtNumber(row.cum_units, 6)}</td>
        <td class="${profitClass}">${profit == null ? "—" : formatBtMoney(profit, true)}</td>
      </tr>
    `;
  }).join("");

  const detailCount = $("pcBtDetailCount");
  const pagination = $("pcBtPagination");
  const pageInfo = $("pcBtPageInfo");
  const pageSize = $("pcBtPageSize");
  const first = $("pcBtFirstPage");
  const prev = $("pcBtPrevPage");
  const next = $("pcBtNextPage");
  const last = $("pcBtLastPage");
  if (detailCount) detailCount.textContent = __("backtest.recordsCount", { total });
  if (pagination) pagination.style.display = total ? "flex" : "none";
  if (pageInfo) pageInfo.textContent = __("backtest.pageInfo", { page: _btPage, pages: totalPages, total });
  if (pageSize) pageSize.value = String(_btPageSize);
  if (first) first.disabled = _btPage <= 1;
  if (prev) prev.disabled = _btPage <= 1;
  if (next) next.disabled = _btPage >= totalPages;
  if (last) last.disabled = _btPage >= totalPages;
}

function updateBacktestFrequencyUI() {
  const mode = btFrequency?.value || "monthly";
  if (!btDayOfMonth || !btWeekday || !btDayOfMonthLabel || !btWeekdayLabel || !btInterval || !btAmount) return;

  if (mode === "once") {
    btInterval.style.display = "none";
    btDayOfMonth.style.display = "none";
    btDayOfMonthLabel.style.display = "none";
    btWeekday.style.display = "none";
    btWeekdayLabel.style.display = "none";
    const intervalLabel = btInterval.previousElementSibling;
    if (intervalLabel) intervalLabel.style.display = "none";
    btAmount.previousElementSibling && (btAmount.previousElementSibling.textContent = __("backtest.labelOnceInvest"));
    return;
  }

  if (mode === "yearly") {
    // yearly: interval is useful (every-N-years), but day-of-month/weekday are not
    const intervalLabel = btInterval.previousElementSibling;
    if (intervalLabel) intervalLabel.style.display = "";
    btInterval.style.display = "";
    btDayOfMonth.style.display = "none";
    btDayOfMonthLabel.style.display = "none";
    btWeekday.style.display = "none";
    btWeekdayLabel.style.display = "none";
    btAmount.previousElementSibling && (btAmount.previousElementSibling.textContent = __("backtest.labelPerTime"));
    return;
  }

  const intervalLabel = btInterval.previousElementSibling;
  if (intervalLabel) intervalLabel.style.display = "";
  btInterval.style.display = "";
  btAmount.previousElementSibling && (btAmount.previousElementSibling.textContent = __("backtest.labelPerTime"));

  if (mode === "daily") {
    btDayOfMonth.style.display = "none";
    btDayOfMonthLabel.style.display = "none";
    btWeekday.style.display = "none";
    btWeekdayLabel.style.display = "none";
    return;
  }

  if (mode === "weekly") {
    btDayOfMonth.style.display = "none";
    btDayOfMonthLabel.style.display = "none";
    btWeekday.style.display = "";
    btWeekdayLabel.style.display = "";
    btWeekdayLabel.textContent = __("backtest.labelWeekDay");
    return;
  }

  btDayOfMonth.style.display = "";
  btDayOfMonthLabel.style.display = "";
  btWeekday.style.display = "none";
  btWeekdayLabel.style.display = "none";
  btDayOfMonthLabel.textContent = __("backtest.labelMonthDay");
}

function populateBacktestOptions() {
  // Default the date range from yearly data when available.
  // The backtest symbol is a free-text input — no dependency on presets.
  if (_lastYearlyData && _lastYearlyData.years) {
    const sortedYears = [..._lastYearlyData.years].map(Number).sort((a, b) => a - b);
    const firstYear = sortedYears[0];
    const lastYear = sortedYears[sortedYears.length - 1];
    if (firstYear && btStartDate && !btStartDate.value) btStartDate.value = `${firstYear}-01-01`;
    if (lastYear && btEndDate && !btEndDate.value) btEndDate.value = `${lastYear}-12-31`;
  }
}

function showBacktestLoading() {
  if (btResult) btResult.style.display = "";
  if (btWrap) btWrap.style.display = "";
  const loading = $("btLoading");
  if (loading) loading.style.display = "flex";
  ["btLiveData", "btChart", "pcBtSummary"].forEach((id) => {
    const el = $(id);
    if (el) el.style.display = "none";
  });
}

function hideBacktestLoading() {
  const loading = $("btLoading");
  if (loading) loading.style.display = "none";
  ["btLiveData", "btChart", "pcBtSummary"].forEach((id) => {
    const el = $(id);
    if (el) el.style.display = "";
  });
}

// Backtest-scoped error box. The shared #pcError lives inside the hidden
// #tab-yearly panel when the backtest tab is active, so backtest errors
// (including compare/record) must render here to be visible at all.
function btError(msg) {
  const el = $("btError");
  if (!el) return;
  el.style.display = msg ? "block" : "none";
  if (msg) el.innerHTML = escapeHtml(msg);
}

async function runBacktest() {
  const assetType = btTypeSelect?.value || "stock";
  const symbol = normalizeAssetSymbol(btSymbolInput?.value || "", assetType);
  if (btSymbolInput) btSymbolInput.value = symbol;
  if (!symbol) {
    btError(__("backtest.errorNoSymbol"));
    return;
  }
  saveBacktestSymbol(symbol, assetType);

  const payload = {
    symbol,
    type: assetType,
    initial_amount: parseFloat(btInitialAmount?.value) || 0,
    amount: parseFloat(btAmount?.value) || 0,
    start_date: btStartDate?.value,
    end_date: btEndDate?.value,
    frequency: btFrequency?.value || "monthly",
    interval: parseInt(btInterval?.value, 10) || 1,
    day_of_month: parseInt(btDayOfMonth?.value, 10) || 1,
    weekday: parseInt(btWeekday?.value, 10) || 0,
  };

  btError(null);
  try {
    showBacktestLoading();
    const resp = await fetch(BACKTEST_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await resp.json();
    if (!resp.ok) throw new Error(result.error || `HTTP ${resp.status}`);
    hideBacktestLoading();
    renderBacktestResult(symbol, result);
    if (typeof gahHistoryRecord === "function") {
      gahHistoryRecord("gah_backtest_history", { symbol: symbol, name: "", type: assetType });
    }
  } catch (e) {
    hideBacktestLoading();
    btError(__("backtest.errorBacktest") + e.message);
  }
}

// Catmull-Rom -> cubic Bezier smoothing: one flowing path, no jagged segments.
function smoothPath(points) {
  if (!points.length) return "";
  let d = `M ${points[0].x} ${points[0].y}`;
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i - 1] || points[i];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[i + 2] || p2;
    const cp1x = p1.x + (p2.x - p0.x) / 6;
    const cp1y = p1.y + (p2.y - p0.y) / 6;
    const cp2x = p2.x - (p3.x - p1.x) / 6;
    const cp2y = p2.y - (p3.y - p1.y) / 6;
    d += ` C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${p2.x} ${p2.y}`;
  }
  return d;
}

function renderBtChart(equityCurve) {
  if (!equityCurve || equityCurve.length === 0) return;
  const c = getChartColors();
  const sampledCurve = sampleEvenly(equityCurve, getBacktestSampleSize());

  // Live header row: currency, date range, and the three amounts that roll up with the reveal.
  const liveEl = document.getElementById("btLiveData");
  const lastRow = sampledCurve[sampledCurve.length - 1];
  const liveTarget = lastRow ? {
    value: lastRow.value,
    invested: lastRow.invested,
    profit: lastRow.value - lastRow.invested,
  } : null;
  if (liveEl) {
    if (!liveTarget) {
      liveEl.innerHTML = "";
    } else {
      const profitClass = liveTarget.profit >= 0 ? "bt-val-positive" : "bt-val-negative";
      // Legend chips sit in the same row as the live data, vertically centered.
      liveEl.innerHTML = `
        <span class="bt-live-legend">
          <button class="bt-legend-chip" type="button" data-series="asset"><span class="bt-legend-swatch" style="background:#2997ff"></span>${__("backtest.totalAssets")}</button>
          <button class="bt-legend-chip" type="button" data-series="invested"><span class="bt-legend-swatch" style="background:${c.invested}"></span>${__("backtest.totalInvested")}</button>
          <button class="bt-legend-chip" type="button" data-series="profit"><span class="bt-legend-swatch" style="background:${c.positiveAlpha88}"></span>${__("backtest.totalReturn")}</button>
        </span>
        <span class="bt-live-static">${escapeHtml(btSymbolInput?.value || _btCurrency)}</span>
        <span class="bt-live-range">${escapeHtml(sampledCurve[0].date)} ~ ${escapeHtml(lastRow.date)}</span>
        <span class="bt-live-item"><span class="bt-live-label">${__("backtest.totalAssets")}</span><b id="btLiveAsset" class="bt-live-val">${formatBtMoney(0)}</b></span>
        <span class="bt-live-item"><span class="bt-live-label">${__("backtest.totalInvested")}</span><b id="btLiveInvested" class="bt-live-val">${formatBtMoney(0)}</b></span>
        <span class="bt-live-item"><span class="bt-live-label">${__("backtest.totalReturn")}</span><b id="btLiveProfit" class="bt-live-val ${profitClass}">${formatBtMoney(0, true)}</b></span>
      `;
      liveEl.querySelectorAll(".bt-legend-chip").forEach((chip) => {
        const series = chip.dataset.series;
        if (_btVisibleSeries[series] === false) chip.style.display = "none";
        chip.addEventListener("click", () => btToggleSeries(series, _btVisibleSeries[series] === false));
      });
    }
  }

  // All three series share one left Y-axis (amounts); the right axis is removed.
  // Geometry and axis styling intentionally match the compare chart.
  const W = 700, H = 240;
  // One shared axis must cover all three series. Using only total assets clips
  // negative profit and produces a misleading synthetic bottom tick.
  const axisVals = sampledCurve.flatMap((row) => [row.value, row.invested, row.value - row.invested]);
  const minAssetVal = Math.min(...axisVals);
  const maxAssetVal = Math.max(...axisVals);
  const assetRange = maxAssetVal - minAssetVal || 1;
  const assetPad = assetRange * 0.03;
  const assetYMin = minAssetVal - assetPad;
  const assetYMax = maxAssetVal + assetPad;
  const assetYRange = assetYMax - assetYMin;
  const yTickCount = 4;
  const yValues = Array.from({ length: yTickCount + 1 }, (_, i) => assetYMin + (assetYRange * i) / yTickCount);
  const yLabels = yValues.map(formatBtAxisMoney);
  const PAD = buildBtChartPadding(yLabels, BT_AXIS_FONT, false);
  const cw = W - PAD.left - PAD.right;
  const ch = H - PAD.top - PAD.bottom;
  const dateValues = sampledCurve.map((row) => btDateMs(row.date)).filter(Number.isFinite);
  const minDateMs = Math.min(...dateValues);
  const maxDateMs = Math.max(...dateValues);
  const dateRangeMs = maxDateMs - minDateMs || 1;
  const xPosMs = (ms) => PAD.left + ((ms - minDateMs) / dateRangeMs) * cw;
  const assetYPos = (v) => PAD.top + ch - ((v - assetYMin) / assetYRange) * ch;
  const axes = buildBtAxes({
    W: W, H: H, PAD: PAD, yValues: yValues, yPos: assetYPos,
    formatY: formatBtAxisMoney,
    xTicks: buildBtDateTicks(minDateMs, maxDateMs, 6), xPosMs: xPosMs,
    fontSize: BT_AXIS_FONT,
    gridColor: "var(--apple-divider)",
    axisColor: "var(--apple-text-tertiary)",
    labelColor: "var(--apple-text-tertiary)",
  });

  const zeroY = assetYPos(0);
  const zeroLine = (zeroY >= PAD.top && zeroY <= H - PAD.bottom)
    ? `<line x1="${PAD.left}" y1="${zeroY}" x2="${W - PAD.right}" y2="${zeroY}" stroke="var(--apple-text-tertiary)" stroke-width="1" stroke-dasharray="4,3" opacity="0.6"/>`
    : "";

  const assetPoints = [];
  const investedPoints = [];
  const profitPoints = [];
  sampledCurve.forEach((row) => {
    const x = xPosMs(btDateMs(row.date));
    assetPoints.push({ x: x, y: assetYPos(row.value) });
    investedPoints.push({ x: x, y: assetYPos(row.invested) });
    profitPoints.push({ x: x, y: assetYPos(row.value - row.invested) });
  });

  const assetCurveD = smoothPath(assetPoints);
  const investedCurveD = smoothPath(investedPoints);
  const profitCurveD = smoothPath(profitPoints);
  // Gradient fill under the total-assets curve, down to the x-axis (plot bottom).
  const assetBottomY = PAD.top + ch;
  const firstX = assetPoints.length ? assetPoints[0].x : 0;
  const lastX = assetPoints.length ? assetPoints[assetPoints.length - 1].x : 0;
  const assetFill = assetPoints.length
    ? `${assetCurveD} L ${lastX} ${assetBottomY} L ${firstX} ${assetBottomY} Z`
    : "";
  const assetPath = assetPoints.length
    ? `<path d="${assetCurveD}" fill="none" stroke="#2997ff" stroke-width="${BT_PRIMARY_LINE_STROKE}" stroke-linecap="round" opacity="0.95"/>`
    : "";
  const investedPath = investedPoints.length
    ? `<path d="${investedCurveD}" fill="none" stroke="${c.invested}" stroke-width="${BT_SECONDARY_LINE_STROKE}" stroke-linecap="round" opacity="0.9"/>`
    : "";
  const profitPath = profitPoints.length
    ? `<path d="${profitCurveD}" fill="none" stroke="${c.positiveAlpha88}" stroke-width="${BT_SECONDARY_LINE_STROKE}" stroke-linecap="round"/>`
    : "";

  const hoverZones = sampledCurve.map((row, idx) => {
    const profit = row.value - row.invested;
    return `<rect
      class="bt-hover-zone"
      data-date="${row.date}"
      data-value="${row.value}"
      data-invested="${row.invested}"
      data-profit="${profit}"
      x="${Math.max(PAD.left, xPosMs(btDateMs(row.date)) - 8)}"
      y="${PAD.top}"
      width="16"
      height="${ch}"
      fill="transparent"
      style="cursor:crosshair;"
    />`;
  }).join("");

  const tooltip = `
    <g id="btTooltip" style="display:none;pointer-events:none;">
      <line id="btTooltipGuide" x1="0" y1="${PAD.top}" x2="0" y2="${PAD.top + ch}" stroke="${c.guide}" stroke-width="1" stroke-dasharray="4,3"/>
      <rect id="btTooltipBg" x="0" y="0" width="168" height="88" rx="8" fill="${c.tooltipBg}" stroke="${c.tooltipBorder}"/>
      <text id="btTooltipDate" x="10" y="16" fill="${c.tooltipText}" font-size="11"></text>
      <text id="btTooltipAsset" x="10" y="32" fill="#2997ff" font-size="11"></text>
      <text id="btTooltipInvested" x="10" y="48" fill="var(--apple-text-secondary)" font-size="11"></text>
      <text id="btTooltipProfit" x="10" y="64" fill="${c.positive}" font-size="11"></text>
      <text id="btTooltipReturn" x="10" y="80" fill="${c.tooltipText}" font-size="11"></text>
    </g>
  `;

  const seriesStyle = (name) => (_btVisibleSeries[name] !== false ? "" : ' style="display:none"');
  // Solid pulsing dot on the latest point of each series (breathing via SMIL).
  // Rendered in a layer OUTSIDE the reveal clip so it is visible during the reveal animation.
  const pulseDot = (pts, color, dotId) => {
    const last = pts[pts.length - 1];
    return last
      ? `<circle id="${dotId}" cx="${last.x}" cy="${last.y}" r="3.2" fill="${color}" stroke="var(--apple-bg)" stroke-width="1.5"><animate attributeName="r" values="3.2;5.4;3.2" dur="1.6s" repeatCount="indefinite"/><animate attributeName="opacity" values="1;0.5;1" dur="1.6s" repeatCount="indefinite"/></circle>`
      : "";
  };
  const pulseLayer = `
    <g id="btPulseLayer">
      <g id="btPulse-asset"${seriesStyle("asset")}>${pulseDot(assetPoints, "#2997ff", "btPulseDot-asset")}</g>
      <g id="btPulse-invested"${seriesStyle("invested")}>${pulseDot(investedPoints, c.invested, "btPulseDot-invested")}</g>
      <g id="btPulse-profit"${seriesStyle("profit")}>${pulseDot(profitPoints, c.positiveAlpha88, "btPulseDot-profit")}</g>
    </g>
  `;
  const svgH = H;
  const animatedLayer = `
    <g id="btAnimatedLayer" clip-path="url(#btChartReveal)">
      <g id="btSeries-asset"${seriesStyle("asset")}>
        <path d="${assetFill}" fill="url(#btAssetGrad)" stroke="none"/>
        ${assetPath}
      </g>
      <g id="btSeries-invested"${seriesStyle("invested")}>
        ${investedPath}
      </g>
      <g id="btSeries-profit"${seriesStyle("profit")}>
        ${profitPath}
      </g>
    </g>
  `;
  $("btChart").innerHTML = `<svg viewBox="0 0 ${W} ${svgH}" style="width:100%;height:auto;display:block;">
    <defs>
      <clipPath id="btChartReveal">
        <rect id="btChartRevealRect" x="0" y="0" width="0" height="${H}"></rect>
      </clipPath>
      <linearGradient id="btAssetGrad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#2997ff" stop-opacity="0.28"/>
        <stop offset="100%" stop-color="#2997ff" stop-opacity="0"/>
      </linearGradient>
    </defs>
    ${axes.grid} ${axes.lines} ${zeroLine} ${animatedLayer} ${pulseLayer} ${axes.labels}
    ${buildBtBrandSvg(W, H, PAD, "var(--apple-text-tertiary)")}
    ${hoverZones} ${tooltip}
  </svg>`;

  const svgEl = $("btChart").querySelector("svg");
  const revealRect = svgEl?.querySelector("#btChartRevealRect");
  const tooltipEl = svgEl?.querySelector("#btTooltip");
  const tooltipGuide = svgEl?.querySelector("#btTooltipGuide");
  const tooltipBg = svgEl?.querySelector("#btTooltipBg");
  const tooltipDate = svgEl?.querySelector("#btTooltipDate");
  const tooltipAsset = svgEl?.querySelector("#btTooltipAsset");
  const tooltipInvested = svgEl?.querySelector("#btTooltipInvested");
  const tooltipProfit = svgEl?.querySelector("#btTooltipProfit");
  const tooltipReturn = svgEl?.querySelector("#btTooltipReturn");

  svgEl?.querySelectorAll(".bt-hover-zone").forEach((zone) => {
    zone.addEventListener("mouseenter", () => {
      const x = parseFloat(zone.getAttribute("x") || "0");
      const value = parseFloat(zone.dataset.value || "0");
      const invested = parseFloat(zone.dataset.invested || "0");
      const profit = parseFloat(zone.dataset.profit || "0");
      const returnPct = invested === 0 ? 0 : (profit / invested) * 100;
      const tooltipX = Math.min(Math.max(x + 10, PAD.left), W - PAD.right - 160);
      const tooltipY = PAD.top + 8;
      if (tooltipEl) tooltipEl.setAttribute("transform", `translate(${tooltipX}, ${tooltipY})`);
      if (tooltipGuide) {
        const guideX = x + 8;
        tooltipGuide.setAttribute("x1", String(guideX));
        tooltipGuide.setAttribute("x2", String(guideX));
      }
      if (tooltipDate) tooltipDate.textContent = zone.dataset.date || "";
      if (tooltipAsset) tooltipAsset.textContent = __("backtest.totalAssets") + ": " + formatBtMoney(value);
      if (tooltipInvested) tooltipInvested.textContent = __("backtest.totalInvested") + ": " + formatBtMoney(invested);
      if (tooltipProfit) {
        tooltipProfit.textContent = __("backtest.totalReturn") + ": " + formatBtMoney(profit, true);
        tooltipProfit.setAttribute("fill", profit >= 0 ? c.positive : c.negative);
      }
      if (tooltipReturn) tooltipReturn.textContent = __("backtest.returnRate") + " " + (returnPct >= 0 ? "+" : "") + returnPct.toFixed(2) + "%";
      if (tooltipBg) tooltipBg.setAttribute("height", "88");
      if (tooltipEl) tooltipEl.style.display = "";
    });
    zone.addEventListener("mouseleave", () => {
      if (tooltipEl) tooltipEl.style.display = "none";
    });
  });

  const durationMs = getBacktestAnimMs();
  const setLive = (progress) => {
    if (!liveTarget) return;
    const assetEl = document.getElementById("btLiveAsset");
    const investedEl = document.getElementById("btLiveInvested");
    const profitEl = document.getElementById("btLiveProfit");
    if (assetEl) assetEl.textContent = formatBtMoney(liveTarget.value * progress);
    if (investedEl) investedEl.textContent = formatBtMoney(liveTarget.invested * progress);
    if (profitEl) profitEl.textContent = formatBtMoney(liveTarget.profit * progress, true);
  };
  // Ride the pulsing dots on the reveal frontier, smoothly interpolated along the curves.
  const movePulse = (progress) => {
    const revealX = W * progress;
    const x = Math.max(PAD.left, Math.min(PAD.left + cw, revealX));
    const place = (dotId, pts) => {
      const el = document.getElementById(dotId);
      if (!el || pts.length < 2) return;
      const span = pts[pts.length - 1].x - pts[0].x || 1;
      const f = ((x - pts[0].x) / span) * (pts.length - 1);
      const i0 = Math.max(0, Math.min(pts.length - 2, Math.floor(f)));
      const frac = f - i0;
      const y = pts[i0].y + (pts[i0 + 1].y - pts[i0].y) * frac;
      el.setAttribute("cx", x);
      el.setAttribute("cy", y);
    };
    place("btPulseDot-asset", assetPoints);
    place("btPulseDot-invested", investedPoints);
    place("btPulseDot-profit", profitPoints);
  };
  if (revealRect) {
    if (durationMs <= 0) {
      revealRect.setAttribute("width", String(W));
      setLive(1);
      movePulse(1);
    } else {
      revealRect.setAttribute("width", "0");
      const start = performance.now();
      const tick = (now) => {
        const progress = Math.max(0, Math.min((now - start) / durationMs, 1));
        // Linear: curve, live numbers, and dots move at one steady pace and finish together.
        revealRect.setAttribute("width", String(W * progress));
        setLive(progress);
        movePulse(progress);
        if (progress < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    }
  }
}

// Count-up animation for the summary values, synced with the chart reveal duration.
const BT_ANIM_FORMATTERS = {
  money: (v) => formatBtMoney(v),
  moneySigned: (v) => formatBtMoney(v, true),
  pct: (v) => (v >= 0 ? "+" : "") + v.toFixed(2) + "%",
  int: (v) => formatBtNumber(Math.round(v), 0),
};

function animateBtSummary(durationMs) {
  const vals = btSummary.querySelectorAll("[data-anim]");
  if (!vals.length) return;
  const targets = Array.from(vals, (el) => Number(el.dataset.value) || 0);
  const format = (el, v) => BT_ANIM_FORMATTERS[el.dataset.anim](v);
  if (durationMs <= 0) {
    vals.forEach((el, i) => { el.textContent = format(el, targets[i]); });
    return;
  }
  const start = performance.now();
  const tick = (now) => {
    const progress = Math.min((now - start) / durationMs, 1);
    const eased = 1 - Math.pow(1 - progress, 3); // easeOutCubic decelerating roll
    vals.forEach((el, i) => { el.textContent = format(el, targets[i] * eased); });
    if (progress < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

function renderBacktestResult(symbol, result) {
  syncBacktestCurrency(result.type, result.currency);
  const summary = result.summary || {};
  renderBtChart(result.equity_curve || []);
  const profit = Number(summary.profit) || 0;
  const returnPct = Number(summary.return_pct) || 0;
  const annualizedReturnPct = Number(summary.annualized_return_pct) || 0;
  _btCashflows = result.cashflows || [];
  _btEquityByDate = Object.fromEntries((result.equity_curve || []).map((row) => [row.date, row]));
  _btPage = 1;

  const animFinal = Number(summary.final_value) || 0;
  const animInvested = Number(summary.invested) || 0;
  const animTradeCount = Number(summary.trade_count) || 0;
  btSummary.innerHTML = `
    <div class="pc-bt-summary-item">
      <div class="pc-bt-summary-label">${__("backtest.finalAssets")}</div>
      <div class="pc-bt-summary-val ${profit >= 0 ? "bt-val-positive" : "bt-val-negative"}" data-anim="money" data-value="${animFinal}">${formatBtMoney(animFinal)}</div>
      <div class="pc-bt-summary-note">${__("backtest.finalAssetsNote", { symbol: escapeHtml(symbol) })}</div>
    </div>
    <div class="pc-bt-summary-item">
      <div class="pc-bt-summary-label">${__("backtest.totalInvested")}</div>
      <div class="pc-bt-summary-val" data-anim="money" data-value="${animInvested}">${formatBtMoney(animInvested)}</div>
      <div class="pc-bt-summary-note">${__("backtest.totalInvestedNote")}</div>
    </div>
    <div class="pc-bt-summary-item">
      <div class="pc-bt-summary-label">${__("backtest.profitAmount")}</div>
      <div class="pc-bt-summary-val ${profit >= 0 ? "bt-val-positive" : "bt-val-negative"}" data-anim="moneySigned" data-value="${profit}">${formatBtMoney(profit, true)}</div>
      <div class="pc-bt-summary-note">${__("backtest.profitAmountNote")}</div>
    </div>
    <div class="pc-bt-summary-item">
      <div class="pc-bt-summary-label">${__("backtest.totalReturnRate")}</div>
      <div class="pc-bt-summary-val ${returnPct >= 0 ? "bt-val-positive" : "bt-val-negative"}" data-anim="pct" data-value="${returnPct}">${returnPct >= 0 ? "+" : ""}${returnPct.toFixed(2)}%</div>
      <div class="pc-bt-summary-note">${__("backtest.totalReturnRateNote")}</div>
    </div>
    <div class="pc-bt-summary-item">
      <div class="pc-bt-summary-label has-tip" title="${__("backtest.irrTooltip")}">${__("backtest.irrAnnualized")}</div>
      <div class="pc-bt-summary-val ${annualizedReturnPct >= 0 ? "bt-val-positive" : "bt-val-negative"}" data-anim="pct" data-value="${annualizedReturnPct}">${annualizedReturnPct >= 0 ? "+" : ""}${annualizedReturnPct.toFixed(2)}%</div>
      <div class="pc-bt-summary-note">${__("backtest.irrNote")}</div>
    </div>
    <div class="pc-bt-summary-item">
      <div class="pc-bt-summary-label">${__("backtest.tradeCount")}</div>
      <div class="pc-bt-summary-val" data-anim="int" data-value="${animTradeCount}">${formatBtNumber(animTradeCount, 0)}</div>
      <div class="pc-bt-summary-note">${__("backtest.tradeCountNote")}</div>
    </div>
  `;
  animateBtSummary(getBacktestAnimMs());

  btHead.innerHTML = "<th>" + __("backtest.colDate") + "</th><th>" + __("backtest.colKind") + "</th><th>" + __("backtest.colAmount") + "</th><th>" + __("backtest.colPrice") + "</th><th>" + __("backtest.colShares") + "</th><th>" + __("backtest.colCumShares") + "</th><th>" + __("backtest.colTotalReturn") + "</th>";
  renderBacktestCashflowPage();

  if (btResult) btResult.style.display = "";
  if (btWrap) btWrap.style.display = "";
}

// ─── Advanced toggle ───
(function () {
  var advCheckbox = document.getElementById("pcBtAdvanced");
  if (!advCheckbox) return;
  advCheckbox.addEventListener("change", function () {
    var show = this.checked;
    document.querySelectorAll(".pc-bt-advanced").forEach(function (el) {
      if (show) {
        el.classList.add("show");
      } else {
        el.classList.remove("show");
      }
    });
  });
})();

// ─── Series visibility checkboxes (advanced panel) ───
(function () {
  [["asset", "btShowAsset"], ["invested", "btShowInvested"], ["profit", "btShowProfit"]].forEach((pair) => {
    const cb = document.getElementById(pair[1]);
    if (cb) cb.addEventListener("change", () => btToggleSeries(pair[0], cb.checked));
  });
})();

// ─── Detail pagination ───
(function () {
  var pageSize = $("pcBtPageSize");
  var first = $("pcBtFirstPage");
  var prev = $("pcBtPrevPage");
  var next = $("pcBtNextPage");
  var last = $("pcBtLastPage");
  if (pageSize) pageSize.addEventListener("change", function () {
    _btPageSize = parseInt(pageSize.value, 10) || 20;
    _btPage = 1;
    renderBacktestCashflowPage();
  });
  if (first) first.addEventListener("click", function () {
    _btPage = 1;
    renderBacktestCashflowPage();
  });
  if (prev) prev.addEventListener("click", function () {
    _btPage -= 1;
    renderBacktestCashflowPage();
  });
  if (next) next.addEventListener("click", function () {
    _btPage += 1;
    renderBacktestCashflowPage();
  });
  if (last) last.addEventListener("click", function () {
    _btPage = Math.max(1, Math.ceil(_btCashflows.length / _btPageSize));
    renderBacktestCashflowPage();
  });
})();

// ─── Backtest Compare (secondary tab) ───────────────────────────────

// Sub-tab switching: 回测详情 / 回测对比.
(function () {
  var tabs = document.querySelectorAll("#btSubTabs .transfer-tab");
  if (!tabs.length) return;
  function selectBtSubTab(sub) {
    var detail = $("btTabDetail");
    var compare = $("btTabCompare");
    if (detail) detail.style.display = sub === "detail" ? "" : "none";
    if (compare) compare.style.display = sub === "compare" ? "" : "none";
    document.querySelectorAll(".bt-action-detail").forEach(function (e) { e.style.display = sub === "detail" ? "" : "none"; });
    document.querySelectorAll(".bt-action-compare").forEach(function (e) { e.style.display = sub === "compare" ? "inline-flex" : "none"; });
    tabs.forEach(function (btn) {
      var on = btn.dataset.btTab === sub;
      btn.classList.toggle("active", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });
  }
  tabs.forEach(function (btn) {
    btn.addEventListener("click", function () {
      selectBtSubTab(btn.dataset.btTab === "compare" ? "compare" : "detail");
    });
  });
})();

// Compare symbol rows.
function initComparePanel() {
  var container = $("pcBtCompareSymbols");
  if (!container) return;
  var addBtn = $("pcBtCompareAdd");
  var runBtn = $("pcBtCompareRun");

  function typeOptions() {
    return [
      ["stock", "yearly.assetTypeStock"],
      ["hk_stock", "yearly.assetTypeHkStock"],
      ["global_stock", "yearly.assetTypeGlobalStock"],
      ["crypto", "yearly.assetTypeCrypto"],
      ["cn_stock", "yearly.assetTypeCnStock"],
    ].map(function (item) {
      return `<option value="${item[0]}">${__(item[1])}</option>`;
    }).join("");
  }

  function bindRow(div) {
    div.querySelector(".cmp-del").addEventListener("click", function () { div.remove(); });
    // Reuse the detail tab's autocomplete. price-change.js exposes it from its
    // DOMContentLoaded init; if this row is created before that, wait for the ready event.
    var sym = div.querySelector(".cmp-sym");
    var typeSel = div.querySelector(".cmp-type");
    function bindAc() { if (typeof window.attachAutocomplete === "function") window.attachAutocomplete(sym, typeSel); }
    if (typeof window.attachAutocomplete === "function") bindAc();
    else window.addEventListener("gah-autocomplete-ready", bindAc, { once: true });
  }

  function addRow(symbol) {
    var div = document.createElement("div");
    div.className = "pc-bt-compare-row";
    div.innerHTML = `
      <input type="text" class="pc-bt-input cmp-sym" placeholder="QQQ" maxlength="30" style="width:120px;text-transform:uppercase;">
      <select class="pc-bt-input cmp-type" style="width:110px;">${typeOptions()}</select>
      <button type="button" class="pc-btn pc-btn-sm cmp-del">${__("backtest.compareRemove")}</button>
    `;
    container.appendChild(div);
    bindRow(div);
    if (symbol) div.querySelector(".cmp-sym").value = symbol;
    return div;
  }

  ["QQQ", "SMH", "GOOGL"].forEach(function (s) { addRow(s); });

  if (addBtn) addBtn.addEventListener("click", function () { addRow(); });
  if (runBtn) runBtn.addEventListener("click", runBacktestCompare);

  // Orientation switch re-renders the chart (and, on record, the video) in the
  // selected aspect, keeping the recording in sync with what is on screen.
  var orientSel = $("pcBtCompareOrientation");
  if (orientSel) {
    orientSel.addEventListener("change", function () {
      _btCompareOrientation = orientSel.value;
      if (_btCompareLastInputs) {
        renderBtCompareChart(_btCompareLastInputs.series, _btCompareLastInputs.context);
      }
    });
  }
}
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initComparePanel);
} else {
  initComparePanel();
}

function readCompareRows() {
  var container = $("pcBtCompareSymbols");
  if (!container) return [];
  return Array.from(container.querySelectorAll(".pc-bt-compare-row")).map(function (row) {
    return {
      symbol: (row.querySelector(".cmp-sym")?.value || "").trim(),
      type: row.querySelector(".cmp-type")?.value || "stock",
    };
  });
}

async function runBacktestCompare() {
  var rows = readCompareRows().filter(function (r) { return normalizeAssetSymbol(r.symbol, r.type); });
  if (!rows.length) { btError(__("backtest.compareNoSymbols")); return; }
  var lump = parseFloat($("pcBtCompareAmount")?.value) || 0;
  if (lump <= 0) { btError(__("backtest.compareAmountInvalid")); return; }
  btError(null);
  var start = $("pcBtCompareStart")?.value || "";
  // Local today (toISOString would shift a day in some time zones).
  var now = new Date();
  var end = now.getFullYear() + "-" + String(now.getMonth() + 1).padStart(2, "0") + "-" + String(now.getDate()).padStart(2, "0");
  var metric = $("pcBtCompareMetric")?.value || "value";
  var loading = $("btCompareLoading");
  if (loading) loading.style.display = "flex";
  try {
    var results = await Promise.all(rows.map(async function (row) {
      var symbol = normalizeAssetSymbol(row.symbol, row.type);
      var resp = await fetch(BACKTEST_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: symbol, type: row.type, initial_amount: lump, amount: 0,
          start_date: start, end_date: end,
          frequency: "once",
        }),
      });
      var data = await resp.json();
      if (!resp.ok) throw new Error(data.error || "HTTP " + resp.status);
      return { symbol: symbol, type: row.type, data: data };
    }));
    if (loading) loading.style.display = "none";
    renderCompareResults(results, metric, lump, start);
  } catch (e) {
    if (loading) loading.style.display = "none";
    btError(__("backtest.errorBacktest") + e.message);
  }
}

var BT_COMPARE_COLORS = ["#2997ff", "#ff9f0a", "#30d158", "#ff375f", "#bf5af2", "#ffd60a", "#64d2ff", "#ac8e68"];

// Centered brand watermark, shared by the on-page chart and the recorded video.
var BT_BRAND_TEXT = "https://qqq.tools24.uk";

function buildBtBrandSvg(W, H, PAD, color) {
  var cx = PAD.left + (W - PAD.left - PAD.right) / 2;
  var cy = PAD.top + (H - PAD.top - PAD.bottom) / 2;
  return `<text x="${cx}" y="${cy}" text-anchor="middle" dominant-baseline="central" font-size="11" fill="${color}" opacity="0.4" style="pointer-events:none;">${escapeHtml(BT_BRAND_TEXT)}</text>`;
}

// Snapshot of the last compare render, so the video recorder can replay the
// exact chart + legend animation offscreen (see recordCompareVideo).
var _btCompareLast = null;
// Current compare orientation; drives both the on-page chart geometry and the
// recorded video, so the two stay in sync. The params-panel selector sets it.
var _btCompareOrientation = "landscape";
// Last compare inputs, kept so switching orientation can re-render the chart.
var _btCompareLastInputs = null;

function renderCompareResults(results, metric, lump, start) {
  var maxPts = getBacktestSampleSize();
  var series = results.map(function (r, i) {
    var curve = r.data.equity_curve || [];
    var sampled = sampleEvenly(curve, maxPts);
    var points = sampled.map(function (p) {
      return { date: p.date, value: p.value, profit: p.value - p.invested };
    });
    return {
      symbol: r.symbol,
      color: BT_COMPARE_COLORS[i % BT_COMPARE_COLORS.length],
      points: points,
    };
  });
  renderBtCompareChart(series, { lump: lump, start: start, metric: metric });
  _btCompareLastInputs = { series: series, context: { lump: lump, start: start, metric: metric } };
}

function renderBtCompareChart(series, context) {
  var chartEl = $("btCompareChart");
  if (!chartEl || !series.length) return;
  var c = getChartColors();
  var isProfit = context && context.metric === "profit";
  var valOf = function (p) { return isProfit ? p.profit : p.value; };
  // Portrait is a compact share preview, not a vertically stretched landscape
  // plot. Both orientations use the same visual tokens and real date scale.
  var portrait = _btCompareOrientation === "portrait";
  var W = portrait ? 360 : 700;
  var H = portrait ? 440 : 280;
  var axisFont = portrait ? 12 : BT_AXIS_FONT;
  var allVals = [];
  series.forEach(function (s) { s.points.forEach(function (p) { allVals.push(valOf(p)); }); });
  // Total-assets comparison should scale to the actual data range. Forcing zero
  // onto the axis creates a large empty band below one-time-investment curves.
  var domainVals = isProfit ? allVals.concat([0]) : allVals;
  var minV = Math.min.apply(null, domainVals);
  var maxV = Math.max.apply(null, domainVals);
  var range = maxV - minV || 1;
  var pad = range * 0.03;
  var yMin = minV - pad, yMax = maxV + pad, yRng = yMax - yMin;
  var yTickCount = 4;
  var yValues = Array.from({ length: yTickCount + 1 }, function (_, i) { return yMin + (yRng * i) / yTickCount; });
  var yLabels = yValues.map(formatBtPlainAxis);
  var PAD = buildBtChartPadding(yLabels, axisFont, portrait);
  var cw = W - PAD.left - PAD.right;
  var ch = H - PAD.top - PAD.bottom;
  var allDateValues = [];
  series.forEach(function (s) {
    s.points.forEach(function (p) {
      var ms = btDateMs(p.date);
      if (Number.isFinite(ms)) allDateValues.push(ms);
    });
  });
  var minDateMs = Math.min.apply(null, allDateValues);
  var maxDateMs = Math.max.apply(null, allDateValues);
  var dateRangeMs = maxDateMs - minDateMs || 1;
  var xPosMs = function (ms) { return PAD.left + ((ms - minDateMs) / dateRangeMs) * cw; };
  var yPos = function (v) { return PAD.top + ch - ((v - yMin) / yRng) * ch; };

  var built = series.map(function (s) {
    var pts = s.points.map(function (p) {
      var dateMs = btDateMs(p.date);
      return { x: xPosMs(dateMs), y: yPos(valOf(p)), value: p.value, profit: p.profit, dateMs: dateMs };
    }).filter(function (p) { return Number.isFinite(p.dateMs); }).sort(function (a, b) { return a.dateMs - b.dateMs; });
    var last = s.points[s.points.length - 1];
    return { symbol: s.symbol, color: s.color, pts: pts, finalValue: last ? valOf(last) : 0, finalProfit: last ? last.profit : 0 };
  });

  var axes = buildBtAxes({
    W: W, H: H, PAD: PAD, yValues: yValues, yPos: yPos,
    formatY: formatBtPlainAxis,
    xTicks: buildBtDateTicks(minDateMs, maxDateMs, portrait ? 5 : 6), xPosMs: xPosMs,
    fontSize: axisFont,
    gridColor: "var(--apple-divider)",
    axisColor: "var(--apple-text-tertiary)",
    labelColor: "var(--apple-text-tertiary)",
  });

  var lineStroke = BT_PRIMARY_LINE_STROKE;
  var lines = built.map(function (b) {
    return `<path d="${smoothPath(b.pts)}" fill="none" stroke="${b.color}" stroke-width="${lineStroke}" stroke-linecap="round" opacity="0.95"/>`;
  }).join("");

  var dots = built.map(function (b, i) {
    var last = b.pts[b.pts.length - 1];
    if (!last) return "";
    return `<circle id="btCmpDot-${i}" cx="${last.x}" cy="${last.y}" r="3.2" fill="${b.color}" stroke="var(--apple-bg)" stroke-width="1.5" style="display:none"><animate attributeName="r" values="3.2;5.4;3.2" dur="1.6s" repeatCount="indefinite"/><animate attributeName="opacity" values="1;0.5;1" dur="1.6s" repeatCount="indefinite"/></circle>`;
  }).join("");

  // Date range spans all symbols (earliest start ~ latest end).
  var allDates = [];
  series.forEach(function (s) { s.points.forEach(function (p) { allDates.push(p.date); }); });
  var sorted = allDates.slice().sort();

  chartEl.setAttribute("data-orientation", portrait ? "portrait" : "landscape");
  chartEl.innerHTML = `<svg class="bt-cmp-chart-svg" viewBox="0 0 ${W} ${H}">
    <defs>
      <clipPath id="btCmpReveal"><rect id="btCmpRevealRect" x="0" y="0" width="0" height="${H}"></rect></clipPath>
    </defs>
    ${axes.grid}
    ${axes.lines}
    <g id="btCmpLayer" clip-path="url(#btCmpReveal)">${lines}</g>
    <g id="btCmpPulse">${dots}</g>
    ${axes.labels}
    ${buildBtBrandSvg(W, H, PAD, "var(--apple-text-tertiary)")}
    <line id="btCmpTooltipGuide" x1="0" y1="${PAD.top}" x2="0" y2="${PAD.top + ch}" stroke="${c.guide}" stroke-width="1" stroke-dasharray="4,3" style="display:none;pointer-events:none;"/>
    <rect id="btCmpHoverPlot" x="${PAD.left}" y="${PAD.top}" width="${cw}" height="${ch}" fill="transparent" style="cursor:crosshair"/>
    <g id="btCmpTooltip" style="display:none;pointer-events:none;">
      <rect id="btCmpTooltipBg" x="0" y="0" width="200" height="60" rx="8" fill="${c.tooltipBg}" stroke="${c.tooltipBorder}"/>
      <g id="btCmpTooltipRows"></g>
    </g>
  </svg>`;

  var svgEl = chartEl.querySelector("svg");
  var tipEl = svgEl.querySelector("#btCmpTooltip");
  var tipGuide = svgEl.querySelector("#btCmpTooltipGuide");
  var tipBg = svgEl.querySelector("#btCmpTooltipBg");
  var tipRows = svgEl.querySelector("#btCmpTooltipRows");
  var hoverPlot = svgEl.querySelector("#btCmpHoverPlot");
  function showCmpTip(guideX) {
    if (!tipEl) return;
    var targetMs = minDateMs + ((guideX - PAD.left) / Math.max(1, cw)) * dateRangeMs;
    var dateLabel = new Date(targetMs).toISOString().slice(0, 10);
    var rows = '<text x="10" y="16" fill="' + c.tooltipText + '" font-size="11" font-weight="600">' + escapeHtml(dateLabel) + '</text>';
    var visibleRows = 0;
    built.forEach(function (b) {
      var p = interpolateBtPointAtX(b.pts, guideX);
      if (!p) return;
      visibleRows += 1;
      var ry = 16 + visibleRows * 16;
      var profitColor = p.profit >= 0 ? c.positive : c.negative;
      rows += '<rect x="10" y="' + (ry - 8) + '" width="8" height="3" rx="1" fill="' + b.color + '"/>';
      rows += '<text x="22" y="' + (ry - 5) + '" fill="' + c.tooltipText + '" font-size="10">' + escapeHtml(b.symbol) + '</text>';
      rows += '<text x="64" y="' + (ry - 5) + '" fill="' + c.tooltipText + '" font-size="10">' + formatBtPlainAxis(p.value) + '</text>';
      rows += '<text x="130" y="' + (ry - 5) + '" fill="' + profitColor + '" font-size="10">' + (p.profit >= 0 ? "+" : "") + formatBtPlainAxis(p.profit) + '</text>';
    });
    if (tipRows) tipRows.innerHTML = rows;
    if (tipBg) tipBg.setAttribute("height", String(18 + visibleRows * 16 + 8));
    var tipX = Math.min(Math.max(guideX + 12, PAD.left), W - PAD.right - 200);
    tipEl.setAttribute("transform", "translate(" + tipX + ", " + (PAD.top + 4) + ")");
    if (tipGuide) {
      tipGuide.setAttribute("x1", String(guideX));
      tipGuide.setAttribute("x2", String(guideX));
      tipGuide.style.display = "";
    }
    tipEl.style.display = "";
  }
  if (hoverPlot) {
    hoverPlot.addEventListener("mousemove", function (event) {
      var point = svgEl.createSVGPoint();
      point.x = event.clientX;
      point.y = event.clientY;
      var local = point.matrixTransform(svgEl.getScreenCTM().inverse());
      var guideX = Math.max(PAD.left, Math.min(PAD.left + cw, local.x));
      showCmpTip(guideX);
    });
    hoverPlot.addEventListener("mouseleave", function () {
      if (tipEl) tipEl.style.display = "none";
      if (tipGuide) tipGuide.style.display = "none";
    });
  }

  var legendEl = $("btCompareLegend");
  if (legendEl && context) {
    legendEl.setAttribute("data-orientation", portrait ? "portrait" : "landscape");
    var metricLabel = context.metric === "profit" ? __("backtest.totalReturn") : __("backtest.totalAssets");
    var startLabel = (context.start || "").slice(0, 7);
    var latest = sorted.length ? sorted[sorted.length - 1].slice(0, 7) : "";
    var titleText = __("backtest.compareCardTitle", {
      lump: formatBtPlainMoney(context.lump, 0),
      range: (startLabel && latest) ? (startLabel + " ~ " + latest) : "",
      metric: metricLabel,
    });
    legendEl.innerHTML =
      '<div class="bt-cmp-card">' +
        '<div class="bt-cmp-card-title">' + escapeHtml(titleText) + '</div>' +
        '<div class="bt-cmp-card-items">' +
          built.map(function (b, i) {
            var vc = b.finalValue >= 0 ? "bt-val-positive" : "bt-val-negative";
            return '<span class="bt-cmp-item"><span class="bt-legend-swatch" style="background:' + b.color + '"></span>' +
              '<span class="bt-cmp-code">' + escapeHtml(b.symbol) + '</span>' +
              '<b id="btCmpVal-' + i + '" class="bt-live-val ' + vc + '">' + formatBtPlainMoney(0) + '</b>' +
              '<span id="btCmpPct-' + i + '" class="bt-cmp-pct">0.00%</span></span>';
          }).join("") +
        '</div>' +
      '</div>';
  }

  // Keep the last compare state so the video recorder can replay chart + legend.
  var rootStyle = getComputedStyle(document.documentElement);
  _btCompareLast = {
    series: series,
    built: built,
    context: context,
    lump: (context && context.lump) || 0,
    W: W, H: H, PAD: PAD, cw: cw, ch: ch, axisFont: axisFont,
    lineStroke: lineStroke,
    xPosMs: xPosMs, yPos: yPos, minV: minV, maxV: maxV,
    minDateMs: minDateMs, maxDateMs: maxDateMs, dateRangeMs: dateRangeMs,
    portrait: portrait,
    c: c,
    bg: rootStyle.getPropertyValue("--apple-bg").trim() || "#000000",
    divider: rootStyle.getPropertyValue("--apple-divider").trim() || "rgba(255,255,255,0.12)",
    textTertiary: rootStyle.getPropertyValue("--apple-text-tertiary").trim() || "#999999",
    textSecondary: rootStyle.getPropertyValue("--apple-text-secondary").trim() || "#cccccc",
    startLabel: ((context && context.start) || "").slice(0, 7),
    latest: sorted.length ? sorted[sorted.length - 1].slice(0, 7) : "",
    sorted: sorted,
  };

  var revealRect = chartEl.querySelector("#btCmpRevealRect");
  var durationMs = getCompareAnimMs();
  var updateLegend = function (progress) {
    var revealX = PAD.left + cw * progress;
    built.forEach(function (b, i) {
      var snapshot = interpolateBtPointAtX(b.pts, revealX);
      var el = $("btCmpVal-" + i);
      var currentValue = snapshot ? (isProfit ? snapshot.profit : snapshot.value) : null;
      if (el) el.textContent = currentValue === null ? "—" : formatBtPlainMoney(currentValue);
      var pct = $("btCmpPct-" + i);
      if (pct) {
        var p = snapshot && context && context.lump ? (snapshot.profit / context.lump) * 100 : null;
        pct.textContent = p === null ? "—" : (p >= 0 ? "+" : "") + p.toFixed(2) + "%";
        pct.style.color = p === null ? "var(--apple-text-tertiary)" : (p >= 0 ? "var(--data-positive)" : "var(--data-negative)");
      }
    });
  };
  var moveDots = function (progress) {
    var revealX = PAD.left + cw * progress;
    built.forEach(function (b, i) {
      var el = $("btCmpDot-" + i);
      if (!el) return;
      var snapshot = interpolateBtPointAtX(b.pts, revealX);
      if (!snapshot) { el.style.display = "none"; return; }
      el.style.display = "";
      el.setAttribute("cx", snapshot.x);
      el.setAttribute("cy", snapshot.y);
    });
  };
  if (durationMs <= 0) {
    revealRect.setAttribute("width", String(W));
    updateLegend(1);
    moveDots(1);
  } else {
    revealRect.setAttribute("width", "0");
    var start = performance.now();
    var tick = function (now) {
      var progress = Math.max(0, Math.min((now - start) / durationMs, 1));
      revealRect.setAttribute("width", String(PAD.left + cw * progress));
      updateLegend(progress);
      moveDots(progress);
      if (progress < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }
}

// ─── Compare toolbar: collapse params + fullscreen ───
(function () {
  function initCompareToolbar() {
    // Collapse the compare parameter area for an immersive chart view.
    var collapse = $("btCmpToggleParams");
    var wrap = $("btCmpParamsWrap");
    function setCompareParamsCollapsed(collapsed) {
      if (wrap) wrap.style.display = collapsed ? "none" : "";
      document.querySelectorAll('[data-cmp-action="collapse"]').forEach(function (btn) {
        btn.textContent = __(collapsed ? "backtest.compareExpand" : "backtest.compareCollapse");
      });
    }
    if (collapse && wrap) {
      collapse.addEventListener("click", function () {
        setCompareParamsCollapsed(wrap.style.display !== "none");
      });
    }
    document.querySelectorAll('[data-cmp-action="collapse"]').forEach(function (btn) {
      btn.addEventListener("click", function () { setCompareParamsCollapsed(wrap && wrap.style.display !== "none"); });
    });
    // In-browser fullscreen: overlay the compare panel without entering OS fullscreen.
    var webFs = $("btCmpWebFs");
    function setWebFullscreen(on) {
      var el = $("btTabCompare");
      if (!el) return;
      el.classList.toggle("bt-cmp-webfs", on);
      if (webFs) webFs.textContent = __(on ? "backtest.compareExit" : "backtest.compareWebFs");
      document.body.style.overflow = on ? "hidden" : "";
    }
    if (webFs) {
      webFs.addEventListener("click", function () {
        var el = $("btTabCompare");
        setWebFullscreen(!(el && el.classList.contains("bt-cmp-webfs")));
      });
    }
    document.querySelectorAll('[data-cmp-action="webfs"]').forEach(function (btn) {
      btn.addEventListener("click", function () { setWebFullscreen(false); });
    });
    // Desktop fullscreen via the Fullscreen API.
    var fs = $("btCmpFullscreen");
    function toggleDesktopFullscreen() {
      var el = $("btTabCompare");
      if (!el) return;
      if (!document.fullscreenElement) {
        (el.requestFullscreen || el.webkitRequestFullscreen || function () {}).call(el);
      } else {
        (document.exitFullscreen || document.webkitExitFullscreen || function () {}).call(document);
      }
    }
    if (fs) fs.addEventListener("click", toggleDesktopFullscreen);
    document.querySelectorAll('[data-cmp-action="desktopfs"]').forEach(function (btn) {
      btn.addEventListener("click", toggleDesktopFullscreen);
    });
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initCompareToolbar);
  } else {
    initCompareToolbar();
  }
})();

// ─── Compare video recording (chart + legend only) ───────────────────
// Native MediaRecorder + canvas.captureStream. The chart is rasterized once,
// then the reveal animation is replayed deterministically on an offscreen
// canvas, so the video contains exactly the chart and legend — no page
// chrome, no cursor, no buttons.
var BT_RECORD_MIN_MS = 3000;    // clamps a 0/1s animation so the video is watchable
var BT_RECORD_MAX_MS = 30000;
var BT_RECORD_HOLD_MS = 1800;
// Standard social/video aspect ratios. The SVG viewBox remains the logical
// layout; these physical pixels only add density, not smaller typography.
var BT_RECORD_LANDSCAPE_W = 1920;
var BT_RECORD_LANDSCAPE_H = 1080;
var BT_RECORD_PORTRAIT_W = 1080;
var BT_RECORD_PORTRAIT_H = 1920;
var BT_RECORD_BITRATE = 12000000;   // high enough to keep axis text crisp
// Legend metrics mirror the on-page .bt-cmp-card hierarchy while keeping text
// comfortably readable after social platforms resize or recompress the video.
var BT_LEGEND_ITEM_GAP = 12;
var BT_LEGEND_ROW_GAP = 10;
var BT_LEGEND_FLEX_GAP = 5;
var BT_LEGEND_CODE_MR = 6;
var BT_LEGEND_VAL_MR = 3;
var BT_LEGEND_SWATCH_W = 16;
var BT_LEGEND_SWATCH_H = 5;
var BT_LEGEND_PCT_MIN_W = 58;
var BT_LEGEND_PAD_Y = 12;
var BT_LEGEND_TITLE_SIZE = 15;
var BT_LEGEND_ITEM_SIZE = 16;
var BT_LEGEND_PCT_SIZE = 14;
var BT_LEGEND_TITLE_LINE_H = 21;
var BT_LEGEND_OVERLAY_INSET = 10;
var BT_LEGEND_OVERLAY_ALPHA = 0.86;

function pickCompareRecMime() {
  if (typeof MediaRecorder === "undefined") return "";
  // H.264 MP4 first: plays everywhere including iOS. Without an explicit codec,
  // Chrome would pick VP9-in-mp4 which iOS cannot play, so name avc1 explicitly.
  var candidates = [
    "video/mp4;codecs=avc1.42E01E",
    "video/mp4",
    "video/webm;codecs=vp9",
    "video/webm;codecs=vp8",
    "video/webm",
  ];
  for (var i = 0; i < candidates.length; i++) {
    if (MediaRecorder.isTypeSupported(candidates[i])) return candidates[i];
  }
  return "";
}

function buildCompareAxisSvg(state, chartW, chartH) {
  var W = state.W, H = state.H, PAD = state.PAD;
  var textColor = state.textTertiary, labelColor = state.textSecondary, bg = state.bg;
  var axisFont = state.axisFont || BT_AXIS_FONT;
  var yValues = Array.from({ length: 5 }, function (_, i) {
    return state.minV + (state.maxV - state.minV) * i / 4;
  });
  var axes = buildBtAxes({
    W: W, H: H, PAD: PAD, yValues: yValues, yPos: state.yPos,
    formatY: formatBtPlainAxis,
    xTicks: buildBtDateTicks(state.minDateMs, state.maxDateMs, state.portrait ? 5 : 6),
    xPosMs: state.xPosMs,
    fontSize: axisFont,
    gridColor: state.divider,
    axisColor: labelColor,
    labelColor: labelColor,
  });
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${chartW}" height="${chartH}" viewBox="0 0 ${W} ${H}">
    <rect x="0" y="0" width="${W}" height="${H}" fill="${bg}"/>${axes.grid}${axes.lines}${axes.labels}
    ${buildBtBrandSvg(W, H, PAD, textColor)}</svg>`;
}

function buildCompareLinesSvg(state, chartW, chartH) {
  var W = state.W, H = state.H;
  var stroke = state.lineStroke || BT_PRIMARY_LINE_STROKE;
  var paths = state.built.map(function (b) {
    return `<path d="${smoothPath(b.pts)}" fill="none" stroke="${b.color}" stroke-width="${stroke}" stroke-linecap="round" opacity="0.95"/>`;
  }).join("");
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${chartW}" height="${chartH}" viewBox="0 0 ${W} ${H}">${paths}</svg>`;
}

function svgToImage(svgString) {
  var url = URL.createObjectURL(new Blob([svgString], { type: "image/svg+xml;charset=utf-8" }));
  return new Promise(function (resolve, reject) {
    var img = new Image();
    img.onload = function () { URL.revokeObjectURL(url); resolve(img); };
    img.onerror = function () { URL.revokeObjectURL(url); reject(new Error("SVG rasterize failed")); };
    img.src = url;
  });
}

// Reflow the same data into the video's native aspect ratio. This keeps the
// chart itself full-frame instead of preserving the shorter on-page plot and
// spending the remaining pixels on a separate legend area.
function buildCompareVideoState(state, canvasW, canvasH) {
  var W = state.W;
  var H = Math.round(W * canvasH / canvasW);
  var portrait = canvasH > canvasW;
  var axisFont = state.axisFont || BT_AXIS_FONT;
  var yRange = state.maxV - state.minV || 1;
  var yPad = yRange * 0.03;
  var yMin = state.minV - yPad;
  var yMax = state.maxV + yPad;
  var yRng = yMax - yMin;
  var yValues = Array.from({ length: 5 }, function (_, i) {
    return state.minV + (state.maxV - state.minV) * i / 4;
  });
  var PAD = buildBtChartPadding(yValues.map(formatBtPlainAxis), axisFont, portrait);
  var cw = W - PAD.left - PAD.right;
  var ch = H - PAD.top - PAD.bottom;
  var xPosMs = function (ms) {
    return PAD.left + ((ms - state.minDateMs) / state.dateRangeMs) * cw;
  };
  var yPos = function (value) {
    return PAD.top + ch - ((value - yMin) / yRng) * ch;
  };
  var isProfit = state.context && state.context.metric === "profit";
  var built = state.series.map(function (series) {
    var pts = series.points.map(function (point) {
      var dateMs = btDateMs(point.date);
      var metricValue = isProfit ? point.profit : point.value;
      return {
        x: xPosMs(dateMs), y: yPos(metricValue), value: point.value,
        profit: point.profit, dateMs: dateMs,
      };
    }).filter(function (point) {
      return Number.isFinite(point.dateMs);
    }).sort(function (a, b) {
      return a.dateMs - b.dateMs;
    });
    var last = series.points[series.points.length - 1];
    return {
      symbol: series.symbol, color: series.color, pts: pts,
      finalValue: last ? (isProfit ? last.profit : last.value) : 0,
      finalProfit: last ? last.profit : 0,
    };
  });
  return Object.assign({}, state, {
    W: W, H: H, PAD: PAD, cw: cw, ch: ch, portrait: portrait,
    axisFont: axisFont, xPosMs: xPosMs, yPos: yPos, built: built,
  });
}

// Wrap legend items into rows of maxWidth. Pure layout logic, kept separate
// so it can be covered by a regression test. gap scales with the canvas width.
function layoutCompareLegendItems(items, maxWidth, gap) {
  gap = gap || BT_LEGEND_ITEM_GAP;
  var rows = [];
  var row = [];
  var rowW = 0;
  items.forEach(function (item) {
    var w = item.width + gap;
    if (row.length && rowW + w > maxWidth) { rows.push(row); row = []; rowW = 0; }
    row.push(item);
    rowW += w;
  });
  if (row.length) rows.push(row);
  return rows;
}

function wrapCompareLegendTitle(ctx, title, maxWidth) {
  var parts = String(title || "").split(" · ");
  var lines = [], line = "";
  parts.forEach(function (part) {
    var candidate = line ? line + " · " + part : part;
    if (line && ctx.measureText(candidate).width > maxWidth) {
      lines.push(line);
      line = part;
    } else {
      line = candidate;
    }
  });
  if (line) lines.push(line);
  return lines.length ? lines : [""];
}

function layoutCompareLegend(ctx, state, canvasW, canvasH) {
  var scale = canvasW / state.W;
  var ls = scale;
  var chartH = canvasH;
  var x0 = Math.round(state.PAD.left * scale);
  var innerPad = Math.round(BT_LEGEND_PAD_Y * ls);
  var maxItemsW = canvasW - x0 - Math.round(state.PAD.right * scale) - innerPad * 2;
  var isProfit = state.context && state.context.metric === "profit";
  var metricLabel = isProfit ? __("backtest.totalReturn") : __("backtest.totalAssets");
  var range = (state.startLabel && state.latest) ? (state.startLabel + " ~ " + state.latest) : "";
  var title = __("backtest.compareCardTitle", {
    lump: formatBtPlainMoney(state.lump, 0),
    range: range,
    metric: metricLabel,
  });
  var itemSize = Math.round(BT_LEGEND_ITEM_SIZE * ls);
  var pctSize = Math.round(BT_LEGEND_PCT_SIZE * ls);
  var titleSize = Math.round(BT_LEGEND_TITLE_SIZE * ls);
  var titleLineH = Math.round(BT_LEGEND_TITLE_LINE_H * ls);
  var codeFont = "600 " + itemSize + "px -apple-system, system-ui, sans-serif";
  var valFont = "700 " + itemSize + "px -apple-system, system-ui, sans-serif";
  var pctFont = "600 " + pctSize + "px -apple-system, system-ui, sans-serif";
  var titleFont = titleSize + "px -apple-system, system-ui, sans-serif";
  ctx.font = titleFont;
  var titleLines = wrapCompareLegendTitle(ctx, title, maxItemsW);
  var gap = BT_LEGEND_ITEM_GAP * ls;
  var items = state.built.map(function (b) {
    var symbol = String(b.symbol).toUpperCase();
    var val = formatBtPlainMoney(b.finalValue);
    var p = state.lump ? (b.finalProfit / state.lump * 100) : 0;
    var pct = (p >= 0 ? "+" : "") + p.toFixed(2) + "%";
    ctx.font = codeFont;
    var codeW = ctx.measureText(symbol).width;
    ctx.font = valFont;
    var valW = ctx.measureText(val).width;
    ctx.font = pctFont;
    var pctW = Math.max(ctx.measureText(pct).width, BT_LEGEND_PCT_MIN_W * ls);
    return {
      symbol: symbol, color: b.color, finalValue: b.finalValue, finalProfit: b.finalProfit, built: b,
      // swatch + flex gap + code + (code margin + gap) + val + (val margin + gap) + pct
      width: (BT_LEGEND_SWATCH_W + BT_LEGEND_FLEX_GAP + BT_LEGEND_CODE_MR +
              BT_LEGEND_FLEX_GAP + BT_LEGEND_VAL_MR + BT_LEGEND_FLEX_GAP) * ls +
             codeW + valW + pctW,
    };
  });
  var rows = layoutCompareLegendItems(items, maxItemsW, gap);
  var padY = Math.round(BT_LEGEND_PAD_Y * ls);
  var rowsGap = rows.length ? Math.round(8 * ls) : 0;
  var titleBlockH = titleLines.length * titleLineH;
  var rowH = Math.round((BT_LEGEND_ITEM_SIZE + BT_LEGEND_ROW_GAP) * ls);
  var overlayInset = Math.round(BT_LEGEND_OVERLAY_INSET * ls);
  var overlayX = x0;
  var overlayY = Math.round(state.PAD.top * scale) + overlayInset;
  var overlayW = canvasW - overlayX - Math.round(state.PAD.right * scale);
  var overlayH = padY + titleBlockH + rowsGap + rows.length * itemSize +
                 Math.max(0, rows.length - 1) * Math.round(BT_LEGEND_ROW_GAP * ls) + padY;
  var contentX = overlayX + padY;
  var titleFirstY = overlayY + padY + titleLineH / 2;
  var rowsY = overlayY + padY + titleBlockH + rowsGap + itemSize / 2;
  return {
    scale: scale, chartH: chartH, canvasW: canvasW, x0: contentX, rows: rows,
    title: title, titleLines: titleLines, titleFirstY: titleFirstY, titleLineH: titleLineH,
    rowsY: rowsY, rowH: rowH,
    codeFont: codeFont, valFont: valFont, pctFont: pctFont,
    legendH: overlayH, legendScale: ls,
    overlayX: overlayX, overlayY: overlayY, overlayW: overlayW, overlayH: overlayH,
  };
}

function fillRoundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  if (typeof ctx.roundRect === "function") ctx.roundRect(x, y, w, h, r);
  else ctx.rect(x, y, w, h);
  ctx.fill();
}

function drawCompareLegend(ctx, state, layout, progress) {
  var rows = layout.rows;
  var x0 = layout.x0;
  var ls = layout.legendScale || 1;
  ctx.save();
  ctx.globalAlpha = BT_LEGEND_OVERLAY_ALPHA;
  ctx.fillStyle = state.bg;
  fillRoundRect(ctx, layout.overlayX, layout.overlayY, layout.overlayW, layout.overlayH, 10 * ls);
  ctx.restore();
  ctx.save();
  ctx.strokeStyle = state.divider;
  ctx.lineWidth = Math.max(1, 0.5 * ls);
  if (typeof ctx.roundRect === "function") {
    ctx.beginPath();
    ctx.roundRect(layout.overlayX, layout.overlayY, layout.overlayW, layout.overlayH, 10 * ls);
    ctx.stroke();
  }
  ctx.restore();
  ctx.textBaseline = "middle";
  ctx.textAlign = "left";
  var revealX = state.PAD.left + state.cw * progress;
  ctx.font = Math.round(BT_LEGEND_TITLE_SIZE * ls) + "px -apple-system, system-ui, sans-serif";
  ctx.fillStyle = state.textSecondary;
  layout.titleLines.forEach(function (line, index) {
    ctx.fillText(line, x0, layout.titleFirstY + index * layout.titleLineH);
  });
  var gap = BT_LEGEND_ITEM_GAP * ls;
  rows.forEach(function (row, r) {
    var cy = layout.rowsY + r * layout.rowH;
    var x = x0;
    row.forEach(function (item) {
      // 14x4 rounded swatch.
      var sw = BT_LEGEND_SWATCH_W * ls, sh = BT_LEGEND_SWATCH_H * ls;
      ctx.fillStyle = item.color;
      fillRoundRect(ctx, x, cy - sh / 2, sw, sh, 2 * ls);
      x += sw + BT_LEGEND_FLEX_GAP * ls;
      // Code: 14px/600 secondary.
      ctx.font = layout.codeFont;
      ctx.fillStyle = state.textSecondary;
      ctx.fillText(item.symbol, x, cy);
      x += ctx.measureText(item.symbol).width + BT_LEGEND_CODE_MR * ls + BT_LEGEND_FLEX_GAP * ls;
      var snapshot = interpolateBtPointAtX(item.built.pts, revealX);
      var metricValue = snapshot ? (state.context && state.context.metric === "profit" ? snapshot.profit : snapshot.value) : null;
      var val = metricValue === null ? "—" : formatBtPlainMoney(metricValue);
      ctx.font = layout.valFont;
      ctx.fillStyle = metricValue === null ? state.textTertiary : (metricValue >= 0 ? state.c.positive : state.c.negative);
      ctx.fillText(val, x, cy);
      x += ctx.measureText(val).width + BT_LEGEND_VAL_MR * ls + BT_LEGEND_FLEX_GAP * ls;
      var p = snapshot && state.lump ? (snapshot.profit / state.lump) * 100 : null;
      var pct = p === null ? "—" : (p >= 0 ? "+" : "") + p.toFixed(2) + "%";
      ctx.font = layout.pctFont;
      var pctW = Math.max(ctx.measureText(pct).width, BT_LEGEND_PCT_MIN_W * ls);
      ctx.fillStyle = p === null ? state.textTertiary : (p >= 0 ? state.c.positive : state.c.negative);
      ctx.textAlign = "right";
      ctx.fillText(pct, x + pctW, cy);
      ctx.textAlign = "left";
      x += pctW + gap;
    });
  });
}

async function recordCompareVideo() {
  var state = _btCompareLast;
  var mime = pickCompareRecMime();
  if (!mime) { btError(__("backtest.recordUnsupported")); return; }
  if (!state || !state.series.length) { btError(__("backtest.recordNeedRun")); return; }

  var portrait = _btCompareOrientation === "portrait";
  var canvasW = portrait ? BT_RECORD_PORTRAIT_W : BT_RECORD_LANDSCAPE_W;
  var canvasH = portrait ? BT_RECORD_PORTRAIT_H : BT_RECORD_LANDSCAPE_H;

  var btn = $("btCmpRecord");
  if (btn) { btn.disabled = true; btn.textContent = __("backtest.recordRecording"); }

  var canvas = document.createElement("canvas");
  canvas.width = canvasW;
  canvas.height = canvasH;
  var ctx = canvas.getContext("2d");
  var videoState = buildCompareVideoState(state, canvasW, canvasH);
  var layout = layoutCompareLegend(ctx, videoState, canvasW, canvasH);

  var chunks = [];
  var aborted = false;
  var rec = null;
  try {
    // Both calls must stay inside the click gesture (required on macOS Safari).
    var stream = canvas.captureStream(30);
    rec = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: BT_RECORD_BITRATE });
    rec.ondataavailable = function (e) { if (e.data && e.data.size) chunks.push(e.data); };
    rec.onstop = function () {
      if (btn) { btn.disabled = false; btn.textContent = __("backtest.record"); }
      if (aborted) return;
      var blob = new Blob(chunks, { type: mime });
      var ext = mime.indexOf("mp4") >= 0 ? "mp4" : "webm";
      var url = URL.createObjectURL(blob);
      var a = document.createElement("a");
      a.href = url;
      a.download = "backtest-compare-" + (portrait ? "portrait-" : "") + Date.now() + "." + ext;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(function () { URL.revokeObjectURL(url); }, 10000);
    };
    rec.start();
  } catch (e) {
    if (btn) { btn.disabled = false; btn.textContent = __("backtest.record"); }
    btError(__("backtest.recordUnsupported"));
    return;
  }

  try {
    var scale = layout.scale;
    var chartW = canvasW;
    var chartH = canvasH;
    var imgs = await Promise.all([
      svgToImage(buildCompareAxisSvg(videoState, chartW, chartH)),
      svgToImage(buildCompareLinesSvg(videoState, chartW, chartH)),
    ]);
    var axisImg = imgs[0], linesImg = imgs[1];
    var PAD = videoState.PAD, cw = videoState.cw, built = videoState.built;

    var drawFrame = function (progress) {
      // Theme background everywhere: the legend area below the chart is plain
      // canvas, which would otherwise encode as transparent→black.
      ctx.fillStyle = videoState.bg;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      // Axis + labels stay visible the whole time.
      ctx.drawImage(axisImg, 0, 0, chartW, chartH);
      // Reveal the lines left→right with a canvas clip, matching the DOM animation.
      ctx.save();
      ctx.beginPath();
      var revealX = PAD.left + cw * progress;
      ctx.rect(0, 0, revealX * scale, chartH);
      ctx.clip();
      ctx.drawImage(linesImg, 0, 0, chartW, chartH);
      ctx.restore();
      // Endpoint dots travel along each line at the reveal frontier.
      built.forEach(function (b) {
        var snapshot = interpolateBtPointAtX(b.pts, revealX);
        if (!snapshot) return;
        var x = snapshot.x * scale;
        var y = snapshot.y * scale;
        ctx.beginPath();
        ctx.arc(x, y, 3.2 * scale, 0, Math.PI * 2);
        ctx.fillStyle = b.color;
        ctx.fill();
        ctx.lineWidth = 1.5 * scale;
        ctx.strokeStyle = videoState.bg;
        ctx.stroke();
      });
      drawCompareLegend(ctx, videoState, layout, progress);
    };

    var durMs = Math.max(BT_RECORD_MIN_MS, Math.min(getCompareAnimMs(), BT_RECORD_MAX_MS));
    var start = performance.now();
    var holdStart = 0;
    var tick = function (now) {
      var progress = Math.max(0, Math.min((now - start) / durMs, 1));
      drawFrame(progress);
      if (progress < 1) requestAnimationFrame(tick);
      else {
        if (!holdStart) holdStart = now;
        if (now - holdStart < BT_RECORD_HOLD_MS) requestAnimationFrame(tick);
        else rec.stop();
      }
    };
    requestAnimationFrame(tick);
  } catch (e) {
    aborted = true;
    if (btn) { btn.disabled = false; btn.textContent = __("backtest.record"); }
    btError(__("backtest.recordUnsupported"));
    try { rec.stop(); } catch (_) {}
  }
}

function initCompareRecorder() {
  var btn = $("btCmpRecord");
  if (!btn) return;
  btn.addEventListener("click", recordCompareVideo);
}
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initCompareRecorder);
} else {
  initCompareRecorder();
}
