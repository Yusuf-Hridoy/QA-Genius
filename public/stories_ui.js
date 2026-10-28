/* QA-Genius v2: the parts of "several stories" that live on every page.
 *
 * It carries the first visit over, saves as you work, keeps the count in the
 * rail honest and puts the story's own id and status beside the page title.
 * Everything it touches is in this browser; nothing is sent anywhere. */
(function (global) {
  "use strict";

  var SAVED_FOR = 4000;
  var hideTimer = null;

  function byId(id) {
    return global.document ? global.document.getElementById(id) : null;
  }

  function stories() {
    return global.QAGStories || null;
  }

  /* ---------- "Saved just now" ---------- */

  var WORDS = {
    "": "Saved just now",
    saving: "Saving…",
    full: "Couldn't save — browser storage is full",
    "no-active": "",
    example: "",
    "no-run": ""
  };

  function showSave(state) {
    var slot = byId("save-status");
    if (!slot) return;
    var words = WORDS[state];
    if (words === undefined) words = "";
    slot.textContent = words;
    slot.classList.toggle("save-status-bad", state === "full");
    if (hideTimer) global.clearTimeout(hideTimer);
    if (state === "" && words) {
      hideTimer = global.setTimeout(function () {
        if (slot.textContent === words) slot.textContent = "";
      }, SAVED_FOR);
    }
  }

  /* ---------- the rail ---------- */

  function paintRail() {
    var link = byId("nav-stories");
    var count = byId("nav-stories-count");
    var store = stories();
    if (!link || !store) return;
    /* Always on the rail, even at nought: "My stories · 0" is how a reader
     * finds out the page exists. */
    link.hidden = false;
    if (count) count.textContent = String(store.count());
  }

  /* ---------- the id and status beside the page title ---------- */

  function labelOf(run) {
    var store = stories();
    var saved = store ? store.active() : null;
    var label = (run && run.story_label) || (saved && saved.label) || "";
    var status = (run && run.story_status) || (saved && saved.status) || "draft";
    return { label: String(label).trim(), status: status };
  }

  function statusWord(status) {
    var store = stories();
    var words = store ? store.STATUS_WORDS : null;
    return (words && words[status]) || "Draft";
  }

  /* The chip a desk shows: "CART-204 · Draft". Nothing without an id. */
  function storyChip(run) {
    var one = labelOf(run);
    if (!one.label) return "";
    return one.label + " · " + statusWord(one.status);
  }

  /* The pill a desk fills itself is left alone; the story chip only takes an
   * empty one, so a desk's own counts always win. */
  function paintPill(run) {
    if (!global.QAG || !global.QAG.setPagePill) return;
    var pill = byId("page-pill");
    if (!pill) return;
    if (pill.textContent && pill.textContent.trim()) return;
    global.QAG.setPagePill(storyChip(run));
  }

  function currentRun() {
    return global.QAGRun ? global.QAGRun.read() : {};
  }

  /* Every trace that starts at the story shows the story's own id once it
   * has one, and the word STORY until then. */
  function paintTraceChips(run) {
    if (!global.document) return;
    var one = labelOf(run);
    var chips = global.document.querySelectorAll(".story-id-chip");
    Array.prototype.forEach.call(chips, function (chip) {
      chip.textContent = one.label || "STORY";
    });
  }

  function paint() {
    var run = currentRun();
    paintRail();
    paintPill(run);
    paintTraceChips(run);
  }

  /* ---------- keeping a sample as your own story ---------- */

  /* The sample on screen becomes a story of your own: a new one, so nothing
   * you already had is written over. */
  function keepExample() {
    var store = stories();
    if (!store || !global.QAGRun) return;
    var run = global.QAGRun.read();
    delete run.story_is_example;
    delete run._is_example;
    var made = store.create({ run: run });
    if (made.error) {
      showSave("full");
      return;
    }
    global.QAGRun.write(run);
    paint();
    var button = byId("example-keep");
    if (button) {
      button.disabled = true;
      button.textContent = "Saved as " + made.story.label;
    }
  }

  /* ---------- starting up ---------- */

  function start() {
    var store = stories();
    if (!store) return;
    /* A reader who already had a story in this tab keeps it. */
    store.migrate(currentRun());
    store.listen(function (problem) {
      showSave(problem);
      paintRail();
    });
    if (global.addEventListener) {
      global.addEventListener(store.CHANGED_EVENT, paintRail);
      if (global.QAGRun) {
        global.addEventListener(global.QAGRun.CHANGED_EVENT, function () {
          showSave("saving");
          paint();
        });
      }
    }
    paint();
    if (global.document) {
      global.document.addEventListener("click", function (event) {
        var target = event.target;
        if (target && target.closest && target.closest("#example-keep")) {
          keepExample();
        }
      });
    }
  }

  global.QAGStoriesUI = {
    paintTraceChips: paintTraceChips,
    storyChip: storyChip,
    statusWord: statusWord,
    labelOf: labelOf,
    paint: paint,
    showSave: showSave
  };

  if (global.document) {
    global.document.addEventListener("DOMContentLoaded", start);
  }
})(typeof window !== "undefined" ? window : globalThis);
