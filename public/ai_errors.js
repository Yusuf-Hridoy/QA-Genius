/* QA-Genius v2: one way to say "that did not work", on every desk.
 *
 * A browser test pressed Check story with the server down and with a
 * refused key. The first did nothing at all - the button went back to
 * normal and no words appeared anywhere. The second printed
 * "…failed (400): Error code: 400" into the result area, which threw away
 * the result the reader already had, in storage as well as on screen.
 *
 * Both are the same mistake: an AI call that fails is handled by whichever
 * desk happened to make it. So every desk uses this instead.
 *
 *   - The note goes under the button that was pressed, never into the
 *     result area. Whatever was already there stays there.
 *   - Four sentences cover every failure: no network, our side broke, the
 *     key was refused, the AI is busy. No status codes, no JSON.
 *   - Every note carries a Try again button.
 *   - Nothing a failure produces is ever written into the run.
 *
 * Nothing here calls the network. It reads a response that already came
 * back (or did not) and puts words on the page. */
(function (global) {
  "use strict";

  /* The server says which of these it was in a header; a failure that
   * never reached a route is worked out from the status instead. */
  var HEADER = "X-QAG-Error";

  var SLOT_CLASS = "ai-error";

  /* Provider id -> the name a reader knows it by. Kept beside the server's
   * table in qagenius/providers.py; a name missing here only costs the
   * sentence its first two words. */
  var PROVIDER_NAMES = {
    gemini: "Gemini",
    groq: "Groq",
    openai: "OpenAI",
    xai: "Grok",
    mistral: "Mistral",
    anthropic: "Claude",
    openrouter: "OpenRouter"
  };

  /* What each desk could not do. The button says which desk it is on. */
  var DEFAULT_TITLE = "That did not work";

  function kindOf(status) {
    /* 0 is the browser saying the request never left, or never came back. */
    if (!status) return "network";
    if (status === 408 || status === 504) return "network";
    if (status === 429) return "busy";
    if (status >= 500) return "server";
    if (status === 401 || status === 403 || status === 400) return "key";
    return "server";
  }

  function words(kind, provider) {
    if (kind === "network") {
      return "We couldn't reach the server. Check your connection and try again.";
    }
    if (kind === "key") {
      var who = provider ? "Your " + provider + " key" : "Your key";
      return who + " was refused. Check it in Keys, or try your other key.";
    }
    if (kind === "busy") {
      return "The AI is busy. Try again in a minute, or add another key.";
    }
    if (kind === "model") {
      return (
        "The AI model isn't available right now. Your keys are fine — " +
        "QA-Genius needs a model update."
      );
    }
    if (kind === "output") {
      return (
        "No key could answer in the shape this desk needs. " +
        "Try again in a minute, or add another key."
      );
    }
    return "Something went wrong on our side. Try again in a minute.";
  }

  /* The provider of the first key the reader listed: the one a refused-key
   * message is almost always about, and the only one this side can know. */
  function firstProvider() {
    try {
      var keys = global.QAG && global.QAG.headerKeys ? global.QAG.headerKeys() : [];
      if (!keys.length) return "";
      return PROVIDER_NAMES[keys[0].provider] || "";
    } catch (e) {
      return "";
    }
  }

  /* The title this desk gives its failure, read off the button or anything
   * above it that names one. */
  function titleFor(node) {
    var at = node;
    while (at && at.getAttribute) {
      var said = at.getAttribute("data-error-title");
      if (said) return said;
      at = at.parentNode;
    }
    return DEFAULT_TITLE;
  }

  /* Where the note goes: directly after the row the button sits in, so it
   * is under the button and not somewhere else on the page. */
  function slotFor(button) {
    var row = button;
    while (row && row.parentNode && row.classList) {
      if (
        row.classList.contains("form-actions") ||
        row.classList.contains("btn-row") ||
        row.classList.contains("panel-actions")
      ) {
        break;
      }
      row = row.parentNode;
    }
    return row && row.parentNode ? row : button;
  }

  function existing(after) {
    var next = after.nextSibling;
    while (next) {
      if (next.classList && next.classList.contains(SLOT_CLASS)) return next;
      next = next.nextSibling;
    }
    return null;
  }

  function clear(button) {
    if (!button) return;
    var after = slotFor(button);
    var note = existing(after);
    if (note && note.parentNode) note.parentNode.removeChild(note);
  }

  /* Every note on the page. Pressing any AI button clears them first, so a
   * second try never leaves the first try's red box behind it. */
  function clearAll() {
    if (!global.document) return;
    var all = global.document.querySelectorAll("." + SLOT_CLASS);
    Array.prototype.forEach.call(all, function (node) {
      if (node.parentNode) node.parentNode.removeChild(node);
    });
  }

  function make(tag, className, text) {
    var node = global.document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  /* Show one failure under one button.
   *
   * `options.kind` and `options.provider` choose the sentence;
   * `options.notes` is the server's one line per key, which says which key
   * did what and never carries a code or a key. */
  function show(button, options) {
    if (!button || !global.document) return null;
    var opts = options || {};
    clear(button);
    var note = make("div", "note note-bad " + SLOT_CLASS);
    note.setAttribute("role", "alert");
    note.appendChild(make("p", "ai-error-title", opts.title || titleFor(button)));
    note.appendChild(make("p", null, words(opts.kind, opts.provider)));
    var lines = opts.notes || [];
    if (lines.length) {
      var list = make("ul", "checklist muted small");
      lines.forEach(function (line) {
        list.appendChild(make("li", null, String(line)));
      });
      note.appendChild(list);
    }
    var again = make("button", "btn btn-ghost ai-error-again", "Try again");
    again.setAttribute("type", "button");
    again.addEventListener("click", function () {
      clear(button);
      if (typeof opts.retry === "function") opts.retry();
      else button.click();
    });
    note.appendChild(again);
    var after = slotFor(button);
    if (after.parentNode) after.parentNode.insertBefore(note, after.nextSibling);
    else after.appendChild(note);
    return note;
  }

  /* The lines the server put under its own message, pulled out of the card
   * it sent. They are already plain words; nothing else in the card is
   * used, because the title and the sentence come from this side. */
  function notesIn(html) {
    var found = [];
    var text = String(html || "");
    var at = text.indexOf("<li>");
    while (at !== -1) {
      var end = text.indexOf("</li>", at);
      if (end === -1) break;
      found.push(unescapeHtml(text.slice(at + 4, end).trim()));
      at = text.indexOf("<li>", end);
    }
    return found;
  }

  function unescapeHtml(text) {
    return String(text)
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'")
      .replace(/&amp;/g, "&");
  }

  /* The button a request came from: the one pressed, or the form's submit. */
  function buttonFor(node) {
    if (!node) return null;
    if (node.tagName === "BUTTON" || node.tagName === "A") return node;
    if (node.tagName === "FORM") {
      return node.querySelector("button[type=submit]") || node;
    }
    return node;
  }

  /* ---------- htmx ---------- */

  /* An error card must never be swapped into the result area: that is the
   * whole of "the previous saved result stays on screen and in storage".
   * The page's own code only saves what it finds in the result area, so
   * keeping the card out of it keeps the failure out of the run. */
  function onBeforeSwap(event) {
    var detail = event.detail || {};
    var xhr = detail.xhr;
    if (!xhr || !xhr.getResponseHeader) return;
    var kind = xhr.getResponseHeader(HEADER);
    if (!kind) return;
    detail.shouldSwap = false;
    detail.isError = true;
    var button = buttonFor(detail.elt || detail.target);
    show(button, {
      kind: kind,
      provider: kind === "key" ? firstProvider() : "",
      notes: notesIn(xhr.responseText),
      title: titleFor(button)
    });
  }

  /* A 500, a timeout, or no network at all. htmx swaps nothing for these,
   * so without this the button simply went back to normal and said nothing. */
  function onFailed(event) {
    var detail = event.detail || {};
    var xhr = detail.xhr || {};
    /* A response that carried the header was already handled above. */
    if (xhr.getResponseHeader && xhr.getResponseHeader(HEADER)) return;
    var status = typeof xhr.status === "number" ? xhr.status : 0;
    var kind = event.type === "htmx:timeout" ? "network" : kindOf(status);
    var button = buttonFor(detail.elt || detail.target);
    show(button, {
      kind: kind,
      provider: kind === "key" ? firstProvider() : "",
      title: titleFor(button)
    });
  }

  /* ---------- fetch ---------- */

  /* For the desks that call fetch rather than htmx. `response` is null for
   * a network error or a timeout. */
  function fromFetch(button, response, retry) {
    var status = response && typeof response.status === "number" ? response.status : 0;
    var kind = response ? kindOf(status) : "network";
    if (response && response.headers && response.headers.get) {
      kind = response.headers.get(HEADER) || kind;
    }
    return show(button, {
      kind: kind,
      provider: kind === "key" ? firstProvider() : "",
      title: titleFor(button),
      retry: retry
    });
  }

  function bind() {
    if (!global.document || !global.document.body) return;
    var body = global.document.body;
    body.addEventListener("htmx:beforeSwap", onBeforeSwap);
    ["htmx:responseError", "htmx:sendError", "htmx:timeout"].forEach(function (name) {
      body.addEventListener(name, onFailed);
    });
    /* A fresh try starts with a clean page. */
    body.addEventListener("htmx:beforeRequest", function (event) {
      clear(buttonFor((event.detail || {}).elt));
    });
  }

  global.QAGAiError = {
    HEADER: HEADER,
    SLOT_CLASS: SLOT_CLASS,
    PROVIDER_NAMES: PROVIDER_NAMES,
    kindOf: kindOf,
    words: words,
    titleFor: titleFor,
    notesIn: notesIn,
    show: show,
    clear: clear,
    clearAll: clearAll,
    fromFetch: fromFetch,
    bind: bind
  };

  if (global.document) {
    if (global.document.readyState === "loading") {
      global.document.addEventListener("DOMContentLoaded", bind);
    } else {
      bind();
    }
  }
})(typeof window !== "undefined" ? window : globalThis);
