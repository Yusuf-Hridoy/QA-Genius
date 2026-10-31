/* Two tabs, one browser: the test that would have caught the lost work.
 *
 * A real browser test opened CART-204 in one tab and CHK-101 in another and
 * found CART-204's words inside CHK-101 a minute later. The cause was one
 * shared "active_id" in localStorage: every tab's auto-save wrote into
 * whichever story was opened last, anywhere.
 *
 * Each tab here is its own sandbox with its own sessionStorage, and they
 * share one localStorage, which is exactly what two tabs of one browser
 * have. Run by `node --test tests/js`. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const read = (name) =>
  readFileSync(join(here, "..", "..", "public", name), "utf8");
const runState = read("run_state.js");
const storyStore = read("story_store.js");
const storiesUi = read("stories_ui.js");

/** One browser: the shared localStorage every tab of it can see. */
function browser() {
  return {};
}

/** One tab of that browser, with a sessionStorage nobody else can reach. */
function tab(local, options = {}) {
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
    confirm: () => options.confirm !== false,
    location: { href: "", reload() {} },
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
    sandbox,
    session,
    /* What the browser does to every other tab after a write. */
    storageEvent: () =>
      sandbox.dispatchEvent({ type: "storage", key: sandbox.QAGStories.KEY }),
    tick: () => timers.forEach((fn) => fn && fn()),
  };
}

const CART = "As a shopper, I want my cart kept so I can finish later.";
const CHECKOUT = "As a shopper, I want to pay with a saved card.";

/* ── one tab, one story ─────────────────────────────────────────────────── */

test("a tab saves only into the story it has open", () => {
  const local = browser();
  const a = tab(local);

  const cart = a.S.create({ run: { story: CART }, label: "CART-204" }).story;
  const checkout = a.S.create({ run: { story: CHECKOUT }, label: "CHK-101" }).story;

  // Tab A goes back to CART-204. Tab B opens CHK-101 and stays there.
  a.S.open(cart.id);
  const b = tab(local);
  b.S.open(checkout.id);

  // Tab A types. Its save must land on CART-204 and nowhere else.
  a.Run.write({ ...a.Run.read(), story: CART + " Even after a reload." });
  assert.equal(a.S.saveRun(a.Run.read()), "");

  assert.match(a.S.get(cart.id).run.story, /Even after a reload/);
  assert.equal(a.S.get(checkout.id).run.story, CHECKOUT);
  assert.equal(a.S.get(checkout.id).label, "CHK-101");
});

test("the two tabs disagree about which story is open, and both are right", () => {
  const local = browser();
  const a = tab(local);
  const first = a.S.create({ run: { story: CART }, label: "CART-204" }).story;
  const second = a.S.create({ run: { story: CHECKOUT }, label: "CHK-101" }).story;
  a.S.open(first.id);
  const b = tab(local);
  b.S.open(second.id);

  assert.equal(a.S.active().id, first.id);
  assert.equal(b.S.active().id, second.id);
  assert.equal(a.S.tabStory(), first.id);
  assert.equal(b.S.tabStory(), second.id);
});

test("a save into a story another tab deleted is refused", () => {
  const local = browser();
  const a = tab(local);
  const story = a.S.create({ run: { story: CART }, label: "CART-204" }).story;
  a.S.open(story.id);

  const b = tab(local);
  assert.equal(b.S.remove(story.id), "");

  assert.equal(a.S.saveStory(story.id, { story: "typed after the delete" }), "deleted");
  assert.equal(a.S.elsewhere(), "deleted");
  assert.deepEqual(a.S.list(), []);
});

/* ── switching, creating and deleting ───────────────────────────────────── */

test("a new story leaves the one that was open untouched", () => {
  const local = browser();
  const a = tab(local);
  const first = a.S.create({
    run: { story: CART, criteria: [{ id: "AC-1", text: "Keep the cart." }] },
    label: "CART-204",
  }).story;
  a.S.open(first.id);

  const made = a.S.create({ run: {} });
  assert.equal(made.error, "");
  assert.notEqual(made.story.id, first.id);
  assert.equal(a.S.count(), 2);
  assert.equal(a.S.tabStory(), made.story.id);

  const kept = a.S.get(first.id);
  assert.equal(kept.run.story, CART);
  assert.deepEqual(kept.run.criteria, [{ id: "AC-1", text: "Keep the cart." }]);
  assert.equal(kept.label, "CART-204");
});

test("deleting the open story leaves nothing to save into", () => {
  const local = browser();
  const a = tab(local);
  const story = a.S.create({ run: { story: CART } }).story;
  a.S.open(story.id);
  a.S.listen();

  a.S.remove(story.id);
  assert.equal(a.S.tabStory(), "");
  assert.equal(a.Run.read().story, undefined);

  // Whatever the page does next, there is nowhere for it to land.
  a.Run.write({ story: "typed on a deleted story" });
  a.tick();
  assert.deepEqual(a.S.list(), []);
});

