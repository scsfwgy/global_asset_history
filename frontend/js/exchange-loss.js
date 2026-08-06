/**
 * Exchange Rate Loss tab — embedded in price-change.html.
 *
 * - Chart: held -> target fiat cross-rate k-line. Supports daily / weekly /
 *   monthly periods, a configurable bar count (defaults 730 / 105 / 24), and
 *   two display modes: line (default) or candlestick. Weekly/monthly bars are
 *   aggregated client-side from the daily OHLC series.
 * - Load is manual: the user clicks the Load button to fetch the pair's daily
 *   series (no auto-load). "Follow calculation range" narrows the chart x-axis
 *   to the calculator's [start, end] window. The x-axis can be zoomed with the
 *   wheel and panned by dragging.
 * - Calculator: held currency + amount, target currency, date range -> the
 *   conversion loss/gain in the target currency. Defaults held=USD,
 *   target=CNY, amount=10000, start=2025-01-01, end=today.
 * - Detail list: the daily series inside [start, end] is re-grouped every N
 *   bars (聚合条数) and each aggregation period reports its own loss/gain
 *   amount and percent, paginated.
 */

(function () {
    var FX_CURRENCIES = ["USD", "CNY", "EUR", "GBP", "JPY", "HKD", "KRW", "SGD", "CAD", "CHF", "AUD", "TWD"];
    var DEFAULT_START = "2025-01-01";
    var PERIOD_COUNTS = { daily: 730, weekly: 105, monthly: 24 };
    var DETAIL_PAGE_SIZE = 50;

    var _fxData = null;
    var _fxLoading = false;
    var _fxPeriod = "daily";
    var _fxMode = "line";
    var _fxPage = 1;
    var _fxZoom = null;
    var _fxDragging = false;
    var _fxDrag = null;
    var _fxDragShift = 0;
    var _fxSvgGeom = null;
    var _flingVx = 0;
    var _flingRaf = 0;
    var _lastPanX = 0;
    var _lastPanT = 0;
    // Race guard: each fetch gets a monotonic id; only the latest response may
    // commit state. An AbortController cancels the in-flight request when a new
    // one starts, so a slow old pair can never overwrite a fresh currency pair.
    var _fxReqId = 0;
    var _fxAbort = null;
    var _countDebounce = 0;

    function $(id) { return document.getElementById(id); }

    function fxColors() {
        var s = getComputedStyle(document.documentElement);
        return {
            line: "#2997ff",
            positive: s.getPropertyValue('--data-positive').trim() || '#30d158',
            negative: s.getPropertyValue('--data-negative').trim() || '#ff453a',
            grid: s.getPropertyValue('--apple-chart-grid').trim() || 'rgba(255,255,255,0.10)',
            text: s.getPropertyValue('--apple-chart-text').trim() || 'rgba(255,255,255,0.75)',
            textDim: s.getPropertyValue('--apple-chart-text-dim').trim() || 'rgba(255,255,255,0.50)',
            crosshair: s.getPropertyValue('--apple-chart-crosshair').trim() || 'rgba(255,255,255,0.32)',
            tooltipBg: s.getPropertyValue('--apple-tooltip-bg').trim() || 'rgba(0,0,0,0.85)',
            tooltipText: s.getPropertyValue('--apple-tooltip-text').trim() || '#fff',
        };
    }

    function fmtRate(v) {
        if (v == null || !Number.isFinite(v)) return "--";
        if (v >= 100) return v.toFixed(2);
        if (v >= 10) return v.toFixed(3);
        return v.toFixed(4);
    }

    function fmtMoney(v, code) {
        var s = Number(Math.abs(v)).toLocaleString("en-US", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
        return code + " " + s;
    }

    function todayStr() {
        var d = new Date();
        var m = String(d.getMonth() + 1).padStart(2, "0");
        var day = String(d.getDate()).padStart(2, "0");
        return d.getFullYear() + "-" + m + "-" + day;
    }

    function pairLabel(held, target) {
        return held + "/" + target;
    }

    function showEmptyState() {
        var container = $("fxChartContainer");
        if (container) {
            container.innerHTML = '<div class="fx-empty">' + __("exchangeLoss.emptyHint") + '</div>';
        }
        var results = $("fxCalcResults");
        if (results) results.style.display = "none";
        var detail = $("fxDetail");
        if (detail) detail.style.display = "none";
        var note = $("fxCalcNoteLine");
        if (note) note.style.display = "none";
        var loading = $("fxLoading");
        if (loading) loading.style.display = "none";
        updateResetZoom();
    }

    function clearData() {
        _fxData = null;
        _fxZoom = null;
        _fxPage = 1;
        showEmptyState();
    }

    function setControlsBusy(busy) {
        ["fxHeldCurrency", "fxTargetCurrency", "fxLoadBtn"].forEach(function (id) {
            var el = $(id);
            if (el) el.disabled = busy;
        });
    }

    function fetchFxData(held, target, callback) {
        var myId = ++_fxReqId;
        // Cancel any in-flight request so its stale pair can't overwrite state.
        if (_fxAbort) { try { _fxAbort.abort(); } catch (e) { /* noop */ } }
        var ctrl = (typeof AbortController !== "undefined") ? new AbortController() : null;
        _fxAbort = ctrl;
        _fxLoading = true;
        setControlsBusy(true);

        var loadingEl = $("fxLoading");
        var errorEl = $("fxError");
        if (loadingEl) loadingEl.style.display = "flex";
        if (errorEl) errorEl.style.display = "none";

        fetch(EXCHANGE_LOSS_ENDPOINT, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ held: held, target: target }),
            signal: ctrl ? ctrl.signal : undefined,
        })
            .then(function (r) {
                if (!r.ok) return r.json().then(function (e) { throw new Error(e.error || "HTTP " + r.status); });
                return r.json();
            })
            .then(function (data) {
                if (myId !== _fxReqId) return; // superseded by a newer pair
                _fxData = data;
                _fxZoom = null;
                _fxPage = 1;
                if (loadingEl) loadingEl.style.display = "none";
                updateChartTitle(held, target);
                var endEl = $("fxEndDate");
                if (endEl && data.latest && data.latest.date && !endEl.value) {
                    endEl.value = data.latest.date;
                }
                renderChart();
                updateCalc();
                if (callback) callback(null, data);
            })
            .catch(function (err) {
                if (myId !== _fxReqId) return; // not the current request anymore
                if (err && err.name === "AbortError") return; // cancelled by a newer fetch
                _fxData = null;
                if (loadingEl) loadingEl.style.display = "none";
                if (errorEl) {
                    errorEl.textContent = __("exchangeLoss.loadFailed") + (err && err.message ? err.message : err);
                    errorEl.style.display = "block";
                }
                showEmptyState();
                if (callback) callback(err);
            })
            .finally(function () {
                if (myId !== _fxReqId) return; // leave controls to the active request
                _fxLoading = false;
                _fxAbort = null;
                setControlsBusy(false);
            });
    }

    function onTabActivated() {
        // No auto-load: the user clicks the Load button.
        if (!_fxData) showEmptyState();
    }

    function updateChartTitle(held, target) {
        var el = $("fxChartTitle");
        if (el) el.textContent = "💱 " + pairLabel(held, target) + " " + __("exchangeLoss.rateHistory");
    }

    // ── chart: period / count / mode / follow / zoom ──────────────────

    function isoWeekKey(dateStr) {
        var d = new Date(dateStr + "T00:00:00Z");
        var day = d.getUTCDay() || 7;
        d.setUTCDate(d.getUTCDate() + 4 - day);
        var yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
        var week = Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
        return d.getUTCFullYear() + "-W" + String(week).padStart(2, "0");
    }

    function groupOHLC(points, period) {
        if (!points || !points.length) return [];
        if (period === "daily") return points;
        var groups = {}, order = [];
        points.forEach(function (p) {
            var key = period === "weekly" ? isoWeekKey(p.date) : p.date.substring(0, 7);
            var g = groups[key];
            if (!g) {
                g = { date: p.date, open: p.open, high: p.high, low: p.low, close: p.close };
                groups[key] = g;
                order.push(key);
            } else {
                g.high = Math.max(g.high, p.high);
                g.low = Math.min(g.low, p.low);
                g.close = p.close;
            }
        });
        return order.map(function (k) { return groups[k]; });
    }

    function readCount() {
        var input = $("fxCountInput");
        var n = input ? parseInt(input.value, 10) : PERIOD_COUNTS[_fxPeriod];
        if (!Number.isFinite(n)) n = PERIOD_COUNTS[_fxPeriod];
        n = Math.max(5, Math.min(n, 2600));
        if (input) input.value = String(n);
        return n;
    }

    function calcDates() {
        var startDate = $("fxStartDate").value || DEFAULT_START;
        var endDate = $("fxEndDate").value || (_fxData && _fxData.latest ? _fxData.latest.date : "");
        return { startDate: startDate, endDate: endDate };
    }

    // 条数 / 跟随收益计算时间 are mutually exclusive (two-segment toggle).
    function followCalc() {
        var active = document.querySelector("#fxRangeModeTabs .transfer-tab.active");
        return !!(active && active.dataset.fxRange === "follow");
    }

    function syncRangeMode() {
        var countInput = $("fxCountInput");
        if (countInput) countInput.disabled = followCalc();
    }

    function computeBase() {
        if (!_fxData) return [];
        var grouped = groupOHLC(_fxData.series || [], _fxPeriod);
        if (followCalc()) {
            var dates = calcDates();
            return grouped.filter(function (p) { return p.date >= dates.startDate && p.date <= dates.endDate; });
        }
        return grouped.slice(-readCount());
    }

    function formatDateLabel(dateStr, period) {
        return period === "monthly" ? dateStr.substring(0, 7) : dateStr.substring(5);
    }

    function rangeWithPad(values, fallbackMin, fallbackMax, padRatio) {
        var valid = values.filter(function (v) { return Number.isFinite(v); });
        if (!valid.length) return { min: fallbackMin, max: fallbackMax, range: fallbackMax - fallbackMin };
        var min = Math.min.apply(null, valid);
        var max = Math.max.apply(null, valid);
        if (min === max) { min -= 1; max += 1; }
        var range = max - min;
        var pad = range * (padRatio || 0.08);
        min -= pad; max += pad;
        return { min: min, max: max, range: max - min };
    }

    function updateResetZoom() {
        var zoomed = !!_fxZoom;
        ["fxResetZoom", "fxJumpLeftBtn", "fxJumpRightBtn"].forEach(function (id) {
            var btn = $(id);
            if (btn) {
                btn.disabled = !zoomed;
                btn.style.opacity = zoomed ? "1" : "0.45";
            }
        });
    }

    function ariaSyncTabs(nodes) {
        nodes.forEach(function (b) {
            b.setAttribute("aria-pressed", b.classList.contains("active") ? "true" : "false");
        });
    }

    // Slide the zoom window to the left / right edge.
    function jumpZoomLeft() {
        if (!_fxZoom || !_fxSvgGeom) return;
        var winLen = _fxZoom.end - _fxZoom.start + 1;
        _fxZoom = { start: 0, end: winLen - 1 };
        renderChart();
    }

    function jumpZoomRight() {
        if (!_fxZoom || !_fxSvgGeom) return;
        var winLen = _fxZoom.end - _fxZoom.start + 1;
        var start = Math.max(0, _fxSvgGeom.fullLen - winLen);
        _fxZoom = { start: start, end: start + winLen - 1 };
        renderChart();
    }

    function renderChart() {
        var container = $("fxChartContainer");
        if (!container || !_fxData) { showEmptyState(); return; }

        var CLR = fxColors();
        var base = computeBase();
        var fullLen = base.length;
        if (_fxZoom && _fxZoom.end >= fullLen) _fxZoom = null;
        if (_fxZoom) base = base.slice(_fxZoom.start, _fxZoom.end + 1);
        var points = base;
        if (points.length < 2) {
            container.innerHTML = '<div class="fx-empty">' + __("exchangeLoss.noData") + '</div>';
            updateResetZoom();
            return;
        }

        var rangeEl = $("fxChartRange");
        if (rangeEl) rangeEl.textContent = points[0].date + " ~ " + points[points.length - 1].date;

        var dates = points.map(function (p) { return p.date; });
        var vals = [];
        points.forEach(function (p) { vals.push(p.open, p.high, p.low, p.close); });
        var rng = rangeWithPad(vals, vals[0], vals[0], 0.08);

        var W = 920, H = 320;
        var PAD = { top: 20, right: 20, bottom: 34, left: 64 };
        var plotW = W - PAD.left - PAD.right;
        var plotH = H - PAD.top - PAD.bottom;
        var xScale = function (i) { return PAD.left + (i / Math.max(dates.length - 1, 1)) * plotW; };
        var yScale = function (v) { return PAD.top + plotH - ((v - rng.min) / rng.range) * plotH; };
        var dateX = {};
        dates.forEach(function (d, i) { dateX[d] = xScale(i); });
        var slotW = plotW / Math.max(dates.length - 1, 1);
        var candleWidth = Math.min(9, Math.max(1.5, slotW * 0.6));

        var svg = '<rect width="' + W + '" height="' + H + '" fill="transparent"/>';
        var gridLines = 5;
        for (var g = 0; g <= gridLines; g++) {
            var val = rng.min + (rng.range / gridLines) * g;
            var y = yScale(val);
            svg += '<line x1="' + PAD.left + '" y1="' + y + '" x2="' + (W - PAD.right) + '" y2="' + y + '" stroke="' + CLR.grid + '" stroke-width="0.5"/>';
            svg += '<text x="' + (PAD.left - 6) + '" y="' + (y + 4) + '" fill="' + CLR.textDim + '" font-size="10" text-anchor="end">' + fmtRate(val) + '</text>';
        }

        if (_fxMode === "candle") {
            for (var i = 0; i < points.length; i++) {
                var p = points[i];
                var cx = dateX[p.date];
                var highY = yScale(p.high);
                var lowY = yScale(p.low);
                var openY = yScale(p.open);
                var closeY = yScale(p.close);
                if (![cx, highY, lowY, openY, closeY].every(Number.isFinite)) continue;
                // Color by day-over-day change (close vs previous close): Yahoo FX
                // often returns open==high==low==close, so open-vs-close coloring
                // would paint a falling trend green. Compare against the previous bar.
                var prevClose = i > 0 ? points[i - 1].close : p.open;
                var color = p.close > prevClose ? CLR.positive : (p.close < prevClose ? CLR.negative : CLR.textDim);
                var bodyY = Math.min(openY, closeY);
                var bodyH = Math.max(1.2, Math.abs(closeY - openY));
                svg += '<line x1="' + cx.toFixed(1) + '" y1="' + highY.toFixed(1) + '" x2="' + cx.toFixed(1) + '" y2="' + lowY.toFixed(1) + '" stroke="' + color + '" stroke-width="1"/>';
                svg += '<rect x="' + (cx - candleWidth / 2).toFixed(1) + '" y="' + bodyY.toFixed(1) + '" width="' + candleWidth.toFixed(1) + '" height="' + bodyH.toFixed(1) + '" fill="' + color + '" fill-opacity="0.9" stroke="' + color + '" stroke-width="1"/>';
            }
        } else {
            // Per-segment line coloring: each segment green (up) / red (down).
            var pathD = "";
            var segmentColor = CLR.line;
            for (var j = 0; j < points.length; j++) {
                var lx = dateX[points[j].date];
                var ly = yScale(points[j].close);
                if (!Number.isFinite(lx) || !Number.isFinite(ly)) continue;
                pathD += (pathD ? "L" : "M") + lx.toFixed(1) + "," + ly.toFixed(1) + " ";
            }
            if (pathD) {
                svg += '<path d="' + pathD + '" fill="none" stroke="' + segmentColor + '" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" opacity="0.35"/>';
            }
            for (var k = 0; k < points.length; k++) {
                if (k === 0) continue;
                var ax = dateX[points[k - 1].date];
                var ay = yScale(points[k - 1].close);
                var bx = dateX[points[k].date];
                var by = yScale(points[k].close);
                if (![ax, ay, bx, by].every(Number.isFinite)) continue;
                var segColor = points[k].close >= points[k - 1].close ? CLR.positive : CLR.negative;
                svg += '<line x1="' + ax.toFixed(1) + '" y1="' + ay.toFixed(1) + '" x2="' + bx.toFixed(1) + '" y2="' + by.toFixed(1) + '" stroke="' + segColor + '" stroke-width="1.6" stroke-linecap="round"/>';
            }
            if (points.length <= 300) {
                for (var m = 0; m < points.length; m++) {
                    var dx = dateX[points[m].date];
                    var dy = yScale(points[m].close);
                    if (!Number.isFinite(dx) || !Number.isFinite(dy)) continue;
                    var dotColor = points[m].close >= (m > 0 ? points[m - 1].close : points[m].open) ? CLR.positive : CLR.negative;
                    svg += '<circle cx="' + dx.toFixed(1) + '" cy="' + dy.toFixed(1) + '" r="1.3" fill="' + dotColor + '" stroke="var(--apple-bg)" stroke-width="0.5"/>';
                }
            }
        }

        svg += '<text x="8" y="13" fill="' + CLR.text + '" font-size="10">' + pairLabel(_fxData.held || "USD", _fxData.target || "CNY") + '</text>';

        var labelEvery = Math.max(1, Math.floor(dates.length / 8));
        for (var n = 0; n < dates.length; n++) {
            if (n % labelEvery !== 0 && n !== dates.length - 1) continue;
            var lx2 = dateX[dates[n]];
            svg += '<text x="' + lx2 + '" y="' + (H - PAD.bottom + 16) + '" fill="' + CLR.textDim + '" font-size="9" text-anchor="middle">' + formatDateLabel(dates[n], _fxPeriod) + '</text>';
        }

        svg += '<line id="fxCrosshair" x1="0" y1="' + PAD.top + '" x2="0" y2="' + (H - PAD.bottom) + '" stroke="' + CLR.crosshair + '" stroke-width="1" stroke-dasharray="4,2" style="display:none;pointer-events:none"/>';
        svg += '<rect id="fxTipRect" x="0" y="0" width="200" height="1" rx="6" fill="' + CLR.tooltipBg + '" style="display:none;pointer-events:none"/>';
        svg += '<text id="fxTipText" x="0" y="0" fill="' + CLR.tooltipText + '" font-size="11" style="display:none;pointer-events:none"></text>';

        for (var z = 0; z < dates.length; z++) {
            var sx = dateX[dates[z]] - slotW / 2;
            svg += '<rect x="' + sx.toFixed(1) + '" y="' + PAD.top + '" width="' + slotW.toFixed(1) + '" height="' + plotH + '" fill="transparent" data-fx-idx="' + z + '" class="fx-hover-zone"/>';
        }

        var ariaLabel = pairLabel(_fxData.held || "USD", _fxData.target || "CNY") + " " + (rangeEl ? rangeEl.textContent : "");
        container.innerHTML = '<svg id="fxSvg" role="img" aria-label="' + ariaLabel.replace(/"/g, "'") + '" viewBox="0 0 ' + W + ' ' + H + '" style="width:100%;height:auto;display:block;font-family:-apple-system,SF Pro Text,Helvetica,Arial,sans-serif;cursor:' + (_fxZoom ? "grab" : "crosshair") + ';">' + svg + '</svg>';
        _fxSvgGeom = { W: W, PAD: PAD, fullLen: fullLen, svgEl: document.getElementById("fxSvg") };
        attachFxInteractions(dates, dateX, points, W, H, PAD, slotW, fullLen);
        updateResetZoom();
    }

    function attachFxInteractions(dates, dateX, points, W, H, PAD, slotW, fullLen) {
        var svgEl = document.getElementById("fxSvg");
        if (!svgEl) return;
        var crosshair = document.getElementById("fxCrosshair");
        var tipRect = document.getElementById("fxTipRect");
        var tipText = document.getElementById("fxTipText");

        // Wheel zoom around the cursor.
        svgEl.addEventListener("wheel", function (e) {
            e.preventDefault();
            if (_flingRaf) { cancelAnimationFrame(_flingRaf); _flingRaf = 0; _flingVx = 0; }
            var win = _fxZoom || { start: 0, end: fullLen - 1 };
            var winLen = win.end - win.start + 1;
            var rect = svgEl.getBoundingClientRect();
            var mx = (e.clientX - rect.left) / rect.width;
            var midIdx = win.start + (win.end - win.start) * mx;
            var factor = e.deltaY > 0 ? 1.25 : 0.8;
            var newLen = Math.max(8, Math.min(fullLen, Math.round(winLen * factor)));
            var ratio = (midIdx - win.start) / winLen;
            var newStart = Math.round(midIdx - ratio * newLen);
            newStart = Math.max(0, Math.min(newStart, fullLen - newLen));
            _fxZoom = { start: newStart, end: newStart + newLen - 1 };
            renderChart();
        }, { passive: false });

        // Drag to pan (only meaningful when zoomed). Pointer Events cover mouse,
        // touch and pen; isPrimary ignores the second finger of a pinch zoom.
        svgEl.addEventListener("pointerdown", function (e) {
            if (!e.isPrimary) return;
            if (_flingRaf) { cancelAnimationFrame(_flingRaf); _flingRaf = 0; }
            _flingVx = 0;
            _lastPanT = 0;
            if (!_fxZoom || (_fxZoom.end - _fxZoom.start + 1) >= fullLen) return;
            _fxDrag = { x: e.clientX, win: { start: _fxZoom.start, end: _fxZoom.end } };
            _fxDragShift = 0;
            _fxDragging = true;
            e.preventDefault();
        });

        svgEl.addEventListener("pointermove", function (e) {
            if (_fxDragging) return;
            if (e.pointerType !== "mouse") return; // touch has no hover tooltip
            var rect = svgEl.getBoundingClientRect();
            var mx = (e.clientX - rect.left) / rect.width * W;
            var closestI = 0, closestDist = Infinity;
            for (var i = 0; i < dates.length; i++) {
                var d = Math.abs(dateX[dates[i]] - mx);
                if (d < closestDist) { closestDist = d; closestI = i; }
            }
            if (closestDist > slotW * 1.5) {
                crosshair.style.display = "none"; tipRect.style.display = "none"; tipText.style.display = "none";
                return;
            }
            var cx = dateX[dates[closestI]];
            var dateStr = dates[closestI];
            var p = points[closestI];
            crosshair.setAttribute("x1", cx); crosshair.setAttribute("x2", cx);
            crosshair.style.display = "";

            var lines;
            if (_fxMode === "candle") {
                lines = [
                    __("exchangeLoss.tooltipDate") + dateStr,
                    __("exchangeLoss.tooltipOhlc") + fmtRate(p.open) + " / " + fmtRate(p.high) + " / " + fmtRate(p.low) + " / " + fmtRate(p.close),
                ];
            } else {
                lines = [
                    __("exchangeLoss.tooltipDate") + dateStr,
                    pairLabel(_fxData.held || "", _fxData.target || "") + " " + fmtRate(p.close),
                ];
            }
            var tipW = 210, lineH = 14, tipH = lineH * lines.length + 14;
            var tipX = cx + 10, tipY = PAD.top + 4;
            if (tipX + tipW > W - PAD.right) tipX = cx - tipW - 10;
            tipRect.setAttribute("x", tipX); tipRect.setAttribute("y", tipY);
            tipRect.setAttribute("width", tipW); tipRect.setAttribute("height", tipH);
            tipRect.style.display = "";
            var tspans = "";
            lines.forEach(function (l, li) {
                tspans += '<tspan x="' + (tipX + 8) + '" y="' + (tipY + lineH + li * lineH + 2) + '">' + l + '</tspan>';
            });
            tipText.innerHTML = tspans;
            tipText.style.display = "";
        });

        svgEl.addEventListener("pointerleave", function () {
            if (_fxDragging) return;
            if (crosshair) crosshair.style.display = "none";
            if (tipRect) tipRect.style.display = "none";
            if (tipText) tipText.style.display = "none";
        });
    }

    // Pan drag continues on window so it works outside the svg bounds.
    function onPanMove(e) {
        if (!_fxDragging || !_fxDrag || !_fxSvgGeom) return;
        // Track drag velocity (px/ms) for the fling on release.
        var now = Date.now();
        if (_lastPanT && now > _lastPanT) {
            _flingVx = (e.clientX - _lastPanX) / (now - _lastPanT);
        }
        _lastPanX = e.clientX;
        _lastPanT = now;

        var geom = _fxSvgGeom;
        var rect = geom.svgEl.getBoundingClientRect();
        var winLen = _fxDrag.win.end - _fxDrag.win.start + 1;
        var dispW = (geom.W - geom.PAD.left - geom.PAD.right) * rect.width / geom.W;
        var slot = dispW > 0 ? dispW / winLen : 1;
        var shift = Math.round((e.clientX - _fxDrag.x) / slot);
        if (shift === _fxDragShift) return;
        _fxDragShift = shift;
        var newStart = Math.max(0, Math.min(_fxDrag.win.start - shift, geom.fullLen - winLen));
        _fxZoom = { start: newStart, end: newStart + winLen - 1 };
        renderChart();
    }

    function onPanUp() {
        _fxDragging = false;
        _fxDrag = null;
        if (Math.abs(_flingVx) > 0.25 && _fxZoom) {
            startFling();
        } else {
            _flingVx = 0;
        }
    }

    // Inertial glide after a quick drag: decay the velocity frame by frame.
    function startFling() {
        if (_flingRaf) cancelAnimationFrame(_flingRaf);
        _flingRaf = requestAnimationFrame(flingStep);
    }

    function flingStep() {
        _flingRaf = 0;
        var geom = _fxSvgGeom;
        if (!geom || !_fxZoom) { _flingVx = 0; return; }
        var winLen = _fxZoom.end - _fxZoom.start + 1;
        var rect = geom.svgEl.getBoundingClientRect();
        var dispW = (geom.W - geom.PAD.left - geom.PAD.right) * rect.width / geom.W;
        var slot = dispW > 0 ? dispW / winLen : 1;
        var stepBars = (_flingVx * 16) / slot; // px per frame -> bars
        _flingVx *= 0.9; // exponential decay
        var oldStart = _fxZoom.start;
        var newStart = Math.max(0, Math.min(oldStart - stepBars, geom.fullLen - winLen));
        var rounded = Math.round(newStart);
        if (rounded === oldStart) { _flingVx = 0; return; }
        _fxZoom = { start: rounded, end: rounded + winLen - 1 };
        renderChart();
        if (Math.abs(_flingVx) > 0.05) {
            _flingRaf = requestAnimationFrame(flingStep);
        } else {
            _flingVx = 0;
        }
    }

    // ── calculator ───────────────────────────────────────────────────

    function rateAt(date) {
        if (!_fxData || !_fxData.series || !date) return null;
        var series = _fxData.series;
        var lo = 0, hi = series.length - 1, ans = -1;
        while (lo <= hi) {
            var mid = (lo + hi) >> 1;
            if (series[mid].date <= date) { ans = mid; lo = mid + 1; }
            else { hi = mid - 1; }
        }
        return ans === -1 ? null : series[ans].close;
    }

    function updateCalc() {
        var card = $("fxCalcCard");
        if (!card || !_fxData) return;

        var latest = _fxData.latest;
        if (!latest) { card.style.display = "none"; return; }
        card.style.display = "";

        var held = $("fxHeldCurrency").value;
        var target = $("fxTargetCurrency").value;
        var amount = parseFloat($("fxAmount").value);
        if (!Number.isFinite(amount) || amount < 0) amount = 0;

        var startDate = $("fxStartDate").value || DEFAULT_START;
        var endDate = $("fxEndDate").value || latest.date;

        var note = $("fxCalcNoteLine");
        var results = $("fxCalcResults");
        if (!results) return;

        if (startDate > endDate) {
            results.style.display = "none";
            var detail = $("fxDetail");
            if (detail) detail.style.display = "none";
            if (note) { note.textContent = __("exchangeLoss.invalidRange"); note.style.display = "block"; }
            return;
        }

        var rateStart = rateAt(startDate);
        var rateEnd = rateAt(endDate);
        if (rateStart == null || rateEnd == null) {
            results.style.display = "none";
            var detail2 = $("fxDetail");
            if (detail2) detail2.style.display = "none";
            if (note) { note.textContent = __("exchangeLoss.dataGap"); note.style.display = "block"; }
            return;
        }
        if (note) note.style.display = "none";

        var startValue = amount * rateStart;
        var endValue = amount * rateEnd;
        var diff = endValue - startValue;
        var pct = startValue > 0 ? (endValue / startValue - 1) * 100 : 0;
        var color = diff >= 0 ? "var(--data-positive)" : "var(--data-negative)";

        $("fxStartRate").textContent = pairLabel(held, target) + " " + fmtRate(rateStart);
        $("fxStartValue").textContent = fmtMoney(startValue, target);
        $("fxEndRate").textContent = pairLabel(held, target) + " " + fmtRate(rateEnd);
        $("fxEndValue").textContent = fmtMoney(endValue, target);
        $("fxGainLoss").textContent = (diff >= 0 ? "+" : "-") + fmtMoney(Math.abs(diff), target);
        $("fxGainLoss").style.color = color;
        $("fxGainLossPct").textContent = (pct >= 0 ? "+" : "") + pct.toFixed(2) + "%";
        $("fxGainLossPct").style.color = color;
        results.style.display = "";

        _fxPage = 1;
        renderDetail();
    }

    // ── detail list: N-bar aggregation, paginated ─────────────────────

    function buildDetailRows() {
        if (!_fxData || !_fxData.series) return [];
        var amount = parseFloat($("fxAmount").value);
        if (!Number.isFinite(amount) || amount < 0) amount = 0;
        var dates = calcDates();
        if (dates.startDate > dates.endDate) return [];

        var bars = [];
        (_fxData.series || []).forEach(function (p) {
            if (p.date >= dates.startDate && p.date <= dates.endDate) bars.push(p);
        });
        if (!bars.length) return [];

        var n = parseInt($("fxAggCount").value, 10);
        if (!Number.isFinite(n) || n < 1) n = 30;

        var target = $("fxTargetCurrency").value;
        var rows = [];
        for (var i = 0; i < bars.length; i += n) {
            var chunk = bars.slice(i, i + n);
            var startRate = chunk[0].close;
            var endRate = chunk[chunk.length - 1].close;
            var startValue = amount * startRate;
            var endValue = amount * endRate;
            var diff = endValue - startValue;
            var pct = startValue > 0 ? (endValue / startValue - 1) * 100 : 0;
            rows.push({
                start: chunk[0].date,
                end: chunk[chunk.length - 1].date,
                startRate: startRate,
                endRate: endRate,
                diff: diff,
                pct: pct,
                target: target,
            });
        }
        return rows;
    }

    function renderDetail() {
        var wrap = $("fxDetail");
        if (!wrap) return;
        var rows = buildDetailRows();
        if (!rows.length) { wrap.style.display = "none"; return; }
        wrap.style.display = "";

        var totalPages = Math.max(1, Math.ceil(rows.length / DETAIL_PAGE_SIZE));
        if (_fxPage > totalPages) _fxPage = totalPages;
        if (_fxPage < 1) _fxPage = 1;
        var start = (_fxPage - 1) * DETAIL_PAGE_SIZE;
        var pageRows = rows.slice(start, start + DETAIL_PAGE_SIZE);

        var body = $("fxDetailBody");
        body.innerHTML = "";
        pageRows.forEach(function (r) {
            var color = r.diff >= 0 ? "var(--data-positive)" : "var(--data-negative)";
            var tr = document.createElement("tr");
            tr.innerHTML =
                '<td>' + r.start + ' ~ ' + r.end + '</td>' +
                '<td>' + fmtRate(r.startRate) + '</td>' +
                '<td>' + fmtRate(r.endRate) + '</td>' +
                '<td style="color:' + color + '">' + (r.diff >= 0 ? "+" : "-") + fmtMoney(Math.abs(r.diff), r.target) + '</td>' +
                '<td style="color:' + color + '">' + (r.pct >= 0 ? "+" : "") + r.pct.toFixed(2) + '%</td>';
            body.appendChild(tr);
        });

        var info = $("fxDetailPageInfo");
        if (info) {
            info.textContent = __("exchangeLoss.pageInfo")
                .replace("{{page}}", String(_fxPage))
                .replace("{{pages}}", String(totalPages))
                .replace("{{total}}", String(rows.length));
        }
        var prevBtn = $("fxDetailPrevBtn");
        var nextBtn = $("fxDetailNextBtn");
        if (prevBtn) prevBtn.disabled = _fxPage <= 1;
        if (nextBtn) nextBtn.disabled = _fxPage >= totalPages;
    }

    // ── init ─────────────────────────────────────────────────────────

    function populateSelect(select, currencies, selected) {
        if (!select || select.options.length) return;
        currencies.forEach(function (code) {
            var o = document.createElement("option");
            o.value = code;
            o.textContent = code;
            if (code === selected) o.selected = true;
            select.appendChild(o);
        });
    }

    function initPeriodTabs() {
        var tabs = document.querySelectorAll("#fxPeriodTabs .transfer-tab");
        tabs.forEach(function (btn) {
            btn.addEventListener("click", function () {
                tabs.forEach(function (b) { b.classList.remove("active"); });
                btn.classList.add("active");
                _fxPeriod = btn.dataset.fxPeriod || "daily";
                _fxZoom = null;
                var input = $("fxCountInput");
                if (input) input.value = String(PERIOD_COUNTS[_fxPeriod]);
                if (_fxData) renderChart();
                ariaSyncTabs(tabs);
            });
        });
        ariaSyncTabs(tabs);
    }

    function initChartControls() {
        var countInput = $("fxCountInput");
        if (countInput) {
            countInput.addEventListener("change", function () { _fxZoom = null; if (_fxData) renderChart(); });
            // Debounce the per-keystroke input event so typing a count doesn't
            // rebuild the whole SVG on every digit (up to 2600 bars × listeners).
            countInput.addEventListener("input", function () {
                _fxZoom = null;
                if (!_fxData) return;
                if (_countDebounce) clearTimeout(_countDebounce);
                _countDebounce = setTimeout(function () { _countDebounce = 0; renderChart(); }, 250);
            });
        }
        var modeTabs = document.querySelectorAll("#fxChartModeTabs .transfer-tab");
        modeTabs.forEach(function (btn) {
            btn.addEventListener("click", function () {
                modeTabs.forEach(function (b) { b.classList.remove("active"); });
                btn.classList.add("active");
                _fxMode = btn.dataset.fxMode || "line";
                if (_fxData) renderChart();
                ariaSyncTabs(modeTabs);
            });
        });
        ariaSyncTabs(modeTabs);
        var rangeTabs = document.querySelectorAll("#fxRangeModeTabs .transfer-tab");
        rangeTabs.forEach(function (btn) {
            btn.addEventListener("click", function () {
                rangeTabs.forEach(function (b) { b.classList.remove("active"); });
                btn.classList.add("active");
                syncRangeMode();
                _fxZoom = null;
                if (_fxData) renderChart();
                ariaSyncTabs(rangeTabs);
            });
        });
        ariaSyncTabs(rangeTabs);
        var resetZoom = $("fxResetZoom");
        if (resetZoom) resetZoom.addEventListener("click", function () { _fxZoom = null; renderChart(); });
        var jumpLeft = $("fxJumpLeftBtn");
        if (jumpLeft) jumpLeft.addEventListener("click", jumpZoomLeft);
        var jumpRight = $("fxJumpRightBtn");
        if (jumpRight) jumpRight.addEventListener("click", jumpZoomRight);
    }

    function initCalculator() {
        populateSelect($("fxHeldCurrency"), FX_CURRENCIES, "USD");
        populateSelect($("fxTargetCurrency"), FX_CURRENCIES, "CNY");
        var startEl = $("fxStartDate");
        if (startEl && !startEl.value) startEl.value = DEFAULT_START;
        var endEl = $("fxEndDate");
        if (endEl && !endEl.value) endEl.value = todayStr();

        var loadBtn = $("fxLoadBtn");
        if (loadBtn) loadBtn.addEventListener("click", function () {
            fetchFxData($("fxHeldCurrency").value, $("fxTargetCurrency").value);
        });

        var held = $("fxHeldCurrency");
        var target = $("fxTargetCurrency");
        [held, target].forEach(function (el) {
            if (el) el.addEventListener("change", clearData);
        });

        ["fxAmount", "fxStartDate", "fxEndDate", "fxAggCount"].forEach(function (id) {
            var el = $(id);
            if (el) {
                el.addEventListener("change", onParamChange);
                el.addEventListener("input", onParamChange);
            }
        });

        var prevBtn = $("fxDetailPrevBtn");
        var nextBtn = $("fxDetailNextBtn");
        if (prevBtn) prevBtn.addEventListener("click", function () { if (_fxPage > 1) { _fxPage--; renderDetail(); } });
        if (nextBtn) nextBtn.addEventListener("click", function () { _fxPage++; renderDetail(); });
    }

    // Dates / amount / aggregation only affect local computation; the chart
    // re-renders too when it follows the calculation range.
    function onParamChange() {
        if (!_fxData) return;
        if (followCalc()) { _fxZoom = null; renderChart(); }
        updateCalc();
    }

    function init() {
        showEmptyState();
        initPeriodTabs();
        initChartControls();
        initCalculator();
        syncRangeMode();
        window.addEventListener("pointermove", onPanMove);
        window.addEventListener("pointerup", onPanUp);
        var fxTab = document.querySelector('.tab-btn[data-tab="exchange-loss"]');
        if (fxTab) fxTab.addEventListener("click", onTabActivated);
        if (document.getElementById("tab-exchange-loss") && document.getElementById("tab-exchange-loss").classList.contains("active")) onTabActivated();
        window._exchangeLossRefreshChart = function () { if (_fxData) renderChart(); };
        var origRefresh = window._refreshCharts;
        window._refreshCharts = function () {
            if (typeof origRefresh === "function") origRefresh();
            if (typeof window._exchangeLossRefreshChart === "function") window._exchangeLossRefreshChart();
        };
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
