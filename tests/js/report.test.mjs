/* Unit tests for public/report.js, run by `node --test tests/js`.
 *
 * The page is a browser script, so it runs here against a small fake
 * window with a DOM thin enough to assert on. The two things worth
 * guarding are that nothing from the link is ever put on the page as HTML,
 * and that "Open in QA-Genius desks" makes exactly one new story and
 * leaves every story already saved alone. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import zlib from "node:zlib";

const here = dirname(fileURLToPath(import.meta.url));
const read = (name) => readFileSync(join(here, "..", "..", "public", name), "utf8");
/* Objects built inside the vm belong to its realm, so deepStrictEqual
 * refuses them against literals written out here. Compare the data. */
const plain = (value) => JSON.parse(JSON.stringify(value));

/* ---------- a DOM small enough to read ---------- */

function makeNode(tag) {
  return {
    tagName: String(tag).toUpperCase(),
    className: "",
    id: "",
    type: "",
    href: "",
    style: {},
    children: [],
    listeners: {},
    _text: "",
    get textContent() {
      if (this._text) return this._text;
      return this.children.map((one) => one.textContent).join("");
    },
    set textContent(value) {
      this._text = String(value);
      this.children = [];
    },
    appendChild(child) {
      this.children.push(child);
      return child;
    },
    addEventListener(name, fn) {
      this.listeners[name] = fn;
    },
    click() {
      if (this.listeners.click) this.listeners.click();
    },
    querySelector(selector) {
      const want = String(selector).replace(/^\./, "");
      const walk = (node) => {
        for (const child of node.children) {
          if (String(child.className).split(/\s+/).includes(want)) return child;
          const found = walk(child);
          if (found) return found;
        }
        return null;
      };
      return walk(this);
    }
  };
}

function everyNode(root, out = []) {
  out.push(root);
  root.children.forEach((child) => everyNode(child, out));
  return out;
}

function findByClass(root, name) {
  return everyNode(root).filter((node) =>
    String(node.className).split(/\s+/).includes(name)
  );
}

function allText(root) {
  return everyNode(root)
    .map((node) => node._text)
    .join(" ");
}

/* ---------- packing, the way the server does ---------- */

function packed(data) {
  const raw = Buffer.from(JSON.stringify(data), "utf8");
  const squeezed = zlib.deflateRawSync(raw, { level: 9 });
  return "v1." + squeezed.toString("base64url");
}

/* ---------- loading the script ---------- */

function load({ hash = "", withStore = false } = {}) {
  const root = makeNode("div");
  root.id = "report-root";
  const store = {};
  const session = {};

  const sandbox = {
    JSON,
    Object,
    Array,
    Math,
    String,
    Number,
    Boolean,
    Date,
    isNaN,
    Error,
    Promise,
    Uint8Array,
    TextDecoder,
    Buffer,
    /* The real ones. The page inflates with the browser's own
     * DecompressionStream, so the test should too — a hand-rolled stub
     * would prove the stub works. */
    DecompressionStream,
    Response,
    atob: (text) => Buffer.from(text, "base64").toString("binary"),
    console,
    setTimeout,
    clearTimeout,
    localStorage: {
      getItem: (k) => (k in store ? store[k] : null),
      setItem: (k, v) => {
        store[k] = String(v);
      },
      removeItem: (k) => {
        delete store[k];
      }
    },
    sessionStorage: {
      getItem: (k) => (k in session ? session[k] : null),
      setItem: (k, v) => {
        session[k] = String(v);
      },
      removeItem: (k) => {
        delete session[k];
      }
    },
    location: { hash, href: "/report" + hash },
    navigator: {},
    document: {
      readyState: "complete",
      createElement: makeNode,
      createTextNode: (value) => {
        const node = makeNode("#text");
        node.textContent = value;
        return node;
      },
      getElementById: (id) => (id === "report-root" ? root : null),
      addEventListener() {},
      dispatchEvent() {}
    },
    addEventListener() {},
    dispatchEvent() {},
    CustomEvent: class {
      constructor(name, options) {
        this.type = name;
        Object.assign(this, options);
      }
    }
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);

  if (withStore) {
    vm.runInContext(read("run_state.js"), sandbox);
    vm.runInContext(read("story_store.js"), sandbox);
  }
  vm.runInContext(read("report.js"), sandbox);
  return { sandbox, root, store, session };
}

/* ---------- a report to draw ---------- */

