/* One main button per screen state, on the Risk radar.
 *
 * A browser pass found two yellow buttons after a reload: the to-do strip
 * at the top offering "Write tests for all 3 →" and the form underneath
 * still offering "Find risks". Loading the example swaps the form away, so
 * the clash only showed on the way back in, which is why it lasted.
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

/* A button that remembers only what this is about: whether it is yellow. */
function button() {
  const classes = new Set(["btn", "btn-primary"]);
  return {
    classList: {
      toggle(name, on) {
        if (on) classes.add(name);
        else classes.delete(name);
      },
    },
    get main() {
      return classes.has("btn-primary");
    },
  };
}

/* `answered` is whether any risk card is drawn; `ids` are the find buttons
 * this page happens to have. A reload draws the paste form, the run draws
 * the other, and the empty state draws neither. */
function page({ answered, ids }) {
  const buttons = {};
  ids.forEach((id) => {
    buttons[id] = button();
  });
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
      getElementById: (id) => buttons[id] || null,
      querySelector: (what) =>
        what === "#risk-list .risk-card" && answered ? {} : null,
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
  return {
    run: sandbox.QAGRisks.keepOneMainButton,
    parts: sandbox.QAGRisks,
    buttons,
  };
}

test("with no risks on the page, Find risks is the main button", () => {
  const { run, buttons } = page({ answered: false, ids: ["risk-find"] });
  run();
  assert.equal(buttons["risk-find"].main, true);
});

test("once the risks are drawn, Find risks stops being the main button", () => {
  const { run, buttons } = page({ answered: true, ids: ["risk-find"] });
  run();
  assert.equal(buttons["risk-find"].main, false);
});

test("the paste form's button is the same button in disguise", () => {
  // The reload path draws this one, and covering only #risk-find left the
  // two yellow buttons exactly where they were.
  const { run, buttons } = page({ answered: true, ids: ["risk-paste-find"] });
  run();
  assert.equal(buttons["risk-paste-find"].main, false);
});

test("both ways in are quietened together", () => {
  const { run, buttons } = page({
    answered: true,
    ids: ["risk-find", "risk-paste-find"],
  });
  run();
  assert.equal(buttons["risk-find"].main, false);
  assert.equal(buttons["risk-paste-find"].main, false);
});

test("a page with neither button is left alone", () => {
  const { run } = page({ answered: true, ids: [] });
  assert.doesNotThrow(run);
});

test("the main button comes back when the answer goes away", () => {
  // Clearing the page puts the only thing worth pressing back in yellow.
  const { run, buttons } = page({ answered: false, ids: ["risk-paste-find"] });
  run();
  assert.equal(buttons["risk-paste-find"].main, true);
});

/* ── the cases a recheck scores against ─────────────────────────────────── */

/* A reload re-scored the risks against nothing and turned "2 high risks
 * have no test" into 3 on a page nobody had touched. The cases were in the
 * run the whole time; the recheck only looked in two of the three places
 * they can be, and an empty list counted as an answer. */
test("the desk that owns the cases is asked first", () => {
  const { firstFilled } = page({ answered: false, ids: [] }).parts;
  assert.deepEqual([...firstFilled(["a"], ["b"], ["c"])], ["a"]);
});

test("an empty list is not an answer, so it falls through", () => {
  const { firstFilled } = page({ answered: false, ids: [] }).parts;
  // This is the whole bug: [] used to count, so the saved cases were
  // never reached and every risk came back "No test yet".
  assert.deepEqual([...firstFilled([], ["b"], ["c"])], ["b"]);
  assert.deepEqual([...firstFilled([], [], ["c"])], ["c"]);
});

test("the copy saved with the analysis is the last resort, not the first", () => {
  const { firstFilled } = page({ answered: false, ids: [] }).parts;
  assert.deepEqual([...firstFilled(["a"], [], ["c"])], ["a"]);
  assert.deepEqual([...firstFilled([], ["b"], [])], ["b"]);
});

test("nothing anywhere is an empty list, never undefined", () => {
  const { firstFilled } = page({ answered: false, ids: [] }).parts;
  assert.deepEqual([...firstFilled([], [], [])], []);
  assert.deepEqual([...firstFilled(null, undefined, null)], []);
});
