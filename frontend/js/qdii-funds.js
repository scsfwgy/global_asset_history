/**
 * QDII fund tracker for Nasdaq-100 / S&P 500 public fund purchase data.
 */
(function () {
    var STATE = {
        loaded: false,
        loading: false,
        activeIndex: "nasdaq100",
        sortCol: "",
        sortDir: "desc",
        filters: {
            share_class: "",
            fund_type: "",
            company: "",
            status: "",
        },
        data: null,
    };
    var NUMERIC_SORT_COLUMNS = {
        daily_limit: true,
        min_purchase: true,
        discounted_rate_num: true,
        source_rate_num: true,
        fund_scale: true,
        daily_return_pct: true,
        return_1m_pct: true,
        return_3m_pct: true,
        return_6m_pct: true,
        return_1y_pct: true,
        return_3y_pct: true,
        return_since_inception_pct: true,
    };

    function $(id) { return document.getElementById(id); }

    function escapeHtml(value) {
        return String(value == null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function fmtMoney(value) {
        if (value == null || value === "") return "--";
        var n = Number(value);
        if (!isFinite(n)) return "--";
        if (n >= 10000) return (n / 10000).toFixed(n % 10000 === 0 ? 0 : 1) + __("qdii.unitWan");
        return n.toFixed(n % 1 === 0 ? 0 : 2) + __("qdii.unitYuan");
    }

    function fmtRate(value) {
        return value || "--";
    }

    function fmtScale(value) {
        if (value == null || value === "") return "--";
        var n = Number(value);
        if (!isFinite(n)) return "--";
        if (n >= 100000000) return (n / 100000000).toFixed(2) + __("qdii.unitYi");
        if (n >= 10000) return (n / 10000).toFixed(0) + __("qdii.unitWan");
        return n.toFixed(0) + __("qdii.unitYuan");
    }

    function fmtPct(value) {
        if (value == null || value === "") return "--";
        var n = Number(value);
        if (!isFinite(n)) return "--";
        return (n > 0 ? "+" : "") + n.toFixed(2) + "%";
    }

    function pctClass(value) {
        var n = Number(value);
        if (!isFinite(n) || n === 0) return "";
        return n > 0 ? "etf-pos" : "etf-neg";
    }

    function fmtUpdated(iso) {
        if (!iso) return "";
        var d = new Date(iso);
        if (isNaN(d.getTime())) return "";
        var pad = function (n) { return String(n).padStart(2, "0"); };
        return __("qdii.updatedPrefix") + pad(d.getHours()) + ":" + pad(d.getMinutes());
    }

    function cacheStatusLabel(status) {
        if (status === "fresh") return __("qdii.statusFresh");
        if (status === "memory") return __("qdii.statusCached");
        if (status === "shared") return __("qdii.statusShared");
        if (status === "local") return __("qdii.statusSnapshot");
        if (status === "local_stale_upstream_failed") return __("qdii.statusLocalStaleFailed");
        if (status === "local_stale_upstream_partial") return __("qdii.statusLocalStalePartial");
        return "";
    }

    function indexLabel(key) {
        if (STATE.data && STATE.data.labels && STATE.data.labels[key]) return STATE.data.labels[key];
        if (key === "active_qdii") return __("qdii.labelActiveQdii");
        return key === "sp500" ? __("qdii.labelSp500") : __("qdii.labelNasdaq100");
    }

    function baseRowsForActiveIndex() {
        return STATE.data && STATE.data.groups ? (STATE.data.groups[STATE.activeIndex] || []) : [];
    }

    function statusKey(row) {
        return row && row.buyable ? "buyable" : "paused";
    }

    function rowSortValue(row, col) {
        if (!row) return null;
        if (col === "index") return indexLabel(row.index);
        if (col === "status") return row.buyable ? __("qdii.statusAvailable") : __("qdii.statusSuspended");
        if (NUMERIC_SORT_COLUMNS[col]) {
            var n = row[col];
            return n == null || n === "" || !isFinite(Number(n)) ? null : Number(n);
        }
        return row[col] == null || row[col] === "" ? null : String(row[col]);
    }

    function compareRows(a, b) {
        var col = STATE.sortCol;
        if (!col) return 0;
        var av = rowSortValue(a, col);
        var bv = rowSortValue(b, col);
        var dir = STATE.sortDir === "asc" ? 1 : -1;
        if (av == null && bv == null) return String(a.code || "").localeCompare(String(b.code || ""));
        if (av == null) return 1;
        if (bv == null) return -1;
        if (typeof av === "number" && typeof bv === "number") {
            if (av === bv) return String(a.code || "").localeCompare(String(b.code || ""));
            return (av - bv) * dir;
        }
        var cmp = String(av).localeCompare(String(bv), "zh-Hans-CN", { numeric: true });
        if (cmp === 0) return String(a.code || "").localeCompare(String(b.code || ""));
        return cmp * dir;
    }

    function optionLabel(prefix, value) {
        return prefix + "：" + (value || __("qdii.filterAll"));
    }

    function setSelectOptions(id, prefix, values, current) {
        var select = $(id);
        if (!select) return;
        var normalizedValues = values.filter(function (v) { return v != null && v !== ""; });
        var hasCurrent = !current || normalizedValues.indexOf(current) >= 0;
        var html = ['<option value="">' + escapeHtml(prefix + "：" + __("qdii.filterAll")) + '</option>'];
        normalizedValues.forEach(function (value) {
            html.push('<option value="' + escapeHtml(value) + '">' + escapeHtml(optionLabel(prefix, value)) + '</option>');
        });
        select.innerHTML = html.join("");
        select.value = hasCurrent ? current : "";
        if (!hasCurrent) {
            if (id === "qdiiFilterShare") STATE.filters.share_class = "";
            if (id === "qdiiFilterType") STATE.filters.fund_type = "";
            if (id === "qdiiFilterCompany") STATE.filters.company = "";
        }
    }

    function renderFilterOptions() {
        var rows = baseRowsForActiveIndex();
        function unique(field) {
            var set = {};
            rows.forEach(function (row) {
                var value = row[field] || "";
                if (value) set[value] = true;
            });
            return Object.keys(set).sort(function (a, b) { return a.localeCompare(b, "zh-Hans-CN", { numeric: true }); });
        }
        setSelectOptions("qdiiFilterShare", __("qdii.filterShare"), unique("share_class"), STATE.filters.share_class);
        setSelectOptions("qdiiFilterType", __("qdii.filterType"), unique("fund_type"), STATE.filters.fund_type);
        setSelectOptions("qdiiFilterCompany", __("qdii.filterCompany"), unique("company"), STATE.filters.company);
        var statusSelect = $("qdiiFilterStatus");
        if (statusSelect) statusSelect.value = STATE.filters.status || "";
    }

    function updateSortHeaders() {
        document.querySelectorAll("#qdiiFundsTable th.qdii-sortable").forEach(function (th) {
            var col = th.dataset.qdiiSort;
            var arrow = th.querySelector(".qdii-sort-arrow");
            th.classList.toggle("active", col === STATE.sortCol);
            if (arrow) {
                arrow.textContent = col === STATE.sortCol ? (STATE.sortDir === "asc" ? "▲" : "▼") : "⇅";
            }
        });
    }

    function clearFiltersAndSort() {
        STATE.filters.share_class = "";
        STATE.filters.fund_type = "";
        STATE.filters.company = "";
        STATE.filters.status = "";
        STATE.sortCol = "";
        STATE.sortDir = "desc";
        renderAll();
    }

    function setLoading(on) {
        STATE.loading = on;
        var el = $("qdiiFundsLoading");
        if (el) el.style.display = on ? "flex" : "none";
        var btn = $("qdiiFundsRefresh");
        if (btn) btn.disabled = on;
    }

    function setError(message) {
        var el = $("qdiiFundsError");
        if (!el) return;
        el.style.display = message ? "block" : "none";
        el.textContent = message || "";
    }

    function rowsForActiveIndex() {
        var rows = baseRowsForActiveIndex();
        rows = rows.slice();
        if (STATE.filters.share_class) {
            rows = rows.filter(function (row) { return (row.share_class || "") === STATE.filters.share_class; });
        }
        if (STATE.filters.fund_type) {
            rows = rows.filter(function (row) { return (row.fund_type || "") === STATE.filters.fund_type; });
        }
        if (STATE.filters.company) {
            rows = rows.filter(function (row) { return (row.company || "") === STATE.filters.company; });
        }
        if (STATE.filters.status) {
            rows = rows.filter(function (row) { return statusKey(row) === STATE.filters.status; });
        }
        if (STATE.sortCol) {
            rows.sort(compareRows);
        }
        return rows;
    }

    function renderSummary() {
        var wrap = $("qdiiFundsSummary");
        if (!wrap) return;
        var rows = rowsForActiveIndex();
        var buyable = rows.filter(function (r) { return r.buyable; });
        var limitSource = buyable.length ? buyable : rows;
        var limits = limitSource.map(function (r) { return r.daily_limit; }).filter(function (v) { return v != null; });
        var maxLimit = limits.length ? Math.max.apply(null, limits) : null;
        var minLimit = limits.length ? Math.min.apply(null, limits) : null;
        var zeroFee = rows.filter(function (r) { return r.discounted_rate_num === 0; }).length;
        var subLabel = STATE.activeIndex === "active_qdii" ? __("qdii.summaryActiveQdiiSub") : indexLabel(STATE.activeIndex) + __("qdii.summaryOtcSuffix");

        wrap.innerHTML = [
            summaryCard(__("qdii.candidateFunds"), rows.length + __("qdii.unitCount"), subLabel),
            summaryCard(__("qdii.publicAvailable"), buyable.length + __("qdii.unitCount"), buyable.length ? __("qdii.needAlipayVerify") : __("qdii.mostSuspended")),
            summaryCard(__("qdii.dailyLimit"), maxLimit == null ? "--" : fmtMoney(minLimit) + " - " + fmtMoney(maxLimit), __("qdii.limitSubjectToChange")),
            summaryCard(__("qdii.zeroFeeShare"), zeroFee + __("qdii.unitCount"), __("qdii.mostlyCClass")),
        ].join("");
    }

    function summaryCard(label, value, sub) {
        return [
            '<div class="qdii-summary-item">',
            '<div class="qdii-summary-label">', escapeHtml(label), '</div>',
            '<div class="qdii-summary-value">', escapeHtml(value), '</div>',
            '<div class="qdii-summary-sub">', escapeHtml(sub), '</div>',
            '</div>',
        ].join("");
    }

    function renderTable() {
        var body = $("qdiiFundsBody");
        if (!body) return;
        var rows = rowsForActiveIndex();
        if (!rows.length) {
            body.innerHTML = '<tr><td colspan="22" style="text-align:center;padding:24px;color:var(--apple-text-secondary);">' + escapeHtml(__("qdii.noMatchingFunds")) + '</td></tr>';
            return;
        }
        body.innerHTML = rows.map(function (row) {
            var statusClass = row.buyable ? "buyable" : "paused";
            var statusText = row.buyable ? __("qdii.statusAvailable") : __("qdii.statusSuspended");
            var statusDetail = row.purchase_status || "--";
            var feeText = fmtRate(row.discounted_rate);
            var rateClass = row.discounted_rate_num === 0 ? "etf-pos" : "";
            return [
                "<tr>",
                "<td>", escapeHtml(indexLabel(row.index)), "</td>",
                '<td><a href="', escapeHtml(row.source_url), '" target="_blank" rel="noopener">', escapeHtml(row.code), "</a></td>",
                '<td title="', escapeHtml(row.name), '">', escapeHtml(row.name), "</td>",
                "<td>", escapeHtml(row.share_class || "--"), "</td>",
                "<td>", escapeHtml(row.fund_type || "--"), "</td>",
                "<td>", escapeHtml(row.company || "--"), "</td>",
                '<td class="qdii-num">', escapeHtml(fmtScale(row.fund_scale)), "</td>",
                "<td>", escapeHtml(row.fund_manager || "--"), "</td>",
                '<td><span class="qdii-status-badge ', statusClass, '">', statusText, '</span> <span title="', escapeHtml(statusDetail), '">', escapeHtml(statusDetail), "</span></td>",
                '<td class="qdii-num">', escapeHtml(fmtMoney(row.daily_limit)), "</td>",
                '<td class="qdii-num">', escapeHtml(fmtMoney(row.min_purchase)), "</td>",
                '<td class="qdii-num ', rateClass, '">', escapeHtml(feeText), "</td>",
                '<td class="qdii-num">', escapeHtml(fmtRate(row.source_rate)), "</td>",
                '<td class="qdii-num ', pctClass(row.daily_return_pct), '">', escapeHtml(fmtPct(row.daily_return_pct)), "</td>",
                '<td class="qdii-num ', pctClass(row.return_1m_pct), '">', escapeHtml(fmtPct(row.return_1m_pct)), "</td>",
                '<td class="qdii-num ', pctClass(row.return_3m_pct), '">', escapeHtml(fmtPct(row.return_3m_pct)), "</td>",
                '<td class="qdii-num ', pctClass(row.return_6m_pct), '">', escapeHtml(fmtPct(row.return_6m_pct)), "</td>",
                '<td class="qdii-num ', pctClass(row.return_1y_pct), '">', escapeHtml(fmtPct(row.return_1y_pct)), "</td>",
                '<td class="qdii-num ', pctClass(row.return_3y_pct), '">', escapeHtml(fmtPct(row.return_3y_pct)), "</td>",
                '<td class="qdii-num ', pctClass(row.return_since_inception_pct), '">', escapeHtml(fmtPct(row.return_since_inception_pct)), "</td>",
                "<td>", escapeHtml(row.nav_date || "--"), "</td>",
                "<td>", escapeHtml(row.redeem_status || "--"), "</td>",
                "</tr>",
            ].join("");
        }).join("");
    }

    function renderGuide() {
        var guide = $("qdiiFundsGuide");
        if (!guide) return;
        var rows = rowsForActiveIndex();
        var buyable = rows.filter(function (r) { return r.buyable; });
        if (STATE.activeIndex === "active_qdii") {
            renderActiveQdiiGuide(guide, rows, buyable);
            return;
        }
        var bestLimit = buyable.slice().sort(function (a, b) {
            return (b.daily_limit || -1) - (a.daily_limit || -1);
        })[0];
        var lowFeeA = buyable.filter(function (r) { return r.share_class === "A" && r.discounted_rate_num != null; })
            .sort(function (a, b) { return a.discounted_rate_num - b.discounted_rate_num; }).slice(0, 3);

        guide.innerHTML = [
            guideBlock(__("qdii.guideToday"), [
                buyable.length ? __("qdii.guideToday1") : __("qdii.guideToday1Alt"),
                bestLimit ? __("qdii.guideToday2", {code: bestLimit.code, company: bestLimit.company, limit: fmtMoney(bestLimit.daily_limit)}) : __("qdii.guideToday2Alt"),
                __("qdii.guideToday3")
            ]),
            guideBlock(__("qdii.guideShareCode"), [
                __("qdii.guideShareCode1"),
                __("qdii.guideShareCode2"),
                __("qdii.guideShareCode3")
            ]),
            guideBlock(__("qdii.guideReminder"), [
                __("qdii.guideReminder1"),
                __("qdii.guideReminder2"),
                lowFeeA.length ? __("qdii.guideReminder3", {list: lowFeeA.map(function (r) { return r.code + "(" + r.discounted_rate + ")"; }).join("、")}) : __("qdii.guideReminder3Alt")
            ]),
        ].join("");
    }

    function renderActiveQdiiGuide(guide, rows, buyable) {
        var typeCounts = {};
        rows.forEach(function (r) {
            var key = r.fund_type || __("qdii.fundTypeOther");
            typeCounts[key] = (typeCounts[key] || 0) + 1;
        });
        var topTypes = Object.keys(typeCounts).sort(function (a, b) { return typeCounts[b] - typeCounts[a]; }).slice(0, 3);
        var bestLimit = buyable.slice().sort(function (a, b) {
            return (b.daily_limit || -1) - (a.daily_limit || -1);
        })[0];
        var lowFeeA = buyable.filter(function (r) { return r.share_class === "A" && r.discounted_rate_num != null; })
            .sort(function (a, b) { return a.discounted_rate_num - b.discounted_rate_num; }).slice(0, 3);

        guide.innerHTML = [
            guideBlock(__("qdii.guideActiveQdii"), [
                __("qdii.guideActiveQdii1"),
                topTypes.length ? __("qdii.guideActiveQdii2", {list: topTypes.map(function (t) { return t + " " + typeCounts[t] + __("qdii.unitCount"); }).join("、")}) : __("qdii.guideActiveQdii2Alt"),
                bestLimit ? __("qdii.guideActiveQdii3", {code: bestLimit.code, company: bestLimit.company, limit: fmtMoney(bestLimit.daily_limit)}) : __("qdii.guideActiveQdii3Alt")
            ]),
            guideBlock(__("qdii.guideActiveKey"), [
                __("qdii.guideActiveKey1"),
                lowFeeA.length ? __("qdii.guideActiveKey2", {list: lowFeeA.map(function (r) { return r.code + "(" + r.discounted_rate + ")"; }).join("、")}) : __("qdii.guideActiveKey2Alt"),
                __("qdii.guideActiveKey3")
            ]),
            guideBlock(__("qdii.guideShareCode"), [
                __("qdii.guideShareCode1"),
                __("qdii.guideShareCode2"),
                __("qdii.guideShareCode3")
            ]),
            guideBlock(__("qdii.guideDataScope"), [
                __("qdii.guideDataScope1"),
                __("qdii.guideDataScope2"),
                __("qdii.guideDataScope3")
            ]),
        ].join("");
    }

    function guideBlock(title, items) {
        return [
            '<div class="qdii-guide-block">',
            '<div class="qdii-guide-title">', escapeHtml(title), '</div>',
            '<ul>',
            items.map(function (item) { return '<li>' + escapeHtml(item) + '</li>'; }).join(""),
            '</ul>',
            '</div>',
        ].join("");
    }

    function renderAll() {
        renderFilterOptions();
        updateSortHeaders();
        renderSummary();
        renderTable();
        renderGuide();
        var updated = $("qdiiFundsUpdated");
        if (updated && STATE.data) {
            var status = cacheStatusLabel(STATE.data.cache_status);
            updated.textContent = [fmtUpdated(STATE.data.updated_at), status].filter(Boolean).join(" · ");
        }
        var note = $("qdiiFundsNote");
        if (note && STATE.data && STATE.data.disclaimer) note.textContent = STATE.data.disclaimer;
    }

    function loadData(force) {
        if (STATE.loading) return Promise.resolve();
        setLoading(true);
        setError("");
        var url = QDII_FUNDS_ENDPOINT + "?index=all" + (force ? "&fresh=1" : "");
        return fetch(url)
            .then(function (res) {
                if (!res.ok) throw new Error(__("qdii.interfaceError") + res.status);
                return res.json();
            })
            .then(function (data) {
                STATE.data = data;
                STATE.loaded = true;
                renderAll();
            })
            .catch(function (err) {
                setError(__("qdii.fetchFailed") + (err && err.message ? err.message : err));
            })
            .finally(function () {
                setLoading(false);
            });
    }

    function init() {
        var panel = $("tab-qdii-funds");
        if (!panel) return;

        document.querySelectorAll("#qdiiFundsTabs .transfer-tab").forEach(function (btn) {
            btn.addEventListener("click", function () {
                document.querySelectorAll("#qdiiFundsTabs .transfer-tab").forEach(function (b) { b.classList.remove("active"); });
                btn.classList.add("active");
                STATE.activeIndex = btn.dataset.qdiiIndex || "nasdaq100";
                STATE.filters.share_class = "";
                STATE.filters.fund_type = "";
                STATE.filters.company = "";
                STATE.filters.status = "";
                renderAll();
            });
        });

        var filterShare = $("qdiiFilterShare");
        if (filterShare) filterShare.addEventListener("change", function () {
            STATE.filters.share_class = filterShare.value || "";
            renderAll();
        });

        var filterType = $("qdiiFilterType");
        if (filterType) filterType.addEventListener("change", function () {
            STATE.filters.fund_type = filterType.value || "";
            renderAll();
        });

        var filterCompany = $("qdiiFilterCompany");
        if (filterCompany) filterCompany.addEventListener("change", function () {
            STATE.filters.company = filterCompany.value || "";
            renderAll();
        });

        var filterStatus = $("qdiiFilterStatus");
        if (filterStatus) filterStatus.addEventListener("change", function () {
            STATE.filters.status = filterStatus.value || "";
            renderAll();
        });

        var clearBtn = $("qdiiClearFilters");
        if (clearBtn) clearBtn.addEventListener("click", clearFiltersAndSort);

        document.querySelectorAll("#qdiiFundsTable th.qdii-sortable").forEach(function (th) {
            th.addEventListener("click", function () {
                var col = th.dataset.qdiiSort;
                if (!col) return;
                if (STATE.sortCol === col) {
                    STATE.sortDir = STATE.sortDir === "asc" ? "desc" : "asc";
                } else {
                    STATE.sortCol = col;
                    STATE.sortDir = (NUMERIC_SORT_COLUMNS[col] || col === "nav_date") ? "desc" : "asc";
                }
                renderAll();
            });
        });

        var refresh = $("qdiiFundsRefresh");
        if (refresh) refresh.addEventListener("click", function () { loadData(true); });
    }

    window._qdiiFundsActivate = function () {
        if (!STATE.loaded && !STATE.loading) loadData(false);
        else renderAll();
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
