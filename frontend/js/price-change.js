/**
 * Yearly price change tracker — heatmap table.
 *
 * Features:
 *   - Add/remove symbols (stock or crypto)
 *   - Preset symbol groups loaded from backend config
 *   - Configurable color range (min/max %)
 *   - Red/green background shading proportional to magnitude
 */

const API_BASE = "";
const ENDPOINT = `${API_BASE}/api/price-change/yearly`;
const CONFIG_ENDPOINT = `${API_BASE}/api/price-change/config`;
const MONTHLY_ENDPOINT = `${API_BASE}/api/price-change/monthly`;
const BATCH_MONTHLY_ENDPOINT = `${API_BASE}/api/price-change/monthly-batch`;

// ─── State ───

let symbols = []; // [{symbol, type}, ...]
let PRESETS = []; // [{key, label, symbols}, ...] loaded from backend
let _currentSymKeys = []; // symbols currently shown in table columns
let _lastYearlyData = null; // {years, data} from last fetch, for line charts
let _mChartHidden = []; // hidden series indices for monthly chart

// ─── DOM refs ───

const $ = (id) => document.getElementById(id);
const symInput = $("pcSymbolInput");
const typeSelect = $("pcTypeSelect");
const addBtn = $("pcAddBtn");
const clearBtn = $("pcClearBtn");
const refreshBtn = $("pcRefreshBtn");
const minRange = $("pcMinRange");
const maxRange = $("pcMaxRange");
const tags = $("pcTags");
const table = $("pcTable");
const tableHead = $("pcTableHead");
const tableBody = $("pcTableBody");
const empty = $("pcEmpty");
const error = $("pcError");
const loading = $("pcLoading");
const metaInfo = $("pcMetaInfo");
const statusDot = $("statusDot");
const statusText = $("statusText");

const yearSelect = $("pcYearSelect");
const yearList = $("pcYearList");

// ─── Backtest DOM refs ───
const btWrap = $("pcBacktest");
const btAmount = $("pcBtAmount");
const btYear = $("pcBtYear");
const btRun = $("pcBtRun");
const btClose = $("pcBtClose");
const btResult = $("pcBtResult");
const btSummary = $("pcBtSummary");
const btHead = $("pcBtHead");
const btBody = $("pcBtBody");

// ─── Status ───

function setConnected(ok) {
  statusDot.className = "status-dot" + (ok ? " connected" : "");
  statusText.textContent = ok ? "已连接" : "未连接";
}

// ─── Error / Loading ───

function showError(msg) {
  if (!msg) { error.style.display = "none"; return; }
  error.textContent = msg;
  error.style.display = "block";
}

function setLoading(on) {
  loading.style.display = on ? "flex" : "none";
}

// ─── Year mode helpers ───

function getSelectedYear() {
  const val = yearSelect?.value?.trim();
  if (!val || val === "历年汇总") return null;
  const num = parseInt(val, 10);
  return isNaN(num) ? null : num;
}

function populateYearOptions() {
  if (!yearList) return;
  const currentYear = new Date().getFullYear();
  const years = [];
  for (let y = currentYear; y >= 2015; y--) {
    years.push(`<option value="${y}">`);
  }
  yearList.innerHTML = years.join("");
}

