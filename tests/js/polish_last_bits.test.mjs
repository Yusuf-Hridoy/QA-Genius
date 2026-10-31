/* The last three UX bits, pinned down.
 *
 * Two of them were the same mistake in different places: a page saying one
 * thing twice. Ship check offered "Start from a story" over the top of a
 * finished report, with a yellow button fighting the report's own; the
 * Risk radar called its sample a sample in the card and again in the
 * result. Both now say it once.
 *
 * Run by `node --test tests/js/*.test.mjs`.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const read = (name) =>
  readFileSync(join(here, "..", "..", "public", name), "utf8");

function sandboxFor(name, document) {
  const sandbox = {
    JSON,
    Object,
    Array,
    Math,
    String,
    Boolean,
    Date,
    isNaN,
    fetch: () => Promise.resolve({ text: () => Promise.resolve("") }),
    sessionStorage: { getItem: () => null, setItem() {} },
    localStorage: { getItem: () => null, setItem() {} },
    document: Object.assign(
      {
        /* "loading" keeps source_card.js from starting itself: these tests
         * are about one function, not the whole desk. */
        readyState: "loading",
        addEventListener() {},
        getElementById: () => null,
        querySelector: () => null,
        querySelectorAll: () => [],
        createElement: () => ({
          setAttribute() {},
          appendChild() {},
          querySelector: () => null,
          style: {},
        }),
        body: { addEventListener() {} },
      },
      document || {}
    ),
    setTimeout: () => 1,
    clearTimeout: () => {},
    setInterval: () => 1,
    addEventListener() {},
  };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(read(name), sandbox);
  return sandbox;
}

/* ── Ship check: one yellow button, and the right thing to ask for ─────── */

const ship = () => sandboxFor("ship_check.js").QAGShip;

test("an empty run has nothing in it", () => {
  const { hasAnyResult } = ship();
  assert.equal(hasAnyResult(null), false);
  assert.equal(hasAnyResult({}), false);
  assert.equal(hasAnyResult({ story: "" }), false);
});

test("a run another desk has filled in counts, whichever desk it was", () => {
  const { hasAnyResult } = ship();
  // Each of these on its own is enough to make "Start from a story" wrong.
  assert.equal(hasAnyResult({ story_analysis: { score: 3 } }), true);
  assert.equal(hasAnyResult({ duel_summary: "two readers disagreed" }), true);
  assert.equal(hasAnyResult({ test_cases: { result: { test_cases: [] } } }), true);
  assert.equal(
    hasAnyResult({ risk_analysis: { analysis: { failure_modes: [] } } }),
    true
  );
  assert.equal(hasAnyResult({ automation: { script: "code" } }), true);
  assert.equal(hasAnyResult({ insights: { note: "x" } }), true);
  assert.equal(hasAnyResult({ matrix: { runs: [] } }), true);
});

test("a half-built desk is not a result", () => {
  const { hasAnyResult } = ship();
  // The key exists but the desk never finished: nothing to show yet.
  assert.equal(hasAnyResult({ test_cases: {} }), false);
  assert.equal(hasAnyResult({ risk_analysis: {} }), false);
  assert.equal(hasAnyResult({ automation: {} }), false);
  assert.equal(hasAnyResult({ matrix: {} }), false);
});

test("criteria on their own count, but blank ones do not", () => {
  const { hasAnyResult } = ship();
  assert.equal(
    hasAnyResult({ criteria: [{ text: "The account locks." }] }),
    true
  );
  assert.equal(hasAnyResult({ criteria: [{ text: "   " }] }), false);
  assert.equal(hasAnyResult({ criteria: [] }), false);
});

/* ── Risk radar: one sample notice ─────────────────────────────────────── */

function sourceCard({ flagOnScreen }) {
  const flag = { getClientRects: () => (flagOnScreen ? [{}] : []) };
  return sandboxFor("source_card.js", {
    querySelector: (what) => (what === ".example-flag" ? flag : null),
  }).QAGSourceCard;
}

test("the card keeps quiet when the result already says it is a sample", () => {
  const { resultSaysSample } = sourceCard({ flagOnScreen: true });
  assert.equal(resultSaysSample(), true);
});

test("after a reload the flag is gone, so the card speaks up", () => {
  // Exactly one notice either way: this is why the sentence is skipped
  // rather than deleted.
  const { resultSaysSample } = sourceCard({ flagOnScreen: false });
  assert.equal(resultSaysSample(), false);
});

test("a flag that is in the page but drawn nowhere does not count", () => {
  const { resultSaysSample } = sourceCard({ flagOnScreen: false });
  assert.equal(resultSaysSample(), false);
});
