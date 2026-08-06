/**
 * FX Calculator — a sub-view of the Exchange Loss page.
 *
 * Renders inside #fxCalcView. Any-pair conversion backed by Frankfurter (ECB)
 * reference rates served from /api/price-change/exchange-rates: base is EUR and
 * any held->target pair is amount * rates[target] / rates[base].
 *
 * Layout mirrors the DevTools exchange tool: an input row (amount + base picker
 * + refresh), a comparison table with one row per target currency (searchable
 * picker, forward/reverse rate, converted value, copy/remove) and localStorage
 * history chips.
 */

(function () {
    var COMMON_CODES = ["CNY", "USD", "EUR", "JPY", "KRW", "HKD", "GBP", "AUD", "CAD", "SGD", "CHF", "THB"];
    var DEFAULT_TARGETS = ["USD", "HKD", "JPY", "KRW", "EUR"];
    var HISTORY_KEY = "fxcalc_history";
    var MAX_HISTORY = 10;

    var _rates = null;          // {CODE: rate_per_EUR}
    var _currencyList = null;   // [{code, name, symbol}]
    var _base = "CNY";
    var _targets = DEFAULT_TARGETS.slice();
    var _loaded = false;
    var _loading = false;
    var _displayNames = null;

    function $(id) { return document.getElementById(id); }
    function t(key) { return (typeof window.__ === "function" && window.__(key)) || key; }
    function localeName() { return document.documentElement.lang === "en" ? "en-US" : "zh-CN"; }

    function currency(code) {
        if (!_currencyList) return null;
        for (var i = 0; i < _currencyList.length; i++) {
            if (_currencyList[i].code === code) return _currencyList[i];
        }
        return null;
    }

    function currencyName(code) {
        var item = currency(code);
        if (item && item.name && item.name !== code) return item.name;
        try {
            if (!_displayNames) _displayNames = new Intl.DisplayNames([localeName()], { type: "currency" });
            var name = _displayNames.of(code);
            if (name && name !== code) return name;
        } catch (e) { /* fall through */ }
        return code;
    }

    function fmt(v) {
        if (!Number.isFinite(v)) return "—";
        if (v === 0) return "0";
        var abs = Math.abs(v);
        if (abs < 0.000001 || abs >= 1e15) return v.toExponential(6);
        return new Intl.NumberFormat(localeName(), {
            maximumFractionDigits: abs < 1 ? 8 : (abs < 100 ? 6 : 2),
            minimumFractionDigits: 0,
        }).format(v);
    }

    function parseAmount(raw) {
        var value = String(raw).trim();
        if (!/^(?:\d+\.?\d*|\.\d+)$/.test(value)) return null;
        var amount = Number(value);
        return Number.isFinite(amount) && amount >= 0 && amount <= 1e15 ? amount : null;
    }

    function escapeHtml(value) {
        return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }

    function sortedCurrencies() {
        if (!_currencyList) return [];
        return _currencyList.slice().sort(function (a, b) {
            var ia = COMMON_CODES.indexOf(a.code), ib = COMMON_CODES.indexOf(b.code);
            if (ia === -1 && ib === -1) return a.code.localeCompare(b.code);
            if (ia === -1) return 1;
            if (ib === -1) return -1;
            return ia - ib;
        });
    }

    // ── currency picker (searchable popover) ─────────────────────────

    function pickerMarkup(id, code, excluded, label) {
        var item = currency(code);
        var content = item
            ? '<span class="fxc-picker-mark" aria-hidden="true">' + escapeHtml(item.symbol || "¤") + '</span>' +
              '<span class="fxc-picker-code">' + escapeHtml(code) + '</span>' +
              '<span class="fxc-picker-name">' + escapeHtml(currencyName(code)) + '</span>'
            : '<span class="fxc-picker-add">' + escapeHtml(t("fxCalc.addCurrency")) + '</span>';
        return '<div class="fxc-picker' + (item ? "" : " is-add") + '" data-code="' + escapeHtml(code) + '" data-excluded="' + escapeHtml(excluded.join(",")) + '">' +
            '<button type="button" class="fxc-picker-trigger"' + (id ? ' id="' + id + '"' : "") + ' aria-haspopup="listbox" aria-expanded="false" aria-label="' + escapeHtml(label) + '">' + content + '<span class="fxc-picker-chevron" aria-hidden="true">▾</span></button>' +
            '<div class="fxc-popover" hidden></div></div>';
    }

    function bindPicker(picker, onSelect) {
        if (!picker) return;
        picker._onCurrencySelect = onSelect;
        var trigger = picker.querySelector(".fxc-picker-trigger");
        if (trigger) trigger.addEventListener("click", function (event) {
            event.stopPropagation();
            var willOpen = picker.querySelector(".fxc-popover").hidden;
            closePickers();
            if (willOpen) openPicker(picker);
        });
    }

    function openPicker(picker) {
        var popover = picker.querySelector(".fxc-popover");
        popover.hidden = false;
        picker.classList.add("is-open");
        picker.querySelector(".fxc-picker-trigger").setAttribute("aria-expanded", "true");
        popover.innerHTML =
            '<div class="fxc-popover-search"><span aria-hidden="true">⌕</span>' +
            '<input class="fxc-search" type="search" autocomplete="off" placeholder="' + escapeHtml(t("fxCalc.searchCurrency")) + '" aria-label="' + escapeHtml(t("fxCalc.searchCurrency")) + '"></div>' +
            '<div class="fxc-popover-list" role="listbox"></div>';
        var search = popover.querySelector(".fxc-search");
        search.addEventListener("input", function () { renderPickerList(picker, this.value); positionPicker(picker); });
        search.addEventListener("keydown", function (event) {
            if (event.key === "Escape") { closePickers(); picker.querySelector(".fxc-picker-trigger").focus(); }
        });
        renderPickerList(picker, "");
        // Wait a frame for the popover to lay out before measuring it for
        // viewport clamping / flipping above when it would overflow the bottom.
        requestAnimationFrame(function () { positionPicker(picker); });
    }

    // Keep the popover inside the viewport (fixed, so it also escapes the
    // overflow:hidden of .fxcalc-table). Flips above when it would exceed
    // the bottom edge — same approach as the DevTools exchange tool.
    function positionPicker(picker) {
        var trigger = picker.querySelector(".fxc-picker-trigger");
        var popover = picker.querySelector(".fxc-popover");
        if (!trigger || !popover || popover.hidden) return;
        var triggerRect = trigger.getBoundingClientRect();
        var popoverRect = popover.getBoundingClientRect();
        var left = Math.max(8, Math.min(triggerRect.left, window.innerWidth - popoverRect.width - 8));
        var top = triggerRect.bottom + 4;
        if (top + popoverRect.height > window.innerHeight - 8 && triggerRect.top > popoverRect.height + 8) {
            top = triggerRect.top - popoverRect.height - 4;
        }
        popover.style.left = left + "px";
        popover.style.top = Math.max(8, top) + "px";
    }

    function renderPickerList(picker, query) {
        var list = picker.querySelector(".fxc-popover-list");
        var selected = picker.dataset.code;
        var excluded = (picker.dataset.excluded || "").split(",").filter(Boolean);
        var normalized = String(query || "").trim().toLocaleLowerCase(localeName());
        var matches = sortedCurrencies().filter(function (item) {
            if (excluded.indexOf(item.code) !== -1 && item.code !== selected) return false;
            if (!normalized) return true;
            var haystack = [item.code, item.name, currencyName(item.code), item.symbol].join(" ").toLocaleLowerCase(localeName());
            return haystack.indexOf(normalized) !== -1;
        });
        if (!matches.length) {
            list.innerHTML = '<div class="fxc-popover-empty">' + escapeHtml(t("fxCalc.noCurrencyMatch")) + '</div>';
            return;
        }
        function optionMarkup(item) {
            return '<button type="button" class="fxc-option' + (item.code === selected ? " is-selected" : "") + '" role="option" aria-selected="' + (item.code === selected ? "true" : "false") + '" data-code="' + item.code + '">' +
                '<span class="fxc-option-mark" aria-hidden="true">' + escapeHtml(item.symbol || "¤") + '</span>' +
                '<strong>' + item.code + '</strong>' +
                '<span>' + escapeHtml(currencyName(item.code)) + '</span>' +
                '<small>' + escapeHtml(item.symbol || item.code) + '</small></button>';
        }
        if (!normalized) {
            var recommended = matches.filter(function (item) { return COMMON_CODES.indexOf(item.code) !== -1; });
            var all = matches.filter(function (item) { return COMMON_CODES.indexOf(item.code) === -1; });
            list.innerHTML = '<div class="fxc-group-label">' + escapeHtml(t("fxCalc.recommendedCurrencies")) + '</div>' + recommended.map(optionMarkup).join("") +
                (all.length ? '<div class="fxc-group-label">' + escapeHtml(t("fxCalc.allCurrencies")) + '</div>' + all.map(optionMarkup).join("") : "");
        } else {
            list.innerHTML = matches.map(optionMarkup).join("");
        }
        list.querySelectorAll(".fxc-option").forEach(function (button) {
            button.addEventListener("click", function (event) {
                event.stopPropagation();
                var code = this.dataset.code;
                closePickers();
                if (picker._onCurrencySelect) picker._onCurrencySelect(code);
            });
        });
    }

    function closePickers() {
        var host = $("fxCalcView");
        if (!host) return;
        host.querySelectorAll(".fxc-picker.is-open").forEach(function (picker) {
            picker.classList.remove("is-open");
            picker.querySelector(".fxc-picker-trigger").setAttribute("aria-expanded", "false");
            picker.querySelector(".fxc-popover").hidden = true;
        });
    }

    // ── conversion ───────────────────────────────────────────────────

    function converted(amount, target) {
        if (!_rates || !_rates[_base] || !_rates[target]) return null;
        // rates[X] = "1 EUR = <rate> X", so 1 base = rates[target]/rates[base] target.
        return amount * _rates[target] / _rates[_base];
    }

    // ── shell + renders ──────────────────────────────────────────────

    function renderShell(host) {
        host.innerHTML =
            '<div class="fxcalc">' +
            '  <div class="fxcalc-input-row">' +
            '    <label class="fxcalc-field"><span class="fxcalc-label" data-fxc-key="fxCalc.amount">' + t("fxCalc.amount") + '</span>' +
            '      <input id="fxcAmount" class="pc-bt-input fxcalc-amount" type="number" inputmode="decimal" min="0" value="100"></label>' +
            '    <label class="fxcalc-field"><span class="fxcalc-label" data-fxc-key="fxCalc.baseCurrency">' + t("fxCalc.baseCurrency") + '</span>' +
            '      <div id="fxcBaseWrap"></div></label>' +
            '    <button id="fxcRefresh" class="pc-btn fxcalc-refresh" type="button" aria-label="' + escapeHtml(t("fxCalc.refresh")) + '">↻ <span data-fxc-key="fxCalc.refresh">' + t("fxCalc.refresh") + '</span></button>' +
            '  </div>' +
            '  <div id="fxcStatus" class="fxcalc-status" role="status" aria-live="polite"></div>' +
            '  <div class="fxcalc-head"><h2 class="fxcalc-head-title" data-fxc-key="fxCalc.comparison">' + t("fxCalc.comparison") + '</h2><div id="fxcAddWrap"></div></div>' +
            '  <div id="fxcResults" class="fxcalc-results"></div>' +
            '  <p class="fxcalc-note">' + t("fxCalc.referenceNote") + '</p>' +
            '  <div id="fxcHistory" class="fxcalc-history"></div>' +
            '</div>';
        $("fxcAmount").addEventListener("input", function () { renderResults(); });
        $("fxcAmount").addEventListener("blur", saveCurrentHistory);
        $("fxcRefresh").addEventListener("click", function () { fetchRates(true); });
        host.addEventListener("click", function (event) { if (!event.target.closest(".fxc-picker")) closePickers(); });
        renderBasePicker();
        renderResults();
        renderHistory();
    }

    function updateShellText() {
        var host = $("fxCalcView");
        if (!host) return;
        host.querySelectorAll("[data-fxc-key]").forEach(function (el) {
            el.textContent = t(el.getAttribute("data-fxc-key"));
        });
        var refresh = $("fxcRefresh");
        if (refresh) refresh.setAttribute("aria-label", t("fxCalc.refresh"));
    }

    function renderBasePicker() {
        var wrap = $("fxcBaseWrap");
        if (!wrap) return;
        wrap.innerHTML = pickerMarkup("fxcBase", _base, [], t("fxCalc.baseCurrency"));
        bindPicker(wrap.querySelector(".fxc-picker"), function (code) {
            if (code === _base || !_rates[code]) return;
            var previousBase = _base;
            _base = code;
            replaceBaseTarget(previousBase);
            renderBasePicker();
            renderResults();
            saveCurrentHistory();
        });
    }

    function renderResults() {
        if (!$("fxcResults")) return;
        closePickers();
        var amountInput = $("fxcAmount");
        var amount = parseAmount(amountInput.value);
        amountInput.classList.toggle("is-invalid", amount === null);
        var rows = _targets.map(function (code, index) {
            var item = currency(code) || { code: code, symbol: code };
            var value = amount === null ? null : converted(amount, code);
            var oneRate = converted(1, code);
            var reverseRate = (oneRate === null || oneRate === 0) ? null : 1 / oneRate;
            var rateMarkup = oneRate === null
                ? '<span class="fxcalc-waiting">' + escapeHtml(t("fxCalc.waiting")) + '</span>'
                : '<span>1 ' + escapeHtml(_base) + ' = ' + escapeHtml(fmt(oneRate)) + ' ' + escapeHtml(code) + '</span>' +
                  '<span class="fxcalc-rate-reverse">' + escapeHtml(fmt(reverseRate)) + ' ' + escapeHtml(_base) + ' = 1 ' + escapeHtml(code) + '</span>';
            var excluded = [_base].concat(_targets.filter(function (x, i) { return i !== index; }));
            return '<tr class="fxcalc-row" data-index="' + index + '">' +
                '<td class="fxcalc-cell-currency">' + pickerMarkup("", code, excluded, t("fxCalc.currency")) + '</td>' +
                '<td class="fxcalc-cell-rate">' + rateMarkup + '</td>' +
                '<td class="fxcalc-cell-value"><strong>' + (value === null ? "—" : escapeHtml(fmt(value))) + '</strong>' +
                '<span>' + escapeHtml(item.symbol || code) + ' · ' + escapeHtml(code) + '</span></td>' +
                '<td class="fxcalc-cell-actions">' +
                '<button class="pc-btn pc-btn-sm fxc-copy" type="button"' + (value === null ? " disabled" : "") + '>' + escapeHtml(t("fxCalc.copy")) + '</button>' +
                '<button class="pc-btn pc-btn-sm fxc-remove" type="button" aria-label="' + escapeHtml(t("fxCalc.removeCurrency")) + '"' + (_targets.length === 1 ? " disabled" : "") + '>×</button>' +
                '</td></tr>';
        }).join("");
        $("fxcResults").innerHTML =
            '<div class="fxcalc-table-wrap"><table class="fxcalc-table">' +
            '<thead><tr><th data-fxc-key="fxCalc.currency">' + t("fxCalc.currency") + '</th><th data-fxc-key="fxCalc.rate">' + t("fxCalc.rate") + '</th><th data-fxc-key="fxCalc.result">' + t("fxCalc.result") + '</th><th></th></tr></thead>' +
            '<tbody>' + rows + '</tbody></table></div>';
        renderAddPicker();
        bindResults();
    }

    function renderAddPicker() {
        var wrap = $("fxcAddWrap");
        if (!wrap) return;
        var excluded = [_base].concat(_targets);
        wrap.innerHTML = pickerMarkup("fxcAdd", "", excluded, t("fxCalc.addCurrency"));
        var picker = wrap.querySelector(".fxc-picker");
        var trigger = picker.querySelector(".fxc-picker-trigger");
        if (trigger) trigger.disabled = !_currencyList || excluded.length >= _currencyList.length;
        bindPicker(picker, function (code) {
            if (!_rates[code] || code === _base || _targets.indexOf(code) !== -1) return;
            _targets.push(code);
            renderResults();
            saveCurrentHistory();
        });
    }

    function bindResults() {
        var host = $("fxCalcView");
        if (!host) return;
        host.querySelectorAll(".fxcalc-row").forEach(function (row) {
            var index = Number(row.dataset.index);
            bindPicker(row.querySelector(".fxc-picker"), function (code) {
                if (!_rates[code] || code === _base || _targets.indexOf(code) !== -1) return;
                _targets[index] = code;
                renderResults();
                saveCurrentHistory();
            });
            var remove = row.querySelector(".fxc-remove");
            if (remove) remove.addEventListener("click", function () {
                if (_targets.length <= 1) return;
                _targets.splice(index, 1);
                renderResults();
                saveCurrentHistory();
            });
            var copy = row.querySelector(".fxc-copy");
            if (copy) copy.addEventListener("click", function () { copyResult(index); });
        });
    }

    function replaceBaseTarget(previousBase) {
        var index = _targets.indexOf(_base);
        if (index === -1) return;
        var replacement = _rates[previousBase] && _targets.indexOf(previousBase) === -1
            ? currency(previousBase) : null;
        if (!replacement) {
            var pick = sortedCurrencies().find(function (item) {
                return item.code !== _base && _rates[item.code] && _targets.indexOf(item.code) === -1;
            });
            if (pick) replacement = pick;
        }
        if (replacement) _targets[index] = replacement.code;
        else _targets.splice(index, 1);
    }

    function copyResult(index) {
        var amount = parseAmount($("fxcAmount").value);
        var code = _targets[index];
        var value = amount === null ? null : converted(amount, code);
        if (value === null || !navigator.clipboard) return;
        var text = fmt(amount) + " " + _base + " = " + fmt(value) + " " + code;
        navigator.clipboard.writeText(text).then(function () {
            if (typeof window.showCopyToast === "function") window.showCopyToast(t("fxCalc.copied"));
            else setStatus(t("fxCalc.copied"), "ok");
        }).catch(function () { setStatus(t("fxCalc.copyFailed"), "error"); });
    }

    function setStatus(message, type) {
        var status = $("fxcStatus");
        if (!status) return;
        status.className = "fxcalc-status" + (type ? " is-" + type : "");
        status.textContent = message;
    }

    // ── history ──────────────────────────────────────────────────────

    function loadHistory() {
        try {
            var history = JSON.parse(localStorage.getItem(HISTORY_KEY)) || [];
            return Array.isArray(history) ? history.slice(0, MAX_HISTORY) : [];
        } catch (e) { return []; }
    }

    function saveCurrentHistory() {
        if (!$("fxcAmount")) return;
        var raw = $("fxcAmount").value.trim();
        if (parseAmount(raw) === null) return;
        var entry = { amount: raw, base: _base, targets: _targets.slice() };
        var history = loadHistory().filter(function (item) {
            return !(item.amount === entry.amount && item.base === entry.base && JSON.stringify(item.targets) === JSON.stringify(entry.targets));
        });
        history.unshift(entry);
        try { localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(0, MAX_HISTORY))); } catch (e) {}
        renderHistory();
    }

    function renderHistory() {
        var container = $("fxcHistory");
        if (!container) return;
        var history = loadHistory();
        if (!history.length) { container.innerHTML = ""; return; }
        container.innerHTML = '<span class="fxcalc-history-label" data-fxc-key="fxCalc.historyLabel">' + t("fxCalc.historyLabel") + '</span>' + history.map(function (item, index) {
            var label = item.amount + " " + item.base + " → " + item.targets.join(" / ");
            return '<button class="history-chip" type="button" data-index="' + index + '" title="' + escapeHtml(label) + '">' + escapeHtml(label) + '</button>';
        }).join("");
        container.querySelectorAll(".history-chip").forEach(function (button) {
            button.addEventListener("click", function () {
                var item = history[Number(this.dataset.index)];
                if (!item || !_rates[item.base]) return;
                _base = item.base;
                _targets = item.targets.filter(function (code, i, list) {
                    return code !== _base && _rates[code] && list.indexOf(code) === i;
                });
                if (!_targets.length) {
                    var pick = sortedCurrencies().find(function (c) { return c.code !== _base && _rates[c.code]; });
                    if (pick) _targets = [pick.code];
                }
                $("fxcAmount").value = item.amount;
                renderBasePicker();
                renderResults();
            });
        });
    }

    // ── data loading ─────────────────────────────────────────────────

    function fetchRates(force) {
        if (_loading) return;
        _loading = true;
        var refresh = $("fxcRefresh");
        if (refresh) refresh.disabled = true;
        setStatus(t("fxCalc.loading"), "loading");
        fetch(EXCHANGE_RATES_ENDPOINT, { cache: force ? "reload" : "default" })
            .then(function (response) {
                if (!response.ok) throw new Error("HTTP " + response.status);
                return response.json();
            })
            .then(function (data) {
                if (!data.rates || typeof data.rates !== "object") throw new Error("Invalid payload");
                _rates = data.rates;
                _currencyList = (data.currencies || []).map(function (c) {
                    return { code: c.code, name: c.name || c.code, symbol: c.symbol || c.code };
                }).filter(function (c) { return _rates[c.code]; });
                _displayNames = null;
                if (!_rates[_base]) _base = "EUR"; // EUR basis is always present
                _targets = _targets.filter(function (code, i, list) {
                    return code !== _base && _rates[code] && list.indexOf(code) === i;
                });
                if (!_targets.length) {
                    var first = sortedCurrencies().find(function (c) { return c.code !== _base && _rates[c.code]; });
                    if (first) _targets = [first.code];
                }
                _loaded = true;
                setStatus(
                    data.stale
                        ? t("fxCalc.stale")
                        : t("fxCalc.updated").replace("{date}", data.date || "—").replace("{count}", Object.keys(_rates).length),
                    data.stale ? "warning" : "ok"
                );
                renderBasePicker();
                renderResults();
            })
            .catch(function (err) {
                setStatus(t("fxCalc.loadFailed") + (err && err.message ? err.message : err), "error");
                renderResults();
            })
            .finally(function () {
                _loading = false;
                if (refresh) refresh.disabled = false;
            });
    }

    function activateCalc() {
        if (!_loaded && !_loading) fetchRates(false);
    }

    // ── sub-tab switching ────────────────────────────────────────────

    function selectFxSubView(sub) {
        var loss = $("fxLossView");
        var calc = $("fxCalcView");
        if (loss) loss.style.display = sub === "loss" ? "block" : "none";
        if (calc) calc.style.display = sub === "calc" ? "block" : "none";
        document.querySelectorAll("#fxSubTabs .transfer-tab").forEach(function (btn) {
            var on = btn.dataset.fxSub === sub;
            btn.classList.toggle("active", on);
            btn.setAttribute("aria-selected", on ? "true" : "false");
        });
        if (sub === "calc") activateCalc();
    }

    function bindSubTabs() {
        var tabs = document.querySelectorAll("#fxSubTabs .transfer-tab");
        tabs.forEach(function (btn) {
            btn.addEventListener("click", function () {
                selectFxSubView(btn.dataset.fxSub === "calc" ? "calc" : "loss");
            });
        });
    }

    function init() {
        var host = $("fxCalcView");
        if (!host) return;
        renderShell(host);
        bindSubTabs();
        updateShellText();
        // Redraw results/pickers with fresh locale text on theme/lang refresh.
        window._fxCalcRefresh = function () {
            if (!_loaded) return;
            renderBasePicker();
            renderResults();
            renderHistory();
            updateShellText();
        };
        var origRefresh = window._refreshCharts;
        window._refreshCharts = function () {
            if (typeof origRefresh === "function") origRefresh();
            if (typeof window._fxCalcRefresh === "function") window._fxCalcRefresh();
        };
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
