/* QA-Genius v2: the parts of "several stories" that live on every page.
 *
 * It binds the tab to one story, saves as you work, keeps the count in the
 * rail honest and puts the story's own id and status beside the page title.
 * When another tab touches the same story it says so rather than letting one
 * of them win in silence. Everything it touches is in this browser; nothing
 * is sent anywhere. */
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

  function doc() {
    return global.document || null;
  }

  function el(tag, className, text) {
    var node = doc().createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  /* ---------- "Saved just now" ---------- */

  var WORDS = {
    "": "Saved just now",
    saving: "Saving…",
    full: "Couldn't save — browser storage is full",
    deleted: "",
    stale: "",
    same: "",
    "no-id": "",
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

  /* The story's own chip is its own element, next to the page title on every
   * page. It used to borrow #page-pill, so any desk that filled that pill
   * with its own counts replaced the story id and the reader lost track of
   * which story they were looking at. The two sit side by side now. */
  function chipSlot() {
    if (!doc()) return null;
    var found = byId("story-chip");
    if (found) return found;
    var head = doc().querySelector(".page-head");
    if (!head) return null;
    var chip = el("span", "chip chip-id story-chip");
    chip.id = "story-chip";
    chip.hidden = true;
    /* First in the header, above the eyebrow: the reader should know which
     * story they are on before they read anything else on the page. */
    head.insertBefore(chip, head.firstChild);
    return chip;
  }

  function paintChip(run) {
    var chip = chipSlot();
    if (!chip) return;
    var words = storyChip(run);
    chip.textContent = words;
    chip.hidden = !words;
  }

  function currentRun() {
    return global.QAGRun ? global.QAGRun.read() : {};
  }

  /* Every trace that starts at the story shows the story's own id once it
   * has one, and the word STORY until then. */
  function paintTraceChips(run) {
    if (!doc()) return;
    var one = labelOf(run);
    var chips = doc().querySelectorAll(".story-id-chip");
    Array.prototype.forEach.call(chips, function (chip) {
      chip.textContent = one.label || "STORY";
    });
  }

  function paint() {
    var run = currentRun();
    paintRail();
    paintChip(run);
    paintTraceChips(run);
  }

  /* ---------- keeping a sample as your own story ---------- */

  /* The id the reader typed on the Story desk, when there is one. */
  function typedLabel() {
    var box = byId("story-label");
    return box ? String(box.value || "").trim() : "";
  }

  /* The sample on screen becomes a story of your own: a new one, so nothing
   * you already had is written over. It takes the id in the Story ID field,
   * or the next S-00n when that is empty. */
  function keepExample() {
    var store = stories();
    if (!store || !global.QAGRun) return;
    var run = global.QAGRun.read();
    delete run.story_is_example;
    delete run._is_example;
    var wanted = typedLabel();
    var button = byId("example-keep");
    if (wanted && !store.validLabel(wanted)) {
      sayOnButton(button, store.LABEL_RULE);
      return;
    }
    if (wanted) run.story_label = wanted;
    var made = store.create({ run: run, label: wanted });
    if (made.error === "duplicate-label") {
      sayOnButton(button, made.message);
      return;
    }
    if (made.error) {
      showSave("full");
      return;
    }
    global.QAGRun.write(store.bound(made.story));
    paint();
    /* The counters under the boxes were drawn before the example filled
     * them, so they read "0 / 3000" under three thousand characters. */
    if (global.QAG && global.QAG.initFields) global.QAG.initFields();
    /* The banner said "this is a saved example". It is your story now, so
     * the banner goes rather than being left to argue with the chip. */
    dropExampleFlag();
    if (button) {
      button.disabled = true;
      button.textContent = "Saved as " + made.story.label;
    }
  }

  function sayOnButton(button, words) {
    if (!button || !button.parentNode) return;
    var line = button.parentNode.querySelector(".example-keep-note");
    if (!line) {
      line = el("span", "muted small example-keep-note");
      line.setAttribute("role", "status");
      button.parentNode.insertBefore(line, button.nextSibling);
    }
    line.textContent = words;
  }

  function dropExampleFlag() {
    if (!doc()) return;
    var flags = doc().querySelectorAll(".example-flag");
    Array.prototype.forEach.call(flags, function (flag) {
      if (flag.parentNode) flag.parentNode.removeChild(flag);
    });
  }

  /* ---------- another tab moved first ---------- */

  var CHANGED_WORDS = "This story changed in another tab.";
  var DELETED_WORDS = "This story was deleted. Start a new story or open another.";
  /* Delete all leaves nothing to open, so "Open another" would be a button
   * that goes to an empty list. One story gone is a different sentence
   * from every story gone. */
  var ALL_GONE_WORDS = "All stories deleted. Start a new one.";

  function barSlot() {
    var found = byId("story-bar");
    if (found) return found;
    if (!doc()) return null;
    var main = doc().querySelector(".content");
    if (!main) return null;
    var bar = el("div", "story-bar card");
    bar.id = "story-bar";
    bar.setAttribute("role", "status");
    bar.hidden = true;
    main.insertBefore(bar, main.firstChild);
    return bar;
  }

  function showBar(words, buttons) {
    var bar = barSlot();
    if (!bar) return;
    bar.textContent = "";
    bar.hidden = false;
    bar.appendChild(el("span", "story-bar-words", words));
    var row = el("span", "story-bar-actions");
    buttons.forEach(function (one) {
      var button = el("button", one.main ? "btn btn-primary btn-sm" : "btn btn-sm", one.words);
      button.type = "button";
      button.addEventListener("click", one.go);
      row.appendChild(button);
    });
    bar.appendChild(row);
  }

  function hideBar() {
    var bar = byId("story-bar");
    if (bar) bar.hidden = true;
  }

  /* Reload takes the other tab's copy; Keep mine writes this tab's over it,
   * and asks first, because that is the one that loses work. */
  function changedBar() {
    showBar(CHANGED_WORDS, [
      {
        words: "Reload",
        main: true,
        go: function () {
          var store = stories();
          if (store) store.open(store.tabStory());
          global.location.reload();
        }
      },
      {
        words: "Keep mine",
        go: askKeepMine
      }
    ]);
  }

  /* The browser's own confirm box is a different app arriving on top of
   * this one: different type, different buttons, no theme. The question
   * is asked in the bar it came from instead. */
  var KEEP_MINE_ASK =
    "Keep this tab's copy? The version saved in the other tab is written " +
    "over and cannot be brought back.";

  function askKeepMine() {
    showBar(KEEP_MINE_ASK, [
      {
        words: "Yes, keep mine",
        main: true,
        go: function () {
          var store = stories();
          if (!store || !global.QAGRun) return;
          store.forceSave(store.tabStory(), global.QAGRun.read());
          hideBar();
        }
      },
      { words: "No, leave it", go: changedBar }
    ]);
  }

  function deletedBar() {
    var store = stories();
    /* Nothing left to open: one button, and it is the only thing to do. */
    if (store && !store.count()) {
      showBar(ALL_GONE_WORDS, [
        { words: "Start a new story", main: true, go: startNewStory }
      ]);
      return;
    }
    showBar(DELETED_WORDS, [
      { words: "Start a new story", main: true, go: startNewStory },
      {
        words: "Open another",
        go: function () {
          global.location.href = "/stories";
        }
      }
    ]);
  }

  /* One way to start a story, used by the bars here and by every page that
   * offers it: save what is open, make a new one, land on the Story step. */
  function startNewStory() {
    var store = stories();
    if (!store) return;
    store.saveLive();
    var made = store.create({ run: {} });
    if (made.error) {
      showSave(made.error === "full-count" ? "full" : "full");
      return;
    }
    if (global.QAGRun) global.QAGRun.write(store.bound(made.story));
    global.location.href = "/requirements/story";
  }

  function onElsewhere(state) {
    if (state === "deleted") {
      deletedBar();
      return;
    }
    if (state === "changed") changedBar();
  }

  /* ---------- starting up ---------- */

  function start() {
    var store = stories();
    if (!store) return;
    /* This tab picks up a story of its own: the one its run names, the one
     * it already had, or the last one opened in any tab. */
    store.adopt();
    /* The tab points at a story that is not there any more: nothing to save
     * into, so the run goes and every desk draws its own empty screen. */
    if (store.tabStory() && !store.active()) store.forgetOpenStory();
    /* Said once, where it happened. A banner that came back on every page
     * and every reload read like the app was stuck, long after the reader
     * had taken it in. */
    store.listen(function (problem) {
      showSave(problem);
      paintRail();
      if (problem === "deleted") deletedBar();
      if (problem === "stale") changedBar();
    });
    store.watch();
    if (global.addEventListener) {
      global.addEventListener(store.CHANGED_EVENT, paintRail);
      global.addEventListener(store.ELSEWHERE_EVENT, function (event) {
        onElsewhere(event && event.detail ? event.detail.state : "");
      });
      if (global.QAGRun) {
        global.addEventListener(global.QAGRun.CHANGED_EVENT, function () {
          showSave("saving");
          paint();
        });
      }
    }
    paint();
    if (doc()) {
      doc().addEventListener("click", function (event) {
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
    showSave: showSave,
    startNewStory: startNewStory,
    changedBar: changedBar,
    deletedBar: deletedBar,
    dropExampleFlag: dropExampleFlag,
    askKeepMine: askKeepMine,
    CHANGED_WORDS: CHANGED_WORDS,
    KEEP_MINE_ASK: KEEP_MINE_ASK,
    DELETED_WORDS: DELETED_WORDS,
    ALL_GONE_WORDS: ALL_GONE_WORDS
  };

  if (global.document) {
    global.document.addEventListener("DOMContentLoaded", start);
  }
})(typeof window !== "undefined" ? window : globalThis);
