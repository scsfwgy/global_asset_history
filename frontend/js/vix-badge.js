/**
 * Site-wide VIX header badge — a small pill in the top-right header showing
 * the latest VIX reading and its fear zone. This is deliberately separate
 * from vix-chart.js (the full VIX tab) because the badge is a header element
 * that must render on every route, while vix-chart.js is only shipped on the
 * VIX tab after route pruning.
 *
 * Exposes window.VixBadge so the VIX tab can update the badge from its own
 * fetch without duplicating the zone/status logic.
 */

(function () {
    "use strict";

    var _latestVix = null;

    function $(id) { return document.getElementById(id); }

    function vixZone(vixVal) {
        if (vixVal == null || isNaN(vixVal)) return null;
        if (vixVal < 12)  return { label: __("vix.zoneExtremeCalm"), tip: __("vix.tipExtremeCalm"), cls: "zone-extreme-low", recommend: false };
        if (vixVal < 15)  return { label: __("vix.zoneLowVol"),   tip: __("vix.tipLowVol"), cls: "zone-low", recommend: false };
        if (vixVal < 20)  return { label: __("vix.zoneNormal"), tip: __("vix.tipNormal"), cls: "zone-normal", recommend: null };
        if (vixVal < 25)  return { label: __("vix.zoneFear"), tip: __("vix.tipFear"), cls: "zone-elevated", recommend: true };
        if (vixVal < 35)  return { label: __("vix.zoneHighFear"), tip: __("vix.tipHighFear"), cls: "zone-high", recommend: true };
        return              { label: __("vix.zoneExtremePanic"), tip: __("vix.tipExtremePanic"), cls: "zone-extreme", recommend: true };
    }

    function vixRuleTip() {
        var hint = typeof __ === "function" ? __("vix.badgeClickHint") : "";
        var base = __("vix.ruleTip");
        return hint && hint !== "vix.badgeClickHint" ? hint + "\n\n" + base : base;
    }

    function buildThresholdUrl(vixVal) {
        var vixTab = document.querySelector('.tab-btn[data-tab="vix"]');
        var basePath = vixTab && vixTab.getAttribute("href")
            ? vixTab.getAttribute("href")
            : (typeof __langPath === "function" && typeof __lang === "function"
                ? __langPath("/vix", __lang())
                : "/vix");
        var url = new URL(basePath, window.location.origin);
        url.searchParams.set("view", "threshold");
        url.searchParams.set("index", "VIX");
        if (vixVal != null && Number.isFinite(Number(vixVal)) && Number(vixVal) > 0) {
            url.searchParams.set("threshold", Number(vixVal).toFixed(2));
            url.searchParams.set("autorun", "1");
        }
        return url.pathname + url.search;
    }

    function navigateToThresholdStats() {
        var thresholdStr = (_latestVix != null && Number.isFinite(_latestVix) && _latestVix > 0)
            ? _latestVix.toFixed(2)
            : null;
        var vixPanel = $("tab-vix");
        if (vixPanel && vixPanel.classList.contains("active") && typeof window.VixThresholdJump === "function") {
            window.VixThresholdJump({
                index: "VIX",
                threshold: thresholdStr,
                autorun: true,
                updateUrl: true,
            });
            return;
        }
        window.location.assign(buildThresholdUrl(_latestVix));
    }

    function bindBadgeInteraction(badge) {
        if (!badge || badge.dataset.vixBound === "1") return;
        badge.dataset.vixBound = "1";
        badge.setAttribute("role", "button");
        badge.setAttribute("tabindex", "0");
        badge.addEventListener("click", function (event) {
            event.preventDefault();
            navigateToThresholdStats();
        });
        badge.addEventListener("keydown", function (event) {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                navigateToThresholdStats();
            }
        });
    }

    function setHeaderBadgeStatus(text, cls) {
        var line = $("vixHeaderLine");
        var badge = $("vixHeaderBadge");
        if (!badge || !line) return;
        bindBadgeInteraction(badge);
        updateHeaderBackground(null);
        line.style.display = "";
        badge.textContent = text;
        badge.className = "vix-header-badge has-tip is-clickable " + (cls || "zone-loading");
        badge.title = vixRuleTip();
    }

    function updateHeaderBackground(zone) {
        var header = document.querySelector(".header");
        if (!header) return;
        ["extreme-low", "low", "normal", "elevated", "high", "extreme"].forEach(function (key) {
            header.classList.remove("vix-bg-" + key);
        });
        if (!zone || !zone.cls) return;
        header.classList.add("vix-bg-" + zone.cls.replace("zone-", ""));
    }

    function updateHeaderBadge(vixVal) {
        var line = $("vixHeaderLine");
        var badge = $("vixHeaderBadge");
        if (!badge || !line) return;
        bindBadgeInteraction(badge);
        if (vixVal == null || isNaN(vixVal)) { setHeaderBadgeStatus("VIX " + __("vix.loadFailed").replace(": ",""), "zone-error"); return; }

        var numericVix = Number(vixVal);
        if (Number.isFinite(numericVix) && numericVix > 0) {
            _latestVix = numericVix;
        }

        var zone = vixZone(numericVix);
        if (!zone) { setHeaderBadgeStatus("VIX " + __("vix.loadFailed").replace(": ",""), "zone-error"); updateHeaderBackground(null); return; }

        updateHeaderBackground(zone);
        line.style.display = "";
        badge.textContent = "VIX " + numericVix.toFixed(2) + " · " +
            (numericVix >= 35 ? __("vix.badgeExtremePanic") :
             numericVix >= 25 ? __("vix.badgeHighFear") :
             numericVix >= 20 ? __("vix.badgeFear") :
             numericVix >= 15 ? __("vix.badgeNormal") :
             numericVix >= 12 ? __("vix.badgeLowVol") :
             __("vix.badgeExtremeCalm"));
        badge.className = "vix-header-badge has-tip is-clickable " + zone.cls;
        badge.title = vixRuleTip();
    }

    function fetchLatestVix() {
        setHeaderBadgeStatus("VIX " + __("vix.loading"), "zone-loading");
        fetch(VIX_COMPARISON_ENDPOINT, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ period: "daily", count: 5 }),
        })
            .then(function (r) {
                if (!r.ok) throw new Error("HTTP " + r.status);
                return r.json();
            })
            .then(function (data) {
                if (data.latest_vix != null) updateHeaderBadge(data.latest_vix);
                else setHeaderBadgeStatus("VIX " + __("vix.loadFailed").replace(": ",""), "zone-error");
            })
            .catch(function () { setHeaderBadgeStatus("VIX " + __("vix.loadFailed").replace(": ",""), "zone-error"); });
    }

    window.VixBadge = {
        update: updateHeaderBadge,
        status: setHeaderBadgeStatus,
        zone: vixZone,
        latest: function () { return _latestVix; },
        buildThresholdUrl: buildThresholdUrl,
        navigateToThresholdStats: navigateToThresholdStats,
    };

    function init() {
        if (typeof window.gahRunWhenIdle === "function") window.gahRunWhenIdle(fetchLatestVix, 2500);
        else window.setTimeout(fetchLatestVix, 800);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