function hideYearlySections() {
  $("pcChartWrap").style.display = "none";
  if (btWrap) btWrap.style.display = "none";
  if (btResult) btResult.style.display = "none";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function renderMetaInfo(meta) {
  if (!metaInfo) return;
  if (!meta || Object.keys(meta).length === 0) {
    metaInfo.style.display = "none";
    metaInfo.innerHTML = "";
    return;
  }

  const items = symbols
    .map((s) => meta[s.symbol])
    .filter(Boolean)
    .map((m) => {
      const source = m.source ? escapeHtml(m.source) : "未知源";
      const points = Number.isFinite(m.points) ? `${m.points} 条日线` : "";
      const suffix = m.error
        ? ` <span class="pc-meta-error">失败: ${escapeHtml(m.error)}</span>`
        : ` ${points}`;
      return `<span><strong>${escapeHtml(m.symbol)}</strong>: ${source}${suffix}</span>`;
    });

  metaInfo.innerHTML = items.join(" · ");
  metaInfo.style.display = items.length ? "block" : "none";
}

// ─── Display name helper ───

function displayName(s) {
  return s.name ? `${s.symbol}(${s.name})` : s.symbol;
}

// ─── Symbol tags ───

function renderTags() {
  if (symbols.length === 0) {
    tags.innerHTML = '<span style="color:var(--apple-text-tertiary);font-size:12px;">暂无代码，输入并添加</span>';
    return;
  }
  tags.innerHTML = symbols
    .map(
      (s, i) =>
        `<span class="pc-tag">
          ${displayName(s)}
          <span class="pc-tag-type">${s.type === "crypto" ? "币" : s.type === "cn_stock" ? "A" : "股"}</span>
          <span class="pc-tag-remove" data-index="${i}">✕</span>
        </span>`
    )
    .join("");

  tags.querySelectorAll(".pc-tag-remove").forEach((el) => {
    el.addEventListener("click", () => {
      const idx = parseInt(el.dataset.index, 10);
      symbols.splice(idx, 1);
      renderTags();
    });
  });
}

// ─── Add symbol ───

function addSymbol(symbol, type) {
  const sym = symbol.trim().toUpperCase();
  if (!sym) return false;
  if (symbols.some((s) => s.symbol === sym && s.type === type)) return false;
  symbols.push({ symbol: sym, type });
  renderTags();
  symInput.value = "";
  symInput.focus();
  return true;
}

// ─── Color helpers ───

function cellColor(val, min, max) {
  // Multi-stop HSL gradient for richer color depth.
  // Positive: light green → vibrant green → deep green
  // Negative: light red → vibrant red → deep red
  if (val > 0) {
    const intensity = Math.min(val / max, 1);
    // Green hue 142°: lightness 88%→35%, saturation 55%→85%, alpha grows
    const lightness = 88 - intensity * 53;
    const saturation = 55 + intensity * 30;
    const alpha = Math.min(0.18 + intensity * 0.72, 0.95);
    return {
      bg: `hsla(142, ${Math.round(saturation)}%, ${Math.round(lightness)}%, ${alpha.toFixed(3)})`,
      text: lightness < 50 ? "#fff" : "var(--data-positive)",
    };
  }
  if (val < 0) {
    const intensity = Math.min(Math.abs(val) / Math.abs(min), 1);
    // Red hue 4°: lightness 88%→35%, saturation 55%→85%, alpha grows
    const lightness = 88 - intensity * 53;
    const saturation = 55 + intensity * 30;
    const alpha = Math.min(0.18 + intensity * 0.72, 0.95);
    return {
      bg: `hsla(4, ${Math.round(saturation)}%, ${Math.round(lightness)}%, ${alpha.toFixed(3)})`,
      text: lightness < 50 ? "#fff" : "var(--data-negative)",
    };
  }
  // Zero or NaN: neutral
  return { bg: "transparent", text: "var(--apple-text-secondary)" };
}

function formatPct(val) {
  if (val == null || isNaN(val)) return "—";
  const sign = val > 0 ? "+" : "";
  return `${sign}${val.toFixed(2)}%`;
}

// ─── API call ───

async function fetchData() {
  if (symbols.length === 0) {
    showError("请至少添加一个代码");
    return;
  }

  // Check if monthly mode (specific year selected)
  const year = getSelectedYear();
  if (year !== null) {
    await fetchMonthlyBatch(year);
    return;
  }

  // Clear previous drilldown cards and chart on new query
  const mc = $("pcMonthlyContainer");
  if (mc) mc.innerHTML = "";
  renderMetaInfo(null);
  $("pcChartWrap").style.display = "none";
  if (btWrap) btWrap.style.display = "none";
  if (btResult) btResult.style.display = "none";
  _btSymbols = [];
  _chartData = null;
  _chartSymbols = null;
  _chartHidden = [];
  _lastYearlyData = null;

  showError(null);
  setLoading(true);
  table.style.display = "none";
  empty.style.display = "none";

  try {
    const resp = await fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbols }),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.error || `HTTP ${resp.status}`);
    }

    const result = await resp.json();
    setConnected(true);
    _lastYearlyData = result;
    renderMetaInfo(result.meta);
    try {
      renderTable(result);
    } catch (renderErr) {
      console.error("renderTable error:", renderErr);
      showError(`渲染失败: ${renderErr.message}`);
    }
  } catch (e) {
    setConnected(false);
    showError(`请求失败: ${e.message}`);
    renderMetaInfo(null);
    empty.style.display = "block";
    table.style.display = "none";
  } finally {
    setLoading(false);
  }
}

// ─── Table render ───

function renderTable(result) {
  const { years, data } = result;

  if (!years || years.length === 0 || Object.keys(data).length === 0) {
    empty.innerHTML =
      "<div>查询完成，但未获取到有效数据</div>" +
      "<div class='pc-empty-hint'>请检查代码是否正确，或该代码暂无历史数据</div>";
    empty.style.display = "block";
    table.style.display = "none";
    return;
  }

  empty.style.display = "none";
  table.style.display = "";

  // Determine which symbols actually have data
  const activeSymbols = symbols.filter((s) => {
    const d = data[s.symbol];
    return d && Object.keys(d).length > 0;
  });
  const symKeys = activeSymbols.map((s) => s.symbol);

  if (symKeys.length === 0) {
    empty.innerHTML = "<div>查询完成，但所有代码均无有效数据</div>";
    empty.style.display = "block";
    table.style.display = "none";
    return;
  }

  // Read current range
  const minVal = parseFloat(minRange.value) || -50;
  const maxVal = parseFloat(maxRange.value) || 50;

  // Build a lookup for display names
  const nameLookup = {};
  const typeLookup = {};
  for (const s of symbols) {
    nameLookup[s.symbol] = s.name || null;
    typeLookup[s.symbol] = s.type || "stock";
  }
  _currentSymKeys = symKeys;

  // Render header — name on a separate line below the symbol
  tableHead.innerHTML =
    `<th>年份</th>` +
    symKeys.map((s) => {
      const name = nameLookup[s];
      return name ? `<th>${s}<span class="pc-th-name">${name}</span></th>` : `<th>${s}</th>`;
    }).join("");

  // Render body (years are already sorted descending from API)
  tableBody.innerHTML = years
    .map((year) => {
      let cells = `<td>${year}</td>`;
      for (const sym of symKeys) {
        const val = data[sym] && data[sym][year];
        const pct = val != null ? val : null;
        const formatted = pct !== null ? formatPct(pct) : "—";
        const colors = pct !== null ? cellColor(pct, minVal, maxVal) : { bg: "transparent", text: "var(--apple-text-tertiary)" };
        cells += `<td class="pc-cell" data-symbol="${sym}" data-year="${year}" data-type="${typeLookup[sym]}" style="background:${colors.bg};color:${colors.text};cursor:pointer;">${formatted}</td>`;
      }
      return `<tr>${cells}</tr>`;
    })
    .join("");

  // Multi-line chart
  _chartData = data;
  _chartSymbols = activeSymbols;
  _chartHidden = [];
  renderMultiLineChart(data, activeSymbols, []);

  // Populate backtest options and show the section
  try { populateBacktestOptions(); } catch (btErr) { console.error("bt opt fail:", btErr); }
  try { renderBtTags(); } catch (btErr) { console.error("bt tags fail:", btErr); }
  if (btWrap) btWrap.style.display = "";
}

// ─── Presets ───

