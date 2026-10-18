/* Unit tests for public/plain_words.js, run by `node --test tests/js`.
 * The file is a browser IIFE that builds DOM nodes, so the fake below is a
 * small element and document rather than a real DOM. What is tested is the
 * behaviour a keyboard user depends on: one button per word, aria-expanded
 * tracking the panel, and Esc closing it. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(
  join(here, "..", "..", "public", "plain_words.js"),
  "utf8",
);

/** The slice of an element the module actually uses. */
function makeElement(tag) {
  return {
    tagName: String(tag).toUpperCase(),
    className: "",
    textContent: "",
    id: "",
    hidden: false,
    type: "",
    childNodes: [],
    attrs: {},
    handlers: {},
    get firstChild() {
      return this.childNodes[0] || null;
    },
    appendChild(node) {
      this.childNodes.push(node);
      return node;
    },
    setAttribute(name, value) {
      this.attrs[name] = String(value);
    },
    getAttribute(name) {
      return name in this.attrs ? this.attrs[name] : null;
    },
    hasAttribute(name) {
      return name in this.attrs;
    },
    addEventListener(name, handler) {
      this.handlers[name] = handler;
    },
    contains() {
      return false;
    },
    classList: {
      add() {},
      remove() {},
    },
  };
}

function load(marks) {
  const docHandlers = {};
  const body = makeElement("body");
  const document = {
    readyState: "complete",
    body,
    createElement: makeElement,
    querySelectorAll: () => marks,
    /* The module asks the document whether a word already has its button. */
    querySelector: (selector) => {
      const key = /\[data-explain="([^"]+)"\]/.exec(selector)[1];
      return (
        marks.find(
          (node) =>
            node.attrs["data-explain"] === key && "data-built" in node.attrs,
        ) || null
      );
    },
    addEventListener: (name, handler) => {
      docHandlers[name] = handler;
    },
  };
  const sandbox = { document };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox);
  return { words: sandbox.QAGWords, docHandlers };
}

function mark(key) {
  const node = makeElement("span");
  node.attrs["data-explain"] = key;
  return node;
}

test("a mark becomes a button and a panel", () => {
  const boundary = mark("boundary");
  load([boundary]);
  const [button, panel] = boundary.childNodes;
  assert.equal(button.tagName, "BUTTON");
  assert.equal(button.type, "button");
  assert.equal(button.textContent, "ⓘ");
  assert.equal(button.getAttribute("aria-expanded"), "false");
  assert.equal(panel.hidden, true);
  assert.equal(button.getAttribute("aria-controls"), panel.id);
});

test("the button names the word it explains", () => {
  const invest = mark("invest");
  load([invest]);
  const label = invest.childNodes[0].getAttribute("aria-label");
  assert.equal(label, "What's this? INVEST");
});

test("the panel says what the word means", () => {
  const boundary = mark("boundary");
  load([boundary]);
  const text = boundary.childNodes[1].childNodes
    .map((node) => node.textContent)
    .join("");
  assert.match(text, /just under and just over/);
});

test("a word is explained once per page", () => {
  const first = mark("boundary");
  const second = mark("boundary");
  load([first, second]);
  assert.equal(first.childNodes.length, 2);
  assert.equal(second.childNodes.length, 0);
});

test("a word nobody wrote a note for is left alone", () => {
  const unknown = mark("quantum-testing");
  load([unknown]);
  assert.equal(unknown.childNodes.length, 0);
});

test("clicking opens the panel and clicking again closes it", () => {
  const boundary = mark("boundary");
  load([boundary]);
  const [button, panel] = boundary.childNodes;
  const click = () =>
    button.handlers.click({ preventDefault() {}, stopPropagation() {} });

  click();
  assert.equal(panel.hidden, false);
  assert.equal(button.getAttribute("aria-expanded"), "true");

  click();
  assert.equal(panel.hidden, true);
  assert.equal(button.getAttribute("aria-expanded"), "false");
});

test("opening one panel closes the one already open", () => {
  const boundary = mark("boundary");
  const invest = mark("invest");
  load([boundary, invest]);
  const open = (node) =>
    node.childNodes[0].handlers.click({
      preventDefault() {},
      stopPropagation() {},
    });

  open(boundary);
  open(invest);
  assert.equal(boundary.childNodes[1].hidden, true);
  assert.equal(invest.childNodes[1].hidden, false);
});

test("Escape closes the open panel", () => {
  const boundary = mark("boundary");
  const { docHandlers } = load([boundary]);
  const [button, panel] = boundary.childNodes;
  button.handlers.click({ preventDefault() {}, stopPropagation() {} });

  docHandlers.keydown({ key: "Escape" });
  assert.equal(panel.hidden, true);
  assert.equal(button.getAttribute("aria-expanded"), "false");
});

test("every word has a term and a sentence", () => {
  const { words } = load([]);
  const entries = Object.keys(words.words);
  assert.ok(entries.length >= 8);
  for (const key of entries) {
    const word = words.words[key];
    assert.ok(word.term.length > 2, key);
    assert.ok(word.text.length > 30, key);
    assert.ok(word.text.endsWith("."), key);
  }
});
