/* Unit tests for public/run_state.js, run by `node --test tests/js`.
 * The module is plain browser script, so it is evaluated against a tiny fake
 * window with a sessionStorage that is just an object. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));

/** Bring a value out of the vm realm so deep comparison works. */
const plain = (value) => JSON.parse(JSON.stringify(value));
const source = readFileSync(join(here, "..", "..", "public", "run_state.js"), "utf8");

function load() {
  const store = {};
  const events = [];
  const sandbox = {
    sessionStorage: {
      getItem: (key) => (key in store ? store[key] : null),
      setItem: (key, value) => {
        store[key] = String(value);
      },
    },
    dispatchEvent: (event) => events.push(event),
    CustomEvent: class {
      constructor(type) {
        this.type = type;
      }
    },
    Date,
    JSON,
    Object,
    Array,
    Math,
    isNaN,
  };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox);
  return { QAGRun: sandbox.QAGRun, store, events };
}

/* A run far enough along that every part has content. */
function fullRun() {
  return {
    story: "As a user navigating the platform, I want a persistent left nav. It helps.",
    story_type: "User story",
    context: "",
    criteria: [
      { id: "AC-1", text: "The active module is highlighted" },
      { id: "AC-2", text: "Routing happens within 200ms" },
    ],
    test_cases: {
      result: {
        test_cases: [
          { id: "TC-001", title: "Highlight" },
          { id: "TC-002", title: "Routing" },
        ],
      },
    },
    automation_cases: [{ id: "TC-001" }],
  };
}

// ---------------------------------------------------------------- hashing

test("the same data hashes the same whatever order the keys came in", () => {
  const { QAGRun } = load();
  assert.equal(
    QAGRun.hash({ a: 1, b: { c: 2, d: 3 } }),
    QAGRun.hash({ b: { d: 3, c: 2 }, a: 1 })
  );
});

test("different data hashes differently", () => {
  const { QAGRun } = load();
  assert.notEqual(QAGRun.hash(["a", "b"]), QAGRun.hash(["b", "a"]));
});

test("a hash is always eight hex characters", () => {
  const { QAGRun } = load();
  for (const value of [null, "", [], { a: 1 }, "a longer string to hash"]) {
    assert.match(QAGRun.hash(value), /^[0-9a-f]{8}$/);
  }
});

// --------------------------------------------------------------- stamping

test("stamp records the hash, the count and the time", () => {
  const { QAGRun } = load();
  const run = fullRun();
  const stamped = QAGRun.stamp(run, "criteria");
  assert.equal(stamped.count, 2);
  assert.match(stamped.hash, /^[0-9a-f]{8}$/);
  assert.ok(stamped.at.startsWith("20"));
});

test("stamp counts test cases and selected cases", () => {
  const { QAGRun } = load();
  const run = fullRun();
  assert.equal(QAGRun.stamp(run, "test_cases").count, 2);
  assert.equal(QAGRun.stamp(run, "automation_cases").count, 1);
});

test("writing a run stamps every part and announces the change", () => {
  const { QAGRun, store, events } = load();
  QAGRun.write(fullRun());
  const saved = JSON.parse(store["qag.run"]);
  for (const part of QAGRun.PARTS) {
    assert.ok(saved.fp[part], `${part} was not stamped`);
  }
  assert.equal(events.length, 1);
  assert.equal(events[0].type, "qag:run-changed");
});

test("an unchanged part keeps its original timestamp", () => {
  const { QAGRun } = load();
  const run = QAGRun.write(fullRun());
  const first = run.fp.criteria.at;
  run.story = "A different story altogether.";
  const again = QAGRun.write(run);
  assert.equal(again.fp.criteria.at, first);
  assert.notEqual(again.fp.story.hash, run.fp.criteria.hash);
});

// ----------------------------------------------------------- desk status

test("a desk with no result is not built yet", () => {
  const { QAGRun } = load();
  const run = QAGRun.write(fullRun());
  for (const desk of ["risks", "matrix", "automation"]) {
    assert.equal(QAGRun.statusOf(desk, run).state, "none");
  }
});

test("a result saved with the run is up to date", () => {
  const { QAGRun } = load();
  const run = fullRun();
  run.risk_analysis = { analysis: { failure_modes: [] } };
  const saved = QAGRun.write(run);
  const status = QAGRun.statusOf("risks", saved);
  assert.equal(status.state, "fresh");
  assert.equal(status.auto, false);
});