async function loadConfigFromServer() {
  try {
    const resp = await fetch(CONFIG_ENDPOINT);
    if (!resp.ok) return { presets: [], colorRange: { min: -100, max: 100 } };
    const cfg = await resp.json();
    return {
      presets: cfg.presets || [],
      colorRange: cfg.color_range || { min: -100, max: 100 },
    };
  } catch {
    return { presets: [], colorRange: { min: -100, max: 100 } };
  }
}

function loadPreset(key) {
  const entry = PRESETS.find((p) => p.key === key);
  if (!entry || !entry.symbols) return;
  symbols = entry.symbols.map((s) => ({ ...s }));
  renderTags();
  fetchData();
}

function renderPresetChips() {
  const container = document.getElementById("pcPresets");
  if (!container) return;
  container.querySelectorAll(".pc-preset-chip").forEach((el) => el.remove());
  for (const p of PRESETS) {
    const chip = document.createElement("span");
    chip.className = "pc-preset-chip";
    chip.textContent = p.label || p.key;
    chip.dataset.preset = p.key;
    chip.addEventListener("click", () => loadPreset(p.key));
    container.appendChild(chip);
  }
}

// ─── Multi-line chart (all symbols overlaid) ───

const LINE_COLORS = [
  "#2997ff", "#e8a43e", "#30d158", "#ff453a", "#5ac8fa",
  "#ff9f0a", "#bf5af2", "#ff6482", "#64d2ff", "#ffd60a",
  "#ff375f", "#00c7be", "#ffb340", "#86868b", "#ff6482",
];

let _chartData = null;
let _chartSymbols = null;
let _chartHidden = []; // indices of hidden series

function renderMultiLineChart(data, symbolsList, hiddenIndices) {
  // Build series list
  const allSeries = [];
  let allYears = new Set();

  for (const s of symbolsList) {
    const yearly = data[s.symbol];
    if (!yearly) continue;
    const pts = Object.entries(yearly)
      .map(([y, v]) => ({ year: parseInt(y, 10), value: v }))
      .filter((p) => p.value != null)
      .sort((a, b) => a.year - b.year);
    if (pts.length < 2) continue;
    allSeries.push({ symbol: s.symbol, name: s.name || s.symbol, points: pts });
    pts.forEach((p) => allYears.add(p.year));
  }

  if (allSeries.length === 0) return;

  // Separate visible vs hidden
  const visibleSeries = allSeries.filter((_, i) => !hiddenIndices.includes(i));
  const hiddenSet = new Set(hiddenIndices);

  // Compute Y range from VISIBLE series only
  let allVals = [];
  visibleSeries.forEach((s) => s.points.forEach((p) => allVals.push(p.value)));
  if (allVals.length === 0) allVals = [0];
  const minVal = Math.min(...allVals, 0);
  const maxVal = Math.max(...allVals, 0);
  const range = maxVal - minVal || 1;
  const pad = range * 0.1;
  const yMin = minVal - pad;
  const yMax = maxVal + pad;
  const yRange = yMax - yMin;

  // Dynamic left padding based on max label width
  const maxAbsLabel = Math.max(Math.abs(yMin), Math.abs(yMax));
  const labelChars = maxAbsLabel.toFixed(1).length + 1; // "+XXX.X%"
  const PAD_LEFT = Math.max(48, labelChars * 7 + 8);
  const W = 700, H = 220, PAD = { top: 20, right: 16, bottom: 30, left: PAD_LEFT };
  const cw = W - PAD.left - PAD.right;
  const ch = H - PAD.top - PAD.bottom;

  // Sorted years across all series (for x-axis)
  const years = Array.from(allYears).sort((a, b) => a - b);
  const xPos = (y) => PAD.left + ((y - years[0]) / (years[years.length - 1] - years[0] || 1)) * cw;
  const yPos = (v) => PAD.top + ch - ((v - yMin) / yRange) * ch;
  const zeroY = yPos(0);

  // Y-axis grid
  const yTicks = 5;
  let yGrid = "";
  for (let i = 0; i <= yTicks; i++) {
    const v = yMin + (yRange * i) / yTicks;
    const y = yPos(v);
    yGrid += `<line x1="${PAD.left}" y1="${y}" x2="${W - PAD.right}" y2="${y}" stroke="var(--apple-divider)" stroke-width="1"/>`;
    yGrid += `<text x="${PAD.left - 6}" y="${y + 4}" text-anchor="end" fill="var(--apple-text-tertiary)" font-size="11">${v.toFixed(1)}%</text>`;
  }

  // Zero line
  const zeroLine = (zeroY >= PAD.top && zeroY <= H - PAD.bottom)
    ? `<line x1="${PAD.left}" y1="${zeroY}" x2="${W - PAD.right}" y2="${zeroY}" stroke="var(--apple-text-tertiary)" stroke-width="1" stroke-dasharray="4,3" opacity="0.6"/>`
    : "";

  // X-axis labels
  let xLabels = "";
  if (years.length > 1) {
    const step = Math.max(1, Math.floor(years.length / 8));
    for (let i = 0; i < years.length; i++) {
      if (i % step === 0 || i === years.length - 1) {
        xLabels += `<text x="${xPos(years[i])}" y="${H - 8}" text-anchor="middle" fill="var(--apple-text-tertiary)" font-size="11">${years[i]}</text>`;
      }
    }
  }

  // Only render visible series
  let seriesGroups = "";
  visibleSeries.forEach((series, vi) => {
    const color = LINE_COLORS[vi % LINE_COLORS.length];
    const pts = series.points;
    let gLines = "";
    let gDots = "";
    for (let i = 0; i < pts.length - 1; i++) {
      const x1 = xPos(pts[i].year), y1 = yPos(pts[i].value);
      const x2 = xPos(pts[i + 1].year), y2 = yPos(pts[i + 1].value);
      gLines += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${color}" stroke-width="1" stroke-linecap="round" opacity="0.75"/>`;
    }
    pts.forEach((p) => {
      gDots += `<circle cx="${xPos(p.year)}" cy="${yPos(p.value)}" r="1.8" fill="${color}" stroke="var(--apple-bg)" stroke-width="0.5"/>`;
    });
    // Use original series index for stable id but only show if visible
    const oi = allSeries.indexOf(series);
    seriesGroups += `<g id="cs-${oi}">${gLines}${gDots}</g>`;
  });

  // Legend (includes ALL series, hidden ones are greyed out)
  let legend = "";
  allSeries.forEach((series, idx) => {
    const isHidden = hiddenSet.has(idx);
    const color = LINE_COLORS[idx % LINE_COLORS.length];
    const label = series.name;
    const lx = 10 + (idx % 5) * 140;
    const ly = H + 14 + Math.floor(idx / 5) * 18;
    const barOpacity = isHidden ? 0.25 : 1;
    const txtOpacity = isHidden ? 0.3 : 0.85;
    const decoration = isHidden ? "line-through" : "none";
    legend += `<g data-legend="${idx}" style="cursor:pointer;">
      <rect x="${lx - 4}" y="${ly - 14}" width="130" height="22" rx="4" fill="rgba(0,0,0,0.001)"/>
      <rect class="cl-bar" x="${lx}" y="${ly - 7}" width="10" height="3" rx="1.5" fill="${color}" opacity="${barOpacity}"/>
      <text class="cl-label" x="${lx + 14}" y="${ly + 1}" fill="var(--apple-text-secondary)" font-size="11" opacity="${txtOpacity}" text-decoration="${decoration}">${label}</text>
    </g>`;
  });

  const svgH = legend ? H + 20 + Math.ceil(allSeries.length / 5) * 18 : H;

  $("pcChartSvg").innerHTML = `<svg viewBox="0 0 ${W} ${svgH}" style="width:100%;height:auto;display:block;">
    ${yGrid}
    ${zeroLine}
    ${seriesGroups}
    ${xLabels}
    ${legend}
  </svg>`;

  $("pcChartWrap").style.display = "";

  // Attach legend interactions (click on <g>, which covers bar + text + hit rect)
  allSeries.forEach((_, idx) => {
    const g = $("pcChartSvg").querySelector(`g[data-legend="${idx}"]`);
    if (!g) return;

    // Click → toggle hidden, re-render
    g.addEventListener("click", (e) => {
      e.stopPropagation();
      let newHidden;
      if (_chartHidden.includes(idx)) {
        newHidden = _chartHidden.filter((i) => i !== idx);
      } else {
        newHidden = [..._chartHidden, idx];
      }
      _chartHidden = newHidden;
      renderMultiLineChart(_chartData, _chartSymbols, _chartHidden);
    });

    // Hover → highlight only this series
    g.addEventListener("mouseenter", () => {
      const svgEl = $("pcChartSvg").querySelector("svg");
      allSeries.forEach((_, i) => {
        if (i === idx || _chartHidden.includes(i)) return;
        const g2 = svgEl.querySelector(`#cs-${i}`);
        if (g2) g2.style.opacity = "0.12";
      });
    });

    g.addEventListener("mouseleave", () => {
      const svgEl = $("pcChartSvg").querySelector("svg");
      allSeries.forEach((_, i) => {
        if (_chartHidden.includes(i)) return;
        const g2 = svgEl.querySelector(`#cs-${i}`);
        if (g2) g2.style.opacity = "1";
      });
    });
  });
}

