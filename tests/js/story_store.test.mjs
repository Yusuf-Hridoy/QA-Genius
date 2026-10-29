/* Unit tests for public/story_store.js, run by `node --test tests/js`.
 * The module is a plain browser script, so it runs against a tiny fake window
 * with a localStorage that is only an object. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(here, "..", "..", "public", "story_store.js"), "utf8");
const runState = readFileSync(join(here, "..", "..", "public", "run_state.js"), "utf8");

const plain = (value) => JSON.parse(JSON.stringify(value));

function load(options = {}) {
  const store = {};
  const session = {};
  const events = [];
  const timers = [];
  const sandbox = {
    JSON,
    Object,
    Array,
    Math,
    String,
    Date,
    isNaN,
    localStorage: {
      getItem: (key) => (key in store ? store[key] : null),
      setItem: (key, value) => {
        if (options.full) throw new Error("QuotaExceededError");
        store[key] = String(value);
      },
      removeItem: (key) => {
        delete store[key];
      }
    },
    sessionStorage: {
      getItem: (key) => (key in session ? session[key] : null),
      setItem: (key, value) => {
        session[key] = String(value);
      },
      removeItem: (key) => {
        delete session[key];
      }
    },
    dispatchEvent: (event) => {
      events.push(event.type);
      (sandbox._on[event.type] || []).forEach((fn) => fn());
      return true;
    },
    addEventListener: (name, fn) => {
      sandbox._on[name] = sandbox._on[name] || [];
      sandbox._on[name].push(fn);
    },
    CustomEvent: class {
      constructor(type) {
        this.type = type;
      }
    },
    setTimeout: (fn) => {
      timers.push(fn);
      return timers.length;
    },
    clearTimeout: (id) => {
      timers[id - 1] = null;
    },
    _on: {}
  };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(runState, sandbox);
  vm.runInContext(source, sandbox);
  return {
    S: sandbox.QAGStories,
    QAGRun: sandbox.QAGRun,
    store,
    events,
    tick: () => timers.forEach((fn) => fn && fn())
  };
}

const RUN = { story: "As a shopper, I want my cart saved so I can finish later." };

/* ── making and opening ─────────────────────────────────────────────────── */

test("a new store is empty", () => {
  const { S } = load();
  assert.deepEqual(plain(S.list()), []);
  assert.equal(S.active(), null);
  assert.equal(S.count(), 0);
});

test("create numbers the first story S-001", () => {
  const { S } = load();
  const made = S.create({ run: RUN });
  assert.equal(made.error, "");
  assert.equal(made.story.label, "S-001");
  assert.equal(made.story.status, "draft");
  assert.match(made.story.id, /^s_[a-z0-9]{10}$/);
  assert.equal(S.count(), 1);
});

test("the numbers keep going up and fill a gap", () => {
  const { S } = load();
  S.create({ run: RUN });
  S.create({ run: RUN });
  assert.equal(S.list()[1].label, "S-002");
  S.remove(S.list()[0].id);
  assert.equal(S.create({ run: RUN }).story.label, "S-001");
});

test("a story keeps the id the reader typed", () => {
  const { S } = load();
  assert.equal(S.create({ run: RUN, label: "CART-204" }).story.label, "CART-204");
  assert.equal(S.create({ run: RUN, label: "no spaces here" }).error, "bad-label");
});

test("the title is the first 80 characters of the story", () => {
  const { S } = load();
  const long = { story: "x".repeat(200) };
  assert.equal(S.create({ run: long }).story.title.length, 80);
});

test("creating a story makes it the one being edited", () => {
  const { S } = load();
  const made = S.create({ run: RUN });
  assert.equal(S.active().id, made.story.id);
});

test("open copies the story's run into the live run", () => {
  const { S, QAGRun } = load();
  const first = S.create({ run: { story: "first story" } }).story;
  S.create({ run: { story: "second story" } });
  S.open(first.id);
  assert.equal(QAGRun.read().story, "first story");
  assert.equal(S.active().id, first.id);
});

