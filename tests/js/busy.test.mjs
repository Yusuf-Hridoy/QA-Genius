/* Unit tests for public/busy.js, run by `node --test tests/js`.
 * The module is a browser IIFE over a handful of DOM calls, so the fake below
 * is the smallest element and document it actually uses. What is tested is
 * what a user sees: the button says it is working, it cannot be pressed
 * twice, the line appears under the card, and everything goes back on stop. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(here, "..", "..", "public", "busy.js"), "utf8");

function makeElement(tag, className) {
  return {
    tagName: String(tag).toUpperCase(),
    className: className || "",
    textContent: "",
    id: "",
    disabled: false,
    style: {},
    attrs: {},
    childNodes: [],
    parentNode: null,
    ownerDocument: null,
    get nextSibling() {
      if (!this.parentNode) return null;
      const at = this.parentNode.childNodes.indexOf(this);
      return this.parentNode.childNodes[at + 1] || null;
    },
    appendChild(node) {
      node.parentNode = this;
      node.ownerDocument = this.ownerDocument;
      this.childNodes.push(node);
      return node;
    },
    insertBefore(node, before) {
      const at = before ? this.childNodes.indexOf(before) : -1;
      node.parentNode = this;
      node.ownerDocument = this.ownerDocument;
      if (at === -1) this.childNodes.push(node);
      else this.childNodes.splice(at, 0, node);
      return node;
    },
    removeChild(node) {
      const at = this.childNodes.indexOf(node);
      if (at !== -1) this.childNodes.splice(at, 1);
      node.parentNode = null;
      return node;
    },
    setAttribute(name, value) {
      this.attrs[name] = String(value);
    },
    getAttribute(name) {
      return name in this.attrs ? this.attrs[name] : null;
    },
    removeAttribute(name) {
      delete this.attrs[name];
    },
    /* The module asks for ".btn-label" and nothing else. */
    querySelector(selector) {
      if (selector !== ".btn-label") return null;
      return this.childNodes.find((one) => one.className === "btn-label") || null;
    },
    /* Walk up the tree for a class, the way Element.closest does. */
    closest(selector) {
      const wanted = selector.replace(".", "");
      let node = this;
      while (node) {
        if (String(node.className).split(" ").includes(wanted)) return node;
        node = node.parentNode;
      }
      return null;
    },
    getBoundingClientRect() {
      return { width: 142 };
    },
  };
}

/** A card with a button in it, hung under a page, as every desk draws it. */
function load({ label } = {}) {
  const page = makeElement("div", "main");
  const doc = {
    createElement: (tag) => {
      const node = makeElement(tag);
      node.ownerDocument = doc;
      return node;
    },
    getElementById: (id) => {
      const find = (node) => {
        if (node.id === id) return node;
        for (const child of node.childNodes) {
          const found = find(child);
          if (found) return found;
        }
        return null;
      };
      return find(page);
    },
  };
  page.ownerDocument = doc;
  const card = makeElement("div", "card");
  page.appendChild(card);
  const button = makeElement("button", "btn btn-primary");
  button.textContent = "Find risks for this";
  card.appendChild(button);
  if (label) {
    const inner = makeElement("span", "btn-label");
    inner.textContent = "Find risks";
    button.textContent = "";
    button.appendChild(inner);
  }

  const sandbox = { document: doc, Math, String };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox);
  return { QAGBusy: sandbox.QAGBusy, page, card, button, doc };
}

const noteOf = (doc) => doc.getElementById("qag-busy-note");

test("start says the button is working and stop takes it back", () => {
  const { QAGBusy, button } = load();
  assert.equal(QAGBusy.start(button, "Finding risks…"), true);
  assert.equal(button.getAttribute("aria-busy"), "true");
  assert.equal(button.disabled, true);
  assert.equal(button.textContent, "Finding risks…");
  assert.equal(button.style.minWidth, "142px");

  QAGBusy.stop(button);
  assert.equal(button.getAttribute("aria-busy"), null);
  assert.equal(button.disabled, false);
  assert.equal(button.textContent, "Find risks for this");
  assert.equal(button.style.minWidth, "");
});

test("the label inside a .btn-label span is the one that changes", () => {
  const { QAGBusy, button } = load({ label: true });
  QAGBusy.start(button, "Writing tests…");
  assert.equal(button.querySelector(".btn-label").textContent, "Writing tests…");
  QAGBusy.stop(button);
  assert.equal(button.querySelector(".btn-label").textContent, "Find risks");
});

test("a second start on a working button does nothing", () => {
  const { QAGBusy, button } = load();
  QAGBusy.start(button, "Finding risks…");
  assert.equal(QAGBusy.start(button, "Something else…"), false);
  assert.equal(button.textContent, "Finding risks…");
  // One stop is still enough to put it back.
  QAGBusy.stop(button);
  assert.equal(button.textContent, "Find risks for this");
  assert.equal(QAGBusy.working().length, 0);
});

test("the button takes its own data-busy-label when none is passed", () => {
  const { QAGBusy, button } = load();
  button.setAttribute("data-busy-label", "Thinking…");
  QAGBusy.start(button);
  assert.equal(button.textContent, "Thinking…");
});

test("the calm line appears under the card and goes with the last button", () => {
  const { QAGBusy, button, card, page, doc } = load();
  const second = makeElement("button", "btn");
  second.textContent = "Find risks";
  card.appendChild(second);

  QAGBusy.start(button, "Finding risks…");
  const note = noteOf(doc);
  assert.ok(note, "no line under the card");
  assert.match(note.textContent, /20–40 seconds/);
  assert.equal(note.getAttribute("role"), "status");
  assert.equal(page.childNodes.indexOf(note), page.childNodes.indexOf(card) + 1);

  // A second button working is still one piece of work and one line.
  QAGBusy.start(second, "Finding risks…");
  assert.equal(page.childNodes.filter((one) => one.id === "qag-busy-note").length, 1);
  QAGBusy.stop(button);
  assert.ok(noteOf(doc), "the line left while work was still running");
  QAGBusy.stop(second);
  assert.equal(noteOf(doc), null);
});

test("stopAll puts back every button a click made busy", () => {
  const { QAGBusy, button, card, doc } = load();
  const second = makeElement("button", "btn");
  second.textContent = "Find risks";
  card.appendChild(second);

  QAGBusy.start(button, "Finding risks…");
  QAGBusy.start(second, "Finding risks…");
  assert.equal(QAGBusy.working().length, 2);
  QAGBusy.stopAll();
  assert.equal(QAGBusy.working().length, 0);
  assert.equal(button.disabled, false);
  assert.equal(second.disabled, false);
  assert.equal(button.getAttribute("aria-busy"), null);
  assert.equal(noteOf(doc), null);
});

test("stop on a button that never started is harmless", () => {
  const { QAGBusy, button } = load();
  QAGBusy.stop(button);
  QAGBusy.stop(null);
  assert.equal(button.disabled, false);
  assert.equal(QAGBusy.isBusy(button), false);
});

test("a button the page had switched off stays off afterwards", () => {
  const { QAGBusy, button } = load();
  button.disabled = true;
  QAGBusy.start(button, "Writing…");
  assert.equal(button.disabled, true);
  QAGBusy.stop(button);
  assert.equal(button.disabled, true, "a validation-disabled button came back on");
});
