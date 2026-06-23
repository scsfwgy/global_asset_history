/**
 * Heatmap (treemap) tab — strip treemap of asset returns.
 *
 * Block size ∝ chosen dimension (turnover / market cap / |return|),
 * color ∝ price change %.  Text is always white; red/green follows the
 * global color-scheme setting.  Hand-crafted SVG, consistent with the
 * project's charting philosophy.
 */

// ─── Independent state ───
var _hmSymbols = [];
var _hmLastData = null;
var _hmLastFetchTime = null;
var _hmLastSymbolKeys = "";
var _hmInitialFetchDone = false;
var _hmSizeBy = "turnover";
var _hmForceRefresh = false;
const HM_STORAGE_KEY = "gah_heatmap_state";

// ─── DOM refs ───
const hmFilterToggle = document.getElementById("hmFilterToggle");
const hmFilterPanel = document.getElementById("hmFilterPanel");
const hmSymInput = document.getElementById("hmSymbolInput");
const hmTypeSelect = document.getElementById("hmTypeSelect");
const hmAddBtn = document.getElementById("hmAddBtn");
const hmClearBtn = document.getElementById("hmClearBtn");
const hmPeriod = document.getElementById("hmPeriod");
const hmSizeBySel = document.getElementById("hmSizeBy");
const hmRefreshBtn = document.getElementById("hmRefreshBtn");
const hmForceBtn = document.getElementById("hmForceBtn");
const hmTopN = document.getElementById("hmTopN");
const hmTags = document.getElementById("hmTags");
const hmError = document.getElementById("hmError");
const hmLoading = document.getElementById("hmLoading");
const hmTreemapWrap = document.getElementById("hmTreemapWrap");
const hmTreemapSvg = document.getElementById("hmTreemapSvg");
const hmEmpty = document.getElementById("hmEmpty");
const hmLegend = document.getElementById("hmLegend");
const hmFreshness = document.getElementById("hmFreshness");

// ─── HTML tooltip overlay ───
var hmTooltipEl = document.createElement("div");
hmTooltipEl.className = "hm-tooltip";
hmTooltipEl.style.display = "none";
document.body.appendChild(hmTooltipEl);

// ─── Helpers ───

function hmSetLoading(on) {
  hmLoading.style.display = on ? "flex" : "none";
  if (on) {
    hmError.style.display = "none";
    hmEmpty.style.display = "none";
    hmTreemapWrap.style.display = "none";
  }
}

function hmShowError(msg) {
  hmError.style.display = msg ? "block" : "none";
  hmError.textContent = msg || "";
}

function hmUpdateFreshness() {
  if (!hmFreshness) return;
  if (!_hmLastFetchTime) { hmFreshness.style.display = "none"; return; }
  var diffMs = Date.now() - _hmLastFetchTime;
  var diffMin = Math.floor(diffMs / 60000);
  var text;
  if (diffMin < 1) text = __("status.justNow");
  else if (diffMin < 60) text = __("status.minutesAgo", {n: diffMin});
  else { var hrs = Math.floor(diffMin / 60); text = __("status.hoursAgo", {n: hrs}); }
  hmFreshness.textContent = "· " + text;
  hmFreshness.className = "pc-freshness" + (diffMin > 30 ? " stale" : "");
  hmFreshness.style.display = "";
}

function hmDisplayName(s) {
  return s.name ? s.symbol + "(" + s.name + ")" : s.symbol;
}

// ─── Tags ───

function renderHmTags() {
  if (!hmTags) return;
  if (_hmSymbols.length === 0) {
    hmTags.innerHTML = '<span style="color:var(--apple-text-tertiary);font-size:12px;">' + __("yearly.noSymbols") + '</span>';
    return;
  }
  hmTags.innerHTML = _hmSymbols
    .map(function (s, i) {
      var typeLabel = s.type === "crypto" ? __("yearly.labelCrypto") : s.type === "cn_stock" ? __("yearly.labelA") : __("yearly.labelStock");
      return '<span class="pc-tag">' +
        escapeHtml(hmDisplayName(s)) +
        '<span class="pc-tag-type">' + typeLabel + '</span>' +
        '<span class="pc-tag-remove" data-index="' + i + '">✕</span>' +
        '</span>';
    })
    .join("");

  hmTags.querySelectorAll(".pc-tag-remove").forEach(function (el) {
    el.addEventListener("click", function () {
      var idx = parseInt(el.dataset.index, 10);
      _hmSymbols.splice(idx, 1);
      renderHmTags();
      saveHmState();
    });
  });
}

