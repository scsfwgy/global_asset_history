/**
 * Header background trend — a faint QQQ full-history area chart rendered
 * behind the title text inside <header class="header">. Pure decoration.
 *
 * - Fetches a server-downsampled daily close series from /header-trend
 * - Renders a hand-built SVG (area fill + stroke), preserveAspectRatio="none"
 *   so it stretches with the header width without a resize listener
 * - Fails silently: on any error/empty data the header keeps its original look
 */

(function () {
    "use strict";

    var HEADER_TREND_ENDPOINT = "/api/price-change/header-trend";
    var DEFAULT_SYMBOL = "QQQ";
    // Decoration-only series: refresh at most once per local calendar day.
    // Backend Yahoo fetch is already 6h-cached (shared PriceSeries cache), so
    // this just avoids re-hitting the API on every page load within a day.
    var CACHE_KEY = "gah_header_trend_v1";

    // Fixed canvas; preserveAspectRatio="none" stretches it to the header box.
    var W = 1000;
    var H = 100;
    var PAD_TOP = 10;     // keep the line off the very top edge
    var PAD_BOTTOM = 6;   // breathing room at the bottom

    function $(id) { return document.getElementById(id); }

    /**
     * Build the SVG markup for an area+stroke trend from [{date, close}, ...].
     * Returns "" when there is not enough data to draw.
     */
    function buildTrendSvg(points) {
        if (!points || points.length < 2) return "";

        var closes = points.map(function (p) { return p.close; });
        var min = Math.min.apply(null, closes);
        var max = Math.max.apply(null, closes);
        if (!isFinite(min) || !isFinite(max) || max === min) {
            // Flat line: draw straight across the middle.
            max = min + 1;
        }

        var usable = H - PAD_TOP - PAD_BOTTOM;
        function x(i) { return (i / (points.length - 1)) * W; }
        function y(v) { return H - PAD_BOTTOM - ((v - min) / (max - min)) * usable; }

        var linePts = points.map(function (p, i) {
            return x(i).toFixed(2) + "," + y(p.close).toFixed(2);
        });

        // Area: along the line, then close along the bottom edge.
        var areaPath = "M0," + H + " L" + linePts.join(" L") + " L" + W + "," + H + " Z";
        // Stroke: the line only.
        var strokePath = "M" + linePts.join(" L");

        return ''
            + '<svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none" focusable="false">'
            +   '<defs>'
            +     '<linearGradient id="htGrad" x1="0" y1="0" x2="0" y2="1">'
            +       '<stop offset="0%"  stop-color="rgba(0,113,227,0.07)"/>'
            +       '<stop offset="100%" stop-color="rgba(0,113,227,0)"/>'
            +     '</linearGradient>'
            +   '</defs>'
            +   '<path class="ht-area"   d="' + areaPath + '"/>'
            +   '<path class="ht-stroke" d="' + strokePath + '"/>'
            + '</svg>';
    }

    function render(points) {
        var host = $("headerTrend");
        if (!host) return;
        var svg = buildTrendSvg(points);
        host.innerHTML = svg;
        if (!svg) host.classList.add("empty");
    }

    function fetchAndRender() {
        var host = $("headerTrend");
        if (!host) return; // not on this page

        var url = HEADER_TREND_ENDPOINT + "?symbol=" + encodeURIComponent(DEFAULT_SYMBOL) + "&points=240";
        fetch(url, { headers: { "Accept": "application/json" } })
            .then(function (r) {
                if (!r.ok) throw new Error("HTTP " + r.status);
                return r.json();
            })
            .then(function (data) {
                var points = data && data.points ? data.points : [];
                render(points);
                if (points.length >= 2) writeCache(points);
            })
            .catch(function () {
                // Decoration only — leave the header as-is on failure.
            });
    }

    /** Local calendar-day key, e.g. "2026-07-05". Data is a daily close series,
     *  so once-per-day refresh is plenty (QQQ only gets a new close once per
     *  US trading day anyway). */
    function todayKey() {
        var d = new Date();
        var m = String(d.getMonth() + 1).padStart(2, "0");
        var day = String(d.getDate()).padStart(2, "0");
        return d.getFullYear() + "-" + m + "-" + day;
    }

    function readCache() {
        try {
            var raw = localStorage.getItem(CACHE_KEY);
            if (!raw) return null;
            var obj = JSON.parse(raw);
            if (!obj || !Array.isArray(obj.points)) return null;
            return obj;
        } catch (e) {
            return null; // corrupt entry or localStorage disabled → just refetch
        }
    }

    function writeCache(points) {
        try {
            localStorage.setItem(CACHE_KEY, JSON.stringify({
                date: todayKey(),
                symbol: DEFAULT_SYMBOL,
                points: points,
            }));
        } catch (e) {
            // Quota exceeded or private mode — caching is best-effort only.
        }
    }

    function init() {
        var cached = readCache();
        if (cached && cached.symbol === DEFAULT_SYMBOL
                && cached.date === todayKey() && cached.points.length >= 2) {
            render(cached.points); // today's data already fetched — skip network
            return;
        }
        fetchAndRender();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
