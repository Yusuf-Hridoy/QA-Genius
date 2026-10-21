/* The story page puts back what you were last looking at, run by
 * `node --test tests/js`. A reader who came back from the test-cases desk
 * found an empty box and had to spend a key again to see the same answer.
 * public/requirements_flow.js is a browser IIFE, so it runs here against a
 * fake document small enough to read. */
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

/** A box the page writes HTML into. */
const box = (html = "") => ({ innerHTML: html, focus() {} });

/** An input or select the page reads and writes. */
const input = (value = "") => ({ value, focus() {} });

function load(run, view, extras = {}) {
  const store = {};
  if (run !== undefined) store["qag.run"] = JSON.stringify(run);
  if (view !== undefined) store["qag.story_view"] = JSON.stringify(view);

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
        addEventListener() {},
        setAttribute() {},
        appendChild() {},
      }),
    },
    sessionStorage: {
      getItem: (key) => (key in store ? store[key] : null),
      setItem: (key, value) => {
        store[key] = String(value);
      },
      removeItem: (key) => {
        delete store[key];
      },
    },
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
  vm.runInContext(source, sandbox);
  return { flow: sandbox.QAGFlow, fields, nodes, actions, store };
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

test("Start a new story clears the fields, the cards and the run", () => {
  const view = { story: STORY, result: "<p>the card</p>" };
  const { flow, fields, nodes, store } = load(
    { ...RUN, story_analysis: { ambiguity_score: 20 }, criteria: [{ id: "AC-1" }] },
    view,
  );
  flow.restoreStoryPage();
  flow.startFreshStory();
  assert.equal(fields.user_story.value, "");
  assert.equal(fields.context.value, "");
  assert.equal(fields.story_type.value, "User story");
  assert.equal(nodes["story-output"].innerHTML, "");
  assert.equal(store["qag.story_view"], undefined);
  const run = JSON.parse(store["qag.run"]);
  assert.equal(run.story, undefined);
  assert.equal(run.story_analysis, undefined);
  // The work the other desks did is theirs to keep or rebuild.
  assert.deepEqual(run.criteria, [{ id: "AC-1" }]);
});
