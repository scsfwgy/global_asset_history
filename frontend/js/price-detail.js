(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const MONTHS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];

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

  function renderSummary(result) {
    const summaryEl = $("pdSummary");
    if (!summaryEl) return;
    const summary = result.summary || {};
    const best = summary.best_month;
    const worst = summary.worst_month;
    const source = result.meta && result.meta.source ? result.meta.source : result.source;
    const cards = [
      [__("detail.summaryYears"), summary.year_count != null ? summary.year_count : "—"],
      [__("detail.summaryAvgYear"), formatPct(summary.avg_yearly_return)],
      [__("detail.summaryWinRate"), formatPct(summary.yearly_win_rate, 1)],
      [__("detail.summaryBestMonth"), best ? `${best.year}-${String(best.month).padStart(2, "0")} ${formatPct(best.return)}` : "—"],
      [__("detail.summaryWorstMonth"), worst ? `${worst.year}-${String(worst.month).padStart(2, "0")} ${formatPct(worst.return)}` : "—"],
      [__("detail.summarySource"), source ? escapeHtml(source) : "—"],
    ];
    summaryEl.innerHTML = cards.map(([label, value]) => (
      `<div class="pd-summary-card">
        <div class="pd-summary-label">${escapeHtml(label)}</div>
        <div class="pd-summary-value">${value}</div>
      </div>`
    )).join("");
  }

  function renderTable(result) {
    const head = $("pdTableHead");
    const body = $("pdTableBody");
    if (!head || !body) return;

    const min = Number($("pdMinRange")?.value || -50);
    const max = Number($("pdMaxRange")?.value || 50);
    const monthHead = MONTHS.map((m) => `<th>${__("yearly.monthLabel", { m })}</th>`).join("");
    head.innerHTML = `<tr><th>${__("yearly.colYear")}</th>${monthHead}<th>${__("yearly.annualTotal")}</th></tr>`;

    const rows = (result.rows || []).map((row) => {
      const monthMap = {};
      (row.months || []).forEach((m) => { monthMap[m.month] = m.return; });
      const monthCells = MONTHS.map((month) => {
        const value = monthMap[month];
        const color = cellColor(value, min, max);
        return `<td style="background:${color.bg};color:${color.text};" title="${row.year}-${String(month).padStart(2, "0")} ${formatPct(value)}">${formatPct(value)}</td>`;
      }).join("");
      const annualColor = cellColor(row.annual_return, min, max);
      return `<tr><td>${row.year}</td>${monthCells}<td style="background:${annualColor.bg};color:${annualColor.text};font-weight:700;">${formatPct(row.annual_return)}</td></tr>`;
    });

    const stats = result.stats || [];
    const byMonth = {};
    stats.forEach((s) => { byMonth[s.month] = s; });

    function statRow(label, field, formatter) {
      const cells = MONTHS.map((month) => {
        const stat = byMonth[month] || {};
        const value = stat[field];
        return `<td>${formatter(value)}</td>`;
      }).join("");
      return `<tr class="pd-stat-row"><td>${escapeHtml(label)}</td>${cells}<td>—</td></tr>`;
    }

    rows.push(statRow(__("detail.avg"), "avg", (v) => formatPct(v)));
    rows.push(statRow(__("detail.median"), "median", (v) => formatPct(v)));
    rows.push(statRow(__("detail.winRate"), "win_rate", (v) => formatPct(v, 1)));
    body.innerHTML = rows.join("");
  }

  function renderLegend() {
    const el = $("pdLegend");
    if (!el) return;
    const neg = cellColor(-50, -50, 50).bg;
    const flat = cellColor(0, -50, 50).bg || "var(--apple-surface-2)";
    const pos = cellColor(50, -50, 50).bg;
    el.innerHTML = `
      <span>${__("detail.legend")}</span>
      <span class="pd-legend-chip" style="background:${neg};"></span>
      <span>${__("detail.negative")}</span>
      <span class="pd-legend-chip" style="background:${flat};border:1px solid var(--apple-divider);"></span>
      <span>${__("detail.neutral")}</span>
      <span class="pd-legend-chip" style="background:${pos};"></span>
      <span>${__("detail.positive")}</span>
    `;
  }

  async function queryDetail() {
    const symbolInput = $("pdSymbolInput");
    const typeSelect = $("pdTypeSelect");
    const symbol = (symbolInput?.value || "").trim().toUpperCase();
    const type = typeSelect?.value || "stock";
    if (!symbol) {
      showError(__("detail.errorNoSymbol"));
      setResultVisible(false);
      return;
    }

    try {
      localStorage.setItem("gah_detail_state", JSON.stringify({
        symbol,
        type,
        minRange: $("pdMinRange")?.value || "-50",
        maxRange: $("pdMaxRange")?.value || "50",
      }));
    } catch (_) {}

    showError(null);
    setLoading(true);
    setResultVisible(false);

    try {
      const resp = await fetch(DETAIL_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol, type }),
      });
      const result = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(result.error || `HTTP ${resp.status}`);
      }
      renderSummary(result);
      renderTable(result);
      renderLegend();
      setResultVisible(true);
    } catch (err) {
      showError(__("detail.errorRequest") + " " + err.message);
      setResultVisible(false);
    } finally {
      setLoading(false);
    }
  }

  function restoreState() {
    try {
      const raw = localStorage.getItem("gah_detail_state");
      if (!raw) return;
      const state = JSON.parse(raw);
      if (state.symbol && $("pdSymbolInput")) $("pdSymbolInput").value = state.symbol;
      if (state.type && $("pdTypeSelect")) $("pdTypeSelect").value = state.type;
      if (state.minRange && $("pdMinRange")) $("pdMinRange").value = state.minRange;
      if (state.maxRange && $("pdMaxRange")) $("pdMaxRange").value = state.maxRange;
    } catch (_) {}
  }

  function init() {
    const btn = $("pdQueryBtn");
    const input = $("pdSymbolInput");
    if (!btn || !input) return;
    restoreState();
    btn.addEventListener("click", queryDetail);
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") queryDetail();
    });
    ["pdMinRange", "pdMaxRange"].forEach((id) => {
      const el = $(id);
      if (el) el.addEventListener("keydown", (event) => {
        if (event.key === "Enter") queryDetail();
      });
    });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
