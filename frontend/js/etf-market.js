/**
 * A-Share ETF real-time market data tab — embedded in price-change.html.
 *
 * - Two sub-tabs: NASDAQ 100 / S&P 500
 * - Sortable table with real-time quotes from Tencent Finance
 * - Row click → expand detail panel with SVG candlestick chart + daily change% overlay
 */
(function () {
    /* ── ETF groups ── */
    var ETF_GROUPS = {
        nasdaq100: {
            label: "纳指100",
            symbols: [
                { code: "513300", name: "华夏" },
                { code: "513110", name: "华泰柏瑞" },
                { code: "159655", name: "华安" },
                { code: "159660", name: "博时" },
                { code: "159632", name: "易方达" },
                { code: "159501", name: "招商" },
                { code: "159513", name: "富国" },
                { code: "159696", name: "摩根" },
                { code: "159529", name: "汇添富" },
            ],
        },
        sp500: {
            label: "标普500",
            symbols: [
                { code: "513650", name: "华夏" },
                { code: "159612", name: "国泰" },
            ],
        },
    };

    /* ── State ── */
    var _quotes = {};
    var _activeTab = "nasdaq100";
    var _sortCol = "price";
    var _sortDir = "desc";
    var _expandedCode = null;

    /* ── Chart constants ── */
    var CHART_COLORS = {
        candleUp: "#30d158",
        candleDown: "#ff453a",
        grid: "rgba(255,255,255,0.08)",
        text: "rgba(255,255,255,0.6)",
        textDim: "rgba(255,255,255,0.35)",
        dim: "rgba(255,255,255,0.35)",
    };

    /* ── Init ── */
    function init() {
        // Sub-tab clicks
        var subTabs = document.querySelectorAll("#etfTabBar .transfer-tab");
        subTabs.forEach(function (btn) {
            btn.addEventListener("click", function () {
                document.querySelectorAll("#etfTabBar .transfer-tab").forEach(function (b) { b.classList.remove("active"); });
                btn.classList.add("active");
                _activeTab = btn.dataset.etfTab;
                _expandedCode = null;
                hideDetail();
                renderTable();
            });
        });

        // Column sort clicks
        document.querySelectorAll(".etf-th-sort").forEach(function (th) {
            th.addEventListener("click", function () {
                var col = th.dataset.etfCol;
                if (_sortCol === col) {
                    _sortDir = _sortDir === "asc" ? "desc" : "asc";
                } else {
                    _sortCol = col;
                    _sortDir = "desc";
                }
                updateSortHeaders();
                renderTable();
            });
        });

        // Refresh button
        var refreshBtn = document.getElementById("etfRefreshBtn");
        if (refreshBtn) refreshBtn.addEventListener("click", fetchQuotes);

        // Detail close
        var closeBtn = document.getElementById("etfDetailClose");
        if (closeBtn) closeBtn.addEventListener("click", function () { hideDetail(); });

        fetchQuotes();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }

    /* ── Fetch real-time quotes ── */
    function fetchQuotes() {
        var symbols = [];
        for (var k in ETF_GROUPS) {
            ETF_GROUPS[k].symbols.forEach(function (s) { symbols.push(s.code); });
        }
        fetch("/api/etf-market/quote?symbols=" + symbols.join(","))
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var map = {};
                (data.quotes || []).forEach(function (q) { map[q.code] = q; });
                _quotes = map;
                var el = document.getElementById("etfRefreshInfo");
                if (el) el.textContent = new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
                renderTable();
            })
            .catch(function () {
                document.getElementById("etfBody").innerHTML = '<tr><td colspan="13" style="text-align:center;padding:24px;color:var(--data-negative)">获取行情失败</td></tr>';
            });
    }

    /* ── Render table ── */
    function renderTable() {
        var list = ETF_GROUPS[_activeTab].symbols;
        var rows = [];

        list.forEach(function (item) {
            var q = _quotes[item.code] || null;
            rows.push(buildRow(item, q));
        });

        rows.sort(function (a, b) {
            var va = a._sv, vb = b._sv;
            if (va == null && vb == null) return 0;
            if (va == null) return 1;
            if (vb == null) return -1;
            if (typeof va === "number" && typeof vb === "number") {
                return _sortDir === "asc" ? va - vb : vb - va;
            }
            return _sortDir === "asc"
                ? String(va).localeCompare(String(vb), "zh-CN")
                : String(vb).localeCompare(String(va), "zh-CN");
        });

        var html = "";
        rows.forEach(function (r) { html += r._html; });
        document.getElementById("etfBody").innerHTML = html;

        // Row click handlers
        document.querySelectorAll("#etfBody tr.etf-row").forEach(function (tr) {
            tr.addEventListener("click", function () {
                var code = tr.dataset.etfCode;
                toggleDetail(code);
            });
        });

        updateSortHeaders();
    }

    function buildRow(item, q) {
        var code = item.code;
        var has = q && q.price != null;

        var getSortVal = function () {
            if (_sortCol === "code") return code;
            if (_sortCol === "name") return (has && q.name) ? q.name : item.name;
            if (has) return q[_sortCol] != null ? q[_sortCol] : null;
            return null;
        };

        var num = function (val, dec, unit) {
            if (val == null) return '<span style="color:var(--apple-text-tertiary);text-align:right;display:block;">--</span>';
            var d = val.toFixed(dec);
            if (unit === "vol") d = (val / 10000).toFixed(1) + "万";
            else if (unit === "amt") { d = val >= 1e8 ? (val / 1e8).toFixed(1) + "亿" : (val / 1e4).toFixed(0) + "万"; }
            else if (unit === "pct") d += "%";
            return '<span style="text-align:right;display:block;">' + d + "</span>";
        };

        var pctCls = "", pctDisp = "--";
        if (has && q.change_pct != null) {
            pctDisp = q.change_pct.toFixed(2) + "%";
            pctCls = q.change_pct > 0 ? "etf-pos" : q.change_pct < 0 ? "etf-neg" : "";
        }
        var premCls = "", premDisp = "--";
        if (has && q.premium != null) {
            premDisp = q.premium.toFixed(2) + "%";
            premCls = q.premium > 0 ? "etf-pos" : q.premium < 0 ? "etf-neg" : "";
        }
        var badge = has ? '<span class="etf-badge-' + q.market.toLowerCase() + '">' + q.market + "</span> " : "";
        var name = (has && q.name) ? q.name : item.name;

        var expandedCls = (_expandedCode === code) ? " expanded" : "";

        var html =
            '<tr class="etf-row' + expandedCls + '" data-etf-code="' + code + '">' +
            "<td>" + badge + code + "</td>" +
            "<td>" + name + "</td>" +
            "<td style=\"font-weight:600;\">" + num(has ? q.price : null, 3) + "</td>" +
            '<td><span class="' + pctCls + '" style="text-align:right;display:block;">' + pctDisp + "</span></td>" +
            "<td>" + num(has ? q.open : null, 3) + "</td>" +
            "<td>" + num(has ? q.high : null, 3) + "</td>" +
            "<td>" + num(has ? q.low : null, 3) + "</td>" +
            "<td>" + num(has ? q.amplitude : null, 2, "pct") + "</td>" +
            "<td>" + num(has ? q.volume : null, 0, "vol") + "</td>" +
            "<td>" + num(has ? q.amount : null, 0, "amt") + "</td>" +
            "<td>" + num(has ? q.turnover : null, 2, "pct") + "</td>" +
            "<td>" + num(has ? q.mc_total : null, 2) + "</td>" +
            '<td><span class="' + premCls + '" style="text-align:right;display:block;">' + premDisp + "</span></td>" +
            "</tr>";

        return { _html: html, _sv: getSortVal() };
    }

    function updateSortHeaders() {
        document.querySelectorAll(".etf-th-sort").forEach(function (th) {
            th.classList.remove("active");
            var a = th.querySelector(".etf-sort-arrow");
            if (a) a.textContent = "⇅";
        });
        var active = document.querySelector('.etf-th-sort[data-etf-col="' + _sortCol + '"]');
        if (active) {
            active.classList.add("active");
            var arr = active.querySelector(".etf-sort-arrow");
            if (arr) arr.textContent = _sortDir === "asc" ? "▲" : "▼";
        }
    }

    /* ── Detail panel (chart) ── */
    function toggleDetail(code) {
        if (_expandedCode === code) { hideDetail(); return; }
        _expandedCode = code;
        renderTable();

        var item = findSymbol(code);
        var q = _quotes[code];
        var name = (q && q.name) || (item ? item.name : code);
        var title = code + " " + name;

        document.getElementById("etfDetailTitle").textContent = title;

        // Stats
        var stats = "";
        if (q) {
            var addStat = function (label, val, unit) {
                if (val == null) return;
                stats += '<span><b>' + label + "</b> " + val.toFixed(val % 1 === 0 ? 0 : 3) + (unit || "") + "</span>";
            };
            addStat("最新价", q.price, " ¥");
            addStat("涨跌幅", q.change_pct, "%");
            addStat("溢价率", q.premium, "%");
            addStat("换手率", q.turnover, "%");
            addStat("振幅", q.amplitude, "%");
            if (q.amount) addStat("成交额", q.amount >= 1e8 ? q.amount / 1e8 : q.amount / 1e4, q.amount >= 1e8 ? "亿" : "万");
        }
        document.getElementById("etfDetailStats").innerHTML = stats;
        document.getElementById("etfDetail").style.display = "block";

        // Fetch history and render chart
        fetch("/api/etf-market/history?symbol=" + code + "&days=120")
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.bars && data.bars.length > 0) {
                    renderChart(data.bars, code, name);
                } else {
                    document.getElementById("etfChartContainer").innerHTML =
                        '<div style="text-align:center;padding:24px;color:var(--apple-text-secondary);">暂无历史数据</div>';
                }
            })
            .catch(function () {
                document.getElementById("etfChartContainer").innerHTML =
                    '<div style="text-align:center;padding:24px;color:var(--data-negative);">加载图表失败</div>';
            });
    }

    function hideDetail() {
        _expandedCode = null;
        document.getElementById("etfDetail").style.display = "none";
        renderTable();
    }

    function findSymbol(code) {
        for (var k in ETF_GROUPS) {
            for (var i = 0; i < ETF_GROUPS[k].symbols.length; i++) {
                if (ETF_GROUPS[k].symbols[i].code === code) return ETF_GROUPS[k].symbols[i];
            }
        }
        return null;
    }

    /* ── SVG Candlestick + change% chart ── */
    function renderChart(bars, code, name) {
        var W = 900, H = 340;
        var PAD = { top: 20, right: 20, bottom: 36, left: 56 };
        var plotW = W - PAD.left - PAD.right;
        var plotH = H - PAD.top - PAD.bottom;
        var n = bars.length;
        if (n < 1) return;

        // Value range (include highs/lows for candles)
        var minV = Infinity, maxV = -Infinity;
        var minC = Infinity, maxC = -Infinity;
        bars.forEach(function (b) {
            if (b.low < minV) minV = b.low;
            if (b.high > maxV) maxV = b.high;
            if (b.change_pct < minC) minC = b.change_pct;
            if (b.change_pct > maxC) maxC = b.change_pct;
        });
        var padV = (maxV - minV) * 0.05 || 1;
        minV -= padV; maxV += padV;
        var vRange = maxV - minV;

        // Change% range (secondary axis)
        var padC = Math.max(Math.abs(minC), Math.abs(maxC)) * 0.2 || 1;
        minC -= padC; maxC += padC;
        var cPctMax = Math.max(Math.abs(minC), Math.abs(maxC));

        var xScale = function (i) { return PAD.left + (i / (n - 1)) * plotW; };
        var yScale = function (v) { return PAD.top + plotH - ((v - minV) / vRange) * plotH; };

        // ── Build SVG ──
        var svg = "";

        // Background
        svg += '<rect width="' + W + '" height="' + H + '" fill="transparent"/>';

        // Grid lines + Y labels
        var gridLines = 5;
        for (var g = 0; g <= gridLines; g++) {
            var val = minV + (vRange / gridLines) * g;
            var y = yScale(val);
            svg += '<line x1="' + PAD.left + '" y1="' + y + '" x2="' + (W - PAD.right) + '" y2="' + y + '" stroke="' + CHART_COLORS.grid + '" stroke-width="0.5"/>';
            svg += '<text x="' + (PAD.left - 6) + '" y="' + (y + 4) + '" fill="' + CHART_COLORS.textDim + '" font-size="10" text-anchor="end">' + val.toFixed(2) + "</text>";
        }

        // Candlesticks
        var slotW = Math.min(plotW / n, 10);
        bars.forEach(function (b, i) {
            var cx = xScale(i);
            var isUp = b.close >= b.open;
            var color = isUp ? CHART_COLORS.candleUp : CHART_COLORS.candleDown;
            var yOpen = yScale(b.open);
            var yClose = yScale(b.close);
            var yHigh = yScale(b.high);
            var yLow = yScale(b.low);

            // Wick
            svg += '<line x1="' + cx + '" y1="' + yHigh + '" x2="' + cx + '" y2="' + yLow + '" stroke="' + color + '" stroke-width="1"/>';
            // Body
            var bodyH = Math.abs(yClose - yOpen);
            var bodyW = Math.max(slotW * 0.65, 1.5);
            if (bodyH < 0.5) bodyH = 0.5; // Doji
            var bodyTop = isUp ? yClose : yOpen;
            svg += '<rect x="' + (cx - bodyW / 2) + '" y="' + bodyTop + '" width="' + bodyW + '" height="' + bodyH + '" fill="' + color + '" stroke="' + color + '" stroke-width="0.5"/>';
        });

        // Daily change% line (overlay on a right-side scale)
        if (bars.length > 1 && cPctMax > 0) {
            var chY = function (cp) { return PAD.top + plotH / 2 - (cp / cPctMax) * (plotH / 2); };
            var zeroY = chY(0);
            var dimColor = "rgba(255,255,255,0.35)";

            // Zero line
            svg += '<line x1="' + PAD.left + '" y1="' + zeroY + '" x2="' + (W - PAD.right) + '" y2="' + zeroY + '" stroke="' + dimColor + '" stroke-width="0.5" stroke-dasharray="3,3"/>';

            // Change% labels on right
            svg += '<text x="' + (W - PAD.right + 4) + '" y="' + (PAD.top + 12) + '" fill="' + dimColor + '" font-size="9">' + "+" + cPctMax.toFixed(1) + "%" + "<" + "/text>";
            svg += '<text x="' + (W - PAD.right + 4) + '" y="' + (zeroY + 4) + '" fill="' + dimColor + '" font-size="9">' + "0%" + "<" + "/text>";
            svg += '<text x="' + (W - PAD.right + 4) + '" y="' + (H - PAD.bottom + 4) + '" fill="' + dimColor + '" font-size="9">' + "-" + cPctMax.toFixed(1) + "%" + "<" + "/text>";

            // Line
            var chPath = "";
            bars.forEach(function (b, i) {
                var y = chY(b.change_pct);
                chPath += (i === 0 ? "M" : "L") + xScale(i).toFixed(1) + "," + y.toFixed(1) + " ";
            });
            svg += '<path d="' + chPath + '" fill="none" stroke="rgba(255,255,255,0.45)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>';
        }

        // X-axis date labels
        var labelEvery = Math.max(1, Math.floor(n / 6));
        bars.forEach(function (b, i) {
            if (i % labelEvery !== 0 && i !== n - 1) return;
            var cx = xScale(i);
            var dateStr = b.date.slice(5); // MM-DD
            svg += '<text x="' + cx + '" y="' + (H - PAD.bottom + 16) + '" fill="' + CHART_COLORS.textDim + '" font-size="9" text-anchor="middle">' + dateStr + "</text>";
            svg += '<line x1="' + cx + '" y1="' + (H - PAD.bottom) + '" x2="' + cx + '" y2="' + (H - PAD.bottom + 5) + '" stroke="' + CHART_COLORS.textDim + '" stroke-width="0.5"/>';
        });

        // Legend
        svg += '<rect x="' + (PAD.left + 4) + '" y="' + (PAD.top + 2) + '" width="10" height="10" fill="' + CHART_COLORS.candleUp + '" rx="1"/>';
        svg += '<text x="' + (PAD.left + 18) + '" y="' + (PAD.top + 11) + '" fill="' + CHART_COLORS.text + '" font-size="10">蜡烛图(OHLC)</text>';
        var lg2x = PAD.left + 120;
        svg += '<line x1="' + lg2x + '" y1="' + (PAD.top + 7) + '" x2="' + (lg2x + 22) + '" y2="' + (PAD.top + 7) + '" stroke="rgba(255,255,255,0.45)" stroke-width="1.5"/>';
        svg += '<text x="' + (lg2x + 26) + '" y="' + (PAD.top + 11) + '" fill="' + CHART_COLORS.text + '" font-size="10">日涨跌幅</text>';

        document.getElementById("etfChartContainer").innerHTML =
            '<svg viewBox="0 0 ' + W + ' ' + H + '" style="width:100%;height:auto;display:block;font-family:-apple-system,SF Pro Text,Helvetica,Arial,sans-serif;">' +
            svg + "</svg>";
    }
})();
