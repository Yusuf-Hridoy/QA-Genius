/* Unit tests for the search, filter and sort helpers in public/stories.js. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(here, "..", "..", "public", "stories.js"), "utf8");

function load() {
  const sandbox = { JSON, Object, Array, Math, String, Date };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox);
  return sandbox.QAGStoriesPage;
}

const page = load();
const plain = (value) => JSON.parse(JSON.stringify(value));

const STORIES = [
  {
    id: "s_1",
    label: "CART-204",
    title: "As a shopper, I want my cart saved",
    status: "draft",
    updated_at: "2026-05-01T10:00:00Z",
    run: { story: "As a shopper, I want my cart saved so I can finish later." }
  },
  {
    id: "s_2",
    label: "LOGIN-7",
    title: "As a shopper, I want my account to lock",
    status: "done",
    updated_at: "2026-05-03T10:00:00Z",
    run: { story: "As a shopper, I want my account to lock after wrong passwords." }
  },
  {
    id: "s_3",
    label: "S-003",
    title: "As an admin, I want a report",
    status: "review",
    updated_at: "2026-05-02T10:00:00Z",
    run: { story: "As an admin, I want a weekly report." }
  }
];

/* ── search ─────────────────────────────────────────────────────────────── */

test("an empty search keeps everything", () => {
  assert.equal(STORIES.filter((one) => page.matches(one, "")).length, 3);
  assert.equal(STORIES.filter((one) => page.matches(one, "   ")).length, 3);
});

test("search finds a story by its id", () => {
  const found = STORIES.filter((one) => page.matches(one, "cart-204"));
  assert.deepEqual(found.map((one) => one.id), ["s_1"]);
});

test("search finds a story by what it says", () => {
  const found = STORIES.filter((one) => page.matches(one, "wrong passwords"));
  assert.deepEqual(found.map((one) => one.id), ["s_2"]);
});

test("search does not care about capitals", () => {
  assert.equal(page.matches(STORIES[0], "SHOPPER"), true);
});

/* ── filter ─────────────────────────────────────────────────────────────── */

test("all means all", () => {
  assert.equal(STORIES.filter((one) => page.withStatus(one, "all")).length, 3);
  assert.equal(STORIES.filter((one) => page.withStatus(one, "")).length, 3);
});

test("a status keeps only that status", () => {
  const found = STORIES.filter((one) => page.withStatus(one, "review"));
  assert.deepEqual(found.map((one) => one.id), ["s_3"]);
});

/* ── sort ───────────────────────────────────────────────────────────────── */

test("last edited comes first by default", () => {
  assert.deepEqual(
    plain(page.sorted(STORIES, "edited")).map((one) => one.id),
    ["s_2", "s_3", "s_1"]
  );
});

test("by ID is alphabetical", () => {
  assert.deepEqual(
    plain(page.sorted(STORIES, "label")).map((one) => one.id),
    ["s_1", "s_2", "s_3"]
  );
});

test("sorting never changes the list it was given", () => {
  const before = STORIES.map((one) => one.id);
  page.sorted(STORIES, "label");
  assert.deepEqual(STORIES.map((one) => one.id), before);
});

test("search, filter and sort work together", () => {
  const found = page.shown(STORIES, { words: "shopper", status: "all", sort: "label" });
  assert.deepEqual(plain(found).map((one) => one.id), ["s_1", "s_2"]);
});

/* ── what a saved story holds ───────────────────────────────────────────── */

test("the facts are counted from the saved run", () => {
  const run = {
    criteria: [{ text: "AC-1" }, { text: "" }, { text: "AC-2" }],
    test_cases: { result: { test_cases: [{ id: "TC-1" }, { id: "TC-2" }] } },
    risk_analysis: {
      analysis: {
        failure_modes: [
          { severity: 5, likelihood: 4, detectability: 4, covered_by: [] },
          { severity: 5, likelihood: 4, detectability: 4, covered_by: ["TC-1"] },
          { severity: 1, likelihood: 1, detectability: 1, covered_by: [] }
        ]
      }
    }
  };
  assert.deepEqual(plain(page.facts(run)), { criteria: 2, cases: 2, risks: 1 });
  assert.equal(page.factsLine(run), "2 criteria · 2 tests · 1 high risk with no test");
});

test("an empty run reads as nothing yet", () => {
  assert.deepEqual(plain(page.facts({})), { criteria: 0, cases: 0, risks: 0 });
  assert.equal(page.factsLine({}), "0 criteria · 0 tests");
});

test("one of a thing is said in the singular", () => {
  const run = {
    criteria: [{ text: "AC-1" }],
    test_cases: { result: { test_cases: [{ id: "TC-1" }] } }
  };
  assert.equal(page.factsLine(run), "1 criterion · 1 test");
});
