(function () {
  "use strict";

  var $ = function (id) { return document.getElementById(id); };

  function localIsoDate(value) {
    var year = value.getFullYear();
    var month = String(value.getMonth() + 1).padStart(2, "0");
    var day = String(value.getDate()).padStart(2, "0");
    return year + "-" + month + "-" + day;
  }

  function setLoading(on) {
    var el = $("downloadLoading");
    if (el) el.style.display = on ? "flex" : "none";
    ["downloadPreviewBtn", "downloadJsonBtn"].forEach(function (id) {
      var button = $(id);
      if (button) button.disabled = on;
    });
  }

  function showError(message) {
    var el = $("downloadError");
    if (!el) return;
    el.textContent = message || "";
    el.style.display = message ? "block" : "none";
  }

  function formValues() {
    return {
      symbol: ($("downloadSymbolInput")?.value || "").trim().toUpperCase(),
      type: $("downloadTypeSelect")?.value || "crypto",
      period: $("downloadPeriodSelect")?.value || "daily",
      start_date: $("downloadStartDate")?.value || "",
      end_date: $("downloadEndDate")?.value || "",
    };
  }

  function validate(values) {
    if (!values.symbol || !values.start_date || !values.end_date) {
      return __("download.errorRequired");
    }
    if (values.start_date > values.end_date) {
      return __("download.errorDateRange");
    }
    return "";
  }

  function enforceIntradayRange() {
    var limits = { "1m": 7, "5m": 60, "1h": 730, "4h": 730 };
    var period = $("downloadPeriodSelect").value;
    var maxDays = limits[period];
    if (!maxDays || !$("downloadEndDate").value) return;
    var end = new Date($("downloadEndDate").value + "T00:00:00");
    var earliest = new Date(end.getFullYear(), end.getMonth(), end.getDate() - maxDays + 1);
    var start = $("downloadStartDate").value;
    if (!start || start < localIsoDate(earliest)) {
      $("downloadStartDate").value = localIsoDate(earliest);
    }
  }

  function render(result) {
    var empty = $("downloadEmpty");
    var resultEl = $("downloadResult");
    if (empty) empty.style.display = "none";
    if (resultEl) resultEl.style.display = "block";
    if ($("downloadSummary")) {
      $("downloadSummary").textContent = __("download.summary", {
        symbol: result.symbol,
        period: result.period,
        count: result.count,
      });
    }
    if ($("downloadPreview")) {
      var preview = Object.assign({}, result, { data: (result.data || []).slice(0, 20) });
      $("downloadPreview").textContent = JSON.stringify(preview, null, 2);
    }
  }

  async function fetchData() {
    var values = formValues();
    var error = validate(values);
    if (error) {
      showError(error);
      throw new Error(error);
    }
    showError("");
    setLoading(true);
    try {
      var response = await fetch(HISTORY_DOWNLOAD_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(values),
      });
      var result = await response.json().catch(function () { return {}; });
      if (!response.ok) throw new Error(result.error || "HTTP " + response.status);
      render(result);
      try { localStorage.setItem("gah_download_state", JSON.stringify(values)); } catch (_) {}
      return result;
    } catch (err) {
      showError(__("download.errorRequest") + " " + err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }

  async function preview() {
    try { await fetchData(); } catch (_) {}
  }

  async function downloadJson() {
    var result;
    try {
      result = await fetchData();
    } catch (_) {
      return;
    }
    var json = JSON.stringify(result, null, 2);
    var blob = new Blob([json], { type: "application/json;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = [result.symbol, result.period, result.start_date, result.end_date].join("-") + ".json";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(function () { URL.revokeObjectURL(url); }, 0);
  }

  function restoreState() {
    var today = new Date();
    var yearAgo = new Date(today.getFullYear() - 1, today.getMonth(), today.getDate());
    $("downloadStartDate").value = localIsoDate(yearAgo);
    $("downloadEndDate").value = localIsoDate(today);
    $("downloadEndDate").max = localIsoDate(today);
    try {
      var saved = JSON.parse(localStorage.getItem("gah_download_state") || "null");
      if (!saved) return;
      if (saved.symbol) $("downloadSymbolInput").value = saved.symbol;
      if (saved.type) $("downloadTypeSelect").value = saved.type;
      if (saved.period) $("downloadPeriodSelect").value = saved.period;
      if (saved.start_date) $("downloadStartDate").value = saved.start_date;
      if (saved.end_date) $("downloadEndDate").value = saved.end_date;
    } catch (_) {}
  }

  function init() {
    if (!$("downloadPreviewBtn")) return;
    restoreState();
    $("downloadPreviewBtn").addEventListener("click", preview);
    $("downloadJsonBtn").addEventListener("click", downloadJson);
    $("downloadPeriodSelect").addEventListener("change", enforceIntradayRange);
    $("downloadEndDate").addEventListener("change", enforceIntradayRange);
    $("downloadSymbolInput").addEventListener("keydown", function (event) {
      if (event.key === "Enter") preview();
    });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