function hmAddSymbol(symbol, type) {
  var sym = symbol.trim().toUpperCase();
  if (!sym) return false;
  if (_hmSymbols.some(function (s) { return s.symbol === sym && s.type === type; })) return false;
  _hmSymbols.push({ symbol: sym, type: type });
  renderHmTags();
  hmSymInput.value = "";
  hmSymInput.focus();
  saveHmState();
  fetchHeatmap();
  return true;
}

// ─── State persistence ───

function saveHmState() {
  try {
    var state = {
      symbols: _hmSymbols.map(function (s) { return { symbol: s.symbol, type: s.type, name: s.name || null }; }),
      period: hmPeriod ? hmPeriod.value : "week",
      topN: hmTopN ? hmTopN.value : "20",
      sizeBy: _hmSizeBy,
    };
    localStorage.setItem(HM_STORAGE_KEY, JSON.stringify(state));
  } catch (_) { /* ignore */ }
}

function restoreHmState() {
  try {
    var raw = localStorage.getItem(HM_STORAGE_KEY);
    if (!raw) return false;
    var state = JSON.parse(raw);
    if (state.symbols && Array.isArray(state.symbols)) _hmSymbols = state.symbols;
    if (state.period && hmPeriod) hmPeriod.value = state.period;
    if (state.topN && hmTopN) hmTopN.value = state.topN;
    if (state.sizeBy && hmSizeBySel) { _hmSizeBy = state.sizeBy; hmSizeBySel.value = state.sizeBy; }
    return _hmSymbols.length > 0;
  } catch (_) {
    return false;
  }
}

// ─── Responsive dimensions ───

function hmGetDims() {
  var cw = hmTreemapWrap.clientWidth || 1000;
  var isMobile = cw < 640;
  var vbW = isMobile ? 640 : 1280;
  // Desktop: wide + tall (0.6 ratio). Mobile: near-square portrait for legible blocks.
  var aspect = isMobile ? 0.95 : 0.58;
  var vbH = Math.round(vbW * aspect);
  return { w: vbW, h: vbH, isMobile: isMobile };
}

// ─── Size weight ───

function hmWeight(d) {
  if (_hmSizeBy === "market_cap") return (d.market_cap && d.market_cap > 0) ? d.market_cap : 0;
  if (_hmSizeBy === "return") return d.return_pct != null ? Math.abs(d.return_pct) : 0;
  return (d.turnover && d.turnover > 0) ? d.turnover : 0;
}

// ─── Strip Treemap Layout ───

function layoutStripTreemap(items, x, y, w, h) {
  if (!items.length || w <= 0 || h <= 0) return [];

  var totalWeight = 0;
  var normalized = items.map(function (it) {
    var wt = it.weight || 0;
    totalWeight += wt;
    return { item: it, weight: wt };
  });

  if (totalWeight === 0) {
    normalized.forEach(function (n) { n.weight = 1; });
    totalWeight = normalized.length;
  }

  var n = normalized.length;
  var targetRows = n <= 4 ? 2 : n <= 8 ? Math.max(3, Math.round(n / 2)) : Math.min(8, Math.round(n / 2.5));
  targetRows = Math.min(targetRows, Math.floor(n / 2));
  targetRows = Math.max(targetRows, 1);

  var targetRowWeight = totalWeight / targetRows;
  var rows = [];
  var currentRow = [];
  var currentSum = 0;

  for (var i = 0; i < normalized.length; i++) {
    currentRow.push(normalized[i]);
    currentSum += normalized[i].weight;
    var remainingItems = normalized.length - i - 1;
    var remainingRows = targetRows - rows.length - 1;
    if (currentSum >= targetRowWeight && remainingItems >= remainingRows && rows.length < targetRows - 1) {
      rows.push({ items: currentRow, sum: currentSum });
      currentRow = [];
      currentSum = 0;
    }
  }
  if (currentRow.length > 0) rows.push({ items: currentRow, sum: currentSum });

  var result = [];
  var cy = y;
  for (var r = 0; r < rows.length; r++) {
    var row = rows[r];
    var rowHeight = Math.max(h * (row.sum / totalWeight), 26);
    var cx = x;
    for (var j = 0; j < row.items.length; j++) {
      var itemW = Math.max(w * (row.items[j].weight / row.sum), w * 0.025);
      result.push({ x: cx, y: cy, w: itemW, h: rowHeight, item: row.items[j].item });
      cx += itemW;
    }
    cy += rowHeight;
  }
  return result;
}

