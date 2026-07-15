/**
 * A-Share ETF real-time market data tab — embedded in price-change.html.
 *
 * - Two sub-tabs: NASDAQ 100 / S&P 500
 * - Sortable table with real-time quotes from Tencent Finance
 * - Row click → expand detail panel with SVG candlestick chart + daily change% overlay
 */
(function () {
    var L = "<"; var C = L + "/";  // < and </ to avoid Node 24 parser issue

    /* ── ETF groups ── */
    var ETF_GROUPS = {
        nasdaq100: { label: "纳指100", preset: "cn_etf_nasdaq100", symbols: [] },
        sp500: { label: "标普500", preset: "cn_etf_sp500", symbols: [] },
        global_others: { label: "其它", preset: "cn_etf_others", symbols: [] },
    };

    /* ── State ── */
    var _quotes = {};
    var _activeTab = "nasdaq100";
    var _sortCol = "mc_total";
    var _sortDir = "desc";
    var _expandedCode = null;
    var _lastChartData = null;
    var _activeView = "rank";
    var _aggregateMetric = "premium";
    var _aggregateHistory = {};
    var _aggregateLoading = false;
    var _aggregateHidden = {};
    var _dataStarted = false;

    /* ── Chart type selection (single-select) ── */
    function activeChartType() {
        var active = document.querySelector('#etfChartToggles .etf-chart-tab.active');
        return active ? active.dataset.etfChart : "candle";
    }

    /* ── Chart colors — use CSS variable references so SVG auto-adapts to theme changes ── */
    function getEtfChartColors() {
        var s = getComputedStyle(document.documentElement);
        return {
            candleUp: s.getPropertyValue('--data-positive').trim() || '#30d158',
            candleDown: s.getPropertyValue('--data-negative').trim() || '#ff453a',
            positive: s.getPropertyValue('--data-positive').trim() || '#30d158',
            positiveAlpha08: s.getPropertyValue('--data-positive-alpha-08').trim() || 'rgba(48,209,88,0.08)',
            grid: 'var(--apple-chart-grid)',
            text: 'var(--apple-chart-text)',
            textDim: 'var(--apple-chart-text-dim)',
            dim: 'var(--apple-chart-text-dim)',
            crosshair: 'var(--apple-chart-crosshair)',
            tooltipBg: 'var(--apple-tooltip-bg)',
            tooltipText: 'var(--apple-tooltip-text)',
            chartColor: 'var(--apple-chart-color)',
        };
    }

    function loadEtfGroupsFromConfig() {
        var request = typeof window.gahLoadConfig === "function"
            ? window.gahLoadConfig()
            : fetch("/api/price-change/config").then(function (r) { return r.ok ? r.json() : null; });
        return request
            .then(function (cfg) {
                var presets = cfg && cfg.presets ? cfg.presets : [];
                for (var key in ETF_GROUPS) {
                    var presetKey = ETF_GROUPS[key].preset;
                    var preset = presets.find(function (p) { return p.key === presetKey; });
                    ETF_GROUPS[key].symbols = (preset && preset.symbols ? preset.symbols : []).map(function (s) {
                        return { code: s.symbol, name: s.name || s.symbol };
                    });
                }
            })
            .catch(function () {
                for (var key in ETF_GROUPS) ETF_GROUPS[key].symbols = [];
            });
    }

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
                if (_activeView === "aggregate") {
                    renderAggregateSymbols();
                    ensureAggregateHistory(false);
                }
            });
        });

        // ETF inner view switch: rank table vs group aggregate chart
        document.querySelectorAll("#etfViewTabs .transfer-tab").forEach(function (btn) {
            btn.addEventListener("click", function () {
                document.querySelectorAll("#etfViewTabs .transfer-tab").forEach(function (b) { b.classList.remove("active"); });
                btn.classList.add("active");
                _activeView = btn.dataset.etfView || "rank";
                var rank = document.getElementById("etfRankView");
                var agg = document.getElementById("etfAggregateView");
                if (rank) rank.style.display = _activeView === "rank" ? "" : "none";
                if (agg) agg.classList.toggle("active", _activeView === "aggregate");
                if (_activeView === "aggregate") {
                    hideDetail();
                    renderAggregateSymbols();
                    ensureAggregateHistory(false);
                }
            });
        });

        document.querySelectorAll("#etfAggregateMetrics .etf-chart-tab").forEach(function (btn) {
            btn.addEventListener("click", function () {
                document.querySelectorAll("#etfAggregateMetrics .etf-chart-tab").forEach(function (b) { b.classList.remove("active"); });
                btn.classList.add("active");
                _aggregateMetric = btn.dataset.etfMetric || "premium";
                renderAggregateChart();
            });
        });

        var aggReloadBtn = document.getElementById("etfAggregateReload");
        if (aggReloadBtn) aggReloadBtn.addEventListener("click", function () {
            ensureAggregateHistory(true);
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

        // Chart type selector (single-select, radio style)
        document.querySelectorAll("#etfChartToggles .etf-chart-tab").forEach(function (btn) {
            btn.addEventListener("click", function (e) {
                e.stopPropagation();
                document.querySelectorAll("#etfChartToggles .etf-chart-tab").forEach(function (b) { b.classList.remove("active"); });
                btn.classList.add("active");
                if (_expandedCode) renderChart();
            });
        });

        // The embedded ETF panel starts on first activation.  The standalone
        // ETF page has no tab panel, so it still loads immediately below.
    }

    function startDataLoad() {
        if (_dataStarted) return;
        _dataStarted = true;
        loadEtfGroupsFromConfig().then(function () {
            renderTable();        // show skeleton (names + "--") as soon as groups are known
            return fetchQuotes(); // fills in live numbers, re-renders on completion
        });
    }

    // Idempotent entry used when the embedded ETF tab is first activated.
    window._etfActivate = function () {
        startDataLoad();
        renderTable();
        if (_activeView === "aggregate") {
            renderAggregateSymbols();
            ensureAggregateHistory(false);
        }
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            init();
            if (!document.getElementById("tab-etf")) startDataLoad();
        });
    } else {
        init();
        if (!document.getElementById("tab-etf")) startDataLoad();
    }

    // Hook into theme-switch refresh chain (follows same pattern as vix-chart.js)
    var _origEtfRefresh = window._refreshCharts;
    window._refreshCharts = function () {
        if (typeof _origEtfRefresh === "function") _origEtfRefresh();
        if (typeof window._refreshEtfChart === "function") window._refreshEtfChart();
    };

    var _valuationLoading = false;
    var _valuationLoaded = false;

    /* ── Progress indicator (shared by embedded tab + standalone page) ── */
    function _setProgress(msg, dotColor) {
        var el = document.getElementById("etfRefreshInfo");
        if (el) el.textContent = msg;
        var rt = document.getElementById("refreshTime");
        if (rt) rt.textContent = msg;
        if (dotColor) {
            var dot = document.getElementById("refreshDot");
            if (dot) dot.style.backgroundColor = dotColor;
        }
    }
    function _timeStr() {
        return new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    }

    /* ── Fetch real-time quotes ── */
    function fetchQuotes() {
        var symbols = [];
        for (var k in ETF_GROUPS) {
            ETF_GROUPS[k].symbols.forEach(function (s) { symbols.push(s.code); });
        }
        _valuationLoaded = false;
        _valuationLoading = false;
        _setProgress(__("etf.loading"), "#ff9f0a");
        fetch("/api/etf-market/quote?symbols=" + symbols.join(","))
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var map = {};
                (data.quotes || []).forEach(function (q) { map[q.code] = q; });
                _quotes = map;
                renderTable();
                // Phase 2: lazy-load East-Money-dependent valuation data
                _setProgress(__("etf.updated") + _timeStr() + "  " + __("etf.estLoading"), "#ff9f0a");
                fetchValuation(symbols);
            })
            .catch(function () {
                _setProgress(__("etf.quoteLoadFailed"), "#ff453a");
                document.getElementById("etfBody").innerHTML = '<tr><td colspan="14" style="text-align:center;padding:24px;color:var(--data-negative)">' + __("etf.fetchFailed") + C + 'td>' + C + 'tr>';
            });
    }

    /* ── Lazy-load valuation error (East Money NAV, slow from US servers) ── */
    function fetchValuation(symbols) {
        if (_valuationLoading) return;
        _valuationLoading = true;
        fetch("/api/etf-market/valuation?symbols=" + symbols.join(","))
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var updated = 0;
                for (var code in data) {
                    if (_quotes[code]) {
                        var d = data[code];
                        for (var k in d) {
                            if (d[k] != null) _quotes[code][k] = d[k];
                        }
                        updated++;
                    }
                }
                _valuationLoaded = true;
                if (updated > 0) renderTable();
                _setProgress(__("etf.updated") + _timeStr() + "  " + __("etf.estLoaded"), "#30d158");
            })
            .catch(function () {
                _setProgress(__("etf.updated") + _timeStr() + "  " + __("etf.estLoadFailed"), "#ff9f0a");
            })
            .finally(function () {
                _valuationLoading = false;
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
            if (_sortCol === "mgmt_fee" || _sortCol === "custody_fee") {
                if (!has || !q[_sortCol]) return null;
                var p = parseFloat(q[_sortCol]);
                return isNaN(p) ? null : p;
            }
            if (has) return q[_sortCol] != null ? q[_sortCol] : null;
            return null;
        };

        // --- Cell helpers ---
        var R = ' style="text-align:right;"';  // right-align attr for numeric <td>

        var num = function (val, dec, unit) {
            if (val == null) return '<td' + R + '><span style="color:var(--apple-text-tertiary);">--' + C + 'span>' + C + 'td>';
            var d = val.toFixed(dec);
            if (unit === "%") d += "%";
            else if (unit) d += unit;
            return '<td' + R + '>' + d + C + 'td>';
        };

        // Standard: green-up / red-down (涨跌幅, 溢价万元盈亏)
        var pctCell = function (val, dec, unit) {
            if (val == null) return '<td' + R + '><span style="color:var(--apple-text-tertiary);">--' + C + 'span>' + C + 'td>';
            var cls = val > 0 ? "etf-pos" : val < 0 ? "etf-neg" : "";
            var d = (val > 0 ? "+" : "") + val.toFixed(dec);
            if (unit === "%") d += "%";
            else if (unit) d += unit;
            return '<td' + R + ' class="' + cls + '">' + d + C + 'td>';
        };

        // Cost columns: positive = loss (RED), negative = gain (GREEN)  — inverted
        var costPctCell = function (val, dec) {
            if (val == null) return '<td' + R + '><span style="color:var(--apple-text-tertiary);">--' + C + 'span>' + C + 'td>';
            var cls = val > 0 ? "etf-neg" : val < 0 ? "etf-pos" : "";
            var d = (val > 0 ? "+" : "") + val.toFixed(dec) + "%";
            return '<td' + R + ' class="' + cls + '">' + d + C + 'td>';
        };

        var costNumCell = function (val, dec, unit) {
            if (val == null) return '<td' + R + '><span style="color:var(--apple-text-tertiary);">--' + C + 'span>' + C + 'td>';
            var cls = val > 0 ? "etf-neg" : val < 0 ? "etf-pos" : "";
            var d = (val > 0 ? "+" : "") + val.toFixed(dec) + (unit || "");
            return '<td' + R + ' class="' + cls + '">' + d + C + 'td>';
        };

        var badge = has ? '<span class="etf-badge-' + q.market.toLowerCase() + '">' + q.market + C + 'span> ' : "";
        var name = (has && q.name) ? q.name : item.name;
        var expandedCls = (_expandedCode === code) ? " expanded" : "";

        // Fee display (strings like "0.60%")
        var feeStrCell = function (val) {
            if (!val) return '<td' + R + '><span style="color:var(--apple-text-tertiary);">--' + C + 'span>' + C + 'td>';
            return '<td' + R + '>' + val + C + 'td>';
        };

        // Columns: 代码 | 名称 | 最新价 | 涨跌幅 | 总市值(亿) | 管理费 | 托管费 | 费率合计 | 万元年费 | 溢价率 | 溢价万元盈亏
        var html =
            '<tr class="etf-row' + expandedCls + '" data-etf-code="' + code + '">' +
            "<td>" + badge + code + C + "td>" +
            "<td>" + name + C + "td>" +
            "<td style=\"font-weight:600;text-align:right;\">" + (has && q.price != null ? q.price.toFixed(3) : '<span style="color:var(--apple-text-tertiary);">--' + C + 'span>') + C + "td>" +
            pctCell(has ? q.change_pct : null, 2, "%") +
            num(has ? q.mc_total : null, 2) +
            feeStrCell(has ? q.mgmt_fee : null) +
            feeStrCell(has ? q.custody_fee : null) +
            num(has ? q.total_fee : null, 2, "%") +
            num(has ? q.fee_per_10k : null, 0, "元") +
            costPctCell(has ? q.premium : null, 2) +
            pctCell(has ? q.premium_cost_per_10k : null, 0, "元") +
            pctCell(has ? q.tracking_error_30d_pct : null, 2, "%") +
            pctCell(has ? q.profit_diff_30d_per_10k : null, 0, "元") +
            // 估值误差 (haoetf-style, single-day)
            (has && q.valuation_error_latest != null
                ? '<td' + R + '>' + (q.valuation_error_latest > 0 ? '+' : '') + q.valuation_error_latest.toFixed(2) + '%' + C + 'td>'
                : '<td' + R + '><span style="color:var(--apple-text-tertiary);">--' + C + 'span>' + C + 'td>') +
            C + "tr>";

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

        // Stats table — DOM API to avoid Node 24 </ parsing issue
        var tbody = document.querySelector("#etfDetailStats tbody");
        tbody.innerHTML = "";

        // Row 1 — matches table: 代码 | 名称 | 最新价 | 涨跌幅 | 总市值 | 管理费 | 托管费 | 费率合计 | 万元年费 | 溢价率 | 溢价万元盈亏 | 追踪误差
        var tr1 = document.createElement("tr");
        function addLbl(v) { var t=document.createElement("td");t.textContent=v;t.className="etf-ds-label";tr1.appendChild(t); }
        function addTipLbl(v, tip) { var t=document.createElement("td");t.textContent=v;t.className="etf-ds-label has-tip";t.title=tip;tr1.appendChild(t); }
        function addVal(v, cls) { var t=document.createElement("td");t.textContent=v;t.className="etf-ds-val" + (cls ? " "+cls : "");tr1.appendChild(t); }
        // Standard: green-up / red-down
        function addStdPct(l, v) {
            addLbl(l);
            if (v==null) addVal("--");
            else addVal((v>0?"+":"")+v.toFixed(2)+"%", v>0?"etf-pos":v<0?"etf-neg":"");
        }
        // Cost columns: positive = loss (RED), negative = gain (GREEN)
        function addCostPct(l, v) {
            addLbl(l);
            if (v==null) addVal("--");
            else addVal((v>0?"+":"")+v.toFixed(2)+"%", v>0?"etf-neg":v<0?"etf-pos":"");
        }

        addLbl(__("etf.colCode")); addVal(code);
        addLbl(__("etf.colName")); addVal(name);
        addLbl(__("etf.colPrice")); addVal(q && q.price != null ? q.price.toFixed(3) + " ¥" : "--", "etf-ds-price");
        addStdPct(__("etf.colChangePct"), q ? q.change_pct : null);
        addLbl(__("etf.colMarketCap")); addVal(q && q.mc_total != null ? q.mc_total.toFixed(2) : "--");
        addLbl(__("etf.colMgmtFee")); addVal(q && q.mgmt_fee ? q.mgmt_fee : "--");
        addLbl(__("etf.colCustodyFee")); addVal(q && q.custody_fee ? q.custody_fee : "--");
        addLbl(__("etf.colFeeTotal")); addVal(q && q.total_fee != null ? q.total_fee.toFixed(2)+"%" : "--");
        addLbl(__("etf.colAnnualFee")); addVal(q && q.fee_per_10k != null ? q.fee_per_10k.toFixed(0)+"元" : "--");
        addCostPct(__("etf.colPremium"), q ? q.premium : null);
        // Premium cost: negative = loss (RED), positive = gain/savings (GREEN)
        addLbl(__("etf.colPremiumProfit"));
        if (q && q.premium_cost_per_10k != null) {
            var pc = q.premium_cost_per_10k;
            var sign = pc > 0 ? "+" : "";
            addVal(sign + pc.toFixed(0) + "元", pc < 0 ? "etf-neg" : pc > 0 ? "etf-pos" : "");
        } else {
            addVal("--");
        }
        var tracking30Tip = __("etf.tooltipTrueError");
        var diff30Tip = __("etf.tooltipReturnDiff");
        addTipLbl(__("etf.colTrackingError"), tracking30Tip);
        if (q && q.tracking_error_30d_pct != null) addVal((q.tracking_error_30d_pct>0?"+":"") + q.tracking_error_30d_pct.toFixed(2)+"%", q.tracking_error_30d_pct>0?"etf-pos":q.tracking_error_30d_pct<0?"etf-neg":"");
        else addVal("--");
        addTipLbl(__("etf.colReturnDiff"), diff30Tip);
        if (q && q.profit_diff_30d_per_10k != null) addVal((q.profit_diff_30d_per_10k>0?"+":"") + q.profit_diff_30d_per_10k.toFixed(0)+"元", q.profit_diff_30d_per_10k>0?"etf-pos":q.profit_diff_30d_per_10k<0?"etf-neg":"");
        else addVal("--");
        var valErrTip = __("etf.tooltipEstError");
        addTipLbl(__("etf.colEstError"), valErrTip);
        if (q && q.valuation_error_latest != null) {
            addVal((q.valuation_error_latest > 0 ? '+' : '') + q.valuation_error_latest.toFixed(2) + "%");
        } else addVal("--");

        tbody.appendChild(tr1);

        document.getElementById("etfDetail").classList.add("open");

        // Fetch history and render chart
        fetch("/api/etf-market/history?symbol=" + code + "&days=120")
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.bars && data.bars.length > 0) {
                    _lastChartData = data;
                    var noteEl = document.getElementById("etfPremiumNote");
                    if (noteEl) noteEl.style.display = data.premium_approx ? "" : "none";
                    appendHistoryStats(data.stats, q);
                    renderChart();
                } else {
                    document.getElementById("etfChartContainer").innerHTML =
                        '<div style="text-align:center;padding:24px;color:var(--apple-text-secondary);">' + __("etf.noHistoryData") + C + 'div>';
                }
            })
            .catch(function () {
                document.getElementById("etfChartContainer").innerHTML =
                    '<div style="text-align:center;padding:24px;color:var(--data-negative);">' + __("etf.chartLoadFailed") + C + 'div>';
            });
    }

    function appendHistoryStats(st, q) {
        if (!st) return;
        var tbody = document.querySelector("#etfDetailStats tbody");
        if (!tbody) return;
        var tr = document.createElement("tr");
        function addLbl(v) { var t=document.createElement("td");t.textContent=v;t.className="etf-ds-label";tr.appendChild(t); }
        function addVal(v, cls) { var t=document.createElement("td");t.textContent=v;t.className="etf-ds-val"+(cls?" "+cls:"");tr.appendChild(t); }
        function addPctLbl(l, v) {
            addLbl(l);
            if (v==null) addVal("--");
            else { var t=document.createElement("td");t.textContent=(v>0?"+":"")+v.toFixed(2)+"%";t.className="etf-ds-val "+(v>0?"etf-pos":v<0?"etf-neg":"");tr.appendChild(t); }
        }
        function amtFmt(v) { return v==null?"--":v>=1e8?(v/1e8).toFixed(2)+"亿":(v/1e4).toFixed(0)+"万"; }
        function volFmt(v) { return v==null?"--":(v/10000).toFixed(1)+"万手"; }

        // Row 2 — supplementary
        addLbl(__("etf.detailFundCompany")); addVal(st.company || "--");
        addLbl(__("etf.detailListed")); addVal((st.first_date||"").slice(0,7));
        addLbl(__("etf.detailDays")); addVal(st.days_since_listed != null ? __("etf.daysValue", {n: st.days_since_listed}) : "?");
        addPctLbl(__("etf.detail1M"), st.ret_1m);
        addPctLbl(__("etf.detail3M"), st.ret_3m);
        addLbl(__("etf.detailOpen")); addVal(q && q.open != null ? q.open.toFixed(3) : "--");
        addLbl(__("etf.detailHigh")); addVal(q && q.high != null ? q.high.toFixed(3) : "--");
        addLbl(__("etf.detailLow")); addVal(q && q.low != null ? q.low.toFixed(3) : "--");
        addLbl(__("etf.detailAmplitude")); addVal(q && q.amplitude != null ? q.amplitude.toFixed(2)+"%" : "--");
        addLbl(__("etf.detailVolume")); addVal(volFmt(q ? q.volume : null));
        addLbl(__("etf.detailAmount")); addVal(amtFmt(q ? q.amount : null));
        addLbl(__("etf.detailTurnover")); addVal(q && q.turnover != null ? q.turnover.toFixed(2)+"%" : "--");

        tbody.appendChild(tr);
    }

    function hideDetail() {
        _expandedCode = null;
        document.getElementById("etfDetail").classList.remove("open");
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

    function getAggregateColors() {
        return ["#2997ff", "#ff9f0a", "#30d158", "#ff453a", "#bf5af2", "#5ac8fa", "#ffd60a", "#ff375f", "#64d2ff", "#32d74b", "#ff9f0a", "#ac8e68"];
    }

    function currentAggregateSymbols() {
        var group = ETF_GROUPS[_activeTab] || { symbols: [] };
        return group.symbols || [];
    }

    function metricConfig(metric) {
        var map = {
            premium: { label: __("etf.configHistPremium"), key: "premium_pct", unit: "%", decimals: 2, symmetric: false },
            valuation: { label: __("etf.configHistEstError"), key: "valuation_error_pct", unit: "%", decimals: 2, symmetric: true },
            real_error: { label: __("etf.configHistTrueError"), key: "price_tracking_deviation_pct", unit: "%", decimals: 2, symmetric: true },
            change: { label: __("etf.configHistPriceChg"), key: "change_pct", unit: "%", decimals: 2, symmetric: true },
            price_return: { label: __("etf.configCumChg"), key: "__cum_return_pct", unit: "%", decimals: 2, symmetric: false },
            profit_diff: { label: __("etf.configReturnDiff"), key: "profit_diff_per_10k", unit: "元", decimals: 0, symmetric: true },
        };
        return map[metric] || map.premium;
    }

    function aggregateCacheKey() {
        return _activeTab + ":120";
    }

    function setAggregateStatus(msg) {
        var el = document.getElementById("etfAggregateStatus");
        if (el) el.textContent = msg || "";
    }

    function ensureAggregateHistory(force) {
        var key = aggregateCacheKey();
        if (_aggregateLoading) return;
        if (!force && _aggregateHistory[key]) {
            renderAggregateChart();
            return;
        }

        var symbols = currentAggregateSymbols();
        if (!symbols.length) {
            setAggregateStatus(__("etf.noSymbolsInGroup"));
            document.getElementById("etfAggregateChart").innerHTML = "";
            return;
        }

        _aggregateLoading = true;
        setAggregateStatus(__("etf.loadingAggregate"));
        document.getElementById("etfAggregateChart").innerHTML =
            '<div style="padding:30px;text-align:center;color:var(--apple-text-secondary);">' + __("etf.loadingData") + C + 'div>';

        Promise.all(symbols.map(function (item) {
            return fetch("/api/etf-market/history?symbol=" + encodeURIComponent(item.code) + "&days=120")
                .then(function (r) { return r.ok ? r.json() : null; })
                .then(function (data) {
                    if (!data || !data.bars) return { code: item.code, name: item.name, error: true, bars: [] };
                    enrichAggregateBars(data.bars);
                    return {
                        code: item.code,
                        name: (_quotes[item.code] && _quotes[item.code].name) || item.name,
                        bars: data.bars,
                        stats: data.stats || {},
                    };
                })
                .catch(function () {
                    return { code: item.code, name: item.name, error: true, bars: [] };
                });
        })).then(function (series) {
            _aggregateHistory[key] = series;
            var ok = series.filter(function (s) { return s.bars && s.bars.length; }).length;
            setAggregateStatus(__("etf.aggregateLoaded", {ok: ok, total: series.length}));
            renderAggregateSymbols();
            renderAggregateChart();
        }).finally(function () {
            _aggregateLoading = false;
        });
    }

    function enrichAggregateBars(bars) {
        var firstClose = null;
        for (var i = 0; i < bars.length; i++) {
            var c = bars[i].close;
            if (firstClose == null && c != null && isFinite(c) && c > 0) firstClose = c;
            bars[i].__cum_return_pct = firstClose && c != null && isFinite(c)
                ? (c / firstClose - 1) * 100
                : null;
        }
    }

    function renderAggregateSymbols() {
        var el = document.getElementById("etfAggregateSymbols");
        if (!el) return;
        var colors = getAggregateColors();
        var hidden = _aggregateHidden[_activeTab] || {};
        var symbols = currentAggregateSymbols();
        var html = "";
        symbols.forEach(function (item, idx) {
            var q = _quotes[item.code];
            var name = (q && q.name) || item.name || item.code;
            var cls = hidden[item.code] ? " hidden" : "";
            html += '<button class="etf-symbol-chip' + cls + '" data-code="' + item.code + '">' +
                '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:' + colors[idx % colors.length] + ';margin-right:6px;"></span>' +
                item.code + " " + name + C + "button>";
        });
        el.innerHTML = html;
        el.querySelectorAll(".etf-symbol-chip").forEach(function (btn) {
            btn.addEventListener("click", function () {
                if (!_aggregateHidden[_activeTab]) _aggregateHidden[_activeTab] = {};
                var code = btn.dataset.code;
                _aggregateHidden[_activeTab][code] = !_aggregateHidden[_activeTab][code];
                renderAggregateSymbols();
                renderAggregateChart();
            });
        });
    }

    function renderAggregateChart() {
        var wrap = document.getElementById("etfAggregateChart");
        if (!wrap) return;
        var data = _aggregateHistory[aggregateCacheKey()];
        if (!data) {
            ensureAggregateHistory(false);
            return;
        }

        var cfg = metricConfig(_aggregateMetric);
        var hidden = _aggregateHidden[_activeTab] || {};
        var colors = getAggregateColors();
        var visible = data.filter(function (s) { return !hidden[s.code] && s.bars && s.bars.length; });
        if (!visible.length) {
            wrap.innerHTML = '<div style="padding:30px;text-align:center;color:var(--apple-text-secondary);">' + __("etf.allSymbolsHidden") + C + 'div>';
            return;
        }

        var dateSet = {};
        var allVals = [];
        visible.forEach(function (s) {
            s.bars.forEach(function (b) {
                var v = b[cfg.key];
                if (v != null && isFinite(v)) {
                    dateSet[b.date] = true;
                    allVals.push(v);
                }
            });
        });
        var dates = Object.keys(dateSet).sort();
        if (!dates.length || !allVals.length) {
            wrap.innerHTML = '<div style="padding:30px;text-align:center;color:var(--apple-text-secondary);">' + __("etf.noComparableData") + C + 'div>';
            return;
        }

        var CLR = getEtfChartColors();
        var W = 940, H = 390;
        var PAD = { top: 34, right: 20, bottom: 42, left: cfg.unit === "元" ? 64 : 56 };
        var plotW = W - PAD.left - PAD.right;
        var plotH = H - PAD.top - PAD.bottom;
        var minV = Math.min.apply(null, allVals), maxV = Math.max.apply(null, allVals);
        if (minV === maxV) { minV -= 1; maxV += 1; }
        var pad = (maxV - minV) * 0.15 || 1;
        if (cfg.symmetric) {
            var absMax = Math.max(Math.abs(minV), Math.abs(maxV)) + pad;
            minV = -absMax; maxV = absMax;
        } else {
            minV -= pad; maxV += pad;
        }
        var range = maxV - minV;
        var xScale = function (i) { return PAD.left + (i / Math.max(dates.length - 1, 1)) * plotW; };
        var yScale = function (v) { return PAD.top + plotH - ((v - minV) / range) * plotH; };
        var dateIndex = {};
        dates.forEach(function (d, i) { dateIndex[d] = i; });

        var svg = '<rect width="' + W + '" height="' + H + '" fill="transparent"' + "/>";
        svg += '<text x="' + PAD.left + '" y="18" fill="' + CLR.text + '" font-size="13" font-weight="600">' + cfg.label + C + "text>";

        for (var g = 0; g <= 5; g++) {
            var val = minV + (range / 5) * g;
            var y = yScale(val);
            svg += '<line x1="' + PAD.left + '" y1="' + y + '" x2="' + (W - PAD.right) + '" y2="' + y + '" stroke="' + CLR.grid + '" stroke-width="0.5"' + "/>";
            svg += '<text x="' + (PAD.left - 7) + '" y="' + (y + 4) + '" fill="' + CLR.textDim + '" font-size="10" text-anchor="end">' + fmtAggregateValue(val, cfg, true) + C + "text>";
        }
        if (minV < 0 && maxV > 0) {
            var zy = yScale(0);
            svg += '<line x1="' + PAD.left + '" y1="' + zy + '" x2="' + (W - PAD.right) + '" y2="' + zy + '" stroke="' + CLR.textDim + '" stroke-width="0.5" stroke-dasharray="3,3"' + "/>";
        }

        visible.forEach(function (s) {
            var groupItems = currentAggregateSymbols();
            var idx = groupItems.findIndex(function (it) { return it.code === s.code; });
            var color = colors[(idx < 0 ? 0 : idx) % colors.length];
            var p = "";
            s.bars.forEach(function (b) {
                var v = b[cfg.key];
                if (v == null || !isFinite(v) || dateIndex[b.date] == null) return;
                p += (p ? "L" : "M") + xScale(dateIndex[b.date]).toFixed(1) + "," + yScale(v).toFixed(1) + " ";
            });
            if (p) svg += '<path d="' + p + '" fill="none" stroke="' + color + '" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"' + "/>";
        });

        var labelEvery = Math.max(1, Math.floor(dates.length / 6));
        dates.forEach(function (d, i) {
            if (i % labelEvery !== 0 && i !== dates.length - 1) return;
            var x = xScale(i);
            svg += '<text x="' + x + '" y="' + (H - PAD.bottom + 18) + '" fill="' + CLR.textDim + '" font-size="10" text-anchor="middle">' + d.slice(5) + C + "text>";
            svg += '<line x1="' + x + '" y1="' + (H - PAD.bottom) + '" x2="' + x + '" y2="' + (H - PAD.bottom + 5) + '" stroke="' + CLR.textDim + '" stroke-width="0.5"' + "/>";
        });

        var hoverId = "etfAggregateHover";
        svg += '<line id="' + hoverId + '_line" x1="0" y1="' + PAD.top + '" x2="0" y2="' + (H - PAD.bottom) + '" stroke="' + CLR.crosshair + '" stroke-width="1" stroke-dasharray="4,2" style="display:none;pointer-events:none"' + "/>";
        svg += '<rect id="' + hoverId + '_tip" x="0" y="0" width="210" height="1" rx="6" fill="' + CLR.tooltipBg + '" style="display:none;pointer-events:none"' + "/>";
        svg += '<text id="' + hoverId + '_text" x="0" y="0" fill="' + CLR.tooltipText + '" font-size="11" style="display:none;pointer-events:none"' + ">" + C + "text>";
        for (var i = 0; i < dates.length; i++) {
            var slotW = plotW / Math.max(dates.length - 1, 1);
            svg += '<rect x="' + (xScale(i) - slotW / 2) + '" y="' + PAD.top + '" width="' + slotW + '" height="' + plotH + '" fill="transparent" class="etf-agg-hover-zone" data-idx="' + i + '"' + "/>";
        }

        wrap.innerHTML = '<svg id="etfAggregateSvg" viewBox="0 0 ' + W + ' ' + H + '" style="width:100%;height:auto;display:block;font-family:-apple-system,SF Pro Text,Helvetica,Arial,sans-serif;">' + svg + C + "svg>";
        attachAggregateHover(dates, visible, cfg, xScale, W, H, PAD);
    }

    function fmtAggregateValue(v, cfg, compact) {
        if (v == null || !isFinite(v)) return "--";
        if (cfg.unit === "元") return (v > 0 ? "+" : "") + v.toFixed(0) + (compact ? "" : "元");
        return (v > 0 ? "+" : "") + v.toFixed(cfg.decimals) + (compact ? cfg.unit : cfg.unit);
    }

    function attachAggregateHover(dates, series, cfg, xScale, W, H, PAD) {
        var svgEl = document.getElementById("etfAggregateSvg");
        if (!svgEl) return;
        var line = document.getElementById("etfAggregateHover_line");
        var rectTip = document.getElementById("etfAggregateHover_tip");
        var text = document.getElementById("etfAggregateHover_text");
        var byCodeDate = {};
        series.forEach(function (s) {
            byCodeDate[s.code] = {};
            s.bars.forEach(function (b) { byCodeDate[s.code][b.date] = b[cfg.key]; });
        });
        svgEl.addEventListener("mousemove", function (e) {
            var rect = svgEl.getBoundingClientRect();
            var mx = (e.clientX - rect.left) / rect.width * W;
            var closest = 0, dist = Infinity;
            for (var i = 0; i < dates.length; i++) {
                var d = Math.abs(xScale(i) - mx);
                if (d < dist) { dist = d; closest = i; }
            }
            var cx = xScale(closest);
            var date = dates[closest];
            var lines = [__("etf.chartDate") + date];
            series.slice(0, 12).forEach(function (s) {
                lines.push(s.code + "：" + fmtAggregateValue(byCodeDate[s.code][date], cfg, false));
            });
            var lineH = 14, tipW = 220, tipH = lineH * lines.length + 14;
            var tipX = cx + 10, tipY = PAD.top + 4;
            if (tipX + tipW > W - PAD.right) tipX = cx - tipW - 10;
            line.setAttribute("x1", cx); line.setAttribute("x2", cx); line.style.display = "";
            rectTip.setAttribute("x", tipX); rectTip.setAttribute("y", tipY);
            rectTip.setAttribute("width", tipW); rectTip.setAttribute("height", tipH);
            rectTip.style.display = "";
            var tspans = "";
            lines.forEach(function (l, li) {
                tspans += '<tspan x="' + (tipX + 8) + '" y="' + (tipY + lineH + li * lineH + 2) + '">' + l + C + "tspan>";
            });
            text.innerHTML = tspans;
            text.style.display = "";
        });
        svgEl.addEventListener("mouseleave", function () {
            line.style.display = "none";
            rectTip.style.display = "none";
            text.style.display = "none";
        });
    }

    // Expose for theme-toggle re-render
    window._refreshEtfChart = function () {
        if (_expandedCode && _lastChartData && _lastChartData.bars) renderChart();
        if (_activeView === "aggregate") renderAggregateChart();
    };

    /* ── SVG Chart — single selected type ── */
    function renderChart() {
        var bars = _lastChartData.bars;
        var hasPremium = _lastChartData.has_premium;
        if (!bars || !bars.length) return;

        var CLR = getEtfChartColors();
        var chartType = activeChartType();
        var W = 900, H = 340;
        var PAD = { top: 20, right: 20, bottom: 36, left: 56 };
        var plotW = W - PAD.left - PAD.right;
        var plotH = H - PAD.top - PAD.bottom;
        var n = bars.length;
        if (n < 1) return;

        var xScale = function (i) { return PAD.left + (i / Math.max(n - 1, 1)) * plotW; };

        var svg = buildChartBody(chartType, bars, hasPremium, W, H, PAD, plotW, plotH, n, xScale);
        if (!svg) return;

        // Crosshair + hover tooltip layer
        var hoverId = "etfHover_" + chartType;
        svg += '<line id="' + hoverId + '_line" x1="0" y1="0" x2="0" y2="' + H + '" stroke="' + CLR.crosshair + '" stroke-width="1" stroke-dasharray="4,2" style="display:none;pointer-events:none"' + "/>";
        svg += '<rect id="' + hoverId + '_tip" x="0" y="0" width="160" height="1" rx="6" fill="' + CLR.tooltipBg + '" style="display:none;pointer-events:none"' + "/>";
        svg += '<text id="' + hoverId + '_text" x="0" y="0" fill="' + CLR.tooltipText + '" font-size="11" style="display:none;pointer-events:none"' + ">" + C + "text>";

        // Invisible hover zones
        var slotW = plotW / Math.max(n - 1, 1);
        for (var i = 0; i < n; i++) {
            var sx = xScale(i) - slotW / 2;
            svg += '<rect x="' + sx + '" y="' + PAD.top + '" width="' + slotW + '" height="' + plotH + '" fill="transparent" data-idx="' + i + '" class="etf-hover-zone"' + "/>";
        }

        document.getElementById("etfChartContainer").innerHTML =
            '<svg id="etfSvg" viewBox="0 0 ' + W + ' ' + H + '" style="width:100%;height:auto;display:block;font-family:-apple-system,SF Pro Text,Helvetica,Arial,sans-serif;">' +
            svg + C + "svg>";

        // Attach hover handlers
        var svgEl = document.getElementById("etfSvg");
        if (svgEl) {
            var tipLine = document.getElementById(hoverId + "_line");
            var tipRect = document.getElementById(hoverId + "_tip");
            var tipText = document.getElementById(hoverId + "_text");

            svgEl.addEventListener("mousemove", function (e) {
                var rect = svgEl.getBoundingClientRect();
                var mx = (e.clientX - rect.left) / rect.width * W;
                var closestI = 0, closestDist = Infinity;
                for (var i = 0; i < n; i++) {
                    var d = Math.abs(xScale(i) - mx);
                    if (d < closestDist) { closestDist = d; closestI = i; }
                }
                if (closestDist > slotW) { tipLine.style.display = "none"; tipRect.style.display = "none"; tipText.style.display = "none"; return; }

                var cx = xScale(closestI);
                var b = bars[closestI];

                tipLine.setAttribute("x1", cx); tipLine.setAttribute("x2", cx);
                tipLine.style.display = "";

                var fmt = function (label, val, unit) {
                    if (val == null || !isFinite(val)) return label + "：--";
                    var s = val.toFixed(val % 1 === 0 ? 0 : 3);
                    if (unit === "pct") s = (val > 0 ? "+" : "") + val.toFixed(2) + "%";
                    if (unit === "amt") s = (val / 1e8).toFixed(2) + "亿";
                    if (unit === "yuan") s = (val > 0 ? "+" : "") + val.toFixed(0) + "元";
                    return label + "：" + s;
                };
                var lines;
                if (chartType === "compare") {
                    lines = [
                        __("etf.chartDate") + b.date,
                        fmt(__("etf.chartEtfProfit"), b.etf_profit_per_10k, "yuan"),
                        fmt(__("etf.chartBenchmarkProfit"), b.benchmark_profit_per_10k, "yuan"),
                        fmt(__("etf.chartProfitDiff"), b.profit_diff_per_10k, "yuan"),
                    ];
                } else if (chartType === "tracking3") {
                    lines = [
                        __("etf.chartDate") + b.date,
                        fmt(__("etf.chartClose"), b.close),
                        fmt(__("etf.chartChangePct"), b.change_pct, "pct"),
                        fmt(__("etf.chartPremiumPct"), b.premium_pct, "pct"),
                        fmt(__("etf.chartTrueError"), b.price_tracking_deviation_pct, "pct"),
                        fmt(__("etf.chartEstError"), b.valuation_error_pct, "pct"),
                    ];
                } else {
                    lines = [
                        __("etf.chartDate") + b.date,
                        fmt(__("etf.chartHigh"), b.high),
                        fmt(__("etf.chartOpen"), b.open),
                        fmt(__("etf.chartLow"), b.low),
                        fmt(__("etf.chartClose"), b.close),
                        fmt(__("etf.chartChangePct"), b.change_pct, "pct"),
                        fmt(__("etf.chartPremiumPct"), b.premium_pct, "pct"),
                        fmt(__("etf.chartNavDeviation"), b.nav_tracking_deviation_pct, "pct"),
                        fmt(__("etf.chartTrackingError"), b.tracking_error_pct, "pct"),
                        fmt(__("etf.chartAmplitude"), b.amplitude_pct, "pct"),
                        fmt(__("etf.chartAmount"), b.amount, "amt"),
                    ];
                }

                var tipW = 155, lineH = 13, tipH = lineH * lines.length + 14;
                var tipX = cx + 10, tipY = PAD.top + 4;
                if (tipX + tipW > W - PAD.right) tipX = cx - tipW - 10;

                tipRect.setAttribute("x", tipX); tipRect.setAttribute("y", tipY);
                tipRect.setAttribute("width", tipW); tipRect.setAttribute("height", tipH);
                tipRect.style.display = "";

                var tspans = "";
                lines.forEach(function (l, li) {
                    var ty = tipY + lineH + li * lineH + 2;
                    tspans += '<tspan x="' + (tipX + 8) + '" y="' + ty + '">' + l + C + "tspan>";
                });
                tipText.innerHTML = tspans;
                tipText.style.display = "";
            });

            svgEl.addEventListener("mouseleave", function () {
                tipLine.style.display = "none";
                tipRect.style.display = "none";
                tipText.style.display = "none";
            });
        }
    }


    /* ── buildChartBody — single-type chart rendering ── */
    function buildChartBody(chartType, bars, hasPremium, W, H, PAD, plotW, plotH, n, xScale) {
        var CLR = getEtfChartColors();
        var svg = '<rect width="' + W + '" height="' + H + '" fill="transparent"' + "/>";
        var gridLines = 5;

        // ── COMPARE: ETF cumulative return vs benchmark cumulative return ──
        if (chartType === "compare") {
            var etfVals = [], benchmarkVals = [], allVals = [];
            for (var i = 0; i < n; i++) {
                etfVals.push(bars[i].etf_profit_per_10k);
                benchmarkVals.push(bars[i].benchmark_profit_per_10k);
                if (bars[i].etf_profit_per_10k != null && isFinite(bars[i].etf_profit_per_10k)) allVals.push(bars[i].etf_profit_per_10k);
                if (bars[i].benchmark_profit_per_10k != null && isFinite(bars[i].benchmark_profit_per_10k)) allVals.push(bars[i].benchmark_profit_per_10k);
            }
            if (!allVals.length) return null;
            var minR = Math.min.apply(null, allVals), maxR = Math.max.apply(null, allVals);
            if (minR === maxR) { minR -= 1; maxR += 1; }
            var padR = (maxR - minR) * 0.15 || 1;
            minR -= padR; maxR += padR;
            var rRange = maxR - minR;
            var ry = function (v) { return PAD.top + plotH - ((v - minR) / rRange) * plotH; };

            for (var g = 0; g <= gridLines; g++) {
                var val = minR + (rRange / gridLines) * g;
                var y = ry(val);
                svg += '<line x1="' + PAD.left + '" y1="' + y + '" x2="' + (W - PAD.right) + '" y2="' + y + '" stroke="' + CLR.grid + '" stroke-width="0.5"' + "/>";
                svg += '<text x="' + (PAD.left - 6) + '" y="' + (y + 4) + '" fill="' + CLR.textDim + '" font-size="10" text-anchor="end">' + val.toFixed(0) + '元' + C + "text>";
            }
            var zeroY = ry(0);
            if (zeroY >= PAD.top && zeroY <= PAD.top + plotH) {
                svg += '<line x1="' + PAD.left + '" y1="' + zeroY + '" x2="' + (W - PAD.right) + '" y2="' + zeroY + '" stroke="' + CLR.textDim + '" stroke-width="0.5" stroke-dasharray="3,3"' + "/>";
            }
            function linePath(vals) {
                var p = "";
                for (var j = 0; j < n; j++) {
                    if (vals[j] == null || !isFinite(vals[j])) continue;
                    p += (p ? "L" : "M") + xScale(j).toFixed(1) + "," + ry(vals[j]).toFixed(1) + " ";
                }
                return p;
            }
            var etfPath = linePath(etfVals);
            var benchmarkPath = linePath(benchmarkVals);
            if (etfPath) svg += '<path d="' + etfPath + '" fill="none" stroke="#2997ff" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"' + "/>";
            if (benchmarkPath) svg += '<path d="' + benchmarkPath + '" fill="none" stroke="#ff9f0a" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"' + "/>";
            var benchmarkName = _lastChartData && _lastChartData.stats && _lastChartData.stats.tracking_error_benchmark ? _lastChartData.stats.tracking_error_benchmark : __("etf.benchmark");
            // Legend: larger indicators + readable spacing
            svg += '<rect x="' + (PAD.left + 4) + '" y="7" width="10" height="10" rx="3" fill="#2997ff"' + "/>";
            svg += '<text x="' + (PAD.left + 20) + '" y="16" fill="' + CLR.text + '" font-size="11">' + __("etf.chartEtfReturn") + C + "text>";
            svg += '<rect x="' + (PAD.left + 140) + '" y="7" width="10" height="10" rx="3" fill="#ff9f0a"' + "/>";
            svg += '<text x="' + (PAD.left + 156) + '" y="16" fill="' + CLR.text + '" font-size="11">' + __("etf.chartBenchmarkReturn", {name: benchmarkName}) + C + "text>";
            svg = addXAxis(svg, bars, n, xScale, H, PAD, CLR);
            return svg;
        }

        // ── TRACKING3: 溢价率 + 真实误差(价格级) + 追踪误差(净值级) 三线 ──
        if (chartType === "tracking3") {
            var series = [
                { key: "premium_pct", label: __("etf.chartPremiumPct"), color: "#ff9f0a", unit: "%" },
                { key: "price_tracking_deviation_pct", label: __("etf.chartTrackingError"), color: "#5ac8fa", unit: "%" },
                { key: "valuation_error_pct", label: __("etf.colEstError"), color: "#30d158", unit: "%" },
            ];
            var allVals = [], seriesData = [];
            for (var s = 0; s < series.length; s++) {
                var vals = [];
                for (var i = 0; i < n; i++) {
                    var v = bars[i][series[s].key];
                    vals.push(v != null && isFinite(v) ? v : null);
                    if (v != null && isFinite(v)) allVals.push(v);
                }
                seriesData.push(vals);
            }
            if (!allVals.length) return null;

            // Shared Y range: symmetric around 0, covering all series
            var absMax = Math.max(Math.abs(Math.min.apply(null, allVals)), Math.abs(Math.max.apply(null, allVals)));
            absMax = Math.max(absMax, 1); // minimum range
            absMax *= 1.15; // 15% padding
            var dMin = -absMax, dMax = absMax, dRange = dMax - dMin;
            var ly = function (v) { return PAD.top + plotH - ((v - dMin) / dRange) * plotH; };

            // Grid + Y labels
            for (var g = 0; g <= gridLines; g++) {
                var val = dMin + (dRange / gridLines) * g;
                var y = ly(val);
                svg += '<line x1="' + PAD.left + '" y1="' + y + '" x2="' + (W - PAD.right) + '" y2="' + y + '" stroke="' + CLR.grid + '" stroke-width="0.5"' + "/>";
                svg += '<text x="' + (PAD.left - 6) + '" y="' + (y + 4) + '" fill="' + CLR.textDim + '" font-size="10" text-anchor="end">' + val.toFixed(1) + "%" + C + "text>";
            }
            // Zero line
            var zy = ly(0);
            svg += '<line x1="' + PAD.left + '" y1="' + zy + '" x2="' + (W - PAD.right) + '" y2="' + zy + '" stroke="' + CLR.textDim + '" stroke-width="0.5" stroke-dasharray="3,3"' + "/>";

            // Draw three lines
            for (var s = 0; s < series.length; s++) {
                var path = "";
                for (var i = 0; i < n; i++) {
                    if (seriesData[s][i] == null) continue;
                    var py = ly(seriesData[s][i]);
                    path += (path ? "L" : "M") + xScale(i).toFixed(1) + "," + py.toFixed(1) + " ";
                }
                if (path) {
                    svg += '<path d="' + path + '" fill="none" stroke="' + series[s].color + '" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"' + "/>";
                }
            }

            // Legend
            var lx = PAD.left + 4, lyOff = PAD.top + 12;
            for (var s = 0; s < series.length; s++) {
                svg += '<rect x="' + lx + '" y="' + (lyOff - 9) + '" width="28" height="3" fill="' + series[s].color + '" rx="1"' + "/>";
                lx += 32;
                svg += '<text x="' + lx + '" y="' + lyOff + '" fill="' + CLR.text + '" font-size="10">' + series[s].label + C + "text>";
                lx += series[s].label.length * 10 + 14;
            }

            // Hover markers — small circles at each data point for the hovered index
            var hoverId3 = "etfHover_tracking3";
            for (var s = 0; s < series.length; s++) {
                svg += '<circle id="' + hoverId3 + '_dot' + s + '" cx="0" cy="0" r="3" fill="' + series[s].color + '" style="display:none;pointer-events:none"' + "/>";
            }
            // Store series info for tooltip
            svg += '<!-- tracking3_series:' + JSON.stringify(series.map(function(s){return s.key;})) + '-->';

            svg = addXAxis(svg, bars, n, xScale, H, PAD, CLR);
            return svg;
        }

        // ── CANDLESTICK ──
        if (chartType === "candle") {
            var minV = Infinity, maxV = -Infinity;
            for (var i = 0; i < n; i++) {
                if (bars[i].low < minV) minV = bars[i].low;
                if (bars[i].high > maxV) maxV = bars[i].high;
            }
            var pad = (maxV - minV) * 0.06 || 0.1;
            minV -= pad; maxV += pad;
            var vRange = maxV - minV;
            var yScale = function (v) { return PAD.top + plotH - ((v - minV) / vRange) * plotH; };

            for (var g = 0; g <= gridLines; g++) {
                var val = minV + (vRange / gridLines) * g;
                var y = yScale(val);
                svg += '<line x1="' + PAD.left + '" y1="' + y + '" x2="' + (W - PAD.right) + '" y2="' + y + '" stroke="' + CLR.grid + '" stroke-width="0.5"' + "/>";
                svg += '<text x="' + (PAD.left - 6) + '" y="' + (y + 4) + '" fill="' + CLR.textDim + '" font-size="10" text-anchor="end">' + val.toFixed(2) + C + "text>";
            }

            var slotW = Math.min(plotW / n, 10);
            for (var i = 0; i < n; i++) {
                var b = bars[i], cx = xScale(i);
                var isUp = b.close >= b.open;
                var color = isUp ? CLR.candleUp : CLR.candleDown;
                var yHigh = yScale(b.high), yLow = yScale(b.low);
                var yOpen = yScale(b.open), yClose = yScale(b.close);

                svg += '<line x1="' + cx + '" y1="' + yHigh + '" x2="' + cx + '" y2="' + yLow + '" stroke="' + color + '" stroke-width="1"' + "/>";
                var bodyH = Math.abs(yClose - yOpen);
                var bodyW = Math.max(slotW * 0.65, 1.5);
                if (bodyH < 0.5) bodyH = 0.5;
                var bodyTop = isUp ? yClose : yOpen;
                svg += '<rect x="' + (cx - bodyW / 2) + '" y="' + bodyTop + '" width="' + bodyW + '" height="' + bodyH + '" fill="' + color + '" stroke="' + color + '" stroke-width="0.5"' + "/>";
            }
            svg += '<text x="' + (PAD.left + 4) + '" y="' + (PAD.top + 12) + '" fill="' + CLR.text + '" font-size="11">' + __("etf.chartCandlestick") + C + "text>";
            svg = addXAxis(svg, bars, n, xScale, H, PAD, CLR);
            return svg;
        }

        // ── LINE CHARTS (change%, premium, tracking error, amplitude, amount) ──
        var values = [], label = "", unit = "", color = CLR.chartColor, symmetric = false;

        if (chartType === "change") {
            for (var i = 0; i < n; i++) values.push(bars[i].change_pct);
            label = __("etf.chartChangePct"); unit = "%"; color = "#5ac8fa"; symmetric = true;
        } else if (chartType === "premium") {
            for (var i = 0; i < n; i++) values.push(bars[i].premium_pct);
            label = __("etf.chartPremiumPct"); unit = "%"; color = "#ff9f0a"; symmetric = false;
        } else if (chartType === "tracking") {
            for (var i = 0; i < n; i++) values.push(bars[i].tracking_error_pct);
            label = __("etf.chartTrackingError"); unit = "%"; color = "#64d2ff";
        } else if (chartType === "amplitude") {
            for (var i = 0; i < n; i++) values.push(bars[i].amplitude_pct);
            label = __("etf.chartAmplitude"); unit = "%"; color = "#bf5af2";
        } else if (chartType === "amount") {
            for (var i = 0; i < n; i++) values.push(bars[i].amount);
            label = __("etf.chartAmount"); unit = "亿"; color = CLR.positive;
        } else {
            return null;
        }

        var validVals = values.filter(function (v) { return v != null && isFinite(v); });
        if (!validVals.length) return null;

        // Uniform 15% padding for all chart types
        var dataMin = Math.min.apply(null, validVals);
        var dataMax = Math.max.apply(null, validVals);
        if (dataMin === dataMax) { dataMin -= 1; dataMax += 1; }
        var dpad = (dataMax - dataMin) * 0.15 || 1;
        if (symmetric) {
            var absMax = Math.max(Math.abs(dataMin), Math.abs(dataMax)) + dpad;
            dataMax = absMax;
            dataMin = -absMax;
        } else {
            if (chartType === "amount") dataMin = 0;
            if (chartType === "amplitude") dataMin = Math.max(0, dataMin - dpad);
            else dataMin -= dpad;
            dataMax += dpad;
        }
        var dRange = dataMax - dataMin;
        var ly = function (v) { return PAD.top + plotH - ((v - dataMin) / dRange) * plotH; };

        // Grid + Y labels
        for (var g = 0; g <= gridLines; g++) {
            var val = dataMin + (dRange / gridLines) * g;
            var y = ly(val);
            svg += '<line x1="' + PAD.left + '" y1="' + y + '" x2="' + (W - PAD.right) + '" y2="' + y + '" stroke="' + CLR.grid + '" stroke-width="0.5"' + "/>";
            var lbl;
            if (chartType === "amount") lbl = (val / 1e8).toFixed(1);
            else lbl = val.toFixed(1) + unit;
            svg += '<text x="' + (PAD.left - 6) + '" y="' + (y + 4) + '" fill="' + CLR.textDim + '" font-size="10" text-anchor="end">' + lbl + C + "text>";
        }

        // Zero line for symmetric charts
        if (symmetric) {
            var zy = ly(0);
            svg += '<line x1="' + PAD.left + '" y1="' + zy + '" x2="' + (W - PAD.right) + '" y2="' + zy + '" stroke="' + CLR.textDim + '" stroke-width="0.5" stroke-dasharray="3,3"' + "/>";
        }

        // Data line
        var path = "";
        for (var i = 0; i < n; i++) {
            if (values[i] == null || !isFinite(values[i])) continue;
            var py = ly(values[i]);
            path += (path ? "L" : "M") + xScale(i).toFixed(1) + "," + py.toFixed(1) + " ";
        }
        if (path) {
            svg += '<path d="' + path + '" fill="none" stroke="' + color + '" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"' + "/>";
        }

        // Amount: fill area below line
        if (chartType === "amount" && path) {
            var areaPath = path + " L" + xScale(n - 1).toFixed(1) + "," + ly(0).toFixed(1) + " L" + xScale(0).toFixed(1) + "," + ly(0).toFixed(1) + " Z";
            svg += '<path d="' + areaPath + '" fill="' + CLR.positiveAlpha08 + '"' + "/>";
        }

        svg += '<text x="' + (PAD.left + 4) + '" y="' + (PAD.top + 12) + '" fill="' + CLR.text + '" font-size="11">' + label + " (" + unit + ")" + C + "text>";
        svg = addXAxis(svg, bars, n, xScale, H, PAD, CLR);
        return svg;
    }

    function addXAxis(svg, bars, n, xScale, H, PAD, CLR) {
        var labelEvery = Math.max(1, Math.floor(n / 6));
        for (var i = 0; i < n; i++) {
            if (i % labelEvery !== 0 && i !== n - 1) continue;
            var cx = xScale(i);
            var ds = bars[i].date.slice(5);
            svg += '<text x="' + cx + '" y="' + (H - PAD.bottom + 16) + '" fill="' + CLR.textDim + '" font-size="9" text-anchor="middle">' + ds + C + "text>";
            svg += '<line x1="' + cx + '" y1="' + (H - PAD.bottom) + '" x2="' + cx + '" y2="' + (H - PAD.bottom + 5) + '" stroke="' + CLR.textDim + '" stroke-width="0.5"' + "/>";
        }
        return svg;
    }
})();
