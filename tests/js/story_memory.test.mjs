/* The story page puts back what you were last looking at, run by
 * `node --test tests/js`. A reader who came back from the test-cases desk
 * found an empty box and had to spend a key again to see the same answer.
 * public/requirements_flow.js is a browser IIFE, so it runs here against a
 * fake document small enough to read.
 *
 * The saved cards travel with the story now rather than with the tab, so
 * run_state.js and story_store.js are loaded beside it: "Start a new story"
 * has to really make one, and the old story has to keep every word. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const read = (name) =>
  readFileSync(join(here, "..", "..", "public", name), "utf8");
const source = read("requirements_flow.js");
const runState = read("run_state.js");
const storyStore = read("story_store.js");

/** A box the page writes HTML into. */
const box = (html = "") => ({ innerHTML: html, focus() {} });

/** An input or select the page reads and writes. */
const input = (value = "") => ({ value, focus() {} });

function load(run, view, extras = {}) {
  const session = {};
  const local = {};
  const saved = view === undefined ? run : { ...run, story_view: view };
  if (saved !== undefined) session["qag.run"] = JSON.stringify(saved);

  const fields = {
    user_story: input(),
    story_type: input(),
    context: input(),
  };
  const nodes = {
    "story-form": { id: "story-form" },
    "story-output": box(),
    "duel-output": box(),
    "story-user-story": fields.user_story,
    ...extras,
  };
  const actions = { children: [], appendChild(node) { this.children.push(node); } };

  const sandbox = {
    document: {
      addEventListener: () => {},
      getElementById: (id) => nodes[id] || null,
      querySelector: (selector) => {
        if (selector === "#story-form") return {};
        if (selector === "#story-form .form-actions") return actions;
        const named = /#story-form \[name="(\w+)"\]/.exec(selector);
        if (named) return fields[named[1]] || null;
        return null;
      },
      querySelectorAll: () => [],
      createElement: (tag) => ({
        tagName: tag,
        className: "",
        textContent: "",
        classList: { add() {}, remove() {}, toggle() {} },
        addEventListener() {},
        setAttribute() {},
        appendChild() {},
      }),
      body: { appendChild() {} },
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
    localStorage: {
      getItem: (key) => (key in local ? local[key] : null),
      setItem: (key, value) => {
        local[key] = String(value);
      },
      removeItem: (key) => {
        delete local[key];
      },
    },
    dispatchEvent: () => true,
    addEventListener: () => {},
    CustomEvent: class {
      constructor(type) {
        this.type = type;
      }
    },
    setTimeout: () => 1,
    clearTimeout: () => {},
    JSON,
    Object,
    Array,
    Math,
    Date,
    Boolean,
    String,
    isNaN,
  };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(runState, sandbox);
  vm.runInContext(storyStore, sandbox);
  vm.runInContext(source, sandbox);
  return {
    flow: sandbox.QAGFlow,
    stories: sandbox.QAGStories,
    run: () => JSON.parse(session["qag.run"] || "{}"),
    fields,
    nodes,
    actions,
    session,
  };
}

const STORY = "As a shopper, I want to sign in so that I can buy.";
const RUN = { story: STORY, story_type: "Technical story", context: "Login page" };

test("the story, its type and the context come back", () => {
  const { flow, fields } = load(RUN, undefined);
  flow.restoreStoryPage();
  assert.equal(fields.user_story.value, STORY);
  assert.equal(fields.story_type.value, "Technical story");
  assert.equal(fields.context.value, "Login page");
});

test("the last result comes back with them", () => {
  const view = { story: STORY, result: "<p>the card</p>", duel: "<p>two readers</p>" };
  const { flow, nodes } = load(RUN, view);
  flow.restoreStoryPage();
  assert.equal(nodes["story-output"].innerHTML, "<p>the card</p>");
  assert.equal(nodes["duel-output"].innerHTML, "<p>two readers</p>");
});

test("a card saved under another story is never shown", () => {
  const view = { story: "A different story.", result: "<p>not yours</p>" };
  const { flow, nodes } = load(RUN, view);
  flow.restoreStoryPage();
  assert.equal(nodes["story-output"].innerHTML, "");
});

test("an empty run leaves the page empty and offers no link", () => {
  const { flow, fields, actions } = load({}, undefined);
  flow.restoreStoryPage();
  assert.equal(fields.user_story.value, "");
  assert.equal(actions.children.length, 0);
});

test("a remembered story offers Start a new story", () => {
  const { flow, actions } = load(RUN, undefined);
  flow.restoreStoryPage();
  assert.equal(actions.children.length, 1);
  assert.equal(actions.children[0].textContent, "Start a new story");
});

test("Start a new story makes a second story and leaves the first alone", () => {
  const view = { story: STORY, result: "<p>the card</p>" };
  const { flow, stories, fields, nodes, run } = load(
    { ...RUN, story_analysis: { ambiguity_score: 20 }, criteria: [{ id: "AC-1" }] },
    view,
  );
  // The run on screen becomes this tab's first saved story.
  const first = stories.create({ run: run() }).story;
  stories.open(first.id);
  flow.restoreStoryPage();

  flow.startFreshStory();

  // The page in front of the reader is empty and ready.
  assert.equal(fields.user_story.value, "");
  assert.equal(fields.context.value, "");
  assert.equal(fields.story_type.value, "User story");
  assert.equal(nodes["story-output"].innerHTML, "");

  // The new story is this tab's, and it is empty.
  assert.equal(stories.count(), 2);
  const now = stories.active();
  assert.notEqual(now.id, first.id);
  assert.equal(now.run.story, undefined);
  assert.equal(run().story, undefined);
  assert.equal(run()._story_id, now.id);

  // Every word of the old one is still there, under its own id.
  const old = stories.get(first.id);
  assert.equal(old.run.story, STORY);
  assert.equal(old.run.context, "Login page");
  assert.deepEqual(old.run.criteria, [{ id: "AC-1" }]);
  assert.equal(old.run.story_view.result, "<p>the card</p>");
});
