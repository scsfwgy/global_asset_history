/** SVG chart renderers for yearly and monthly return/drawdown trend views. */

const LINE_COLORS = [
  "#2997ff", "#e8a43e", "#30d158", "#ff453a", "#5ac8fa",
  "#ff9f0a", "#bf5af2", "#ff6482", "#64d2ff", "#ffd60a",
  "#ff375f", "#00c7be", "#ffb340", "#86868b", "#ff6482",
];

let _chartData = null;
let _chartDrawdowns = null;
let _chartSymbols = null;
let _chartHidden = []; // original series indices hidden in the yearly chart
let _chartScaleMode = "focus";
let _activeChartRender = null;

function chartNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function chartQuantile(sortedValues, percentile) {
  if (!sortedValues.length) return 0;
  const index = (sortedValues.length - 1) * percentile;
  const lower = Math.floor(index);
  const upper = Math.ceil(index);
  if (lower === upper) return sortedValues[lower];
  return sortedValues[lower] + (sortedValues[upper] - sortedValues[lower]) * (index - lower);
}

/**
 * Use a wide Tukey fence in focus mode. Normal variation remains visible, while
 * isolated crypto/leveraged-asset spikes no longer flatten every other series.
 */
function computeChartRange(values, mode) {
  const clean = values.map(chartNumber).filter((value) => value !== null).sort((a, b) => a - b);
  if (!clean.length) clean.push(0);

  const rawMin = Math.min(clean[0], 0);
  const rawMax = Math.max(clean[clean.length - 1], 0);
  let coreMin = rawMin;
  let coreMax = rawMax;

  if (mode === "focus" && clean.length >= 8) {
    const q1 = chartQuantile(clean, 0.25);
    const q3 = chartQuantile(clean, 0.75);
    const iqr = q3 - q1;
    if (iqr > 0) {
      const fenceMin = Math.min(q1 - iqr * 3, 0);
      const fenceMax = Math.max(q3 + iqr * 3, 0);
      const focusedSpan = fenceMax - fenceMin;
      const rawSpan = rawMax - rawMin;
      if (rawSpan > focusedSpan * 1.25) {
        coreMin = Math.max(rawMin, fenceMin);
        coreMax = Math.min(rawMax, fenceMax);
      }
    }
  }

  const coreRange = coreMax - coreMin || Math.max(Math.abs(coreMax), 1);
  const padding = coreRange * 0.1;
  const min = coreMin - padding;
  const max = coreMax + padding;
  return {
    min,
    max,
    range: max - min || 1,
    clipped: clean.filter((value) => value < min || value > max).length,
  };
}

function chartClamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function chartMetricValue(point, metric) {
  return metric === "drawdown" ? drawdownValue(point.drawdown) : chartNumber(point.value);
}

function chartPointAttributes(series, point, x, panel) {
  const drawdown = drawdownValue(point.drawdown);
  const peak = point.drawdown && point.drawdown.peak_date ? point.drawdown.peak_date : "";
  const trough = point.drawdown && point.drawdown.trough_date ? point.drawdown.trough_date : "";
  const aria = series.name + " " + point.label + " " + metricCellTitle(point.value, point.drawdown);
  return [
    'class="pc-chart-point"',
    'data-chart-point="1"',
    `data-chart-panel="${panel}"`,
    `data-chart-x="${x}"`,
    `data-symbol="${escapeHtml(series.name)}"`,
    `data-period="${escapeHtml(point.label)}"`,
    `data-return="${point.value == null ? "" : point.value}"`,
    `data-drawdown="${drawdown == null ? "" : drawdown}"`,
    `data-peak="${escapeHtml(peak)}"`,
    `data-trough="${escapeHtml(trough)}"`,
    'tabindex="0"',
    'role="graphics-symbol"',
    `aria-label="${escapeHtml(aria)}"`,
  ].join(" ");
}

