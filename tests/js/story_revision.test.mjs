/* The revision a tab has seen lives in the tab, not in the run.
 *
 * A browser test found that only the first edit after a page load was ever
 * saved. The criteria page keeps a copy of the run in memory. It saved once,
 * the store wrote revision 5 and recorded it inside the run in
 * sessionStorage - but the page's own copy still said revision 4, and its
 * next write put that number back. Every edit after the first was refused
 * as "This story changed in another tab", and Reload brought deleted
 * criteria back.
 *
 * The binding is two sessionStorage keys now, "qag.tab_story" and
 * "qag.tab_rev", and no page copy can reach either. Run by
 * `node --test tests/js`. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const read = (name) => readFileSync(join(here, "..", "..", "public", name), "utf8");
const runState = read("run_state.js");
const storyStore = read("story_store.js");

/** One browser: the shared localStorage every tab of it can see. */
function browser() {
  return {};
}

/** One tab of that browser, with a sessionStorage nobody else can reach. */
function tab(local) {
  const session = {};
  const timers = [];
  const listeners = {};
  const sandbox = {
    JSON,
    Object,
    Array,
    Math,
    String,
    Boolean,
    Date,
    isNaN,
    parseInt,
    localStorage: {
      getItem: (key) => (key in local ? local[key] : null),
      setItem: (key, value) => {
        local[key] = String(value);
      },
      removeItem: (key) => {
        delete local[key];
      },
    },
    sessionStorage: {
      getItem: (key) => (key in session ? session[key] : null),
      setItem: (key, value) => {
        session[key] = String(value);
      },
      removeItem: (key) => {
        delete session[key];
      },
    },
    dispatchEvent: (event) => {
      (listeners[event.type] || []).forEach((fn) => fn(event));
      return true;
    },
    addEventListener: (name, fn) => {
      listeners[name] = listeners[name] || [];
      listeners[name].push(fn);
    },
    CustomEvent: class {
      constructor(type, init) {
        this.type = type;
        this.detail = (init || {}).detail;
      }
    },
    setTimeout: (fn) => {
      timers.push(fn);
      return timers.length;
    },
    clearTimeout: (id) => {
      timers[id - 1] = null;
    },
  };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(runState, sandbox);
  vm.runInContext(storyStore, sandbox);
  return {
    S: sandbox.QAGStories,
    Run: sandbox.QAGRun,
    session,
    tick: () => timers.forEach((fn) => fn && fn()),
  };
}

const STORY = "As a shopper, I want my cart kept so I can finish later.";

/** What the criteria page does: it holds a copy of the run and edits that. */
function criteriaPage(t, id) {
  const page = { run: t.Run.read() };
  page.addCriterion = (text) => {
    page.run.criteria = (page.run.criteria || []).concat([
      { id: "AC-" + ((page.run.criteria || []).length + 1), text: text },
    ]);
    /* The page writes its own copy, exactly as the real page does. */
    t.Run.write(page.run);
    return t.S.saveStory(id, t.Run.read());
  };
  return page;
}

/* ── BUG-01: every edit is saved ────────────────────────────────────────── */

test("five criteria edits in a row are all saved", () => {
  const local = browser();
  const a = tab(local);
  const story = a.S.create({ run: { story: STORY } }).story;
  a.S.open(story.id);
  const before = a.S.get(story.id).revision;

  const page = criteriaPage(a, story.id);
  const results = [];
  for (let n = 1; n <= 5; n++) results.push(page.addCriterion("Rule number " + n));

  assert.deepEqual(results, ["", "", "", "", ""]);
  assert.equal(a.S.get(story.id).revision, before + 5);
  assert.equal(a.S.get(story.id).run.criteria.length, 5);
  assert.equal(a.S.get(story.id).run.criteria[4].text, "Rule number 5");
});

test("a deleted criterion does not come back on reload", () => {
  const local = browser();
  const a = tab(local);
  const story = a.S.create({
    run: { story: STORY, criteria: [{ id: "AC-1", text: "One" }, { id: "AC-2", text: "Two" }] },
  }).story;
  a.S.open(story.id);

  const page = criteriaPage(a, story.id);
  page.addCriterion("Three");
  page.run.criteria = page.run.criteria.filter((one) => one.text !== "Two");
  a.Run.write(page.run);
  assert.equal(a.S.saveStory(story.id, a.Run.read()), "");

  // Reload: a fresh tab opens the same story out of localStorage.
  const b = tab(local);
  b.S.open(story.id);
  assert.deepEqual(
    b.Run.read().criteria.map((one) => one.text),
    ["One", "Three"]
  );
});

test("a page holding a run copy from before its own save can still save", () => {
  const local = browser();
  const a = tab(local);
  const story = a.S.create({ run: { story: STORY } }).story;
  a.S.open(story.id);

  /* The copy this page loaded, kept across both saves. */
  const stale = JSON.parse(JSON.stringify(a.Run.read()));

  a.Run.write({ ...a.Run.read(), story: STORY + " First edit." });
  assert.equal(a.S.saveStory(story.id, a.Run.read()), "");

  /* Now the page writes from the copy it has held all along. */
  stale.story = STORY + " Second edit, from the old copy.";
  a.Run.write(stale);
  assert.equal(a.S.saveStory(story.id, a.Run.read()), "");
  assert.match(a.S.get(story.id).run.story, /Second edit/);
});

