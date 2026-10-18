/* Unit tests for the pure helpers in public/requirements_flow.js, run by
 * `node --test tests/js`. The file is a browser IIFE that only touches
 * `document.addEventListener` while it loads, so a tiny fake is enough. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(
  join(here, "..", "..", "public", "requirements_flow.js"),
  "utf8",
);

/** Bring a value out of the vm realm so deep comparison works. */
const plain = (value) => JSON.parse(JSON.stringify(value));

function load() {
  const store = {};
  const sandbox = {
    document: { addEventListener: () => {}, querySelector: () => null },
    sessionStorage: {
      getItem: (key) => (key in store ? store[key] : null),
      setItem: (key, value) => {
        store[key] = String(value);
      },
    },
    JSON,
    Object,
    Array,
    Math,
    Date,
    isNaN,
  };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox);
  return sandbox.QAGFlow;
}

const payload = () => ({
  result: {
    test_cases: [
      { id: "TC-001", title: "From the AI", tags: [] },
      { id: "TC-002", title: "From the principal QA", tags: ["principal-qa"] },
      { id: "TC-003", title: "Also from the AI", tags: [] },
    ],
    summary: { total_generated: 3 },
  },
  criteria: ["The account locks after 5 attempts"],
});

test("withoutCase drops exactly the case asked for", () => {
  const next = plain(load().withoutCase(payload(), "TC-002"));
  assert.deepEqual(
    next.result.test_cases.map((one) => one.id),
    ["TC-001", "TC-003"],
  );
});

test("withoutCase keeps the summary and the criteria", () => {
  const next = plain(load().withoutCase(payload(), "TC-002"));
  assert.deepEqual(next.criteria, ["The account locks after 5 attempts"]);
  assert.deepEqual(next.summary, undefined);
  assert.deepEqual(next.result.summary, { total_generated: 3 });
});

test("withoutCase never changes the payload it was given", () => {
  const before = payload();
  load().withoutCase(before, "TC-002");
  assert.equal(before.result.test_cases.length, 3);
});

test("withoutCase returns null when the id is not there", () => {
  assert.equal(load().withoutCase(payload(), "TC-099"), null);
});

test("withoutCase survives a payload that is not a list of cases", () => {
  const flow = load();
  assert.equal(flow.withoutCase(null, "TC-001"), null);
  assert.equal(flow.withoutCase({}, "TC-001"), null);
  assert.equal(flow.withoutCase({ result: {} }, "TC-001"), null);
});

test("criterion ids always follow position", () => {
  const renumbered = plain(load().renumber(["first", { text: "second" }]));
  assert.deepEqual(renumbered, [
    { id: "AC-1", text: "first" },
    { id: "AC-2", text: "second" },
  ]);
});