const REPORT = {
  schema_version: "1.0",
  tool: "ship_check",
  summary: "not ready · grade D · 4 of 7 checks run",
  story_label: "AUR-14",
  story: "As a shopper I want to apply a coupon so that I pay less.",
  context: "Coupons need an order of at least $50.",
  decision: "not ready",
  grade: { letter: "D", points: 4, max: 8, lines: ["Criteria with a test: fine (2 of 2)"] },
  path_to_ready: ["Add the missing tests for AC-2"],
  criteria: [
    { id: "AC-1", text: "A coupon on a cart over $50 applies the discount" },
    { id: "AC-2", text: "A coupon on a smaller cart is refused" }
  ],
  test_cases: [
    {
      id: "TC-1",
      title: "A valid coupon on a cart over the minimum",
      steps: ["Put $60.00 in the cart", "Enter a valid coupon"],
      expected: "The total drops by the discount",
      test_data: "cart_total=$60.00",
      covers: ["AC-1"],
      kind: "normal"
    }
  ],
  problems: [
    {
      id: "D-1a2b",
      kind: "depth",
      level: "high",
      says: "AC-2 has no tests yet.",
      fix: "Write at least one test that covers AC-2.",
      criteria: ["AC-2"],
      tests: []
    }
  ],
  ask_the_po: ["Nobody says what happens at exactly $50."],
  notes: ["A check with nothing sent for it reads “not done yet”."],
  fixed_since_last_check: ["L-9999"],
  still_open: ["D-1a2b"]
};

/* A report carrying something for every desk, which is what the "Open in
 * QA-Genius desks" button has to fill. */
const FULL_REPORT = {
  ...REPORT,
  risks_in: [
    {
      id: "R1",
      title: "The same coupon is applied twice",
      effect: "The shop gives double the discount",
      cause: "Two requests race before either is recorded",
      category: "data",
      how_bad: 5,
      how_likely: 3,
      how_hard_to_notice: 4,
      linked_criteria: ["AC-1"],
      tested_by: []
    }
  ],
  matrix_input: {
    factors: [
      { name: "Browser", options: ["Chrome", "Firefox"] },
      { name: "Device", options: ["Desktop", "Phone"] }
    ],
    rules: [],
    pinned: []
  }
};

/* ---------- the page draws ---------- */

test("the report draws from the link", async () => {
  const { sandbox, root } = load({ hash: "#" + packed(REPORT) });
  const data = await sandbox.QAGReport.unpack("#" + packed(REPORT));
  sandbox.QAGReport.draw(root, data);

  const said = allText(root);
  assert.ok(said.includes("REPORT FROM CLAUDE · AUR-14"));
  assert.ok(said.includes("Nothing stored — the data is in this link."));
  assert.ok(said.includes("not ready"));
  assert.ok(said.includes("AC-2 has no tests yet."));
  assert.ok(said.includes("Nobody says what happens at exactly $50."));
});

test("a report with no story id still says so", async () => {
  const bare = { ...REPORT, story_label: "" };
  const { sandbox, root } = load();
  sandbox.QAGReport.draw(root, bare);
  assert.ok(allText(root).includes("REPORT FROM CLAUDE · NO ID"));
});

test("the stat row counts criteria, tests, fixed and still open", async () => {
  const { sandbox, root } = load();
  sandbox.QAGReport.draw(root, REPORT);
  const numbers = findByClass(root, "num").map((node) => node.textContent);
  assert.deepEqual(numbers, ["2", "1", "1", "1"]);
});

test("open problems come before fixed ones", async () => {
  const { sandbox, root } = load();
  sandbox.QAGReport.draw(root, REPORT);
  const rows = findByClass(root, "report-row");
  assert.ok(String(rows[0].className).includes("report-open"));
  assert.ok(String(rows[1].className).includes("report-fixed"));
});

test("nothing from the link is ever put on the page as HTML", async () => {
  const nasty = {
    ...REPORT,
    story: "<img src=x onerror=alert(1)>",
    problems: [
      {
        id: "<script>",
        kind: "depth",
        level: "high",
        says: "<b>bold</b> & <script>alert(1)</script>",
        fix: "</p><iframe>",
        criteria: [],
        tests: []
      }
    ]
  };
  const { sandbox, root } = load();
  sandbox.QAGReport.draw(root, nasty);
  /* It is all there, and all of it is text. The fake DOM has no innerHTML
   * at all, so a script that reached for one would have thrown by now. */
  const said = allText(root);
  assert.ok(said.includes("<img src=x onerror=alert(1)>"));
  assert.ok(said.includes("<b>bold</b> & <script>alert(1)</script>"));
  assert.ok(everyNode(root).every((node) => node.innerHTML === undefined));
});

