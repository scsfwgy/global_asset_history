/**
 * QDII fund tracker for Nasdaq-100 / S&P 500 public fund purchase data.
 */
(function () {
    var STATE = {
        loaded: false,
        loading: false,
        activeIndex: "nasdaq100",
        onlyBuyable: false,
        preferC: false,
        data: null,
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
        return key === "sp500" ? "标普500" : "纳指100";
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
        var rows = STATE.data && STATE.data.groups ? (STATE.data.groups[STATE.activeIndex] || []) : [];
        rows = rows.slice();
        if (STATE.onlyBuyable) {
            rows = rows.filter(function (row) { return !!row.buyable; });
        }
        if (STATE.preferC) {
            rows.sort(function (a, b) {
                var ac = a.share_class === "C" ? 0 : 1;
                var bc = b.share_class === "C" ? 0 : 1;
                if (ac !== bc) return ac - bc;
                var al = a.daily_limit == null ? -1 : a.daily_limit;
                var bl = b.daily_limit == null ? -1 : b.daily_limit;
                return bl - al;
            });
        }
        return rows;
    }

    function renderSummary() {
        var wrap = $("qdiiFundsSummary");
        if (!wrap) return;
        var rows = STATE.data && STATE.data.groups ? (STATE.data.groups[STATE.activeIndex] || []) : [];
        var buyable = rows.filter(function (r) { return r.buyable; });
        var limitSource = buyable.length ? buyable : rows;
        var limits = limitSource.map(function (r) { return r.daily_limit; }).filter(function (v) { return v != null; });
        var maxLimit = limits.length ? Math.max.apply(null, limits) : null;
        var minLimit = limits.length ? Math.min.apply(null, limits) : null;
        var zeroFee = rows.filter(function (r) { return r.discounted_rate_num === 0; }).length;

        wrap.innerHTML = [
            summaryCard("候选基金", rows.length + "只", indexLabel(STATE.activeIndex) + " 场外人民币份额"),
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
            body.innerHTML = '<tr><td colspan="12" style="text-align:center;padding:24px;color:var(--apple-text-secondary);">没有符合筛选条件的基金</td></tr>';
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
                "<td>", escapeHtml(row.company || "--"), "</td>",
                '<td><span class="qdii-status-badge ', statusClass, '">', statusText, '</span> <span title="', escapeHtml(statusDetail), '">', escapeHtml(statusDetail), "</span></td>",
                "<td>", escapeHtml(fmtMoney(row.daily_limit)), "</td>",
                "<td>", escapeHtml(fmtMoney(row.min_purchase)), "</td>",
                '<td class="', rateClass, '">', escapeHtml(feeText), "</td>",
                "<td>", escapeHtml(fmtRate(row.source_rate)), "</td>",
                "<td>", escapeHtml(row.nav_date || "--"), "</td>",
                "<td>", escapeHtml(row.redeem_status || "--"), "</td>",
                "</tr>",
            ].join("");
        }).join("");
    }

    function renderGuide() {
        var guide = $("qdiiFundsGuide");
        if (!guide) return;
        var rows = STATE.data && STATE.data.groups ? (STATE.data.groups[STATE.activeIndex] || []) : [];
        var buyable = rows.filter(function (r) { return r.buyable; });
        var bestLimit = buyable.slice().sort(function (a, b) {
            return (b.daily_limit || -1) - (a.daily_limit || -1);
        })[0];
        var zeroFee = buyable.filter(function (r) { return r.discounted_rate_num === 0; }).slice(0, 3);
        var lowFeeA = buyable.filter(function (r) { return r.share_class === "A" && r.discounted_rate_num != null; })
            .sort(function (a, b) { return a.discounted_rate_num - b.discounted_rate_num; }).slice(0, 3);

        guide.innerHTML = [
            guideBlock("今天怎么筛", [
                buyable.length ? "先看“公开可买”，再按单日限额从高到低排。" : "公开接口当前没有可买项，支付宝里也大概率需要等额度。",
                bestLimit ? "当前限额较高的候选：" + bestLimit.code + " " + bestLimit.company + "，" + fmtMoney(bestLimit.daily_limit) + "。" : "限额字段缺失时，以支付宝下单页为准。",
                "用代码搜索基金，避免搜名称时混进场内 ETF 或行业指数。"
            ]),
            guideBlock("A/C 类取舍", [
                zeroFee.length ? "C 类零申购费候选：" + zeroFee.map(function (r) { return r.code; }).join("、") + "。" : "C 类通常零申购费，但要查销售服务费。",
                lowFeeA.length ? "A 类折扣费率较低候选：" + lowFeeA.map(function (r) { return r.code + "(" + r.discounted_rate + ")"; }).join("、") + "。" : "长期持有再比较 A 类申购费和持有成本。",
                "短期偏 C，长期偏 A 只是经验，最终看销售服务费、赎回费和持有时间。"
            ]),
            guideBlock("攻略提醒", [
                "QDII 限额经常变，表格适合做每日快照。",
                "支付宝最终可买状态、优惠券、账号限额以 App 为准。",
                "场内 ETF 另看溢价率，不要把场外基金限额问题直接用高溢价场内 ETF 硬替代。"
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
                renderAll();
            });
        });

        var onlyBuyable = $("qdiiOnlyBuyable");
        if (onlyBuyable) {
            onlyBuyable.addEventListener("change", function () {
                STATE.onlyBuyable = !!onlyBuyable.checked;
                renderAll();
            });
        }

        var preferC = $("qdiiPreferC");
        if (preferC) {
            preferC.addEventListener("change", function () {
                STATE.preferC = !!preferC.checked;
                renderAll();
            });
        }

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
