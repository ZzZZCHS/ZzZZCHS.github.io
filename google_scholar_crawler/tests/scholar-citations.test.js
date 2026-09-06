const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../../assets/js/scholar-citations.js"), "utf8");
const now = Date.parse("2026-09-06T12:00:00Z");
class Clock extends Date {
  static now() { return now; }
}

function snapshot() {
  return {
    profile_id: "profile",
    updated: "2026-09-06T10:00:00Z",
    publications: {
      "profile:second": { num_citations: 1234 },
      "profile:first": { num_citations: 0 }
    }
  };
}

async function render(fetch, images = []) {
  const counts = [{ textContent: "9" }, { textContent: "20" }];
  const links = ["first", "second"].map((id, index) => ({
    dataset: { scholarId: "profile:" + id },
    title: "Original update date",
    hidden: index === 0,
    parentElement: {
      hidden: index === 0,
      querySelector: () => index === 1 ? { className: "github-stars" } : null
    },
    querySelector: () => counts[index]
  }));
  const updated = { dateTime: "2026-09-06", textContent: "Sep 06, 2026" };
  const document = {
    hidden: false,
    currentScript: { dataset: { scholarProfile: "profile", scholarSource: "https://example.test/stats.json" } },
    querySelectorAll: (selector) => selector === "[data-scholar-id]" ? links : images,
    querySelector: () => updated,
    addEventListener() {}
  };
  vm.runInNewContext(source, {
    document, fetch, Date: Clock, Intl, AbortController,
    setTimeout() {}, clearTimeout() {}, setInterval() {}
  });
  await new Promise(setImmediate);
  return { counts: counts.map((count) => count.textContent), links, updated };
}

function response(data) {
  return async () => ({ ok: true, json: async () => data });
}

function assertFallback(result) {
  assert.deepEqual(result.counts, ["9", "20"]);
  assert.equal(result.updated.dateTime, "2026-09-06");
  assert.equal(result.links[0].title, "Original update date");
  assert.deepEqual(result.links.map((link) => link.hidden), [true, false]);
  assert.deepEqual(result.links.map((link) => link.parentElement.hidden), [true, false]);
}

test("updates counts by Scholar ID, including zero, and changes the date together", async () => {
  const result = await render(response(snapshot()));
  assert.deepEqual(result.counts, ["0", "1,234"]);
  assert.equal(result.updated.dateTime, snapshot().updated);
  assert.match(result.links[0].title, /Google Scholar citations/);
  assert.deepEqual(result.links.map((link) => link.hidden), [true, false]);
});

test("shows citations at 10, hides them below 10, and keeps GitHub stars visible", async () => {
  const data = snapshot();
  data.publications["profile:first"].num_citations = 10;
  data.publications["profile:second"].num_citations = 9;
  const result = await render(response(data));
  assert.deepEqual(result.counts, ["10", "9"]);
  assert.deepEqual(result.links.map((link) => link.hidden), [false, true]);
  assert.deepEqual(result.links.map((link) => link.parentElement.hidden), [false, false]);
});

test("offline, HTTP errors and malformed JSON preserve the dated snapshot", async () => {
  for (const fetch of [
    async () => { throw new Error("offline"); },
    async () => ({ ok: false }),
    async () => ({ ok: true, json: async () => { throw new Error("invalid JSON"); } })
  ]) assertFallback(await render(fetch));
});

test("rejects stale, future, undated and wrong-profile payloads", async () => {
  for (const replacement of [
    { updated: "2026-09-05T23:59:59Z" },
    { updated: "2026-09-07T00:00:00Z" },
    { updated: "invalid" },
    { profile_id: "anotherProfile" }
  ]) assertFallback(await render(response({ ...snapshot(), ...replacement })));
});

test("rejects partial or invalid counts without updating any paper", async () => {
  for (const entry of [undefined, { num_citations: -1 }, { num_citations: "4" }, { num_citations: null }]) {
    const data = snapshot();
    data.publications["profile:second"] = entry;
    assertFallback(await render(response(data)));
  }
});

test("failed star badge keeps a usable text link, including repeated errors", async () => {
  const link = { textContent: "" };
  let onError;
  const image = {
    parentElement: link, complete: true, naturalWidth: 0,
    addEventListener: (_, handler) => { onError = handler; }
  };
  await render(response(snapshot()), [image]);
  assert.equal(link.textContent, "GitHub stars ↗");
  image.parentElement = null;
  assert.doesNotThrow(onError);
});
