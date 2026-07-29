/**
 * Shared visit bootstrap for anonymous cumulative language statistics.
 */
(function () {
  "use strict";

  var STORAGE_KEY = "gah_anonymous_id";

  function getAnonymousId() {
    try {
      var stored = localStorage.getItem(STORAGE_KEY);
      if (stored) return stored;
    } catch (_) {}

    var id = window.crypto && typeof window.crypto.randomUUID === "function"
      ? window.crypto.randomUUID()
      : "anon-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 12);
    try {
      localStorage.setItem(STORAGE_KEY, id);
    } catch (_) {}
    return id;
  }

  window.gahRecordVisit = function (tab) {
    return fetch("/api/visits/increment", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        anonymous_id: getAnonymousId(),
        tab: tab || "",
        site_language: typeof window.__lang === "function" ? window.__lang() : "zh-CN",
        device_language: navigator.language || ""
      }),
      keepalive: true
    }).then(function (response) {
      if (!response.ok) throw new Error("visit tracking failed");
      return response.json();
    });
  };
})();