function panelGrid(range, geometry, label) {
  const { left, right, plotTop, plotBottom, width } = geometry;
  const plotHeight = plotBottom - plotTop;
  const yPos = (value) => plotBottom - ((value - range.min) / range.range) * plotHeight;
  const ticks = 4;
  let markup = `<text x="${left}" y="${geometry.top + 12}" fill="var(--apple-text-secondary)" font-size="11" font-weight="600">${escapeHtml(label)}</text>`;
  for (let i = 0; i <= ticks; i++) {
    const value = range.min + (range.range * i) / ticks;
    const y = yPos(value);
    markup += `<line x1="${left}" y1="${y}" x2="${width - right}" y2="${y}" stroke="var(--apple-divider)" stroke-width="1"/>`;
    markup += `<text x="${left - 7}" y="${y + 4}" text-anchor="end" fill="var(--apple-text-tertiary)" font-size="10">${value.toFixed(1)}%</text>`;
  }
  const zeroY = yPos(0);
  if (zeroY >= plotTop && zeroY <= plotBottom) {
    markup += `<line x1="${left}" y1="${zeroY}" x2="${width - right}" y2="${zeroY}" stroke="var(--apple-text-tertiary)" stroke-width="1" stroke-dasharray="4,3" opacity="0.65"/>`;
  }
  return { markup, yPos };
}

function renderReturnPanel(allSeries, visibleSeries, range, geometry, xPos, prefix) {
  const grid = panelGrid(range, geometry, __("chart.returnPanel"));
  let seriesMarkup = "";

  visibleSeries.forEach((series) => {
    const color = LINE_COLORS[series.index % LINE_COLORS.length];
    const points = series.points.filter((point) => chartMetricValue(point, "return") !== null);
    let lines = "";
    let dots = "";

    for (let i = 0; i < points.length - 1; i++) {
      const first = points[i];
      const second = points[i + 1];
      lines += `<line x1="${xPos(first.period)}" y1="${grid.yPos(chartClamp(first.value, range.min, range.max))}" x2="${xPos(second.period)}" y2="${grid.yPos(chartClamp(second.value, range.min, range.max))}" stroke="${color}" stroke-width="1.5" stroke-linecap="round" opacity="0.78"/>`;
    }

    points.forEach((point) => {
      const value = chartNumber(point.value);
      const clipped = value < range.min || value > range.max;
      const x = xPos(point.period);
      const y = grid.yPos(chartClamp(value, range.min, range.max));
      const attrs = chartPointAttributes(series, point, x, "return");
      if (clipped) {
        const direction = value > range.max ? -1 : 1;
        dots += `<path d="M ${x - 3.5} ${y + direction * 5} L ${x} ${y} L ${x + 3.5} ${y + direction * 5} Z" fill="${color}"/>`;
      }
      dots += `<circle cx="${x}" cy="${y}" r="${clipped ? 3 : 2.3}" fill="${color}" stroke="var(--apple-bg)" stroke-width="0.8" ${attrs}/>`;
    });
    seriesMarkup += `<g id="${prefix}-${series.index}" data-chart-series="${series.index}">${lines}${dots}</g>`;
  });

  return grid.markup + seriesMarkup;
}

function renderDrawdownPanel(allSeries, visibleSeries, range, geometry, xPos, prefix) {
  const grid = panelGrid(range, geometry, __("chart.drawdownPanel"));
  const zeroY = grid.yPos(chartClamp(0, range.min, range.max));
  const count = Math.max(visibleSeries.length, 1);
  const step = Math.min(3.2, 15 / count);
  let seriesMarkup = "";

  visibleSeries.forEach((series, visibleIndex) => {
    const color = LINE_COLORS[series.index % LINE_COLORS.length];
    const offset = (visibleIndex - (count - 1) / 2) * step;
    let bars = "";
    series.points.forEach((point) => {
      const value = chartMetricValue(point, "drawdown");
      if (value === null) return;
      const clipped = value < range.min || value > range.max;
      const baseX = xPos(point.period);
      const x = baseX + offset;
      const y = grid.yPos(chartClamp(value, range.min, range.max));
      const attrs = chartPointAttributes(series, point, baseX, "drawdown");
      bars += `<line x1="${x}" y1="${zeroY}" x2="${x}" y2="${y}" stroke="${color}" stroke-width="${Math.max(1.4, step * 0.65)}" opacity="0.72"/>`;
      if (clipped) {
        bars += `<path d="M ${x - 3} ${y - 4} L ${x} ${y} L ${x + 3} ${y - 4} Z" fill="${color}"/>`;
      }
      bars += `<circle cx="${x}" cy="${y}" r="${clipped ? 2.8 : 1.9}" fill="${color}" stroke="var(--apple-bg)" stroke-width="0.7" ${attrs}/>`;
    });
    seriesMarkup += `<g id="${prefix}-${series.index}" data-chart-series="${series.index}">${bars}</g>`;
  });

  return grid.markup + seriesMarkup;
}