// ─── Color Mapping (all-white text; hue follows color scheme) ───

function hmColor(returnPct, maxAbs) {
  var isRedUp = (typeof window.getColorScheme === 'function' && window.getColorScheme() === 'red_up');
  var posHue = isRedUp ? 4 : 142;
  var negHue = isRedUp ? 142 : 4;

  if (returnPct == null || isNaN(returnPct) || maxAbs === 0) {
    return { bg: "rgba(140,140,150,0.30)", text: "#fff" };
  }

  var raw = Math.min(Math.abs(returnPct) / maxAbs, 1);
  var intensity = Math.pow(raw, 0.45);          // amplify small moves
  var hue = returnPct >= 0 ? posHue : negHue;
  var lightness = 48 - intensity * 24;           // 48% → 24% (always dark enough for white)
  var saturation = 70 + intensity * 25;          // 70 → 95
  var alpha = 0.62 + intensity * 0.38;           // 0.62 → 1.0

  return {
    bg: "hsla(" + hue + ", " + Math.round(saturation) + "%, " + Math.round(lightness) + "%, " + alpha.toFixed(3) + ")",
    text: "#fff",
  };
}

// ─── Formatting ───

function hmFormatPct(val) {
  if (val == null || isNaN(val)) return "—";
  var sign = val > 0 ? "+" : "";
  return sign + val.toFixed(2) + "%";
}

function hmFormatBig(val) {
  if (val == null || isNaN(val)) return "—";
  if (val >= 1e12) return (val / 1e12).toFixed(2) + "T";
  if (val >= 1e9) return (val / 1e9).toFixed(2) + "B";
  if (val >= 1e6) return (val / 1e6).toFixed(2) + "M";
  if (val >= 1e3) return (val / 1e3).toFixed(2) + "K";
  return val.toFixed(0);
}

// ─── SVG Rendering ───