test("changed criteria make risk radar out of date", () => {
  const { QAGRun } = load();
  const run = fullRun();
  run.risk_analysis = { analysis: { failure_modes: [] } };
  const saved = QAGRun.write(run);
  saved.criteria.push({ id: "AC-3", text: "Focus rings are visible" });
  const after = QAGRun.write(saved);
  const status = QAGRun.statusOf("risks", after);
  assert.equal(status.state, "stale");
  assert.match(status.changes[0], /Your criteria changed .* \(2 → 3\)/);
});

test("changed test cases alone leave risk radar fresh, for code to recheck", () => {
  const { QAGRun } = load();
  const run = fullRun();
  run.risk_analysis = { analysis: { failure_modes: [] } };
  const saved = QAGRun.write(run);
  saved.test_cases.result.test_cases.push({ id: "TC-003", title: "Focus" });
  const after = QAGRun.write(saved);
  const status = QAGRun.statusOf("risks", after);
  assert.equal(status.state, "fresh");
  assert.equal(status.auto, true);
  assert.match(status.changes[0], /Your test cases changed .* \(2 → 3\)/);
});

test("an edited story makes the matrix out of date", () => {
  const { QAGRun } = load();
  const run = fullRun();
  run.matrix = { runs: 12 };
  const saved = QAGRun.write(run);
  assert.equal(QAGRun.statusOf("matrix", saved).state, "fresh");

  saved.story = "A completely different story.";
  const after = QAGRun.write(saved);
  const status = QAGRun.statusOf("matrix", after);
  assert.equal(status.state, "stale");
  assert.match(status.changes[0], /Your story changed after this was built/);
});

test("changed test cases do not touch the matrix", () => {
  const { QAGRun } = load();
  const run = fullRun();
  run.matrix = { runs: 12 };
  const saved = QAGRun.write(run);
  saved.test_cases.result.test_cases.push({ id: "TC-003", title: "Focus" });
  assert.equal(QAGRun.statusOf("matrix", QAGRun.write(saved)).state, "fresh");
});

test("changed criteria make the test cases out of date", () => {
  const { QAGRun } = load();
  const run = fullRun();
  const saved = QAGRun.write(run);
  assert.equal(QAGRun.statusOf("test_cases", saved).state, "fresh");
  saved.criteria.push({ id: "AC-3", text: "Focus rings are visible" });
  assert.equal(QAGRun.statusOf("test_cases", QAGRun.write(saved)).state, "stale");
});

test("a changed selection makes the automation out of date", () => {
  const { QAGRun } = load();
  const run = fullRun();
  run.automation = { script: { framework: "Playwright (JavaScript)" } };
  const saved = QAGRun.write(run);
  assert.equal(QAGRun.statusOf("automation", saved).state, "fresh");

  saved.automation_cases = [{ id: "TC-001" }, { id: "TC-002" }];
  const status = QAGRun.statusOf("automation", QAGRun.write(saved));
  assert.equal(status.state, "stale");
  assert.match(status.changes[0], /Your selected test cases changed .*\(1 → 2\)/);
});

test("ship check is always fresh but lists the inputs that are not", () => {
  const { QAGRun } = load();
  const run = fullRun();
  run.risk_analysis = { analysis: { failure_modes: [] } };
  run.matrix = { runs: 12 };
  const saved = QAGRun.write(run);
  assert.deepEqual(plain(QAGRun.statusOf("ship", saved).changes), []);

  saved.story = "A completely different story.";
  const after = QAGRun.write(saved);
  const status = QAGRun.statusOf("ship", after);
  assert.equal(status.state, "fresh");
  assert.deepEqual(plain(status.changes).sort(), ["matrix", "risks", "test_cases"].sort());
  assert.deepEqual(plain(QAGRun.staleInputs(after)).sort(), plain(status.changes).sort());
});

test("keeping the factors marks the matrix current without rebuilding it", () => {
  const { QAGRun } = load();
  const run = fullRun();
  run.matrix = { runs: 12 };
  const saved = QAGRun.write(run);
  saved.story = "A completely different story.";
  const stale = QAGRun.write(saved);
  assert.equal(QAGRun.statusOf("matrix", stale).state, "stale");

  QAGRun.markBuilt(stale, "matrix");
  assert.equal(QAGRun.statusOf("matrix", stale).state, "fresh");
});

// ------------------------------------------------------------- time words