// ─── Monthly batch view (symbols × months table for a specific year) ───

async function fetchMonthlyBatch(year) {
  showError(null);
  setLoading(true);
  table.style.display = "none";
  empty.style.display = "none";
  hideYearlySections();
  const mc = $("pcMonthlyContainer");
  if (mc) mc.innerHTML = "";
  renderMetaInfo(null);
  _lastYearlyData = null;

  try {
    const resp = await fetch(BATCH_MONTHLY_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbols, year }),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.error || `HTTP ${resp.status}`);
    }

    const result = await resp.json();
    setConnected(true);
    renderMonthlyTable(result);
  } catch (e) {
    setConnected(false);
    showError(`请求失败: ${e.message}`);
    empty.style.display = "block";
    table.style.display = "none";
  } finally {
    setLoading(false);
  }
}

function renderMonthlyTable(result) {
  const { year, data } = result;

  const symKeys = Object.keys(data).filter(k => data[k] && data[k].some(m => m.return !== null));
  if (symKeys.length === 0) {
    empty.innerHTML = "<div>查询完成，但未获取到有效数据</div>";
    empty.style.display = "block";
    table.style.display = "none";
    $("pcChartWrap").style.display = "none";
    return;
  }

  empty.style.display = "none";
  table.style.display = "";

  const minVal = parseFloat(minRange.value) || -50;
  const maxVal = parseFloat(maxRange.value) || 50;

  const nameLookup = {};
  for (const s of symbols) nameLookup[s.symbol] = s.name || null;

  // Transposed table: rows = months, columns = symbols
  // Header: 月份 | SYM1 | SYM2 | ...
  tableHead.innerHTML = `<th>${year}年</th>` +
    symKeys.map(sym => {
      const name = nameLookup[sym];
      return name ? `<th>${sym}<span class="pc-th-name">${name}</span></th>` : `<th>${sym}</th>`;
    }).join("");

  // Build monthMap[sym][month] = return
  const monthMap = {};
  for (const sym of symKeys) {
    monthMap[sym] = {};
    for (const m of data[sym]) {
      monthMap[sym][m.month] = m.return;
    }
  }

  // Annual return from monthly data (compounded)
  function annualReturn(months) {
    let product = 1, hasData = false;
    for (const m of months) {
      if (m.return !== null) { product *= (1 + m.return / 100); hasData = true; }
    }
    return hasData ? roundTo((product - 1) * 100, 2) : null;
  }

  const annualReturns = {};
  for (const sym of symKeys) {
    annualReturns[sym] = annualReturn(data[sym]);
  }

  // Body rows: 12 months then annual total
  const rows = [];
  for (let m = 1; m <= 12; m++) {
    let cells = `<td>${m}月</td>`;
    for (const sym of symKeys) {
      const val = monthMap[sym][m];
      const formatted = val !== null ? formatPct(val) : "—";
      const clr = val !== null ? cellColor(val, minVal, maxVal) : { bg: "transparent", text: "var(--apple-text-tertiary)" };
      cells += `<td style="background:${clr.bg};color:${clr.text};">${formatted}</td>`;
    }
    rows.push(`<tr>${cells}</tr>`);
  }

  // Annual total row (with top border to distinguish)
  let annualCells = `<td style="font-weight:600;">全年</td>`;
  for (const sym of symKeys) {
    const val = annualReturns[sym];
    const formatted = val !== null ? formatPct(val) : "—";
    const clr = val !== null ? cellColor(val, minVal, maxVal) : { bg: "transparent", text: "var(--apple-text-tertiary)" };
    annualCells += `<td style="background:${clr.bg};color:${clr.text};font-weight:600;">${formatted}</td>`;
  }
  rows.push(`<tr style="border-top:2px solid var(--apple-divider);">${annualCells}</tr>`);

  tableBody.innerHTML = rows.join("");

  // Annual note
  let note = $("pcMonthlyBatchNote");
  if (!note) {
    note = document.createElement("div");
    note.id = "pcMonthlyBatchNote";
    table.parentElement.appendChild(note);
  }
  note.style.cssText = "margin-top:8px;font-size:12px;color:var(--apple-text-tertiary);";
  note.textContent = "「全年」为各月涨跌幅复利累计值";

  // Render monthly trend chart (reset hidden state)
  _mChartHidden = [];
  renderMonthlyChart(year, symKeys, monthMap, annualReturns);
}