function renderTreemap(result, animate) {
  var data = result.data;
  if (!data || !data.length) {
    hmEmpty.style.display = "block";
    hmTreemapWrap.style.display = "none";
    return;
  }

  var valid = data.filter(function (d) { return d.return_pct != null; });
  if (!valid.length) {
    hmEmpty.innerHTML = "<div>" + __("heatmap.errorNoData") + "</div>";
    hmEmpty.style.display = "block";
    hmTreemapWrap.style.display = "none";
    return;
  }

  hmEmpty.style.display = "none";
  hmTreemapWrap.style.display = "";

  // Container-level entrance animation on fresh data (complements cell cascade)
  if (animate) {
    hmTreemapWrap.classList.remove("hm-entering");
    void hmTreemapWrap.offsetWidth; // force reflow to restart animation
    hmTreemapWrap.classList.add("hm-entering");
  }

  // Attach weight + sort by chosen dimension
  var prepared = valid.map(function (d) {
    return Object.assign({}, d, { weight: hmWeight(d) });
  });
  prepared.sort(function (a, b) { return b.weight - a.weight; });

  var maxAbs = 0;
  prepared.forEach(function (d) { if (d.return_pct != null) maxAbs = Math.max(maxAbs, Math.abs(d.return_pct)); });
  if (maxAbs === 0) maxAbs = 5;

  var dims = hmGetDims();
  var svgW = dims.w, svgH = dims.h, pad = 4, gap = 3;
  var rects = layoutStripTreemap(prepared, pad, pad, svgW - pad * 2, svgH - pad * 2);

  hmTreemapSvg.setAttribute("viewBox", "0 0 " + svgW + " " + svgH);

  var svgParts = [];
  svgParts.push('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + svgW + ' ' + svgH + '" class="hm-treemap-svg-inner">');

  var tooltipData = {};

  for (var i = 0; i < rects.length; i++) {
    var r = rects[i];
    var d = r.item;
    var color = hmColor(d.return_pct, maxAbs);
    var rx = r.x + gap / 2;
    var ry = r.y + gap / 2;
    var rw = Math.max(r.w - gap, 2);
    var rh = Math.max(r.h - gap, 2);
    var delay = animate ? Math.min(i * 24, 600) : 0;

    svgParts.push('<rect class="hm-cell" id="hm-cell-' + i + '"');
    svgParts.push(' x="' + rx.toFixed(1) + '" y="' + ry.toFixed(1) + '"');
    svgParts.push(' width="' + rw.toFixed(1) + '" height="' + rh.toFixed(1) + '"');
    svgParts.push(' rx="6" fill="' + color.bg + '"');
    if (animate) svgParts.push(' style="animation-delay:' + delay + 'ms"');
    svgParts.push('/>');

    // Labels (3 tiers) — always white
    var minW = d.symbol.length * 7.4 + 16;
    if (rw >= minW && rh >= 22) {
      var isLarge = rw >= 130 && rh >= 52;
      var isMedium = rw >= 72 && rh >= 36;
      var cx = rx + rw / 2;
      var labelDelay = animate ? (delay + 90) : 0;
      var labelStyle = animate ? (' style="animation-delay:' + labelDelay + 'ms"') : '';

      if (isLarge) {
        svgParts.push('<text x="' + cx.toFixed(1) + '" y="' + (ry + rh * 0.36).toFixed(1) + '" text-anchor="middle" dominant-baseline="middle" font-size="15" font-weight="700" fill="#fff" class="hm-label"' + labelStyle + '>' + escapeHtml(d.symbol) + '</text>');
        svgParts.push('<text x="' + cx.toFixed(1) + '" y="' + (ry + rh * 0.64).toFixed(1) + '" text-anchor="middle" dominant-baseline="middle" font-size="13" font-weight="600" fill="#fff" class="hm-label"' + labelStyle + '>' + escapeHtml(hmFormatPct(d.return_pct)) + '</text>');
      } else if (isMedium) {
        svgParts.push('<text x="' + cx.toFixed(1) + '" y="' + (ry + rh * 0.38).toFixed(1) + '" text-anchor="middle" dominant-baseline="middle" font-size="12" font-weight="700" fill="#fff" class="hm-label"' + labelStyle + '>' + escapeHtml(d.symbol) + '</text>');
        svgParts.push('<text x="' + cx.toFixed(1) + '" y="' + (ry + rh * 0.70).toFixed(1) + '" text-anchor="middle" dominant-baseline="middle" font-size="10" font-weight="500" fill="#fff" fill-opacity="0.92" class="hm-label"' + labelStyle + '>' + escapeHtml(hmFormatPct(d.return_pct)) + '</text>');
      } else {
        svgParts.push('<text x="' + cx.toFixed(1) + '" y="' + (ry + rh / 2).toFixed(1) + '" text-anchor="middle" dominant-baseline="central" font-size="10" font-weight="600" fill="#fff" class="hm-label"' + labelStyle + '>' + escapeHtml(d.symbol) + '</text>');
      }
    }

    tooltipData[i] = d;
  }

  svgParts.push('</svg>');
  hmTreemapSvg.innerHTML = svgParts.join("");

  // Hover → HTML tooltip
  for (var i = 0; i < rects.length; i++) {
    (function (idx) {
      var cell = hmTreemapSvg.querySelector("#hm-cell-" + idx);
      if (!cell) return;
      cell.addEventListener("mousemove", function (e) { hmShowTooltip(e, tooltipData[idx]); });
      cell.addEventListener("mouseleave", hmHideTooltip);
    })(i);
  }

  renderHmLegend(maxAbs, prepared);
}

// ─── Tooltip ───

function hmShowTooltip(evt, d) {
  if (!d) return;
  var retCls = d.return_pct >= 0 ? "hm-tt-up" : "hm-tt-down";
  var nameLine = d.name ? escapeHtml(d.name) : "";
  var rows = "";
  rows += '<div class="hm-tt-row"><span class="hm-tt-label">' + __("heatmap.tooltipReturn") + '</span><span class="hm-tt-val ' + retCls + '">' + hmFormatPct(d.return_pct) + '</span></div>';
  rows += '<div class="hm-tt-row"><span class="hm-tt-label">' + __("heatmap.tooltipTurnover") + '</span><span class="hm-tt-val">' + hmFormatBig(d.turnover) + " " + (d.turnover_currency || "") + '</span></div>';
  if (d.market_cap != null) {
    rows += '<div class="hm-tt-row"><span class="hm-tt-label">' + __("heatmap.tooltipMarketCap") + '</span><span class="hm-tt-val">$' + hmFormatBig(d.market_cap) + '</span></div>';
  }
  hmTooltipEl.innerHTML =
    '<div class="hm-tt-sym">' + escapeHtml(d.symbol) + (nameLine ? ' <span class="hm-tt-name">' + nameLine + '</span>' : '') + '</div>' +
    rows;

  hmTooltipEl.style.display = "block";
  // Position near cursor, clamped to viewport
  var ttW = hmTooltipEl.offsetWidth, ttH = hmTooltipEl.offsetHeight;
  var tx = evt.clientX + 14;
  var ty = evt.clientY - ttH - 12;
  if (tx + ttW > window.innerWidth - 8) tx = evt.clientX - ttW - 14;
  if (ty < 8) ty = evt.clientY + 16;
  hmTooltipEl.style.left = tx + "px";
  hmTooltipEl.style.top = ty + "px";
}

function hmHideTooltip() {
  hmTooltipEl.style.display = "none";
}

// ─── Legend ───

function renderHmLegend(maxAbs, prepared) {
  if (!hmLegend) return;
  hmLegend.style.display = "flex";

  var gradientStops = [];
  for (var s = 0; s <= 10; s++) {
    var t = s / 10;
    var pct = (t - 0.5) * 2 * maxAbs;
    gradientStops.push(hmColor(pct, maxAbs).bg + " " + (t * 100) + "%");
  }

  var sizeLabel = _hmSizeBy === "market_cap" ? __("heatmap.sizeByMarketCap")
    : _hmSizeBy === "return" ? __("heatmap.sizeByReturn") : __("heatmap.sizeByTurnover");

  var noData = prepared.every(function (d) { return !d.weight; });

  var html = '<span class="hm-legend-seg">' + __("heatmap.legendLeft") + '</span>';
  html += '<div class="hm-legend-gradient" style="background:linear-gradient(to right,' + gradientStops.join(",") + ');"></div>';
  html += '<span class="hm-legend-seg">' + __("heatmap.legendRight") + '</span>';
  html += '<span class="hm-legend-sep">·</span>';
  html += '<span class="hm-legend-seg">' + __("heatmap.legendSizeHint") + ' ' + sizeLabel + '</span>';
  if (noData) {
    html += '<span class="hm-legend-sep">·</span>';
    html += '<span class="hm-legend-seg">' + __("heatmap.legendNoData") + '</span>';
  }
  hmLegend.innerHTML = html;
}

// ─── Data Fetching ───

function needMarketCap() { return _hmSizeBy === "market_cap"; }

function hasMarketCapData() {
  return _hmLastData && _hmLastData.data && _hmLastData.data.some(function (d) { return d.market_cap != null; });
}

async function fetchHeatmap() {
  var autoN = parseInt(hmTopN.value, 10) || 20;
  if (_hmSymbols.length === 0 && autoN <= 0) {
    hmShowError(__("heatmap.errorNoSymbols"));
    hmEmpty.style.display = "block";
    hmTreemapWrap.style.display = "none";
    return;
  }

  hmShowError(null);
  hmSetLoading(true);

  var period = hmPeriod ? hmPeriod.value : "week";

  try {
    var body = { symbols: _hmSymbols, period: period, auto_top_n: autoN, include_market_cap: needMarketCap() };
    if (_hmForceRefresh) { body.force = true; _hmForceRefresh = false; }
    var resp = await fetch(HEATMAP_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!resp.ok) {
      var err = await resp.json().catch(function () { return {}; });
      throw new Error(err.error || "HTTP " + resp.status);
    }

    var result = await resp.json();
    _hmLastData = result;
    _hmLastFetchTime = Date.now();
    _hmLastSymbolKeys = _hmSymbols.map(function (s) { return s.symbol + "|" + s.type; }).sort().join(",");
    hmUpdateFreshness();
    saveHmState();
    renderTreemap(result, true);
  } catch (e) {
    hmShowError(__("heatmap.errorRequest") + " " + e.message);
    hmEmpty.style.display = "block";
    hmTreemapWrap.style.display = "none";
  } finally {
    hmSetLoading(false);
  }
}

// Re-render from cached data without refetching (used on size-by / resize).
function rerender() {
  if (_hmLastData) renderTreemap(_hmLastData, false);
}

// ─── Init ───

var _hmResizeTimer;
async function initHeatmap() {
  if (!hmRefreshBtn || !hmPeriod) return;

  hmFilterToggle.addEventListener("click", function () {
    var isOpen = hmFilterPanel.style.display !== "none";
    hmFilterPanel.style.display = isOpen ? "none" : "block";
    var arrow = hmFilterToggle.querySelector(".hm-filter-arrow");
    if (arrow) arrow.textContent = isOpen ? "▸" : "▾";
  });

  restoreHmState();
  renderHmTags();
  if (!hmPeriod.value) hmPeriod.value = "week";

  hmAddBtn.addEventListener("click", function () { hmAddSymbol(hmSymInput.value, hmTypeSelect.value); });
  hmSymInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter") hmAddSymbol(hmSymInput.value, hmTypeSelect.value);
  });

  hmClearBtn.addEventListener("click", function () {
    _hmSymbols = [];
    renderHmTags();
    _hmLastData = null;
    _hmLastFetchTime = null;
    _hmLastSymbolKeys = "";
    _hmInitialFetchDone = false;
    saveHmState();
    hmUpdateFreshness();
    hmEmpty.style.display = "block";
    hmTreemapWrap.style.display = "none";
    fetchHeatmap();
  });

  hmRefreshBtn.addEventListener("click", function () { _hmForceRefresh = false; fetchHeatmap(); });
  hmForceBtn.addEventListener("click", function () { _hmForceRefresh = true; fetchHeatmap(); });

  hmPeriod.addEventListener("change", function () { saveHmState(); fetchHeatmap(); });
  hmTopN.addEventListener("change", function () { saveHmState(); fetchHeatmap(); });

  // Size-by: re-render locally when possible, fetch only for market_cap w/o data
  hmSizeBySel.addEventListener("change", function () {
    _hmSizeBy = hmSizeBySel.value;
    saveHmState();
    if (_hmSizeBy === "market_cap" && !hasMarketCapData()) {
      fetchHeatmap();
    } else {
      rerender();
    }
  });

  // Re-render when switching to heatmap tab (dimensions may have changed)
  document.querySelectorAll('.tab-btn[data-tab="heatmap"]').forEach(function (btn) {
    btn.addEventListener("click", function () {
      renderHmTags();
      var currentKeys = _hmSymbols.map(function (s) { return s.symbol + "|" + s.type; }).sort().join(",");
      if (!_hmInitialFetchDone) {
        fetchHeatmap();
      } else if (_hmSymbols.length > 0 && currentKeys !== _hmLastSymbolKeys) {
        fetchHeatmap();
      } else {
        // Just re-layout at current dimensions
        setTimeout(rerender, 0);
      }
    });
  });

  // Responsive: re-layout on resize
  window.addEventListener("resize", function () {
    clearTimeout(_hmResizeTimer);
    _hmResizeTimer = setTimeout(rerender, 180);
  });
  window.addEventListener("scroll", hmHideTooltip, { passive: true });

  fetchHeatmap();
  _hmInitialFetchDone = true;
}

// Wait for DOM and i18n
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initHeatmap);
} else {
  var _hmPoll = setInterval(function () {
    if (typeof __ === "function" && __("heatmap.query") !== "[heatmap.query]") {
      clearInterval(_hmPoll);
      initHeatmap();
    }
  }, 50);
  setTimeout(function () { clearInterval(_hmPoll); initHeatmap(); }, 2000);
}
