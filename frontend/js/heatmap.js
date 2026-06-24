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
const hmStats = document.getElementById("hmStats");

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
  _hmSymbols.unshift({ symbol: sym, type: type }); // insert at first position
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
      period: hmPeriod ? hmPeriod.value : "today",
      topN: hmTopN ? hmTopN.value : "60",
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

// ─── Squarified Treemap Layout ───
//
// Bruls/Huizing/van Wijk squarified algorithm: keeps tiles as close to square
// as possible, giving the regular mosaic look of pro market heatmaps instead of
// the top-heavy banner that a row-strip layout produces. Items must be sorted
// by weight descending before calling.

function _hmWorstRatio(row, rowSum, side) {
  // side = the fixed length of the current strip; returns worst aspect ratio.
  var max = -Infinity, min = Infinity;
  for (var i = 0; i < row.length; i++) {
    var w = row[i].weight;
    if (w > max) max = w;
    if (w < min) min = w;
  }
  var s2 = rowSum * rowSum;
  var side2 = side * side;
  return Math.max((side2 * max) / s2, s2 / (side2 * min));
}

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

  // Scale weights to area (w*h) so geometry math is in pixel² units.
  var area = w * h;
  var scale = area / totalWeight;
  normalized.forEach(function (n) { n.weight = n.weight * scale; });

  var result = [];
  // Free rectangle we keep carving strips off of.
  var rx = x, ry = y, rw = w, rh = h;
  var idx = 0;
  var n = normalized.length;

  while (idx < n) {
    var shortSide = Math.min(rw, rh);
    var row = [normalized[idx]];
    var rowSum = normalized[idx].weight;
    var worst = _hmWorstRatio(row, rowSum, shortSide);
    var next = idx + 1;

    // Grow the strip while it keeps tiles squarer.
    while (next < n) {
      var trySum = rowSum + normalized[next].weight;
      var tryRow = row.concat([normalized[next]]);
      var tryWorst = _hmWorstRatio(tryRow, trySum, shortSide);
      if (tryWorst > worst) break;
      row = tryRow; rowSum = trySum; worst = tryWorst; next++;
    }

    // Lay the strip along the shorter side, stacked on the longer side.
    var stripThick = rowSum / shortSide;
    if (rw <= rh) {
      // strip is a row across the top, height = stripThick
      var cx = rx;
      for (var i = 0; i < row.length; i++) {
        var cw = row[i].weight / stripThick;
        result.push({ x: cx, y: ry, w: cw, h: stripThick, item: row[i].item });
        cx += cw;
      }
      ry += stripThick; rh -= stripThick;
    } else {
      // strip is a column down the left, width = stripThick
      var cy = ry;
      for (var j = 0; j < row.length; j++) {
        var ch = row[j].weight / stripThick;
        result.push({ x: rx, y: cy, w: stripThick, h: ch, item: row[j].item });
        cy += ch;
      }
      rx += stripThick; rw -= stripThick;
    }
    idx = next;
  }

  return result;
}

// ─── Color Mapping (all-white text; hue follows color scheme) ───
//
// Discrete 5-stop palettes interpolated in RGB — keeps deep cells "vivid red"
// instead of the muddy maroon a raw HSL ramp produces, and pins near-zero to a
// clean neutral slate instead of a washed-out pink. Mirrors the look of
// professional market heatmaps (Finviz / TradingView).

var HM_NEUTRAL = [108, 112, 122];               // near-zero slate (dead zone)
// 0% (light) → 100% (deep) intensity. Greens & reds tuned to stay luminous.
var HM_GREEN_RAMP = [
  [86, 196, 120], [55, 178, 96], [34, 158, 78], [22, 134, 66], [16, 110, 56],
];
var HM_RED_RAMP = [
  [233, 110, 104], [222, 78, 72], [206, 52, 50], [183, 38, 40], [156, 30, 34],
];
var HM_DEAD_ZONE = 0.3;                          // |return%| below this = neutral

function _hmLerp(a, b, t) { return a + (b - a) * t; }

function _hmRampColor(ramp, intensity) {
  // intensity 0..1 → blend from neutral (at 0) through the ramp stops.
  if (intensity <= 0) return HM_NEUTRAL.slice();
  var stops = [HM_NEUTRAL].concat(ramp);         // anchor low end at neutral
  var seg = (stops.length - 1) * Math.min(intensity, 1);
  var lo = Math.floor(seg);
  var hi = Math.min(lo + 1, stops.length - 1);
  var t = seg - lo;
  return [
    _hmLerp(stops[lo][0], stops[hi][0], t),
    _hmLerp(stops[lo][1], stops[hi][1], t),
    _hmLerp(stops[lo][2], stops[hi][2], t),
  ];
}

