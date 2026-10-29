/* The words and shapes R4.2 and R4.3 pinned down, run by
 * `node --test tests/js`.
 *
 * A real browser test found three of these: "Write a test" that said
 * nothing about what it had done, a criterion card that printed its own
 * first words as a title above itself, and "+0 added" shown as a success.
 * Each one is a sentence now, and a sentence can be tested. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const read = (name) =>
  readFileSync(join(here, "..", "..", "public", name), "utf8");

/* ── Write a test, on the Risk radar ────────────────────────────────────── */

function risks() {
  const sandbox = {
    JSON,
    Object,
    Array,
    Math,
    String,
    Boolean,
    Date,
    isNaN,
    FormData: class {
      append() {}
    },
    fetch: () => Promise.resolve({ text: () => Promise.resolve("") }),
    sessionStorage: { getItem: () => null, setItem() {} },
    document: {
      addEventListener() {},
      getElementById: () => null,
      querySelector: () => null,
      querySelectorAll: () => [],
      createElement: () => ({
        setAttribute() {},
        appendChild() {},
        querySelector: () => null,
      }),
    },
    setTimeout: () => 1,
    clearTimeout: () => {},
    addEventListener() {},
  };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(read("risk_radar.js"), sandbox);
  return sandbox.QAGRisks;
}

const suite = (...ids) => ({
  result: { test_cases: ids.map((id) => ({ id })), summary: "" },
  criteria: [],
});

test("what counts as added is what was not there before", () => {
  const R = risks();
  const before = suite("TC-001", "TC-002");
  const after = suite("TC-001", "TC-002", "TC-018", "TC-019");
  assert.deepEqual([...R.addedIds(before, after)], ["TC-018", "TC-019"]);
});

test("a proposal that adds nothing adds nothing", () => {
  const R = risks();
  const before = suite("TC-001");
  assert.equal(R.addedIds(before, suite("TC-001")).length, 0);
  // Even a list that lost a case has added none of its own.
  assert.equal(R.addedIds(before, suite()).length, 0);
});

test("the ids that were written are named, not counted", () => {
  const R = risks();
  assert.equal(R.addedWords(["TC-018", "TC-019"]), "Added 2 tests: TC-018, TC-019.");
  assert.equal(R.addedWords(["TC-018"]), "Added 1 test: TC-018.");
});

test("a run that wrote nothing says so, and says what to do instead", () => {
  const R = risks();
  assert.equal(
    R.nothingWritten(["R2"]),
    "The AI didn't return a test for R2. Try again, or write one yourself " +
      "on the Test cases page."
  );
});

test("a payload with no cases in it counts as no cases", () => {
  const R = risks();
  // The arrays come back from the sandbox, so their length is what to read.
  assert.equal(R.caseIds(null).length, 0);
  assert.equal(R.caseIds({}).length, 0);
  assert.equal(R.caseIds({ result: {} }).length, 0);
});

/* ── the criterion card ─────────────────────────────────────────────────── */

function flow() {
  const sandbox = {
    JSON,
    Object,
    Array,
    Math,
    String,
    Boolean,
    Date,
    isNaN,
    sessionStorage: { getItem: () => null, setItem() {} },
    document: {
      addEventListener() {},
      getElementById: () => null,
      querySelector: () => null,
      querySelectorAll: () => [],
      createElement: () => ({
        setAttribute() {},
        appendChild() {},
        classList: { add() {}, remove() {}, toggle() {} },
      }),
    },
    setTimeout: () => 1,
    clearTimeout: () => {},
  };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(read("requirements_flow.js"), sandbox);
  return sandbox.QAGFlow;
}

const GWT =
  "Given a cart with two items When I close the tab Then the cart is still there";

test("Given, When and Then keep a line each", () => {
  const F = flow();
  assert.equal(
    F.bodyText(GWT),
    "Given a cart with two items\nWhen I close the tab\nThen the cart is still there"
  );
});

test("the card's title is the criterion's id, not its own first words", () => {
  const F = flow();
  const title = F.cardTitle({ id: "AC-1", text: GWT });
  assert.equal(title, "AC-1");
  // And the words are not said twice: the title is nowhere in the body.
  assert.equal(F.bodyText(GWT).includes(title), false);
});

test("a criterion somebody named keeps its name, and says it once", () => {
  const F = flow();
  const named = "Scenario: a cart survives a closed tab Given a cart Then it is there";
  assert.equal(F.cardTitle({ id: "AC-2", text: named }), "Scenario: a cart survives a closed tab");
  assert.equal(F.bodyText(named), "Given a cart\nThen it is there");
});

test("a criterion written as one plain sentence is left as one", () => {
  const F = flow();
  const plain = "The cart is kept for thirty days.";
  assert.equal(F.cardTitle({ id: "AC-3", text: plain }), "AC-3");
  assert.equal(F.bodyText(plain), plain);
});
