/* Keep server-rendered counts when the source is unavailable or incomplete. */
(function () {
  "use strict";

  var script = document.currentScript;
  var citations = Array.from(document.querySelectorAll("[data-scholar-id]"));
  var updated = document.querySelector("[data-scholar-updated]");
  if (!script || !citations.length || !updated) return;

  var profile = script.dataset.scholarProfile;
  var source = script.dataset.scholarSource;
  var lastUpdated = Date.parse(updated.dateTime);
  var lastAttempt = 0;
  var refreshing = false;
  var refreshInterval = 15 * 60 * 1000;
  var formatter = new Intl.NumberFormat("en-US");
  var dateFormatter = new Intl.DateTimeFormat("en-US", {
    month: "short", day: "numeric", year: "numeric", timeZone: "UTC"
  });
  var starImages = Array.from(document.querySelectorAll(".github-stars img"));

  starImages.forEach(function (image) {
    function showLink() {
      if (image.parentElement) image.parentElement.textContent = "GitHub stars ↗";
    }
    image.addEventListener("error", showLink, { once: true });
    if (image.complete && !image.naturalWidth) showLink();
  });

  function applyStats(data) {
    var timestamp = data && Date.parse(data.updated);
    if (!data || data.profile_id !== profile || !Number.isFinite(timestamp) ||
        timestamp < lastUpdated || timestamp > Date.now() + 5 * 60 * 1000 ||
        !data.publications || typeof data.publications !== "object") return;

    // Reject partial responses rather than displaying mixed-age counts as fresh.
    var entries = citations.map(function (link) {
      return data.publications[link.dataset.scholarId];
    });
    if (!entries.every(function (entry) {
      return entry && Number.isSafeInteger(entry.num_citations) && entry.num_citations >= 0;
    })) return;

    var date = dateFormatter.format(new Date(timestamp));
    citations.forEach(function (link, index) {
      link.querySelector(".citation-count").textContent = formatter.format(entries[index].num_citations);
      link.title = "Google Scholar citations · updated " + date;
      link.hidden = entries[index].num_citations < 10;
      var metrics = link.parentElement;
      metrics.hidden = link.hidden && !metrics.querySelector(".github-stars");
    });
    updated.dateTime = data.updated;
    updated.textContent = date;
    lastUpdated = timestamp;
  }

  async function refresh() {
    if (document.hidden || refreshing || Date.now() - lastAttempt < refreshInterval) return;
    refreshing = true;
    lastAttempt = Date.now();
    var controller = new AbortController();
    var timeout = setTimeout(function () { controller.abort(); }, 10000);
    try {
      var response = await fetch(source, { cache: "no-cache", signal: controller.signal });
      if (response.ok) applyStats(await response.json());
    } catch (_) {
      // The displayed snapshot and its original date remain truthful when offline.
    } finally {
      clearTimeout(timeout);
      refreshing = false;
    }
  }

  refresh();
  setInterval(function () {
    if (document.hidden) return;
    refresh();
    // Revalidate already-visible badges after their HTTP cache expires.
    starImages.forEach(function (image) {
      if (image.isConnected && image.complete && image.naturalWidth) image.src = image.src;
    });
  }, refreshInterval);
  document.addEventListener("visibilitychange", refresh);
})();