test("after a delete the tab does not pick up the next story along", () => {
  // Found in a browser: delete the open story, land on the Story desk, and
  // the page quietly opened the other story and typed over it 600ms later.
  const local = browser();
  const a = tab(local);
  const cart = a.S.create({ run: { story: CART }, label: "CART-204" }).story;
  const checkout = a.S.create({ run: { story: CHECKOUT }, label: "CHK-101" }).story;
  a.S.open(cart.id);
  a.S.remove(cart.id);

  // A page load on the same tab: nothing is adopted and nothing is saved.
  assert.equal(a.S.adopt(), null);
  assert.equal(a.S.tabStory(), "");
  a.S.listen();
  a.Run.write({ story: "typed after the delete" });
  a.tick();
  assert.equal(a.S.get(checkout.id).run.story, CHECKOUT);
  assert.equal(a.S.count(), 1);

  // Starting a story again clears it, and the tab works normally after.
  const fresh = a.S.create({ run: {} }).story;
  assert.equal(a.S.storyWasDeleted(), false);
  assert.equal(a.S.saveStory(fresh.id, { story: "a new one" }), "");
});

test("switching stories brings the other one's run with it", () => {
  const local = browser();
  const a = tab(local);
  const first = a.S.create({ run: { story: CART } }).story;
  const second = a.S.create({ run: { story: CHECKOUT } }).story;
  a.S.open(first.id);
  assert.equal(a.Run.read().story, CART);
  a.S.open(second.id);
  assert.equal(a.Run.read().story, CHECKOUT);
  assert.equal(a.Run.read()._story_id, second.id);
});

/* ── no lost updates ────────────────────────────────────────────────────── */

test("a tab holding an older revision cannot save over a newer one", () => {
  const local = browser();
  const a = tab(local);
  const story = a.S.create({ run: { story: CART } }).story;
  a.S.open(story.id);
  const mine = a.Run.read();

  // Another tab saves the same story twice while this one sits still.
  const b = tab(local);
  b.S.open(story.id);
  b.S.saveStory(story.id, { ...b.Run.read(), story: CART + " B was here." });

  assert.equal(a.S.saveStory(story.id, { ...mine, story: "A was here." }), "stale");
  assert.match(a.S.get(story.id).run.story, /B was here/);
});

test("keeping mine writes over the newer copy, and only when asked", () => {
  const local = browser();
  const a = tab(local);
  const story = a.S.create({ run: { story: CART } }).story;
  a.S.open(story.id);
  const mine = { ...a.Run.read(), story: "A insists." };

  const b = tab(local);
  b.S.open(story.id);
  b.S.saveStory(story.id, { ...b.Run.read(), story: "B was here." });

  assert.equal(a.S.forceSave(story.id, mine), "");
  assert.equal(a.S.get(story.id).run.story, "A insists.");
});

test("a revision goes up on every real write and never on a reopen", () => {
  const local = browser();
  const a = tab(local);
  const story = a.S.create({ run: { story: CART } }).story;
  assert.equal(story.revision, 1);
  a.S.saveStory(story.id, { ...a.S.bound(story), story: CART + " Edited." });
  assert.equal(a.S.get(story.id).revision, 2);
  a.S.open(story.id);
  assert.equal(a.S.get(story.id).revision, 2);
});

test("the storage event tells this tab what the other one did", () => {
  const local = browser();
  const a = tab(local);
  const story = a.S.create({ run: { story: CART } }).story;
  a.S.open(story.id);
  const seen = [];
  a.sandbox.addEventListener(a.S.ELSEWHERE_EVENT, (event) => {
    seen.push(event.detail.state);
  });
  a.S.watch();

  const b = tab(local);
  b.S.open(story.id);
  b.S.saveStory(story.id, { ...b.Run.read(), story: "B was here." });
  a.storageEvent();
  assert.deepEqual(seen, ["changed"]);

  b.S.remove(story.id);
  a.storageEvent();
  assert.deepEqual(seen, ["changed", "deleted"]);
});

/* ── ids and labels ─────────────────────────────────────────────────────── */

test("opening a story moves Last opened and leaves Last edited", () => {
  const local = browser();
  const a = tab(local);
  const story = a.S.create({ run: { story: CART } }).story;
  const edited = a.S.get(story.id).updated_at;
  a.S.open(story.id);
  // The run written on open is the story's own, so there is nothing to save.
  assert.equal(a.S.saveRun(a.Run.read()), "same");
  assert.equal(a.S.get(story.id).updated_at, edited);
  assert.ok(a.S.get(story.id).opened_at >= edited);
});

