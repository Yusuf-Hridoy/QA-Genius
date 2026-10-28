/* Unit tests for the Overview helpers in public/home.js.
 * The file is a plain browser script, so it is evaluated against a tiny fake
 * window with no document: everything tested here is pure. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(here, "..", "..", "public", "home.js"), "utf8");

function load() {
  const sandbox = { JSON, Object, Array, Math, String, Date };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox);
  return sandbox.QAGHome;
}

const home = load();

const plain = (value) => JSON.parse(JSON.stringify(value));

/* ── the one open question ─────────────────────────────────────────────── */

test("no story means no question", () => {
  assert.equal(home.topQuestion({}), null);
  assert.equal(home.topQuestion(null), null);
});

test("a limit nobody has decided comes first", () => {
  const run = {
    story_notes: {
      limit_notes: ["AC-03 says 30 days and AC-05 says 60. Nobody has decided."],
      epic: { title: "This story is really four features" }
    },
    story_analysis: {
      vague_phrases: [{ phrase: "quickly", severity: "high", replacement: "under 2 seconds" }]
    }
  };
  const question = home.topQuestion(run);
  assert.match(question.text, /Nobody has decided/);
  assert.equal(question.href, "/requirements/criteria");
  assert.equal(question.label, "Answer it");
});

test("an empty limit note is not a question", () => {
  const run = {
    story_notes: { limit_notes: ["", "   "], epic: { title: "Really four features" } }
  };
  assert.match(home.topQuestion(run).text, /four features/);
});

test("the epic warning comes before the unclear words", () => {
  const run = {
    story_notes: { limit_notes: [], epic: { title: "This story is really four features" } },
    story_analysis: { vague_phrases: [{ phrase: "quickly", severity: "high" }] }
  };
  const question = home.topQuestion(run);
  assert.match(question.text, /four features/);
  assert.equal(question.href, "/requirements/story#recommended-split");
  assert.equal(question.label, "See the split");
});

test("the worst unclear word is the one that is shown", () => {
  const run = {
    story_analysis: {
      vague_phrases: [
        { phrase: "soon", severity: "low", replacement: "within one hour" },
        { phrase: "quickly", severity: "high", replacement: "under 2 seconds" },
        { phrase: "often", severity: "medium" }
      ]
    }
  };
  const question = home.topQuestion(run);
  assert.match(question.text, /"quickly"/);
  assert.match(question.text, /under 2 seconds/);
  assert.equal(question.href, "/requirements/story");
});

test("an unclear word with no replacement still asks the question", () => {
  const run = { story_analysis: { vague_phrases: [{ phrase: "often", severity: "medium" }] } };
  const question = home.topQuestion(run);
  assert.match(question.text, /"often"/);
  assert.doesNotMatch(question.text, /Say\s+instead/);
});

test("a story with nothing open shows no strip", () => {
  const run = { story: "As a shopper…", story_analysis: { vague_phrases: [] } };
  assert.equal(home.topQuestion(run), null);
});

/* ── what needs attention ──────────────────────────────────────────────── */

const report = {
  items: [
    { id: "clarity", title: "How clear the story is", status: "pass", summary: "82 of 100", link: "/requirements/story" },
    { id: "coverage", title: "Criteria with a test", status: "warn", summary: "4 of 5", link: "/requirements/test-cases" },
    { id: "risks", title: "Risks with a test", status: "fail", summary: "2 high risks have no test", link: "/risks" },
    { id: "matrix", title: "Combinations", status: "not_checked", summary: "", link: "/requirements/matrix" }
  ]
};

test("needs fixing comes before check this", () => {
  const items = plain(home.attentionItems(report, {}));
  assert.equal(items.length, 2);
  assert.equal(items[0].title, "Risks with a test");
  assert.equal(items[0].tone, "bad");
  assert.equal(items[1].title, "Criteria with a test");
  assert.equal(items[1].tone, "warn");
});

test("a check that passed or never ran is not an item", () => {
  const items = plain(home.attentionItems(report, {}));
  const titles = items.map((one) => one.title);
  assert.ok(!titles.includes("How clear the story is"));
  assert.ok(!titles.includes("Combinations"));
});

test("an out-of-date desk comes last, after the checks", () => {
  const items = plain(
    home.attentionItems(report, { risks: "fresh", matrix: "stale", test_cases: "none" })
  );
  assert.equal(items.length, 3);
  assert.equal(items[2].title, "Test matrix is out of date");
  assert.equal(items[2].href, "/requirements/matrix");
  assert.equal(items[2].kind, "stale");
});

test("no report at all still lists the out-of-date desks", () => {
  const items = plain(home.attentionItems(null, { risks: "stale" }));
  assert.equal(items.length, 1);
  assert.equal(items[0].title, "Risk radar is out of date");
});

test("nothing wrong means nothing to show", () => {
  const clean = { items: [{ id: "clarity", title: "x", status: "pass", summary: "", link: "/" }] };
  assert.deepEqual(plain(home.attentionItems(clean, { risks: "fresh" })), []);
});

test("the panel never promises more than three rows", () => {
  assert.equal(home.MAX_ATTENTION, 3);
});

/* ── how clear ─────────────────────────────────────────────────────────── */

test("the clarity score is the other side of the ambiguity score", () => {
  assert.deepEqual(plain(home.clarityOf({ story_analysis: { ambiguity_score: 18 } })), {
    score: 82
  });
  assert.equal(home.clarityOf({}), null);
  assert.equal(home.clarityOf({ story_analysis: {} }), null);
});

test("a score outside 0-100 is pulled back into it", () => {
  assert.equal(home.clarityOf({ story_analysis: { ambiguity_score: 140 } }).score, 0);
  assert.equal(home.clarityOf({ story_analysis: { ambiguity_score: -20 } }).score, 100);
});