function renderMonthlyChart(year, symKeys, monthMap, annualReturns) {
  const nameLookup = {};
  for (const s of symbols) nameLookup[s.symbol] = s.name || s.symbol;

  const allSeries = [];
  for (const sym of symKeys) {
    const pts = [];
    for (let m = 1; m <= 12; m++) {
      const val = monthMap[sym][m];
      if (val !== null) pts.push({ month: m, value: val });
    }
    if (pts.length > 0) {
      allSeries.push({ symbol: sym, name: nameLookup[sym] || sym, points: pts });
    }
  }

  if (allSeries.length === 0) return;

  const hiddenSet = new Set(_mChartHidden);
  const visibleSeries = allSeries.filter((_, i) => !hiddenSet.has(i));

  const W = 700, H = 220, PAD = { top: 20, right: 16, bottom: 30, left: 48 };

  const allVals = [];
  visibleSeries.forEach(s => s.points.forEach(p => allVals.push(p.value)));
  if (allVals.length === 0) {
    // All hidden — show empty chart
  }
  const minVal = Math.min(...allVals, 0);
  const maxVal = Math.max(...allVals, 0);
  const range = maxVal - minVal || 1;
  const yMin = minVal - range * 0.1;
  const yMax = maxVal + range * 0.1;
  const yRange = yMax - yMin;
  const cw = W - PAD.left - PAD.right;
  const ch = H - PAD.top - PAD.bottom;
  const xPos = (m) => PAD.left + ((m - 1) / 11) * cw;
  const yPos = (v) => PAD.top + ch - ((v - yMin) / yRange) * ch;

  // Y-axis grid
  const yTicks = 5;
  let yGrid = "";
  for (let i = 0; i <= yTicks; i++) {
    const v = yMin + (yRange * i) / yTicks;
    const y = yPos(v);
    yGrid += `<line x1="${PAD.left}" y1="${y}" x2="${W - PAD.right}" y2="${y}" stroke="var(--apple-divider)" stroke-width="1"/>`;
    yGrid += `<text x="${PAD.left - 6}" y="${y + 4}" text-anchor="end" fill="var(--apple-text-tertiary)" font-size="11">${v.toFixed(1)}%</text>`;
  }
  const zeroY = yPos(0);
  const zeroLine = (zeroY >= PAD.top && zeroY <= H - PAD.bottom)
    ? `<line x1="${PAD.left}" y1="${zeroY}" x2="${W - PAD.right}" y2="${zeroY}" stroke="var(--apple-text-tertiary)" stroke-width="1" stroke-dasharray="4,3" opacity="0.6"/>` : "";

  // X-axis: month labels
  let xLabels = "";
  for (let m = 1; m <= 12; m++) {
    xLabels += `<text x="${xPos(m)}" y="${H - 8}" text-anchor="middle" fill="var(--apple-text-tertiary)" font-size="11">${m}月</text>`;
  }

  // Legend — all series, hidden ones greyed out
  let legend = "";
  allSeries.forEach((series, idx) => {
    const isHidden = hiddenSet.has(idx);
    const color = LINE_COLORS[idx % LINE_COLORS.length];
    const lx = 10 + (idx % 5) * 140;
    const ly = H + 14 + Math.floor(idx / 5) * 18;
    const barOpacity = isHidden ? 0.25 : 1;
    const txtOpacity = isHidden ? 0.3 : 0.85;
    const decoration = isHidden ? "line-through" : "none";
    legend += `<g data-legend="${idx}" style="cursor:pointer;">
      <rect x="${lx - 4}" y="${ly - 14}" width="130" height="22" rx="4" fill="rgba(0,0,0,0.001)"/>
      <rect x="${lx}" y="${ly - 7}" width="10" height="3" rx="1.5" fill="${color}" opacity="${barOpacity}"/>
      <text x="${lx + 14}" y="${ly + 1}" fill="var(--apple-text-secondary)" font-size="11" opacity="${txtOpacity}" text-decoration="${decoration}">${series.name}</text>
    </g>`;
  });

  // Series groups (lines + dots), per-series for hover interaction
  let seriesGroups = "";
  visibleSeries.forEach((series, vi) => {
    const realIdx = allSeries.indexOf(series);
    const color = LINE_COLORS[vi % LINE_COLORS.length];
    let gLines = "", gDots = "";
    for (let i = 0; i < series.points.length - 1; i++) {
      const x1 = xPos(series.points[i].month), y1 = yPos(series.points[i].value);
      const x2 = xPos(series.points[i + 1].month), y2 = yPos(series.points[i + 1].value);
      gLines += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${color}" stroke-width="1.5" stroke-linecap="round" opacity="0.85"/>`;
    }
    series.points.forEach(p => {
      gDots += `<circle cx="${xPos(p.month)}" cy="${yPos(p.value)}" r="2.5" fill="${color}" stroke="var(--apple-bg)" stroke-width="0.8"/>`;
    });
    seriesGroups += `<g id="ms-${realIdx}">${gLines}${gDots}</g>`;
  });

  const svgH = legend ? H + 20 + Math.ceil(allSeries.length / 5) * 18 : H;
  $("pcChartSvg").innerHTML = `<svg viewBox="0 0 ${W} ${svgH}" style="width:100%;height:auto;display:block;">
    ${yGrid} ${zeroLine} ${seriesGroups} ${xLabels} ${legend}
  </svg>`;

  // Update chart header & show
  const titleEl = document.querySelector("#pcChartWrap .pc-chart-title");
  if (titleEl) titleEl.textContent = `${year} 年月度涨跌幅走势`;
  $("pcChartWrap").style.display = "";

  // Attach legend interactions
  const svgEl = $("pcChartSvg").querySelector("svg");
  allSeries.forEach((_, idx) => {
    const g = svgEl?.querySelector(`g[data-legend="${idx}"]`);
    if (!g) return;

    g.addEventListener("click", (e) => {
      e.stopPropagation();
      _mChartHidden = _mChartHidden.includes(idx)
        ? _mChartHidden.filter(i => i !== idx)
        : [..._mChartHidden, idx];
      renderMonthlyChart(year, symKeys, monthMap, annualReturns);
    });

    g.addEventListener("mouseenter", () => {
      allSeries.forEach((_, i) => {
        if (i === idx || _mChartHidden.includes(i)) return;
        const g2 = svgEl?.querySelector(`#ms-${i}`);
        if (g2) g2.style.opacity = "0.12";
      });
    });

    g.addEventListener("mouseleave", () => {
      allSeries.forEach((_, i) => {
        if (_mChartHidden.includes(i)) return;
        const g2 = svgEl?.querySelector(`#ms-${i}`);
        if (g2) g2.style.opacity = "1";
      });
    });
  });
}