function chartXAxis(periods, geometry, xPos, periodLabel) {
  if (periods.length < 2) return "";
  const maxLabels = 9;
  const step = Math.max(1, Math.ceil(periods.length / maxLabels));
  let labels = "";
  periods.forEach((period, index) => {
    if (index % step !== 0 && index !== periods.length - 1) return;
    labels += `<text x="${xPos(period)}" y="${geometry.bottom - 7}" text-anchor="middle" fill="var(--apple-text-tertiary)" font-size="10">${escapeHtml(periodLabel(period))}</text>`;
  });
  return labels;
}

function updateChartScaleControls() {
  const focusButton = $("pcChartScaleFocus");
  const fullButton = $("pcChartScaleFull");
  if (focusButton) {
    focusButton.classList.toggle("active", _chartScaleMode === "focus");
    focusButton.setAttribute("aria-pressed", String(_chartScaleMode === "focus"));
  }
  if (fullButton) {
    fullButton.classList.toggle("active", _chartScaleMode === "full");
    fullButton.setAttribute("aria-pressed", String(_chartScaleMode === "full"));
  }
}

function setChartScaleMode(mode) {
  if (!["focus", "full"].includes(mode) || mode === _chartScaleMode) return;
  _chartScaleMode = mode;
  updateChartScaleControls();
  if (_activeChartRender) _activeChartRender();
}

function setChartSeriesOpacity(activeIndex, hiddenSet) {
  const svg = $("pcChartSvg")?.querySelector("svg");
  if (!svg) return;
  svg.querySelectorAll("[data-chart-series]").forEach((group) => {
    const index = Number(group.dataset.chartSeries);
    group.style.opacity = activeIndex == null || index === activeIndex || hiddenSet.has(index) ? "1" : "0.12";
  });
}

function renderChartLegend(allSeries, hiddenIndices, setHidden, rerender) {
  const container = $("pcChartLegend");
  if (!container) return;
  const hiddenSet = new Set(hiddenIndices);
  const visibleIndices = allSeries.map((series) => series.index).filter((index) => !hiddenSet.has(index));
  const focusedIndex = visibleIndices.length === 1 ? visibleIndices[0] : null;

  const buttons = allSeries.map((series) => {
    const color = LINE_COLORS[series.index % LINE_COLORS.length];
    const classes = ["pc-chart-legend-btn"];
    if (hiddenSet.has(series.index)) classes.push("is-hidden");
    if (focusedIndex === series.index) classes.push("is-focused");
    return `<button type="button" class="${classes.join(" ")}" data-chart-legend="${series.index}">
      <span class="pc-chart-legend-swatch" style="background:${color};"></span>
      <span>${escapeHtml(series.name)}</span>
    </button>`;
  }).join("");
  container.innerHTML = `<button type="button" class="pc-chart-show-all" data-chart-show-all>${escapeHtml(__("chart.showAll"))}</button>${buttons}`;

  container.querySelector("[data-chart-show-all]")?.addEventListener("click", () => {
    setHidden([]);
    rerender();
  });

  container.querySelectorAll("[data-chart-legend]").forEach((button) => {
    const index = Number(button.dataset.chartLegend);
    button.addEventListener("click", (event) => {
      let nextHidden;
      if (event.ctrlKey || event.metaKey) {
        const next = new Set(hiddenSet);
        if (next.has(index)) next.delete(index);
        else next.add(index);
        nextHidden = next.size === allSeries.length ? [] : Array.from(next);
      } else if (focusedIndex === index) {
        nextHidden = [];
      } else {
        nextHidden = allSeries.map((series) => series.index).filter((seriesIndex) => seriesIndex !== index);
      }
      setHidden(nextHidden);
      rerender();
    });
    button.addEventListener("mouseenter", () => setChartSeriesOpacity(index, hiddenSet));
    button.addEventListener("mouseleave", () => setChartSeriesOpacity(null, hiddenSet));
  });
}