test("sections only appear when the report has them", async () => {
  const { sandbox, root } = load();
  sandbox.QAGReport.draw(root, REPORT);
  assert.equal(findByClass(root, "table").length, 0);

  const withRisks = {
    ...REPORT,
    risks: [
      {
        id: "R1",
        title: "The coupon is used twice",
        category: "data",
        score: 60,
        max_score: 125,
        level: "high",
        coverage: "no test",
        tested_by: []
      }
    ]
  };
  const second = load();
  second.sandbox.QAGReport.draw(second.root, withRisks);
  const said = allText(second.root);
  assert.ok(said.includes("Risks"));
  assert.ok(said.includes("60/125"));
});

/* ---------- a link that cannot be read ---------- */

test("a broken link gets the friendly page", async () => {
  const { sandbox, root } = load();
  sandbox.QAGReport.broken(root);
  assert.ok(allText(root).includes("broken or incomplete"));
  assert.ok(allText(root).includes("Ask Claude to run the check again"));
});

test("rubbish after the hash is refused rather than drawn", async () => {
  const { sandbox } = load();
  await assert.rejects(() => sandbox.QAGReport.unpack("#not-a-report"));
  await assert.rejects(() => sandbox.QAGReport.unpack("#v1.zzzz"));
  await assert.rejects(() => sandbox.QAGReport.unpack(""));
});

test("valid packing that is not a report object is refused", async () => {
  const { sandbox } = load();
  await assert.rejects(() => sandbox.QAGReport.unpack("#" + packed([1, 2, 3])));
});

/* ---------- open in the desks ---------- */

test("the run it builds is the shape the desks read", async () => {
  const { sandbox } = load();
  const run = sandbox.QAGReport.runFrom(REPORT);
  assert.equal(run.story, REPORT.story);
  assert.equal(run.context, REPORT.context);
  assert.equal(run.story_type, "User story");
  assert.deepEqual(run.test_cases.criteria, [
    "A coupon on a cart over $50 applies the discount",
    "A coupon on a smaller cart is refused"
  ]);
  const first = run.test_cases.result.test_cases[0];
  assert.equal(first.id, "TC-1");
  assert.equal(first.expected_result, "The total drops by the discount");
  assert.equal(first.traceability, "AC-1");
  assert.equal(first.category, "Functional");
});

/* The Criteria desk reads run.criteria as {id, text} objects and renumbers
 * them by position. Strings, or ids carried over from the agent, leave the
 * desk empty or mislabelled. */
test("the criteria are objects the Criteria desk can read", async () => {
  const { sandbox } = load();
  const run = sandbox.QAGReport.runFrom(REPORT);
  assert.deepEqual(plain(run.criteria), [
    { id: "AC-1", text: "A coupon on a cart over $50 applies the discount" },
    { id: "AC-2", text: "A coupon on a smaller cart is refused" }
  ]);
});

test("the ids follow position, whatever the agent called them", async () => {
  const { sandbox } = load();
  const run = sandbox.QAGReport.runFrom({
    ...REPORT,
    criteria: [
      { id: "PAY-7", text: "First" },
      { id: "PAY-2", text: "Second" }
    ]
  });
  assert.deepEqual(
    run.criteria.map((one) => one.id),
    ["AC-1", "AC-2"]
  );
});

test("the risks keep their own scores, not placeholder threes", async () => {
  const { sandbox } = load();
  const run = sandbox.QAGReport.runFrom({
    ...REPORT,
    risks_in: [
      {
        id: "R1",
        title: "The coupon is used twice",
        effect: "Double discount",
        cause: "A race between two requests",
        category: "data",
        how_bad: 5,
        how_likely: 3,
        how_hard_to_notice: 4,
        linked_criteria: ["AC-1"],
        tested_by: ["TC-1"]
      }
    ]
  });
  const risk = run.risk_analysis.analysis.failure_modes[0];
  assert.equal(risk.severity, 5);
  assert.equal(risk.likelihood, 3);
  assert.equal(risk.detectability, 4);
  assert.equal(risk.effect, "Double discount");
  assert.equal(risk.cause, "A race between two requests");
  assert.deepEqual(risk.related_criteria, ["AC-1"]);
  /* The Risk radar scores against the cases in the run, so they travel. */
  assert.equal(run.risk_analysis.cases.length, 1);
  assert.equal(run.risk_analysis.criteria.length, 2);
});

