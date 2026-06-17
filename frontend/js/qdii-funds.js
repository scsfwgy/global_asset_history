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
        if (n >= 10000) return (n / 10000).toFixed(n % 10000 === 0 ? 0 : 1) + "万";
        return n.toFixed(n % 1 === 0 ? 0 : 2) + "元";
    }

    function fmtRate(value) {
        return value || "--";
    }

    function fmtScale(value) {
        if (value == null || value === "") return "--";
        var n = Number(value);
        if (!isFinite(n)) return "--";
        if (n >= 100000000) return (n / 100000000).toFixed(2) + "亿";
        if (n >= 10000) return (n / 10000).toFixed(0) + "万";
        return n.toFixed(0) + "元";
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
        return "更新 " + pad(d.getHours()) + ":" + pad(d.getMinutes());
    }

    function cacheStatusLabel(status) {
        if (status === "fresh") return "刚更新";
        if (status === "memory") return "内存缓存";
        if (status === "local") return "本地快照";
        if (status === "local_stale_upstream_failed") return "本地快照 · 上游失败";
        if (status === "local_stale_upstream_partial") return "本地快照 · 上游不完整";
        return "";
    }

    function indexLabel(key) {
        if (STATE.data && STATE.data.labels && STATE.data.labels[key]) return STATE.data.labels[key];
        if (key === "active_qdii") return "QDII主动";
        return key === "sp500" ? "标普500" : "纳指100";
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
        if (col === "status") return row.buyable ? "可买" : "暂停";
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
        return prefix + "：" + (value || "全部");
    }

    function setSelectOptions(id, prefix, values, current) {
        var select = $(id);
        if (!select) return;
        var normalizedValues = values.filter(function (v) { return v != null && v !== ""; });
        var hasCurrent = !current || normalizedValues.indexOf(current) >= 0;
        var html = ['<option value="">' + escapeHtml(prefix + "：全部") + '</option>'];
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
        setSelectOptions("qdiiFilterShare", "份额", unique("share_class"), STATE.filters.share_class);
        setSelectOptions("qdiiFilterType", "类型", unique("fund_type"), STATE.filters.fund_type);
        setSelectOptions("qdiiFilterCompany", "公司", unique("company"), STATE.filters.company);
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
        var subLabel = STATE.activeIndex === "active_qdii" ? "主动 QDII 人民币份额" : indexLabel(STATE.activeIndex) + " 场外人民币份额";

        wrap.innerHTML = [
            summaryCard("候选基金", rows.length + "只", subLabel),
            summaryCard("公开可买", buyable.length + "只", buyable.length ? "仍需支付宝 App 复核" : "当前公开接口多为暂停"),
            summaryCard("单日限额", maxLimit == null ? "--" : fmtMoney(minLimit) + " - " + fmtMoney(maxLimit), "QDII 额度可能日内变化"),
            summaryCard("零申购费份额", zeroFee + "只", "多为 C 类，需看销售服务费"),
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
            body.innerHTML = '<tr><td colspan="22" style="text-align:center;padding:24px;color:var(--apple-text-secondary);">没有符合筛选条件的基金</td></tr>';
            return;
        }
        body.innerHTML = rows.map(function (row) {
            var statusClass = row.buyable ? "buyable" : "paused";
            var statusText = row.buyable ? "可买" : "暂停";
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
            guideBlock("今天怎么筛", [
                buyable.length ? "先看“公开可买”，再按单日限额从高到低排。" : "公开接口当前没有可买项，支付宝里也大概率需要等额度。",
                bestLimit ? "当前限额较高的候选：" + bestLimit.code + " " + bestLimit.company + "，" + fmtMoney(bestLimit.daily_limit) + "。" : "限额字段缺失时，以支付宝下单页为准。",
                "用代码搜索基金，避免搜名称时混进场内 ETF 或行业指数。"
            ]),
            guideBlock("份额字母速查", [
                "A 类常见为申购时收申购费，不从该份额资产中计提销售服务费；总结：A 类更适合长期持有。",
                "C 类常见为不收申购费，但按日计提销售服务费，持有越久越要比较总成本；总结：C 类更适合短期持有。",
                "B/D/E/I 等字母没有全市场统一含义，可能对应后端收费、特定渠道、币种、门槛或机构份额。"
            ]),
            guideBlock("攻略提醒", [
                "QDII 限额经常变，表格适合做每日快照。",
                "支付宝最终可买状态、优惠券、账号限额以 App 为准。",
                lowFeeA.length ? "A 类低费率候选：" + lowFeeA.map(function (r) { return r.code + "(" + r.discounted_rate + ")"; }).join("、") + "；最终看销售服务费、赎回费和持有时间。" : "短期偏 C、长期偏 A 只是经验，最终看销售服务费、赎回费和持有时间。"
            ]),
        ].join("");
    }

    function renderActiveQdiiGuide(guide, rows, buyable) {
        var typeCounts = {};
        rows.forEach(function (r) {
            var key = r.fund_type || "其他";
            typeCounts[key] = (typeCounts[key] || 0) + 1;
        });
        var topTypes = Object.keys(typeCounts).sort(function (a, b) { return typeCounts[b] - typeCounts[a]; }).slice(0, 3);
        var bestLimit = buyable.slice().sort(function (a, b) {
            return (b.daily_limit || -1) - (a.daily_limit || -1);
        })[0];
        var lowFeeA = buyable.filter(function (r) { return r.share_class === "A" && r.discounted_rate_num != null; })
            .sort(function (a, b) { return a.discounted_rate_num - b.discounted_rate_num; }).slice(0, 3);

        guide.innerHTML = [
            guideBlock("主动 QDII 怎么筛", [
                "先按类型分层看：股票/混合偏股偏权益，纯债/混合债偏美元债或海外债。",
                topTypes.length ? "当前样本最多的类型：" + topTypes.map(function (t) { return t + " " + typeCounts[t] + "只"; }).join("、") + "。" : "类型字段缺失时，回到基金详情页看投资范围。",
                bestLimit ? "当前公开可买且限额较高的候选：" + bestLimit.code + " " + bestLimit.company + "，" + fmtMoney(bestLimit.daily_limit) + "。" : "公开接口当前没有可买项，支付宝里也大概率需要等额度。"
            ]),
            guideBlock("主动基金重点", [
                "不要只看短期涨幅，重点看基金经理、主题范围、地区暴露、规模和回撤。",
                lowFeeA.length ? "A 类折扣费率较低候选：" + lowFeeA.map(function (r) { return r.code + "(" + r.discounted_rate + ")"; }).join("、") + "。" : "长期持有再比较 A 类申购费和持有成本。",
                "C 类零申购费不等于低成本，还要看销售服务费和赎回费。"
            ]),
            guideBlock("份额字母速查", [
                "A 类常见为申购时收申购费，不从该份额资产中计提销售服务费；总结：A 类更适合长期持有。",
                "C 类常见为不收申购费，但按日计提销售服务费，持有越久越要比较总成本；总结：C 类更适合短期持有。",
                "B/D/E/I 等字母没有全市场统一含义，可能对应后端收费、特定渠道、币种、门槛或机构份额。"
            ]),
            guideBlock("数据口径", [
                "这里自动排除了指数、ETF、联接、LOF、FOF、商品、美元/港币份额。",
                "这是公开接口筛选结果，不等同于支付宝当前全部可售清单。",
                "客户若要严格“主动权益基金”，可以再排除债券类 QDII。"
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
                if (!res.ok) throw new Error("接口返回 " + res.status);
                return res.json();
            })
            .then(function (data) {
                STATE.data = data;
                STATE.loaded = true;
                renderAll();
            })
            .catch(function (err) {
                setError("获取 QDII 基金数据失败：" + (err && err.message ? err.message : err));
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