function positionChartTooltip(event, target) {
  const plot = $("pcChartPlot");
  const tooltip = $("pcChartTooltip");
  if (!plot || !tooltip) return;
  const plotRect = plot.getBoundingClientRect();
  const targetRect = target.getBoundingClientRect();
  const clientX = event && Number.isFinite(event.clientX) ? event.clientX : targetRect.left + targetRect.width / 2;
  const clientY = event && Number.isFinite(event.clientY) ? event.clientY : targetRect.top;
  const desiredLeft = clientX - plotRect.left + plot.scrollLeft + 12;
  const desiredTop = clientY - plotRect.top - tooltip.offsetHeight - 12;
  tooltip.style.left = Math.max(8, Math.min(desiredLeft, plot.scrollWidth - tooltip.offsetWidth - 8)) + "px";
  tooltip.style.top = Math.max(8, desiredTop) + "px";
}

function showChartTooltip(event, target) {
  const tooltip = $("pcChartTooltip");
  const crosshair = $("pcChartSvg")?.querySelector("#pcChartCrosshair");
  if (!tooltip) return;
  const returnValue = chartNumber(target.dataset.return);
  const drawdown = chartNumber(target.dataset.drawdown);
  const peak = target.dataset.peak;
  const trough = target.dataset.trough;
  let html = `<div class="pc-chart-tooltip-title">${escapeHtml(target.dataset.symbol)} · ${escapeHtml(target.dataset.period)}</div>`;
  html += `<div class="pc-chart-tooltip-row"><span class="pc-chart-tooltip-label">${escapeHtml(__("yearly.returnLabel"))}</span><span class="pc-chart-tooltip-value">${escapeHtml(formatPct(returnValue))}</span></div>`;
  if (showDrawdownInCells()) {
    html += `<div class="pc-chart-tooltip-row"><span class="pc-chart-tooltip-label">${escapeHtml(__("yearly.maxDrawdown"))}</span><span class="pc-chart-tooltip-value">${escapeHtml(formatPct(drawdown))}</span></div>`;
    if (peak && trough) {
      html += `<div class="pc-chart-tooltip-range">${escapeHtml(__("yearly.drawdownRange", {peak, trough}))}</div>`;
    }
  }
  tooltip.innerHTML = html;
  tooltip.hidden = false;
  positionChartTooltip(event, target);
  if (crosshair) {
    crosshair.setAttribute("x1", target.dataset.chartX);
    crosshair.setAttribute("x2", target.dataset.chartX);
    crosshair.style.visibility = "visible";
  }
}

function hideChartTooltip() {
  const tooltip = $("pcChartTooltip");
  const crosshair = $("pcChartSvg")?.querySelector("#pcChartCrosshair");
  if (tooltip) tooltip.hidden = true;
  if (crosshair) crosshair.style.visibility = "hidden";
}

function bindChartTooltip() {
  const svg = $("pcChartSvg")?.querySelector("svg");
  if (!svg) return;
  svg.querySelectorAll("[data-chart-point]").forEach((point) => {
    point.addEventListener("mouseenter", (event) => showChartTooltip(event, point));
    point.addEventListener("mousemove", (event) => positionChartTooltip(event, point));
    point.addEventListener("mouseleave", hideChartTooltip);
    point.addEventListener("focus", (event) => showChartTooltip(event, point));
    point.addEventListener("blur", hideChartTooltip);
    point.addEventListener("click", (event) => showChartTooltip(event, point));
  });
  svg.addEventListener("mouseleave", hideChartTooltip);
}