function hmColor(returnPct, maxAbs) {
  var isRedUp = (typeof window.getColorScheme === 'function' && window.getColorScheme() === 'red_up');

  if (returnPct == null || isNaN(returnPct) || maxAbs === 0) {
    return { bg: "rgb(" + HM_NEUTRAL.join(",") + ")", text: "#fff" };
  }

  var abs = Math.abs(returnPct);
  if (abs < HM_DEAD_ZONE) {
    return { bg: "rgb(" + HM_NEUTRAL.join(",") + ")", text: "#fff" };
  }

  var raw = Math.min(abs / maxAbs, 1);
  var intensity = Math.pow(raw, 0.55);           // gently amplify small moves
  var isUp = returnPct >= 0;
  var useGreen = isUp ? !isRedUp : isRedUp;
  var rgb = _hmRampColor(useGreen ? HM_GREEN_RAMP : HM_RED_RAMP, intensity);

  return {
    bg: "rgb(" + Math.round(rgb[0]) + "," + Math.round(rgb[1]) + "," + Math.round(rgb[2]) + ")",
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
  var svgW = dims.w, svgH = dims.h, pad = 5, gap = 4;
  var rects = layoutStripTreemap(prepared, pad, pad, svgW - pad * 2, svgH - pad * 2);

  hmTreemapSvg.setAttribute("viewBox", "0 0 " + svgW + " " + svgH);

  var svgParts = [];
  svgParts.push('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + svgW + ' ' + svgH + '" class="hm-treemap-svg-inner">');

  // Defs: top sheen overlay (volume) + drop shadow for label legibility.
  svgParts.push('<defs>');
  svgParts.push('<linearGradient id="hmSheen" x1="0" y1="0" x2="0" y2="1">');
  svgParts.push('<stop offset="0%" stop-color="#fff" stop-opacity="0.14"/>');
  svgParts.push('<stop offset="42%" stop-color="#fff" stop-opacity="0.03"/>');
  svgParts.push('<stop offset="100%" stop-color="#000" stop-opacity="0.12"/>');
  svgParts.push('</linearGradient>');
  svgParts.push('<filter id="hmLabelShadow" x="-20%" y="-20%" width="140%" height="140%">');
  svgParts.push('<feDropShadow dx="0" dy="0.6" stdDeviation="0.7" flood-color="#000" flood-opacity="0.45"/>');
  svgParts.push('</filter>');
  svgParts.push('</defs>');

  var tooltipData = {};

  for (var i = 0; i < rects.length; i++) {
    var r = rects[i];
    var d = r.item;
    var color = hmColor(d.return_pct, maxAbs);
    var rx = r.x + gap / 2;
    var ry = r.y + gap / 2;
    var rw = Math.max(r.w - gap, 2);
    var rh = Math.max(r.h - gap, 2);
    var delay = animate ? Math.min(i * 22, 600) : 0;
    var radius = Math.min(6, rw / 2, rh / 2);

    // Group so fill, sheen and labels pop together as one tile.
    var gStyle = animate ? (' style="animation-delay:' + delay + 'ms"') : '';
    svgParts.push('<g class="hm-cell" id="hm-cell-' + i + '"' + gStyle);
    svgParts.push(' data-symbol="' + escapeHtml(d.symbol) + '" data-type="' + escapeHtml(d.type) + '" data-name="' + escapeHtml(d.name || '') + '">');

    var rectAttrs = ' x="' + rx.toFixed(1) + '" y="' + ry.toFixed(1) + '"' +
      ' width="' + rw.toFixed(1) + '" height="' + rh.toFixed(1) + '" rx="' + radius.toFixed(1) + '"';
    // Base fill
    svgParts.push('<rect' + rectAttrs + ' fill="' + color.bg + '"/>');
    // Top sheen → volume
    svgParts.push('<rect' + rectAttrs + ' fill="url(#hmSheen)"/>');
    // Inner hairline stroke → crisp edge
    svgParts.push('<rect' + rectAttrs + ' fill="none" stroke="rgba(255,255,255,0.10)" stroke-width="1"/>');

    // Labels (3 tiers) — always white, shadowed for legibility
    var minW = d.symbol.length * 7.4 + 16;
    if (rw >= minW && rh >= 22) {
      var isLarge = rw >= 130 && rh >= 52;
      var isMedium = rw >= 72 && rh >= 36;
      var cx = rx + rw / 2;
      var labelDelay = animate ? (delay + 90) : 0;
      var labelStyle = animate ? (' style="animation-delay:' + labelDelay + 'ms"') : '';

      if (isLarge) {
        svgParts.push('<text x="' + cx.toFixed(1) + '" y="' + (ry + rh * 0.40).toFixed(1) + '" text-anchor="middle" dominant-baseline="middle" font-size="14" font-weight="600" fill="#fff" filter="url(#hmLabelShadow)" class="hm-label"' + labelStyle + '>' + escapeHtml(d.symbol) + '</text>');
        svgParts.push('<text x="' + cx.toFixed(1) + '" y="' + (ry + rh * 0.66).toFixed(1) + '" text-anchor="middle" dominant-baseline="middle" font-size="17" font-weight="700" fill="#fff" filter="url(#hmLabelShadow)" class="hm-label"' + labelStyle + '>' + escapeHtml(hmFormatPct(d.return_pct)) + '</text>');
      } else if (isMedium) {
        svgParts.push('<text x="' + cx.toFixed(1) + '" y="' + (ry + rh * 0.38).toFixed(1) + '" text-anchor="middle" dominant-baseline="middle" font-size="12" font-weight="600" fill="#fff" filter="url(#hmLabelShadow)" class="hm-label"' + labelStyle + '>' + escapeHtml(d.symbol) + '</text>');
        svgParts.push('<text x="' + cx.toFixed(1) + '" y="' + (ry + rh * 0.68).toFixed(1) + '" text-anchor="middle" dominant-baseline="middle" font-size="13" font-weight="700" fill="#fff" filter="url(#hmLabelShadow)" class="hm-label"' + labelStyle + '>' + escapeHtml(hmFormatPct(d.return_pct)) + '</text>');
      } else {
        svgParts.push('<text x="' + cx.toFixed(1) + '" y="' + (ry + rh / 2).toFixed(1) + '" text-anchor="middle" dominant-baseline="central" font-size="10" font-weight="600" fill="#fff" filter="url(#hmLabelShadow)" class="hm-label"' + labelStyle + '>' + escapeHtml(d.symbol) + '</text>');
      }
    }

    svgParts.push('</g>');
    tooltipData[i] = d;
  }

  svgParts.push('</svg>');
  hmTreemapSvg.innerHTML = svgParts.join("");

  // Hover → HTML tooltip, Click → jump to yearly tab
  for (var i = 0; i < rects.length; i++) {
    (function (idx) {
      var cell = hmTreemapSvg.querySelector("#hm-cell-" + idx);
      if (!cell) return;
      cell.addEventListener("mousemove", function (e) { hmShowTooltip(e, tooltipData[idx]); });
      cell.addEventListener("mouseleave", hmHideTooltip);
      cell.addEventListener("click", function () { hmJumpToYearly(tooltipData[idx]); });
    })(i);
  }

  renderHmLegend(maxAbs, prepared);
  renderHmStats(prepared);

  // Trigger return-ranked breathing effect after initial animation completes
  if (animate) {
    setTimeout(function () { hmTriggerBreathing(prepared); }, 800);
  }
}

// ─── Breathing effect: highlight tiles by return% descending ───

function hmTriggerBreathing(prepared) {
  // Sort by return descending (biggest gainers first)
  var sorted = prepared.slice().sort(function (a, b) {
    return (b.return_pct || 0) - (a.return_pct || 0);
  });

  var totalDuration = 5000; // 5s total
  var perItem = totalDuration / sorted.length;

  sorted.forEach(function (item, idx) {
    var cellId = "hm-cell-" + prepared.indexOf(item);
    var cell = document.getElementById(cellId);
    if (!cell) return;

    var delay = idx * perItem;
    setTimeout(function () {
      cell.classList.add("hm-breathing");
      setTimeout(function () { cell.classList.remove("hm-breathing"); }, 800);
    }, delay);
  });
}

// ─── Click → jump to yearly tab and fill symbol ───

function hmJumpToYearly(d) {
  if (!d || !d.symbol) return;

  // Switch to yearly tab
  var yearlyTab = document.querySelector('.tab-btn[data-tab="yearly"]');
  if (yearlyTab) {
    var allBtns = document.querySelectorAll('.tab-btn');
    var allPanels = document.querySelectorAll('.tab-panel');
    allBtns.forEach(function (b) { b.classList.remove('active'); });
    allPanels.forEach(function (p) { p.classList.remove('active'); });
    yearlyTab.classList.add('active');
    var yearlyPanel = document.getElementById('tab-yearly');
    if (yearlyPanel) yearlyPanel.classList.add('active');
  }

  // If symbol exists, remove it first; then insert at first position
  if (typeof symbols !== 'undefined' && Array.isArray(symbols)) {
    var sym = d.symbol.toUpperCase();
    var type = d.type || 'stock';
    var idx = symbols.findIndex(function (s) { return s.symbol === sym && s.type === type; });
    if (idx !== -1) symbols.splice(idx, 1);
    symbols.unshift({ symbol: sym, type: type, name: d.name || null });
  }

  // Update UI and fetch
  if (typeof renderTags === 'function') renderTags();
  if (typeof fetchData === 'function') {
    setTimeout(function () { fetchData(); }, 50);
  }
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

  // Discrete 5-stop legend matching the ramp palette.
  var stops = [
    { label: '< -' + (maxAbs * 0.7).toFixed(1) + '%', pct: -maxAbs },
    { label: '-' + (maxAbs * 0.4).toFixed(1) + '%', pct: -maxAbs * 0.5 },
    { label: '±' + HM_DEAD_ZONE.toFixed(1) + '%', pct: 0 },
    { label: '+' + (maxAbs * 0.4).toFixed(1) + '%', pct: maxAbs * 0.5 },
    { label: '> +' + (maxAbs * 0.7).toFixed(1) + '%', pct: maxAbs },
  ];

  var sizeLabel = _hmSizeBy === "market_cap" ? __("heatmap.sizeByMarketCap")
    : _hmSizeBy === "return" ? __("heatmap.sizeByReturn") : __("heatmap.sizeByTurnover");

  var noData = prepared.every(function (d) { return !d.weight; });

  var html = '';
  for (var i = 0; i < stops.length; i++) {
    var color = hmColor(stops[i].pct, maxAbs).bg;
    html += '<div class="hm-legend-cell" style="background:' + color + ';"></div>';
    html += '<span class="hm-legend-label">' + stops[i].label + '</span>';
    if (i < stops.length - 1) html += '<span class="hm-legend-sep">·</span>';
  }
  html += '<span class="hm-legend-sep">·</span>';
  html += '<span class="hm-legend-seg">' + __("heatmap.legendSizeHint") + ' ' + sizeLabel + '</span>';
  if (noData) {
    html += '<span class="hm-legend-sep">·</span>';
    html += '<span class="hm-legend-seg">' + __("heatmap.legendNoData") + '</span>';
  }
  hmLegend.innerHTML = html;
}

// ─── Overview Stats ───

function renderHmStats(prepared) {
  if (!hmStats || !prepared || !prepared.length) {
    if (hmStats) hmStats.style.display = "none";
    return;
  }

  var ups = 0, downs = 0, sumPct = 0, sumWeighted = 0, totalWeight = 0;
  prepared.forEach(function (d) {
    if (d.return_pct == null) return;
    if (d.return_pct > 0) ups++;
    else if (d.return_pct < 0) downs++;
    sumPct += d.return_pct;
    var wt = d.weight || 0;
    sumWeighted += d.return_pct * wt;
    totalWeight += wt;
  });

  var avgPct = prepared.length ? (sumPct / prepared.length) : 0;
  var weightedPct = totalWeight ? (sumWeighted / totalWeight) : avgPct;

  var avgCls = avgPct >= 0 ? 'hm-stat-up' : 'hm-stat-down';
  var wtCls = weightedPct >= 0 ? 'hm-stat-up' : 'hm-stat-down';

  var html = '';
  html += '<div class="hm-stat-card"><span class="hm-stat-icon">↑</span><span class="hm-stat-val hm-stat-up">' + ups + '</span><span class="hm-stat-label">' + __("heatmap.statsUp") + '</span></div>';
  html += '<div class="hm-stat-card"><span class="hm-stat-icon">↓</span><span class="hm-stat-val hm-stat-down">' + downs + '</span><span class="hm-stat-label">' + __("heatmap.statsDown") + '</span></div>';
  html += '<div class="hm-stat-card"><span class="hm-stat-label">' + __("heatmap.statsAvg") + '</span><span class="hm-stat-val ' + avgCls + '">' + hmFormatPct(avgPct) + '</span></div>';
  html += '<div class="hm-stat-card"><span class="hm-stat-label">' + __("heatmap.statsWeighted") + '</span><span class="hm-stat-val ' + wtCls + '">' + hmFormatPct(weightedPct) + '</span></div>';

  // Force reflow to restart animation on re-render
  hmStats.style.display = "none";
  void hmStats.offsetWidth;
  hmStats.innerHTML = html;
  hmStats.style.display = "flex";
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

  var period = hmPeriod ? hmPeriod.value : "today";

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
  if (!hmPeriod.value) hmPeriod.value = "today";

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

  // Register refresh hook for color scheme changes
  var _origHmRefresh = window._refreshCharts;
  window._refreshCharts = function () {
    if (_origHmRefresh) _origHmRefresh();
    // Re-render heatmap if data exists (color mapping depends on scheme)
    if (_hmLastData && _hmLastData.data && _hmLastData.data.length) {
      rerender();
    }
  };

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