test("time ago falls into the buckets a person would use", () => {
  const { QAGRun } = load();
  const ago = (ms) => QAGRun.timeAgo(new Date(Date.now() - ms).toISOString());
  assert.equal(ago(5 * 1000), "just now");
  assert.equal(ago(59 * 1000), "just now");
  assert.equal(ago(3 * 60 * 1000), "3 min ago");
  assert.equal(ago(59 * 60 * 1000), "59 min ago");
  assert.equal(ago(2 * 3600 * 1000), "2 h ago");
  assert.equal(ago(25 * 3600 * 1000), "yesterday");
  assert.equal(QAGRun.timeAgo(""), "");
  assert.equal(QAGRun.timeAgo("not a date"), "");
});

// ---------------------------------------------------------- what we hold

test("the run is described in the words the card shows", () => {
  const { QAGRun } = load();
  const found = QAGRun.describeLatest(fullRun());
  assert.equal(
    found.storyTitle,
    "As a user navigating the platform, I want a persistent left nav"
  );
  assert.equal(found.criteriaCount, 2);
  assert.equal(found.caseCount, 2);
  assert.equal(found.automationCount, 1);
});

test("a long story title is cut on a word boundary", () => {
  const { QAGRun } = load();
  const long = "word ".repeat(40);
  const title = QAGRun.describeLatest({ story: long }).storyTitle;
  assert.ok(title.length <= 71, title.length);
  assert.ok(title.endsWith("…"));
});

test("an empty run describes itself without throwing", () => {
  const { QAGRun } = load();
  const found = QAGRun.describeLatest({});
  assert.deepEqual(plain(found), {
    storyTitle: "",
    criteriaCount: 0,
    caseCount: 0,
    automationCount: 0,
  });
});

test("blank criteria are not counted", () => {
  const { QAGRun } = load();
  const run = fullRun();
  run.criteria.push({ id: "AC-3", text: "   " });
  assert.equal(QAGRun.describeLatest(run).criteriaCount, 2);
});

test("reading a run back out of storage survives a round trip", () => {
  const { QAGRun } = load();
  QAGRun.write(fullRun());
  const back = QAGRun.read();
  assert.equal(back.story.startsWith("As a user"), true);
  assert.ok(back.fp.story.hash);
});

test("a blocked or empty storage reads as an empty run", () => {
  const { QAGRun } = load();
  assert.deepEqual(plain(QAGRun.read()), {});
});


// ---------------------------------------------- a sample is not your work

test("a loaded sample reports itself as a sample, not as up to date", () => {
  const { QAGRun } = load();
  const run = fullRun();
  run.risk_analysis = { analysis: { failure_modes: [] } };
  run.risk_analysis_is_example = true;
  const saved = QAGRun.write(run);
  assert.equal(QAGRun.statusOf("risks", saved).state, "example");
});

test("a sample never records what it was built from", () => {
  const { QAGRun } = load();
  const run = fullRun();
  run.matrix = { runs: 12 };
  run.matrix_is_example = true;
  const saved = QAGRun.write(run);
  assert.equal(saved.matrix_built_from, undefined);
  assert.equal(saved.matrix_built_at, undefined);
});

test("a real run clears the sample flag and starts counting again", () => {
  const { QAGRun } = load();
  const run = fullRun();
  run.risk_analysis = { analysis: { failure_modes: [] } };
  run.risk_analysis_is_example = true;
  let saved = QAGRun.write(run);
  assert.equal(QAGRun.statusOf("risks", saved).state, "example");

  // The desk runs for real: the flag goes and the result is yours.
  delete saved.risk_analysis_is_example;
  saved.risk_analysis = { analysis: { failure_modes: [{ id: "R1" }] } };
  saved = QAGRun.write(saved);
  assert.equal(QAGRun.statusOf("risks", saved).state, "fresh");
  assert.ok(saved.risk_analysis_built_from.story.hash);
});

test("a sample never makes ship check think an input is stale", () => {
  const { QAGRun } = load();
  const run = fullRun();
  run.risk_analysis = { analysis: { failure_modes: [] } };
  run.risk_analysis_is_example = true;
  const saved = QAGRun.write(run);
  assert.deepEqual(plain(QAGRun.statusOf("ship", saved).changes), []);
});

test("editing the story leaves a sample a sample", () => {
  const { QAGRun } = load();
  const run = fullRun();
  run.matrix = { runs: 12 };
  run.matrix_is_example = true;
  const saved = QAGRun.write(run);
  saved.story = "A completely different story.";
  assert.equal(QAGRun.statusOf("matrix", QAGRun.write(saved)).state, "example");
});