function renderTrendChart(options) {
  const { allSeries, periods, periodLabel, hiddenIndices, setHidden, prefix, rerender } = options;
  if (!allSeries.length || !periods.length) return;

  const hiddenSet = new Set(hiddenIndices);
  let visibleSeries = allSeries.filter((series) => !hiddenSet.has(series.index));
  if (!visibleSeries.length) visibleSeries = allSeries;

  const returnValues = [];
  const drawdownValues = [];
  visibleSeries.forEach((series) => series.points.forEach((point) => {
    const returnValue = chartMetricValue(point, "return");
    const drawdown = chartMetricValue(point, "drawdown");
    if (returnValue !== null) returnValues.push(returnValue);
    if (drawdown !== null) drawdownValues.push(drawdown);
  }));

  const combined = showDrawdownInCells() && drawdownValues.length > 0;
  const returnRange = computeChartRange(returnValues, _chartScaleMode);
  const rawDrawdownRange = computeChartRange(drawdownValues, _chartScaleMode);
  const drawdownMin = Math.max(-100, Math.min(rawDrawdownRange.min, -0.1));
  const drawdownRange = {
    ...rawDrawdownRange,
    min: drawdownMin,
    max: 0,
    range: Math.abs(drawdownMin) || 1,
  };
  const maxAbsLabel = Math.max(
    Math.abs(returnRange.min), Math.abs(returnRange.max),
    combined ? Math.abs(drawdownRange.min) : 0,
  );
  const left = Math.max(52, maxAbsLabel.toFixed(1).length * 6.5 + 14);
  const width = 700;
  const right = 18;
  const returnHeight = 220;
  const drawdownTop = returnHeight + 8;
  const drawdownHeight = combined ? 142 : 0;
  const svgHeight = combined ? drawdownTop + drawdownHeight : returnHeight;
  const returnGeometry = {
    top: 0, bottom: returnHeight, plotTop: 23,
    plotBottom: returnHeight - (combined ? 10 : 29), left, right, width,
  };
  const drawdownGeometry = {
    top: drawdownTop, bottom: svgHeight, plotTop: drawdownTop + 23,
    plotBottom: svgHeight - 29, left, right, width,
  };
  const minPeriod = periods[0];
  const maxPeriod = periods[periods.length - 1];
  const chartWidth = width - left - right;
  const xPos = (period) => left + ((period - minPeriod) / (maxPeriod - minPeriod || 1)) * chartWidth;

  let markup = renderReturnPanel(allSeries, visibleSeries, returnRange, returnGeometry, xPos, prefix + "-return");
  if (combined) {
    markup += renderDrawdownPanel(allSeries, visibleSeries, drawdownRange, drawdownGeometry, xPos, prefix + "-drawdown");
  }
  const xGeometry = combined ? drawdownGeometry : returnGeometry;
  markup += chartXAxis(periods, xGeometry, xPos, periodLabel);
  markup += `<line id="pcChartCrosshair" x1="0" y1="${returnGeometry.plotTop}" x2="0" y2="${xGeometry.plotBottom}" stroke="var(--apple-text-tertiary)" stroke-width="1" stroke-dasharray="3,3" opacity="0.55" style="visibility:hidden;pointer-events:none;"/>`;

  $("pcChartSvg").innerHTML = `<svg viewBox="0 0 ${width} ${svgHeight}" style="width:100%;height:auto;display:block;">${markup}</svg>`;
  $("pcChartWrap").style.display = "";
  updateChartScaleControls();

  const clippedCount = returnRange.clipped + (combined ? drawdownRange.clipped : 0);
  const note = $("pcChartScaleNote");
  if (note) {
    note.textContent = _chartScaleMode === "focus" && clippedCount > 0
      ? __("chart.focusedOutliers", {n: clippedCount})
      : "";
  }

  renderChartLegend(allSeries, hiddenIndices, setHidden, rerender);
  bindChartTooltip();
}

