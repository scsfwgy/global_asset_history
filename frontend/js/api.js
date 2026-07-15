/** API endpoint constants. */

const API_BASE = "";
const ENDPOINT = `${API_BASE}/api/price-change/yearly`;
const CONFIG_ENDPOINT = `${API_BASE}/api/price-change/config`;
const MONTHLY_ENDPOINT = `${API_BASE}/api/price-change/monthly`;
const BATCH_MONTHLY_ENDPOINT = `${API_BASE}/api/price-change/monthly-batch`;
const DAILY_ENDPOINT = `${API_BASE}/api/price-change/daily`;
const DETAIL_ENDPOINT = `${API_BASE}/api/price-change/detail`;
const HISTORY_DOWNLOAD_ENDPOINT = `${API_BASE}/api/price-change/history-download`;
const BACKTEST_ENDPOINT = `${API_BASE}/api/price-change/backtest`;
const CRASH_STATS_ENDPOINT = `${API_BASE}/api/price-change/crash-stats`;
const CRASH_CHART_ENDPOINT = `${API_BASE}/api/price-change/crash-chart`;
const HEATMAP_ENDPOINT = `${API_BASE}/api/price-change/heatmap`;
const MARKET_PULSE_ENDPOINT = `${API_BASE}/api/price-change/market-pulse`;
const VIX_COMPARISON_ENDPOINT = `${API_BASE}/api/price-change/vix-comparison`;
const QDII_FUNDS_ENDPOINT = `${API_BASE}/api/etf-market/qdii-funds`;
const WISHES_ENDPOINT = `${API_BASE}/api/wishes`;
const WISH_CAPTCHA_ENDPOINT = `${API_BASE}/api/wishes/captcha`;
const WISH_VERIFY_ADMIN_ENDPOINT = `${API_BASE}/api/wishes/verify-admin`;

// Share the immutable application-config request across feature modules.  The
// page uses classic scripts, so a promise on window is the simplest way to
// prevent each tab from issuing its own GET /config during startup.
window.gahLoadConfig = function () {
  if (!window.__GAH_CONFIG_PROMISE__) {
    window.__GAH_CONFIG_PROMISE__ = fetch(CONFIG_ENDPOINT).then(function (resp) {
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      return resp.json();
    }).catch(function (error) {
      // A failed request must remain retryable for a later tab activation.
      window.__GAH_CONFIG_PROMISE__ = null;
      throw error;
    });
  }
  return window.__GAH_CONFIG_PROMISE__;
};

window.gahRunWhenIdle = function (callback, timeout) {
  // requestIdleCallback may run almost immediately while network requests are
  // still in flight.  Delay first, then use an idle slot for decoration-only
  // work so it does not join the initial request burst.
  window.setTimeout(function () {
    if (typeof window.requestIdleCallback === "function") {
      window.requestIdleCallback(callback, { timeout: 1000 });
    } else {
      callback();
    }
  }, timeout || 2500);
};