test("opening a story that is not there changes nothing", () => {
  const { S } = load();
  S.create({ run: RUN });
  assert.equal(S.open("s_nothing"), null);
});

/* ── saving as you work ─────────────────────────────────────────────────── */

test("saveStory writes the run back over the story it names", () => {
  const { S } = load();
  const id = S.create({ run: RUN }).story.id;
  assert.equal(S.saveStory(id, { story: "an edited story" }), "");
  assert.equal(S.get(id).run.story, "an edited story");
  assert.equal(S.get(id).title, "an edited story");
});

test("a save with no story id goes nowhere", () => {
  const { S } = load();
  S.create({ run: RUN });
  assert.equal(S.saveStory("", { story: "lost" }), "no-id");
});

test("a run that lost its id is saved into the story this tab is on", () => {
  const { S } = load();
  const id = S.create({ run: RUN }).story.id;
  // A desk that built a fresh run object rather than copying the old one.
  assert.equal(S.saveRun({ story: "pasted on another desk" }), "");
  assert.equal(S.get(id).run.story, "pasted on another desk");
});

test("the first words on a tab with no story at all make one", () => {
  const { S, QAGRun } = load();
  QAGRun.write({ story: "typed before anything existed" });
  assert.equal(S.saveRun(QAGRun.read()), "");
  assert.equal(S.count(), 1);
  assert.equal(S.active().run.story, "typed before anything existed");
  assert.equal(QAGRun.read()._story_id, S.active().id);
});

test("but not on a tab whose story was just deleted", () => {
  const { S, QAGRun } = load();
  const id = S.create({ run: RUN }).story.id;
  S.open(id);
  S.remove(id);
  assert.equal(S.storyWasDeleted(), true);
  QAGRun.write({ story: "typed after the delete" });
  assert.equal(S.saveRun(QAGRun.read()), "deleted");
  assert.deepEqual(plain(S.list()), []);
});

test("a save into a story that is gone is refused", () => {
  const { S } = load();
  const id = S.create({ run: RUN }).story.id;
  S.remove(id);
  assert.equal(S.saveStory(id, { story: "too late" }), "deleted");
});

test("an example is never saved over your story", () => {
  const { S } = load();
  const id = S.create({ run: RUN }).story.id;
  assert.equal(
    S.saveStory(id, { story: "the sample", story_is_example: true }),
    "example"
  );
  assert.equal(S.get(id).run.story, RUN.story);
});

test("the id and status in the run reach the saved story", () => {
  const { S } = load();
  const id = S.create({ run: RUN }).story.id;
  S.saveStory(id, { story: "x", story_label: "CART-9", story_status: "review" });
  assert.equal(S.get(id).label, "CART-9");
  assert.equal(S.get(id).status, "review");
});

test("saving what is already there is not an edit", () => {
  const { S } = load();
  const made = S.create({ run: RUN }).story;
  const before = S.get(made.id).updated_at;
  assert.equal(S.saveStory(made.id, S.bound(made)), "same");
  assert.equal(S.get(made.id).updated_at, before);
  assert.equal(S.get(made.id).revision, made.revision);
});

test("an id another story already uses is refused", () => {
  const { S } = load();
  S.create({ run: RUN, label: "CHK-101" });
  const second = S.create({ run: RUN, label: "CART-204" }).story;
  const clash = S.create({ run: RUN, label: "CHK-101" });
  assert.equal(clash.error, "duplicate-label");
  assert.match(clash.message, /CHK-101 is already used by another story/);
  assert.equal(S.rename(second.id, "CHK-101"), "duplicate-label");
  assert.equal(S.get(second.id).label, "CART-204");
});

