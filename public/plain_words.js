/* QA-Genius v2: "What's this?" for the few QA words worth keeping.
 *
 * Some words a tester has to learn: acceptance criteria, boundary, INVEST.
 * Replacing those would leave someone unable to talk to their team, so they
 * stay — with a small ⓘ that says what they mean in one or two sentences.
 *
 * A template marks a word with <span data-explain="boundary"></span> and this
 * file turns that span into the button and its panel. One word is explained
 * once per page: the first mark wins and later ones are left alone, so a long
 * result page does not sprout a row of identical buttons.
 *
 * Everything is built with DOM methods and textContent. No HTML is parsed
 * here, so nothing a model or a user wrote can become markup. */
(function (global) {
  "use strict";

  var WORDS = {
    "acceptance-criteria": {
      term: "Acceptance criteria",
      text:
        "The list of things that must be true before a story is done. " +
        "Each one should be short enough to test on its own."
    },
    "test-case": {
      term: "Test case",
      text:
        "One test, written down: what to set up, what to do, and what should " +
        "happen. Anyone on the team should be able to follow it."
    },
    boundary: {
      term: "At the limit (boundary)",
      text:
        "A test right at, just under and just over a number in the rules, " +
        "like 4, 5 and 6 tries. Most off-by-one bugs hide there."
    },
    negative: {
      term: "Wrong input (negative)",
      text:
        "A test that does the wrong thing on purpose — a bad password, an " +
        "empty box, a file that is too big — to check the app says so."
    },
    "edge-case": {
      term: "Unusual case (edge case)",
      text:
        "A test for something real but rare: two tabs open, a name with " +
        "accents, the clocks changing. Rare is not the same as never."
    },
    invest: {
      term: "INVEST",
      text:
        "Six things a good story has. It stands alone, can be discussed, is " +
        "worth doing, can be sized, is small, and can be tested."
    },
    "risk-score": {
      term: "Risk score",
      text:
        "How bad × how likely × how hard to notice, each from 1 to 5. " +
        "The lowest score is 1 and the highest is 125."
    },
    playwright: {
      term: "Playwright",
      text:
        "A free tool that drives a real browser to run your tests. " +
        "Cypress and Selenium do the same job."
    },
    "given-when-then": {
      term: "Given / When / Then",
      text:
        "A way of writing a test as three lines: what was already true, what " +
        "you do, and what should happen. Teams also call it BDD."
    },
    pairwise: {
      term: "Every two options together",
      text:
        "Most bugs that depend on the setup need only two things to meet. " +
        "So you test every pair at least once instead of every combination."
    }
  };

  var OPEN_CLASS = "explain-open";
  var open = null;

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function close() {
    if (!open) return;
    open.button.setAttribute("aria-expanded", "false");
    open.panel.hidden = true;
    open.panel.classList.remove(OPEN_CLASS);
    open = null;
  }

  function show(entry) {
    if (open && open.button === entry.button) {
      close();
      return;
    }
    close();
    entry.button.setAttribute("aria-expanded", "true");
    entry.panel.hidden = false;
    entry.panel.classList.add(OPEN_CLASS);
    open = entry;
  }

  /* One mark becomes a button plus the panel it opens. */
  function build(mark, key, index) {
    var word = WORDS[key];
    if (!word) return;
    var id = "explain-" + key + "-" + index;

    var button = el("button", "explain-btn", "ⓘ");
    button.type = "button";
    button.setAttribute("aria-expanded", "false");
    button.setAttribute("aria-controls", id);
    /* The word is in the button's own label, so a screen reader hears
     * "What's this? Boundary" rather than a lone symbol. */
    button.setAttribute("aria-label", "What's this? " + word.term);
    button.setAttribute("title", "What's this?");

    var panel = el("span", "explain-panel");
    panel.id = id;
    panel.hidden = true;
    panel.setAttribute("role", "note");
    panel.appendChild(el("strong", null, word.term));
    panel.appendChild(el("span", null, " " + word.text));

    var entry = { button: button, panel: panel };
    button.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      show(entry);
    });

    mark.className = "explain " + (mark.className || "").replace("explain", "");
    mark.setAttribute("data-built", "1");
    mark.appendChild(button);
    mark.appendChild(panel);
  }

  /* Is this word already explained somewhere on the page right now?
   *
   * Asking the document, rather than counting within one pass, is what makes
   * "once per page" true when a result card is swapped in later: the old
   * card's button left with it, so the new card gets one. */
  function explained(key) {
    return document.querySelector('[data-explain="' + key + '"][data-built]') !== null;
  }

  function render(root) {
    var marks = (root || document).querySelectorAll("[data-explain]");
    for (var i = 0; i < marks.length; i++) {
      var mark = marks[i];
      var key = mark.getAttribute("data-explain");
      if (mark.hasAttribute("data-built") || explained(key)) continue;
      build(mark, key, i);
    }
  }

  function start() {
    render(document);
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") close();
    });
    document.addEventListener("click", function (event) {
      if (open && !open.panel.contains(event.target)) close();
    });
    /* A result card arrives after the page does, and not always the same way:
     * HTMX swaps some in, a fetch writes others into the page itself. One
     * observer covers both, so no desk has to remember to call render(). */
    if (typeof MutationObserver === "function") {
      var pending = false;
      new MutationObserver(function () {
        if (pending) return;
        pending = true;
        /* Several nodes usually land together; render once after them. */
        setTimeout(function () {
          pending = false;
          render(document);
        }, 0);
      }).observe(document.body, { childList: true, subtree: true });
    }
  }

  global.QAGWords = { words: WORDS, render: render };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})(window);
