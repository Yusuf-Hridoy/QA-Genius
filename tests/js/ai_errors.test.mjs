/* One way to say "that did not work", on every desk.
 *
 * A browser test pressed Check story with the server down: the button went
 * back to normal and nothing appeared anywhere. It pressed it with a
 * refused key: "…failed (400): Error code: 400" landed in the result area
 * and replaced the saved result, after a reload as well.
 *
 * Run by `node --test tests/js`. The DOM here is the smallest one the
 * module actually touches. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const read = (name) => readFileSync(join(here, "..", "..", "public", name), "utf8");

/* ── the smallest DOM that answers the question ─────────────────────────── */

class Node {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase();
    this.children = [];
    this.parentNode = null;
    this.attrs = {};
    this.text = "";
    this.handlers = {};
    this.className = "";
  }
  get classList() {
    const self = this;
    return {
      contains: (name) => String(self.className).split(/\s+/).indexOf(name) !== -1,
    };
  }
  setAttribute(name, value) {
    this.attrs[name] = String(value);
  }
  getAttribute(name) {
    return name in this.attrs ? this.attrs[name] : null;
  }
  set textContent(value) {
    this.text = String(value);
    this.children = [];
  }
  get textContent() {
    return this.children.length
      ? this.children.map((one) => one.textContent).join(" ")
      : this.text;
  }
  appendChild(child) {
    child.parentNode = this;
    this.children.push(child);
    return child;
  }
  insertBefore(child, before) {
    child.parentNode = this;
    const at = this.children.indexOf(before);
    if (at === -1) this.children.push(child);
    else this.children.splice(at, 0, child);
    return child;
  }
  removeChild(child) {
    const at = this.children.indexOf(child);
    if (at !== -1) this.children.splice(at, 1);
    child.parentNode = null;
    return child;
  }
  get nextSibling() {
    if (!this.parentNode) return null;
    const at = this.parentNode.children.indexOf(this);
    return this.parentNode.children[at + 1] || null;
  }
  addEventListener(name, fn) {
    this.handlers[name] = this.handlers[name] || [];
    this.handlers[name].push(fn);
  }
  fire(name, detail) {
    (this.handlers[name] || []).forEach((fn) => fn({ type: name, detail }));
  }
  click() {
    this.fire("click", {});
  }
  querySelector(selector) {
    if (selector !== "button[type=submit]") return null;
    return (
      this.all().find(
        (one) => one.tagName === "BUTTON" && one.getAttribute("type") === "submit"
      ) || null
    );
  }
  /** Every node under this one, this one included. */
  all() {
    return this.children.reduce((found, one) => found.concat(one.all()), [this]);
  }
  /** The words a reader sees, flattened. */
  words() {
    return this.all()
      .map((one) => one.text)
      .filter(Boolean)
      .join(" ");
  }
}

function load(options = {}) {
  const body = new Node("body");
  const document = {
    readyState: "complete",
    body: body,
    createElement: (tag) => new Node(tag),
    addEventListener: (name, fn) => body.addEventListener(name, fn),
    querySelectorAll: (selector) => {
      const want = selector.replace(".", "");
      return body.all().filter((one) => one.classList.contains(want));
    },
  };
  const sandbox = {
    JSON,
    Object,
    Array,
    String,
    Boolean,
    Number,
    document,
    QAG: { headerKeys: () => options.keys || [] },
  };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(read("ai_errors.js"), sandbox);
  return { E: sandbox.QAGAiError, body, document };
}

/** A form with a submit button inside an actions row, as the desks have. */
function desk(body, title) {
  const form = new Node("form");
  form.setAttribute("data-error-title", title);
  const card = form.appendChild(new Node("div"));
  const result = form.appendChild(new Node("div"));
  result.className = "result";
  result.textContent = "The result you already had";
  const row = card.appendChild(new Node("div"));
  row.className = "form-actions";
  const button = row.appendChild(new Node("button"));
  button.setAttribute("type", "submit");
  body.appendChild(form);
  return { form, button, row, result };
}

/* ── which failure it was ───────────────────────────────────────────────── */

test("a request that never came back is a network failure", () => {
  const { E } = load();
  assert.equal(E.kindOf(0), "network");
  assert.equal(E.kindOf(408), "network");
  assert.equal(E.kindOf(504), "network");
});

test("500 is our side, 429 is busy, 400 and 401 are the key", () => {
  const { E } = load();
  assert.equal(E.kindOf(500), "server");
  assert.equal(E.kindOf(502), "server");
  assert.equal(E.kindOf(429), "busy");
  assert.equal(E.kindOf(400), "key");
  assert.equal(E.kindOf(401), "key");
  assert.equal(E.kindOf(403), "key");
});

test("every failure has a sentence, and none of them has a code in it", () => {
  const { E } = load();
  const said = [
    E.words("network"),
    E.words("server"),
    E.words("busy"),
    E.words("key", "Gemini"),
  ];
  assert.equal(
    said[0],
    "We couldn't reach the server. Check your connection and try again."
  );
  assert.equal(said[1], "Something went wrong on our side. Try again in a minute.");
  assert.equal(said[2], "The AI is busy. Try again in a minute, or add another key.");
  assert.equal(
    said[3],
    "Your Gemini key was refused. Check it in Keys, or try your other key."
  );
  said.forEach((line) => {
    assert.ok(!/\d{3}/.test(line), line);
    assert.ok(line.indexOf("{") === -1, line);
  });
});