test("a write to the run saves the story one tick later", () => {
  const { S, QAGRun, tick } = load();
  const id = S.create({ run: RUN }).story.id;
  S.listen();
  QAGRun.write({ story: "typed just now", _story_id: id });
  assert.equal(S.get(id).run.story, RUN.story, "not saved before the wait");
  tick();
  assert.equal(S.get(id).run.story, "typed just now");
});

test("the wait is 600ms, so typing does not write on every key", () => {
  const { S } = load();
  assert.equal(S.SAVE_DELAY, 600);
});

/* ── renaming, status, copies and deleting ──────────────────────────────── */

test("rename takes only ids that look like ids", () => {
  const { S } = load();
  const id = S.create({ run: RUN }).story.id;
  assert.equal(S.rename(id, "CART-204"), "");
  assert.equal(S.get(id).label, "CART-204");
  assert.equal(S.rename(id, "two words"), "bad-label");
  assert.equal(S.rename("s_nothing", "OK-1"), "not-found");
});

test("the three statuses are the only three", () => {
  const { S } = load();
  const id = S.create({ run: RUN }).story.id;
  assert.equal(S.setStatus(id, "done"), "");
  assert.equal(S.get(id).status, "done");
  assert.equal(S.setStatus(id, "shipped"), "bad-status");
  assert.deepEqual(plain(S.STATUSES), ["draft", "review", "done"]);
});

test("a copy is a new story with the same run", () => {
  const { S } = load();
  const first = S.create({ run: RUN, label: "CART-204" }).story;
  const copy = S.duplicate(first.id).story;
  assert.notEqual(copy.id, first.id);
  assert.equal(copy.run.story, RUN.story);
  assert.notEqual(copy.label, "CART-204", "a copy gets its own number");
  assert.equal(S.count(), 2);
});

test("remove takes one story and leaves the rest", () => {
  const { S } = load();
  const first = S.create({ run: { story: "first" } }).story;
  const second = S.create({ run: { story: "second" } }).story;
  assert.equal(S.remove(first.id), "");
  assert.equal(S.count(), 1);
  assert.equal(S.active().id, second.id);
});

test("removing the open story leaves this tab with none", () => {
  const { S, QAGRun } = load();
  const first = S.create({ run: { story: "first" } }).story;
  S.create({ run: { story: "second" } });
  S.open(first.id);
  S.remove(first.id);
  // Nothing to show and nothing to save into: the page draws its empty
  // start screen rather than the deleted story's words.
  assert.equal(S.active(), null);
  assert.equal(S.tabStory(), "");
  assert.equal(QAGRun.read().story, undefined);
});

test("removeAll leaves nothing behind", () => {
  const { S, store } = load();
  S.create({ run: RUN });
  S.create({ run: RUN });
  assert.equal(S.removeAll(), "");
  assert.deepEqual(plain(S.list()), []);
  assert.equal(store["qag.stories.v1"], undefined);
});

/* ── the limits ─────────────────────────────────────────────────────────── */

test("twenty-five stories is the most", () => {
  const { S } = load();
  for (let at = 0; at < 25; at++) assert.equal(S.create({ run: RUN }).error, "");
  const over = S.create({ run: RUN });
  assert.equal(over.error, "full-count");
  assert.equal(S.count(), 25);
});

test("a run too big to save is refused, not half written", () => {
  const { S } = load();
  const id = S.create({ run: RUN }).story.id;
  const huge = { story: "x".repeat(5 * 1024 * 1024) };
  assert.equal(S.saveStory(id, huge), "full");
  assert.equal(S.get(id).run.story, RUN.story);
});

test("storage that refuses every write never throws", () => {
  const { S } = load({ full: true });
  const made = S.create({ run: RUN });
  assert.equal(made.error, "full");
  assert.deepEqual(plain(S.list()), []);
});

/* ── the first visit ────────────────────────────────────────────────────── */

test("a story already in the tab becomes S-001", () => {
  const { S } = load();
  const story = S.migrate(RUN);
  assert.equal(story.label, "S-001");
  assert.equal(S.count(), 1);
});