test("an id another story already uses is never taken twice", () => {
  const local = browser();
  const a = tab(local);
  a.S.create({ run: { story: CART }, label: "CHK-101" });
  const clash = a.S.create({ run: { story: CHECKOUT }, label: "CHK-101" });
  assert.equal(clash.error, "duplicate-label");
  assert.equal(a.S.takenMessage("CHK-101"), "CHK-101 is already used by another story.");

  // Auto-save keeps the id the story already had rather than stealing one.
  const second = a.S.create({ run: { story: CHECKOUT }, label: "CART-204" }).story;
  a.S.saveStory(second.id, { story: CHECKOUT + " x", story_label: "CHK-101" });
  assert.equal(a.S.get(second.id).label, "CART-204");
});

test("an import that would make two of one id skips it and says so", () => {
  const local = browser();
  const a = tab(local);
  a.S.create({ run: { story: CART }, label: "CHK-101" });
  const result = a.S.importAll(
    JSON.stringify({
      version: 1,
      stories: [{ id: "s_other", label: "CHK-101", run: { story: CHECKOUT } }],
    })
  );
  assert.equal(result.added, 0);
  assert.equal(result.skipped, 1);
  assert.match(result.errors[0], /CHK-101 is already used by another story/);
});

/* ── a brand new tab picks a story up ───────────────────────────────────── */

test("a new tab opens the story last opened anywhere", () => {
  const local = browser();
  const a = tab(local);
  const first = a.S.create({ run: { story: CART } }).story;
  const second = a.S.create({ run: { story: CHECKOUT } }).story;
  a.S.open(second.id);

  const fresh = tab(local);
  assert.equal(fresh.S.tabStory(), "");
  assert.equal(fresh.S.adopt().id, second.id);
  assert.equal(fresh.Run.read().story, CHECKOUT);
  assert.notEqual(second.id, first.id);
});

test("a tab whose run names a story keeps that story, whatever other tabs did", () => {
  const local = browser();
  const a = tab(local);
  const first = a.S.create({ run: { story: CART } }).story;
  const second = a.S.create({ run: { story: CHECKOUT } }).story;

  const b = tab(local);
  b.Run.write({ story: CART, _story_id: first.id });
  b.S.adopt();
  assert.equal(b.S.tabStory(), first.id);
  assert.equal(b.Run.read().story, CART);
  assert.notEqual(b.S.tabStory(), second.id);
});

/* ── the words the page shows about all this ────────────────────────────── */

test("the two bars say what happened in plain words", () => {
  const local = browser();
  const one = tab(local);
  const nodes = {};
  const made = [];
  const element = (tagName) => ({
    tagName,
    id: "",
    className: "",
    /* Setting textContent empties a node, which is how showBar clears the
     * bar before writing the next message into it. */
    _text: "",
    get textContent() {
      return this._text;
    },
    set textContent(value) {
      this._text = String(value);
      this.children = [];
    },
    hidden: false,
    children: [],
    classList: { add() {}, remove() {}, toggle() {} },
    setAttribute() {},
    addEventListener(name, fn) {
      this[name] = fn;
    },
    appendChild(node) {
      this.children.push(node);
      if (node.id) nodes[node.id] = node;
    },
    insertBefore(node) {
      this.children.unshift(node);
      if (node.id) nodes[node.id] = node;
    },
    querySelector: () => null,
    querySelectorAll: () => [],
    get firstChild() {
      return this.children[0] || null;
    },
  });
  const content = element("main");
  content.className = "content";
  one.sandbox.document = {
    addEventListener() {},
    getElementById: (id) => nodes[id] || null,
    querySelector: (selector) => (selector === ".content" ? content : null),
    querySelectorAll: () => [],
    createElement: (tag) => {
      const node = element(tag);
      made.push(node);
      return node;
    },
  };
  vm.runInContext(storiesUi, one.sandbox);
  const ui = one.sandbox.QAGStoriesUI;

  // Nothing left in the browser: one sentence, one button.
  ui.deletedBar();
  const gone = nodes["story-bar"];
  assert.equal(gone.hidden, false);
  assert.equal(gone.children[0].textContent, ui.ALL_GONE_WORDS);
  assert.equal(ui.ALL_GONE_WORDS, "All stories deleted. Start a new one.");
  assert.equal(gone.children[1].children.length, 1);
  assert.equal(gone.children[1].children[0].textContent, "Start a new story");

  // One story deleted while others remain: there is another to open.
  one.S.create({ run: { story: CART }, label: "CART-204" });
  ui.deletedBar();
  const bar = nodes["story-bar"];
  assert.equal(bar.children[0].textContent, ui.DELETED_WORDS);
  assert.equal(
    ui.DELETED_WORDS,
    "This story was deleted. Start a new story or open another."
  );

  ui.changedBar();
  assert.equal(nodes["story-bar"].children[0].textContent, ui.CHANGED_WORDS);
  assert.equal(ui.CHANGED_WORDS, "This story changed in another tab.");
  // Reload is the main button; Keep mine is the one that asks first.
  const buttons = nodes["story-bar"].children[1].children;
  assert.equal(buttons[0].textContent, "Reload");
  assert.equal(buttons[1].textContent, "Keep mine");
});