test("a matrix becomes factors and rules the Test matrix desk redraws from", async () => {
  const { sandbox } = load();
  const run = sandbox.QAGReport.runFrom({
    ...REPORT,
    matrix_input: {
      factors: [
        { name: "Browser", options: ["Chrome", "Firefox"] },
        { name: "Device", options: ["Desktop", "Phone"] }
      ],
      rules: [
        { a: "Browser=Firefox", b: "Device=Phone", reason: "No mobile Firefox." }
      ],
      pinned: []
    }
  });
  assert.deepEqual(plain(run.matrix.factors), [
    { name: "Browser", values: ["Chrome", "Firefox"], reason: "" },
    { name: "Device", values: ["Desktop", "Phone"], reason: "" }
  ]);
  assert.deepEqual(plain(run.matrix.rules), [
    {
      if_factor: "Browser",
      if_value: "Firefox",
      then_factor: "Device",
      then_value: "Phone",
      reason: "No mobile Firefox.",
      source: "ai"
    }
  ]);
});

test("a matrix with fewer than two factors is left out rather than half-built", async () => {
  const { sandbox } = load();
  const run = sandbox.QAGReport.runFrom({
    ...REPORT,
    matrix_input: { factors: [{ name: "Browser", options: ["Chrome", "Firefox"] }] }
  });
  assert.equal(run.matrix, undefined);
});

test("each kind becomes the category the desks count", async () => {
  const { sandbox } = load();
  const kinds = ["normal", "wrong input", "at the limit", "unusual"];
  const run = sandbox.QAGReport.runFrom({
    ...REPORT,
    test_cases: kinds.map((kind, n) => ({
      id: "TC-" + n,
      title: "x",
      steps: ["a"],
      expected: "b",
      covers: [],
      kind
    }))
  });
  assert.deepEqual(
    run.test_cases.result.test_cases.map((one) => one.category),
    ["Functional", "Negative", "Boundary", "Edge Case"]
  );
});

test("a report with no risks plants no empty risk analysis", async () => {
  const { sandbox } = load();
  assert.equal(sandbox.QAGReport.runFrom(REPORT).risk_analysis, undefined);
});

test("open in desks makes exactly one new story", async () => {
  const { sandbox } = load({ withStore: true });
  assert.equal(sandbox.QAGStories.count(), 0);
  const made = sandbox.QAGReport.openInDesks(REPORT);
  assert.ok(made.story);
  assert.equal(sandbox.QAGStories.count(), 1);
  const saved = sandbox.QAGStories.get(made.story.id);
  assert.equal(saved.run.story, REPORT.story);
  assert.equal(saved.run.test_cases.result.test_cases.length, 1);
});

test("open in desks leaves the stories already saved alone", async () => {
  const { sandbox } = load({ withStore: true });
  const mine = sandbox.QAGStories.create({
    run: { story: "A story I was already working on" }
  });
  const before = sandbox.QAGStories.get(mine.story.id);

  sandbox.QAGReport.openInDesks(REPORT);

  assert.equal(sandbox.QAGStories.count(), 2);
  const after = sandbox.QAGStories.get(mine.story.id);
  assert.equal(after.run.story, "A story I was already working on");
  assert.equal(after.revision, before.revision);
});

test("open in desks points this tab at the new story", async () => {
  const { sandbox } = load({ withStore: true });
  const made = sandbox.QAGReport.openInDesks(REPORT);
  assert.equal(sandbox.QAGStories.tabStory(), made.story.id);
});

/* Saving the story is only half of it. Every desk reads the run out of
 * sessionStorage, so a story that is saved and not opened leaves all four
 * desks blank — and the button still navigates, so it looks like it
 * worked. This is the test for that. */
test("open in desks writes the run where the desks actually look", async () => {
  const { sandbox, session } = load({ withStore: true });
  sandbox.QAGReport.openInDesks(FULL_REPORT);

  const run = JSON.parse(session["qag.run"]);
  assert.equal(run.story, FULL_REPORT.story);
  assert.equal(run.criteria.length, FULL_REPORT.criteria.length);
  assert.equal(
    run.test_cases.result.test_cases.length,
    FULL_REPORT.test_cases.length
  );
  assert.ok(run.risk_analysis.analysis.failure_modes.length);
  assert.ok(run.matrix.factors.length >= 2);
});