test("migration happens once, and never for an example", () => {
  const { S } = load();
  S.migrate(RUN);
  assert.equal(S.migrate({ story: "another" }), null);
  const { S: other } = load();
  assert.equal(other.migrate({ story: "a sample", story_is_example: true }), null);
  assert.equal(other.migrate({}), null);
  assert.equal(other.count(), 0);
});

/* ── carrying stories in and out ────────────────────────────────────────── */

test("export writes our own format", () => {
  const { S } = load();
  S.create({ run: RUN, label: "CART-204" });
  const data = JSON.parse(S.exportAll());
  assert.equal(data.version, 1);
  assert.equal(data.stories.length, 1);
  assert.equal(data.stories[0].label, "CART-204");
});

test("import brings back everything export wrote", () => {
  const first = load();
  first.S.create({ run: RUN, label: "CART-204" });
  const text = first.S.exportAll();

  const second = load();
  const result = second.S.importAll(text);
  assert.deepEqual(plain(result), { added: 1, updated: 0, skipped: 0, errors: [] });
  assert.equal(second.S.list()[0].label, "CART-204");
});

test("a file that is not ours is refused in plain words", () => {
  const { S } = load();
  assert.match(S.importAll("not json at all").errors[0], /not the one QA-Genius writes/);
  assert.match(
    S.importAll(JSON.stringify({ version: 99, stories: [] })).errors[0],
    /not the one QA-Genius writes/
  );
});

test("a story shaped wrongly is skipped with its reason", () => {
  const { S } = load();
  const result = S.importAll(
    JSON.stringify({
      version: 1,
      stories: [
        { id: "s_1", label: "GOOD-1", run: { story: "a real story" }, updated_at: "2026-01-01" },
        { id: "s_2", label: "BAD-1", run: { story: 7 } },
        { id: "s_3", label: "BAD-2" }
      ]
    })
  );
  assert.equal(result.added, 1);
  assert.equal(result.skipped, 2);
  assert.equal(result.errors.length, 2);
  assert.match(result.errors[0], /BAD-1: the story is not text/);
});

test("the same story twice: the newer one wins", () => {
  const { S } = load();
  const mine = {
    version: 1,
    stories: [
      { id: "s_1", label: "A-1", run: { story: "old" }, updated_at: "2026-01-01T00:00:00Z" }
    ]
  };
  S.importAll(JSON.stringify(mine));

  const newerOne = {
    version: 1,
    stories: [
      { id: "s_1", label: "A-1", run: { story: "new" }, updated_at: "2026-06-01T00:00:00Z" }
    ]
  };
  const result = S.importAll(JSON.stringify(newerOne));
  assert.equal(result.updated, 1);
  assert.equal(S.get("s_1").run.story, "new");

  const older = {
    version: 1,
    stories: [
      { id: "s_1", label: "A-1", run: { story: "older" }, updated_at: "2020-01-01T00:00:00Z" }
    ]
  };
  const second = S.importAll(JSON.stringify(older));
  assert.equal(second.skipped, 1);
  assert.equal(S.get("s_1").run.story, "new");
});

test("import stops at twenty-five and says why", () => {
  const { S } = load();
  for (let at = 0; at < 25; at++) S.create({ run: RUN });
  const result = S.importAll(
    JSON.stringify({
      version: 1,
      stories: [{ id: "s_new", label: "X-1", run: { story: "one more" } }]
    })
  );
  assert.equal(result.added, 0);
  assert.equal(result.skipped, 1);
  assert.match(result.errors[0], /already have 25 stories/);
});

/* ── the words a reader sees ────────────────────────────────────────────── */

test("the three statuses have plain names", () => {
  const { S } = load();
  assert.deepEqual(plain(S.STATUS_WORDS), {
    draft: "Draft",
    review: "Ready for review",
    done: "Done"
  });
});