function renderMultiLineChart(data, symbolsList, hiddenIndices, drawdowns) {
  const allSeries = [];
  const allPeriods = new Set();
  for (const symbolEntry of symbolsList) {
    const yearly = data[symbolEntry.symbol];
    if (!yearly) continue;
    const points = Object.entries(yearly)
      .map(([year, value]) => {
        const numericYear = parseInt(year, 10);
        const drawdown = drawdowns && drawdowns[symbolEntry.symbol]
          ? drawdowns[symbolEntry.symbol][String(year)]
          : null;
        return {period: numericYear, label: String(numericYear), value: chartNumber(value), drawdown};
      })
      .filter((point) => point.value !== null)
      .sort((first, second) => first.period - second.period);
    if (points.length < 2) continue;
    const index = allSeries.length;
    allSeries.push({index, symbol: symbolEntry.symbol, name: symbolEntry.name || symbolEntry.symbol, points});
    points.forEach((point) => allPeriods.add(point.period));
  }
  if (!allSeries.length) return;

  _chartData = data;
  _chartDrawdowns = drawdowns || {};
  _chartSymbols = symbolsList;
  const periods = Array.from(allPeriods).sort((a, b) => a - b);
  const rerender = () => renderMultiLineChart(_chartData, _chartSymbols, _chartHidden, _chartDrawdowns);
  _activeChartRender = rerender;
  const title = document.querySelector("#pcChartWrap .pc-chart-title");
  if (title) title.textContent = __("yearly.chartTitle");
  renderTrendChart({
    allSeries,
    periods,
    periodLabel: (period) => String(period),
    hiddenIndices: hiddenIndices || [],
    setHidden: (next) => { _chartHidden = next; },
    prefix: "yearly-series",
    rerender,
  });
}

// ─── Monthly batch view (symbols × months table for a specific year) ───

function renderMonthlyChart(year, symKeys, monthMap, monthDrawdownMap) {
  const nameLookup = {};
  for (const symbolEntry of symbols) nameLookup[symbolEntry.symbol] = symbolEntry.name || symbolEntry.symbol;

  const allSeries = [];
  for (const symbol of symKeys) {
    const points = [];
    for (let month = 1; month <= 12; month++) {
      const value = chartNumber(monthMap[symbol][month]);
      if (value === null) continue;
      points.push({
        period: month,
        label: __("yearly.monthLabel", {m: month}),
        value,
        drawdown: monthDrawdownMap[symbol] && monthDrawdownMap[symbol][month],
      });
    }
    if (points.length) {
      allSeries.push({index: allSeries.length, symbol, name: nameLookup[symbol] || symbol, points});
    }
  }
  if (!allSeries.length) return;

  const periods = Array.from({length: 12}, (_, index) => index + 1);
  const rerender = () => renderMonthlyChart(year, symKeys, monthMap, monthDrawdownMap);
  _activeChartRender = rerender;
  const title = document.querySelector("#pcChartWrap .pc-chart-title");
  if (title) title.textContent = year + " " + __("chart.monthlyTrend");
  renderTrendChart({
    allSeries,
    periods,
    periodLabel: (period) => __("yearly.monthLabel", {m: period}),
    hiddenIndices: _mChartHidden,
    setHidden: (next) => { _mChartHidden = next; },
    prefix: "monthly-series",
    rerender,
  });
}

function initYearlyChartControls() {
  const focusButton = $("pcChartScaleFocus");
  const fullButton = $("pcChartScaleFull");
  if (focusButton && !focusButton.dataset.bound) {
    focusButton.dataset.bound = "1";
    focusButton.addEventListener("click", () => setChartScaleMode("focus"));
  }
  if (fullButton && !fullButton.dataset.bound) {
    fullButton.dataset.bound = "1";
    fullButton.addEventListener("click", () => setChartScaleMode("full"));
  }
  updateChartScaleControls();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initYearlyChartControls);
} else {
  initYearlyChartControls();
}