test("the run in the session is the run that was saved", async () => {
  const { sandbox, session } = load({ withStore: true });
  const made = sandbox.QAGReport.openInDesks(FULL_REPORT);
  const saved = sandbox.QAGStories.get(made.story.id).run;
  const live = JSON.parse(session["qag.run"]);
  assert.equal(live.story, saved.story);
  assert.equal(live._story_id, made.story.id);
});

test("open in desks says so rather than throwing when there is no store", async () => {
  const { sandbox } = load();
  const made = sandbox.QAGReport.openInDesks(REPORT);
  assert.equal(made.error, "no-store");
});

/* The point of the button: every desk has something in it afterwards.
 * These read the saved run the way each desk's own code reads it, so a
 * shape that is nearly right fails here rather than looking fine until
 * somebody clicks through and finds three empty pages. */
test("after opening, the Story desk has the story", async () => {
  const { sandbox } = load({ withStore: true });
  const made = sandbox.QAGReport.openInDesks(FULL_REPORT);
  const run = sandbox.QAGStories.get(made.story.id).run;
  // requirements_flow.js: setField("user_story", run.story || "")
  assert.equal(run.story, FULL_REPORT.story);
  assert.equal(run.context, FULL_REPORT.context);
  assert.ok(run.story_type);
});

test("after opening, the Criteria desk has the criteria", async () => {
  const { sandbox } = load({ withStore: true });
  const made = sandbox.QAGReport.openInDesks(FULL_REPORT);
  const run = sandbox.QAGStories.get(made.story.id).run;
  // requirements_flow.js: (run.criteria || []).map(c => c.text)
  const texts = (run.criteria || []).map((one) => one.text);
  assert.deepEqual(
    texts,
    FULL_REPORT.criteria.map((one) => one.text)
  );
  assert.ok(texts.every((one) => one.trim() !== ""));
});

test("after opening, the Test cases desk has every test", async () => {
  const { sandbox } = load({ withStore: true });
  const made = sandbox.QAGReport.openInDesks(FULL_REPORT);
  const run = sandbox.QAGStories.get(made.story.id).run;
  // requirements_flow.js: run.test_cases.result.test_cases
  const cases =
    run.test_cases && run.test_cases.result ? run.test_cases.result.test_cases : [];
  assert.equal(cases.length, FULL_REPORT.test_cases.length);
  assert.deepEqual(
    cases.map((one) => one.id),
    FULL_REPORT.test_cases.map((one) => one.id)
  );
  // casesFor() matches on traceability, so a criterion finds its tests.
  const forAc1 = cases.filter((one) =>
    String(one.traceability).toUpperCase().includes("AC-1")
  );
  assert.ok(forAc1.length > 0);
});

test("after opening, the Risk radar has the risks with their scores", async () => {
  const { sandbox } = load({ withStore: true });
  const made = sandbox.QAGReport.openInDesks(FULL_REPORT);
  const run = sandbox.QAGStories.get(made.story.id).run;
  // risk_radar.js: run.risk_analysis.analysis
  assert.ok(run.risk_analysis && run.risk_analysis.analysis);
  const modes = run.risk_analysis.analysis.failure_modes;
  assert.equal(modes.length, 1);
  assert.equal(modes[0].severity, 5);
});

test("after opening, the Test matrix has its factors", async () => {
  const { sandbox } = load({ withStore: true });
  const made = sandbox.QAGReport.openInDesks(FULL_REPORT);
  const run = sandbox.QAGStories.get(made.story.id).run;
  // test_matrix.js: saved.factors && saved.factors.length >= 2
  assert.ok(run.matrix && run.matrix.factors.length >= 2);
});

test("a report with only a story leaves the other desks alone", async () => {
  const { sandbox } = load({ withStore: true });
  const made = sandbox.QAGReport.openInDesks({
    story: "As a shopper I want to sign in.",
    criteria: [],
    test_cases: []
  });
  const run = sandbox.QAGStories.get(made.story.id).run;
  assert.equal(run.criteria, undefined);
  assert.equal(run.test_cases, undefined);
  assert.equal(run.risk_analysis, undefined);
  assert.equal(run.matrix, undefined);
});

/* ---------- markdown ---------- */

test("copy as markdown says the decision and every open problem", async () => {
  const { sandbox } = load();
  const markdown = sandbox.QAGReport.toMarkdown(REPORT);
  assert.ok(markdown.includes("# QA-Genius report"));
  assert.ok(markdown.includes("**Decision:** not ready"));
  assert.ok(markdown.includes("**D-1a2b**"));
  assert.ok(markdown.includes("Write at least one test that covers AC-2."));
  assert.ok(markdown.includes("## Ask your PO"));
});