function roundTo(val, decimals) {
  const factor = Math.pow(10, decimals);
  return Math.round(val * factor) / factor;
}

// ─── Monthly drilldown card (line chart + monthly grid) ───

async function fetchMonthly(symbol, type, year) {
  try {
    const resp = await fetch(MONTHLY_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, type, year }),
    });
    if (!resp.ok) return;
    const result = await resp.json();
    renderMonthlyCard(symbol, type, year, result.months);
  } catch {
    // silently fail
  }
}

function renderMonthlyCard(symbol, type, year, months) {
  // Build title with display name if available
  const sym = symbols.find((s) => s.symbol === symbol);
  const label = sym && sym.name ? `${symbol}(${sym.name})` : symbol;

  const container = $("pcMonthlyContainer");

  // Create card
  const card = document.createElement("div");
  card.className = "pc-monthly";

  // Header
  const header = document.createElement("div");
  header.className = "pc-monthly-header";
  const title = document.createElement("span");
  title.className = "pc-monthly-title";
  title.textContent = `${label} — ${year} 年月度涨跌幅`;
  const closeBtn = document.createElement("button");
  closeBtn.className = "pc-btn";
  closeBtn.style.cssText = "padding:4px 10px;font-size:12px;";
  closeBtn.textContent = "关闭";
  closeBtn.addEventListener("click", () => card.remove());
  header.appendChild(title);
  header.appendChild(closeBtn);
  card.appendChild(header);

  // Monthly grid
  const grid = document.createElement("div");
  grid.className = "pc-monthly-grid";
  grid.innerHTML = months
    .map((m) => {
      const val = m.return;
      const formatted = val !== null ? formatPct(val) : "—";
      const colors = val !== null ? cellColor(val, -50, 50) : { bg: "var(--apple-surface-2)", text: "var(--apple-text-tertiary)" };
      return `<div class="pc-month-block" style="background:${colors.bg};">
        <div class="pc-month-num">${m.month}月</div>
        <div class="pc-month-val" style="color:${colors.text};">${formatted}</div>
      </div>`;
    })
    .join("");
  card.appendChild(grid);

  container.appendChild(card);

  // Scroll to the new card
  card.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// Table cell click → monthly drilldown
tableBody.addEventListener("click", (e) => {
  const cell = e.target.closest(".pc-cell");
  if (!cell) return;
  const { symbol, year, type } = cell.dataset;
  if (!symbol || !year) return;
  fetchMonthly(symbol, type, parseInt(year, 10));
});

// ─── Backtest (multi-symbol) ───

let _btSymbols = []; // [{symbol, label}, ...]

function renderBtTags() {
  const el = $("btTags");
  if (!el) return;
  if (_btSymbols.length === 0) {
    el.innerHTML = '<span style="color:var(--apple-text-tertiary);font-size:12px;">暂无，请添加</span>';
    return;
  }
  el.innerHTML = _btSymbols
    .map(
      (s, i) =>
        `<span class="pc-tag">
          ${s.label}
          <span class="pc-tag-remove" data-index="${i}">✕</span>
        </span>`
    )
    .join("");
  el.querySelectorAll(".pc-tag-remove").forEach((el2) => {
    el2.addEventListener("click", () => {
      _btSymbols.splice(parseInt(el2.dataset.index, 10), 1);
      renderBtTags();
    });
  });
}

function populateBacktestOptions() {
  if (!_lastYearlyData) return;
  const { years, data } = _lastYearlyData;
  const addSel = $("btAddSelect");
  if (!addSel || !btYear) return;

  // Symbols picker dropdown (for adding)
  const opts = symbols
    .filter((s) => data[s.symbol] && Object.keys(data[s.symbol]).length > 0)
    .map((s) => {
      const label = s.name ? `${s.symbol}(${s.name})` : s.symbol;
      return `<option value="${s.symbol}">${label}</option>`;
    })
    .join("");
  addSel.innerHTML = opts || '<option value="">—</option>';

  // Years
  const sortedYears = [...years].sort((a, b) => a - b);
  btYear.innerHTML = sortedYears
    .filter((y) => y < new Date().getFullYear())
    .map((y) => `<option value="${y}">${y}</option>`)
    .join("");
  if (sortedYears.length > 0) btYear.value = sortedYears[Math.max(0, sortedYears.length - 7)];

  // Add first symbol by default
  if (_btSymbols.length === 0 && addSel.options.length > 0) {
    const v = addSel.value;
    const sym = symbols.find((s) => s.symbol === v);
    if (sym) {
      _btSymbols.push({ symbol: v, label: sym.name ? `${v}(${sym.name})` : v });
      renderBtTags();
    }
  }
}

function addBtSymbol() {
  const sel = $("btAddSelect");
  if (!sel) return;
  const v = sel.value;
  if (!v) return;
  if (_btSymbols.some((s) => s.symbol === v)) return;
  const sym = symbols.find((s) => s.symbol === v);
  const label = sym && sym.name ? `${v}(${sym.name})` : v;
  _btSymbols.push({ symbol: v, label });
  renderBtTags();
}

function runBacktest() {
  if (!_lastYearlyData) return;
  const { data } = _lastYearlyData;
  const amount = parseFloat(btAmount.value) || 0;
  const startYear = parseInt(btYear.value, 10);
  if (_btSymbols.length === 0 || !amount || !startYear) return;

  // Compute portfolio for each symbol
  const results = [];
  let allYearsSet = new Set();

  for (const bs of _btSymbols) {
    const yearlyReturns = data[bs.symbol];
    if (!yearlyReturns) continue;
    const yrs = Object.keys(yearlyReturns)
      .map(Number)
      .filter((y) => y >= startYear)
      .sort((a, b) => a - b);
    if (yrs.length === 0) continue;

    let portfolio = amount;
    const rows = [];
    for (const y of yrs) {
      portfolio = portfolio * (1 + yearlyReturns[y] / 100);
      rows.push({ year: y, value: portfolio });
    }
    results.push({ symbol: bs.symbol, label: bs.label, rows });
    yrs.forEach((y) => allYearsSet.add(y));
  }

  if (results.length === 0) return;

  const allYears = Array.from(allYearsSet).sort((a, b) => a - b);

  // ── Line chart ──
  renderBtChart(results, allYears, amount);

  // ── Summary ──
  btSummary.innerHTML = results
    .map((r) => {
      const finalV = r.rows[r.rows.length - 1].value;
      const profit = finalV - amount;
      const pct = (profit / amount) * 100;
      return `<div class="pc-bt-summary-item">
        <div class="pc-bt-summary-label">${r.label}</div>
        <div class="pc-bt-summary-val ${profit >= 0 ? "bt-val-positive" : "bt-val-negative"}">$${finalV.toFixed(2)} (${profit >= 0 ? "+" : ""}${profit.toFixed(2)}, ${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%)</div>
      </div>`;
    })
    .join("");

  // ── Table ──
  const headCells = ["<th>年份</th>"];
  for (const r of results) {
    headCells.push(`<th>${r.label}<br><span style="font-weight:400;font-size:10px;color:var(--apple-text-tertiary)">涨跌幅</span></th>`);
    headCells.push(`<th>${r.label}<br><span style="font-weight:400;font-size:10px;color:var(--apple-text-tertiary)">市值</span></th>`);
  }
  btHead.innerHTML = headCells.join("");

  btBody.innerHTML = allYears
    .map((y) => {
      let cells = `<td>${y}</td>`;
      for (const r of results) {
        const row = r.rows.find((x) => x.year === y);
        if (row) {
          const ret = (row.value / (r.rows.find((x) => x.year === y - 1)?.value || amount) - 1) * 100;
          const retStr = `${ret >= 0 ? "+" : ""}${ret.toFixed(2)}%`;
          cells += `<td class="${ret >= 0 ? "bt-val-positive" : "bt-val-negative"}">${retStr}</td>`;
          cells += `<td>$${row.value.toFixed(2)}</td>`;
        } else {
          cells += "<td>—</td><td>—</td>";
        }
      }
      return `<tr>${cells}</tr>`;
    })
    .join("");

  if (btResult) btResult.style.display = "";
  if (btWrap) btWrap.style.display = "";
}

function renderBtChart(results, allYears, initialAmount) {
  if (results.length === 0) return;

  // Build a lookup: years → [{symbol, value}, ...]
  const W = 700, H = 220, PAD = { top: 20, right: 16, bottom: 30, left: 56 };

  // Collect all values
  const allVals = [initialAmount];
  for (const r of results) {
    for (const row of r.rows) allVals.push(row.value);
  }
  const minVal = Math.min(...allVals, 0);
  const maxVal = Math.max(...allVals, 0);
  const range = maxVal - minVal || 1;
  const pad = range * 0.1;
  const yMin = minVal - pad;
  const yMax = maxVal + pad;
  const yRange = yMax - yMin;
  const cw = W - PAD.left - PAD.right;
  const ch = H - PAD.top - PAD.bottom;
  const xPos = (y) => PAD.left + ((y - allYears[0]) / (allYears[allYears.length - 1] - allYears[0] || 1)) * cw;
  const yPos = (v) => PAD.top + ch - ((v - yMin) / yRange) * ch;

  // Y-axis grid
  const yTicks = 5;
  let yGrid = "";
  for (let i = 0; i <= yTicks; i++) {
    const v = yMin + (yRange * i) / yTicks;
    const y = yPos(v);
    yGrid += `<line x1="${PAD.left}" y1="${y}" x2="${W - PAD.right}" y2="${y}" stroke="var(--apple-divider)" stroke-width="1"/>`;
    const label = v >= 1000 ? `$${(v / 1000).toFixed(1)}k` : `$${v.toFixed(0)}`;
    yGrid += `<text x="${PAD.left - 6}" y="${y + 4}" text-anchor="end" fill="var(--apple-text-tertiary)" font-size="11">${label}</text>`;
  }

  // Zero line
  const zeroY = yPos(0);
  const zeroLine = (zeroY >= PAD.top && zeroY <= H - PAD.bottom)
    ? `<line x1="${PAD.left}" y1="${zeroY}" x2="${W - PAD.right}" y2="${zeroY}" stroke="var(--apple-text-tertiary)" stroke-width="1" stroke-dasharray="4,3" opacity="0.6"/>`
    : "";

  // X-axis labels
  let xLabels = "";
  if (allYears.length > 1) {
    const step = Math.max(1, Math.floor(allYears.length / 8));
    for (let i = 0; i < allYears.length; i++) {
      if (i % step === 0 || i === allYears.length - 1)
        xLabels += `<text x="${xPos(allYears[i])}" y="${H - 8}" text-anchor="middle" fill="var(--apple-text-tertiary)" font-size="11">${allYears[i]}</text>`;
    }
  }

  // Lines for each result
  const colors = ["#2997ff", "#e8a43e", "#30d158", "#ff453a", "#5ac8fa", "#ff9f0a", "#bf5af2", "#64d2ff"];
  let lines = "", dots = "", legend = "";
  results.forEach((r, idx) => {
    const color = colors[idx % colors.length];
    for (let i = 0; i < r.rows.length - 1; i++) {
      const x1 = xPos(r.rows[i].year), y1 = yPos(r.rows[i].value);
      const x2 = xPos(r.rows[i + 1].year), y2 = yPos(r.rows[i + 1].value);
      lines += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${color}" stroke-width="1.5" stroke-linecap="round" opacity="0.85"/>`;
    }
    r.rows.forEach((row) => {
      dots += `<circle cx="${xPos(row.year)}" cy="${yPos(row.value)}" r="2.5" fill="${color}" stroke="var(--apple-bg)" stroke-width="0.8"/>`;
    });
    const lx = 10 + (idx % 4) * 175;
    const ly = H + 12 + Math.floor(idx / 4) * 18;
    legend += `<rect x="${lx}" y="${ly - 8}" width="10" height="3" rx="1.5" fill="${color}" opacity="0.85"/>`;
    legend += `<text x="${lx + 14}" y="${ly}" fill="var(--apple-text-secondary)" font-size="11">${r.label}</text>`;
  });

  const svgH = legend ? H + 20 + Math.ceil(results.length / 4) * 18 : H;
  $("btChart").innerHTML = `<svg viewBox="0 0 ${W} ${svgH}" style="width:100%;height:auto;display:block;">
    ${yGrid} ${zeroLine} ${lines} ${dots} ${xLabels} ${legend}
  </svg>`;
}

// ─── Init ───

async function init() {
  // Load config (presets + color range)
  const cfg = await loadConfigFromServer();
  PRESETS = cfg.presets;
  minRange.value = cfg.colorRange.min;
  maxRange.value = cfg.colorRange.max;

  // Add button
  addBtn.addEventListener("click", () => {
    addSymbol(symInput.value, typeSelect.value);
  });

  symInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") addSymbol(symInput.value, typeSelect.value);
  });

  clearBtn.addEventListener("click", () => {
    symbols = [];
    renderTags();
    const mc = $("pcMonthlyContainer");
    if (mc) mc.innerHTML = "";
    $("pcChartWrap").style.display = "none";
    _chartData = null;
    _chartSymbols = null;
    _chartHidden = [];
    _lastYearlyData = null;
    if (yearSelect) yearSelect.value = "";
    renderMetaInfo(null);
    table.style.display = "none";
    empty.style.display = "block";
  });

  refreshBtn.addEventListener("click", fetchData);

  // Chart close button
  $("pcChartClose").addEventListener("click", () => {
    $("pcChartWrap").style.display = "none";
  });

  // Backtest buttons
  if (btRun) btRun.addEventListener("click", runBacktest);
  const _btAddBtn = $("btAddBtn");
  if (_btAddBtn) _btAddBtn.addEventListener("click", addBtSymbol);
  if (btClose) btClose.addEventListener("click", () => {
    btWrap.style.display = "none";
    btResult.style.display = "none";
  });

  // Populate year options and set default
  populateYearOptions();

  // Year select: Enter triggers query, Escape reverts to "历年汇总"
  if (yearSelect) {
    yearSelect.addEventListener("keydown", (e) => {
      if (e.key === "Enter") fetchData();
      if (e.key === "Escape") { yearSelect.value = ""; fetchData(); }
    });
  }

  // Render preset chips after loading presets
  renderPresetChips();

  // Enter key also triggers search in min/max fields
  minRange.addEventListener("keydown", (e) => { if (e.key === "Enter") fetchData(); });
  maxRange.addEventListener("keydown", (e) => { if (e.key === "Enter") fetchData(); });

  // Check backend health
  fetch(`${API_BASE}/api/health`)
    .then((r) => r.ok && setConnected(true))
    .catch(() => setConnected(false));
}

document.addEventListener("DOMContentLoaded", init);