test("a refused key names the provider the key is for", () => {
  const { E } = load({ keys: [{ provider: "groq" }] });
  assert.equal(E.PROVIDER_NAMES.groq, "Groq");
  assert.match(E.words("key", "Groq"), /Your Groq key was refused/);
  assert.match(E.words("key", ""), /^Your key was refused/);
});

/* ── where the note goes ────────────────────────────────────────────────── */

test("the note lands under the button, and the old result stays put", () => {
  const { E, body } = load();
  const page = desk(body, "Could not check the story");
  E.show(page.button, { kind: "server" });

  const note = page.row.nextSibling;
  assert.ok(note, "no note after the button's row");
  assert.ok(note.classList.contains("note-bad"));
  assert.match(note.words(), /Could not check the story/);
  assert.match(note.words(), /Something went wrong on our side/);
  assert.equal(page.result.textContent, "The result you already had");
});

test("the title comes from the desk the button is on", () => {
  const { E, body } = load();
  const risks = desk(body, "Could not find risks");
  E.show(risks.button, { kind: "busy" });
  assert.match(risks.row.nextSibling.words(), /Could not find risks/);
  assert.equal(E.titleFor(risks.button), "Could not find risks");
});

test("every note carries Try again, and it runs the action again", () => {
  const { E, body } = load();
  const page = desk(body, "Could not write a test");
  let tried = 0;
  E.show(page.button, { kind: "network", retry: () => (tried += 1) });
  const again = page.row.nextSibling
    .all()
    .find((one) => one.classList.contains("ai-error-again"));
  assert.ok(again);
  assert.equal(again.text, "Try again");
  again.click();
  assert.equal(tried, 1);
  // Pressing it clears the note first, so there is never a stale red box.
  assert.equal(page.row.nextSibling, null);
});

test("a second failure replaces the first note rather than stacking", () => {
  const { E, body } = load();
  const page = desk(body, "Could not write test cases");
  E.show(page.button, { kind: "server" });
  E.show(page.button, { kind: "busy" });
  assert.match(page.row.nextSibling.words(), /The AI is busy/);
  assert.equal(page.row.nextSibling.nextSibling, null);
});

/* ── htmx ───────────────────────────────────────────────────────────────── */

const xhr = (status, headers = {}, text = "") => ({
  status,
  responseText: text,
  getResponseHeader: (name) => (name in headers ? headers[name] : null),
});

test("a 500 with no body still says something under the button", () => {
  const { E, body } = load();
  const page = desk(body, "Could not check the story");
  body.fire("htmx:responseError", { elt: page.form, xhr: xhr(500) });
  assert.match(page.row.nextSibling.words(), /Could not check the story/);
  assert.match(page.row.nextSibling.words(), /Something went wrong on our side/);
});

test("no network at all says so, in words about the connection", () => {
  const { E, body } = load();
  const page = desk(body, "Could not find risks");
  body.fire("htmx:sendError", { elt: page.form, xhr: xhr(0) });
  assert.match(page.row.nextSibling.words(), /couldn't reach the server/);
});

test("an error card from the server is never swapped into the result", () => {
  const { E, body } = load({ keys: [{ provider: "gemini" }] });
  const page = desk(body, "Could not check the story");
  const detail = {
    elt: page.form,
    shouldSwap: true,
    xhr: xhr(200, { "X-QAG-Error": "key" }, "<ul><li>Key 1 (Gemini) looked invalid</li></ul>"),
  };
  body.fire("htmx:beforeSwap", detail);

  assert.equal(detail.shouldSwap, false);
  assert.equal(page.result.textContent, "The result you already had");
  const said = page.row.nextSibling.words();
  assert.match(said, /Your Gemini key was refused/);
  assert.match(said, /Key 1 \(Gemini\) looked invalid/);
  assert.ok(said.indexOf("400") === -1, said);
});

test("a busy answer from the server says busy, not refused", () => {
  const { E, body } = load();
  const page = desk(body, "Could not write test cases");
  body.fire("htmx:beforeSwap", {
    elt: page.form,
    shouldSwap: true,
    xhr: xhr(200, { "X-QAG-Error": "busy" }, ""),
  });
  assert.match(page.row.nextSibling.words(), /The AI is busy/);
});

test("pressing the button again clears the note first", () => {
  const { E, body } = load();
  const page = desk(body, "Could not check the story");
  body.fire("htmx:responseError", { elt: page.form, xhr: xhr(500) });
  assert.ok(page.row.nextSibling);
  body.fire("htmx:beforeRequest", { elt: page.form });
  assert.equal(page.row.nextSibling, null);
});

/* ── fetch ──────────────────────────────────────────────────────────────── */

const response = (status, kind) => ({
  status,
  ok: status >= 200 && status < 300,
  headers: { get: (name) => (name === "X-QAG-Error" ? kind || null : null) },
});

test("a fetch desk gets the same words as an htmx one", () => {
  const { E, body } = load();
  const page = desk(body, "Could not suggest what to vary");
  E.fromFetch(page.button, response(500));
  assert.match(page.row.nextSibling.words(), /Could not suggest what to vary/);
  assert.match(page.row.nextSibling.words(), /Something went wrong on our side/);

  E.fromFetch(page.button, null);
  assert.match(page.row.nextSibling.words(), /couldn't reach the server/);

  E.fromFetch(page.button, response(200, "busy"));
  assert.match(page.row.nextSibling.words(), /The AI is busy/);
});
