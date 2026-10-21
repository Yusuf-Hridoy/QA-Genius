/* Unit tests for the key-form guard in public/app.js, run by
 * `node --test tests/js`. app.js is a browser IIFE, so it is evaluated
 * against the smallest fake document that lets it reach its own exports;
 * nothing here touches the DOM work, only the rule that decides whether
 * what is in the box can be an API key at all. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(here, "..", "..", "public", "app.js"), "utf8");

function load() {
  const node = () => ({
    addEventListener() {},
    appendChild() {},
    setAttribute() {},
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    style: {},
    focus() {},
  });
  const sandbox = {
    document: {
      readyState: "complete",
      body: node(),
      documentElement: node(),
      addEventListener() {},
      getElementById: () => null,
      querySelector: () => null,
      querySelectorAll: () => [],
      createElement: node,
    },
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    location: { search: "", pathname: "/" },
    addEventListener() {},
    setTimeout,
    clearTimeout,
    URLSearchParams,
    JSON,
    Date,
    Math,
    String,
    Object,
    Array,
    Promise,
    console,
  };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox);
  return sandbox.window.QAG;
}

const QAG = load();

test("a plain key is accepted", () => {
  assert.equal(QAG.looksLikeKey("AIzaSyA-1234567890abcdefGHIJ"), true);
  assert.equal(QAG.looksLikeKey("  gsk_abc123  "), true);
});

test("an email address is refused", () => {
  assert.equal(QAG.looksLikeKey("name@example.com"), false);
});

test("anything with a space in it is refused", () => {
  assert.equal(QAG.looksLikeKey("my secret password"), false);
  assert.equal(QAG.looksLikeKey("abc\tdef"), false);
});

test("an empty box is refused", () => {
  assert.equal(QAG.looksLikeKey(""), false);
  assert.equal(QAG.looksLikeKey("   "), false);
  assert.equal(QAG.looksLikeKey(null), false);
});

test("the message says what went wrong in plain words", () => {
  assert.equal(
    QAG.NOT_A_KEY,
    "This looks like an email or password, not an API key.",
  );
});