test("the run never carries a revision, in storage or in the tab", () => {
  const local = browser();
  const a = tab(local);
  const story = a.S.create({ run: { story: STORY } }).story;
  a.S.open(story.id);
  a.Run.write({ ...a.Run.read(), story: STORY + " edited" });
  a.S.saveStory(story.id, a.Run.read());

  assert.equal(a.Run.read()._story_rev, undefined);
  assert.equal(a.S.get(story.id).run._story_rev, undefined);
  assert.equal(a.S.tabRev(), a.S.get(story.id).revision);
  assert.equal(a.session[a.S.REV_KEY], String(a.S.get(story.id).revision));
});

test("a revision left inside an old saved run is ignored and dropped", () => {
  const local = browser();
  const a = tab(local);
  const story = a.S.create({ run: { story: STORY } }).story;
  /* A file written before the revision moved into the tab. */
  const raw = JSON.parse(local[a.S.KEY]);
  raw.stories[0].run._story_rev = 0;
  raw.stories[0].revision = 7;
  local[a.S.KEY] = JSON.stringify(raw);

  const b = tab(local);
  b.S.open(story.id);
  assert.equal(b.Run.read()._story_rev, undefined);
  b.Run.write({ ...b.Run.read(), story: STORY + " edited" });
  assert.equal(b.S.saveStory(story.id, b.Run.read()), "");
  assert.equal(b.S.get(story.id).revision, 8);
});

/* ── a real clash is still refused ──────────────────────────────────────── */

test("a real save from another tab still makes this tab stale", () => {
  const local = browser();
  const a = tab(local);
  const story = a.S.create({ run: { story: STORY } }).story;
  a.S.open(story.id);

  const b = tab(local);
  b.S.open(story.id);
  b.Run.write({ ...b.Run.read(), story: STORY + " edited in tab B" });
  assert.equal(b.S.saveStory(story.id, b.Run.read()), "");

  a.Run.write({ ...a.Run.read(), story: STORY + " edited in tab A" });
  assert.equal(a.S.saveStory(story.id, a.Run.read()), "stale");
  assert.equal(a.S.elsewhere(), "changed");
  assert.match(a.S.get(story.id).run.story, /tab B/);
});

test("Keep mine writes over the newer copy and then saves normally again", () => {
  const local = browser();
  const a = tab(local);
  const story = a.S.create({ run: { story: STORY } }).story;
  a.S.open(story.id);

  const b = tab(local);
  b.S.open(story.id);
  b.Run.write({ ...b.Run.read(), story: STORY + " tab B" });
  b.S.saveStory(story.id, b.Run.read());

  a.Run.write({ ...a.Run.read(), story: STORY + " tab A wins" });
  assert.equal(a.S.forceSave(story.id, a.Run.read()), "");
  assert.match(a.S.get(story.id).run.story, /tab A wins/);

  a.Run.write({ ...a.Run.read(), story: STORY + " tab A again" });
  assert.equal(a.S.saveStory(story.id, a.Run.read()), "");
});

/* ── BUG-11: opening is not editing ─────────────────────────────────────── */

test("another tab opening the same story does not make this tab stale", () => {
  const local = browser();
  const a = tab(local);
  const story = a.S.create({ run: { story: STORY } }).story;
  a.S.open(story.id);
  const revision = a.S.get(story.id).revision;

  /* Tab B opens it, reloads, opens it again. No edit anywhere. */
  const b = tab(local);
  b.S.open(story.id);
  b.S.open(story.id);
  tab(local).S.open(story.id);

  assert.equal(a.S.get(story.id).revision, revision);
  assert.equal(a.S.elsewhere(), "");

  a.Run.write({ ...a.Run.read(), story: STORY + " edited in tab A" });
  assert.equal(a.S.saveStory(story.id, a.Run.read()), "");
});

test("opening a story changes neither the revision nor Last edited", () => {
  const local = browser();
  const a = tab(local);
  const story = a.S.create({ run: { story: STORY } }).story;
  const edited = a.S.get(story.id).updated_at;
  const revision = a.S.get(story.id).revision;

  a.S.open(story.id);
  a.S.listen();
  a.tick();

  assert.equal(a.S.get(story.id).updated_at, edited);
  assert.equal(a.S.get(story.id).revision, revision);
  assert.equal(a.S.saveRun(a.Run.read()), "same");
});

test("a page load that normalises old data in memory writes nothing", () => {
  const local = browser();
  const a = tab(local);
  const story = a.S.create({ run: { story: STORY } }).story;
  const revision = a.S.get(story.id).revision;

  const b = tab(local);
  b.S.open(story.id);
  /* The page tidies its own copy and never hands it to the store. */
  const page = b.Run.read();
  page.criteria = (page.criteria || []).map((one) =>
    typeof one === "string" ? { id: "AC-1", text: one } : one
  );

  assert.equal(b.S.get(story.id).revision, revision);
  assert.equal(a.S.elsewhere(), "");
});
