/* QA-Genius v2: the "My stories" page.
 *
 * Every story on it comes out of this browser's own storage. The helpers at
 * the top touch no DOM so they can be unit tested; everything below writes
 * through textContent, never innerHTML. */
(function (global) {
  "use strict";

  /* ---------- search, filter, sort ---------- */

  function matches(story, words) {
    var wanted = String(words || "").trim().toLowerCase();
    if (!wanted) return true;
    var haystack = [
      story.label || "",
      story.title || "",
      (story.run && story.run.story) || ""
    ]
      .join(" ")
      .toLowerCase();
    return haystack.indexOf(wanted) !== -1;
  }

  function withStatus(story, status) {
    return !status || status === "all" || story.status === status;
  }

  function sorted(list, how) {
    var out = (list || []).slice();
    if (how === "label") {
      out.sort(function (a, b) {
        return String(a.label || "").localeCompare(String(b.label || ""));
      });
      return out;
    }
    /* "Last opened" and "Last edited" are two different questions and the
     * page now asks whichever one the reader picked. Opening a story moves
     * opened_at and leaves updated_at where it was. */
    if (how === "opened") {
      out.sort(function (a, b) {
        var first = String(a.opened_at || a.updated_at || "");
        var second = String(b.opened_at || b.updated_at || "");
        return second.localeCompare(first);
      });
      return out;
    }
    /* Last edited first: the story you last changed is at the top. */
    out.sort(function (a, b) {
      return String(b.updated_at || "").localeCompare(String(a.updated_at || ""));
    });
    return out;
  }

  function shown(list, options) {
    var opts = options || {};
    return sorted(
      (list || []).filter(function (one) {
        return matches(one, opts.words) && withStatus(one, opts.status);
      }),
      opts.sort
    );
  }

  /* The same rule qagenius/risk_radar.py uses, so a card and the desk it
   * stands for never disagree about what counts as high. */
  var HIGH_RPN = 40;

  function isHigh(one) {
    var severity = one.severity || 0;
    var rpn = severity * (one.likelihood || 0) * (one.detectability || 0);
    return rpn >= HIGH_RPN || (severity === 5 && (one.likelihood || 0) >= 3);
  }

  /* What a saved run has in it, without opening it.
   *
   * A risk with a test, and a risk somebody wrote down a reason for, are
   * both decided. Counting either of them as "no test" on the card made a
   * finished story look unfinished every time it was listed. */
  function facts(run) {
    var criteria = ((run && run.criteria) || []).filter(function (one) {
      var text = typeof one === "string" ? one : (one && one.text) || "";
      return String(text).trim() !== "";
    }).length;
    var cases =
      run && run.test_cases && run.test_cases.result
        ? (run.test_cases.result.test_cases || []).length
        : 0;
    var risks = 0;
    var modes =
      run && run.risk_analysis && run.risk_analysis.analysis
        ? run.risk_analysis.analysis.failure_modes || []
        : [];
    var accepted = (run && run.risk_acceptances) || {};
    modes.forEach(function (one) {
      var covered = (one.covered_by || []).length > 0;
      if (!isHigh(one) || covered || accepted[one.id]) return;
      risks += 1;
    });
    return { criteria: criteria, cases: cases, risks: risks };
  }

  function factsLine(run) {
    var one = facts(run);
    var parts = [
      one.criteria + (one.criteria === 1 ? " criterion" : " criteria"),
      one.cases + (one.cases === 1 ? " test" : " tests")
    ];
    if (one.risks) {
      parts.push(one.risks + " high risk" + (one.risks === 1 ? "" : "s") + " with no test");
    }
    return parts.join(" · ");
  }

  /* "2 hours ago", from whatever run_state.js already knows about time. The
   * word in front of it says which of the two times it is, because "2 h ago"
   * on its own was read as "edited" when the story had only been opened. */
  function edited(story, how) {
    if (!global.QAGRun) return "";
    if (how === "opened") {
      var opened = global.QAGRun.timeAgo(story.opened_at || story.updated_at);
      return opened ? "Opened " + opened : "";
    }
    var when = global.QAGRun.timeAgo(story.updated_at);
    return when ? "Edited " + when : "";
  }

  var api = {
    matches: matches,
    withStatus: withStatus,
    sorted: sorted,
    shown: shown,
    facts: facts,
    factsLine: factsLine
  };
  global.QAGStoriesPage = api;

  if (typeof document === "undefined") return;

  /* ---------- the page ---------- */

  function byId(id) {
    return document.getElementById(id);
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function store() {
    return global.QAGStories;
  }

  function statusWord(status) {
    return global.QAGStoriesUI
      ? global.QAGStoriesUI.statusWord(status)
      : "Draft";
  }

  var DECISION_WORDS = {
    ship: "Ready to release",
    ship_with_risks: "Release with known risks",
    dont_ship: "Not ready"
  };

  function decisionChip(run) {
    var decision = run && run.ship_decision;
    if (!decision || !DECISION_WORDS[decision]) return null;
    var tone =
      decision === "ship" ? "chip-ok" : decision === "dont_ship" ? "chip-bad" : "chip-warn";
    return el("span", "chip " + tone, DECISION_WORDS[decision]);
  }

  function readOptions() {
    return {
      words: (byId("stories-search") || {}).value || "",
      status: (byId("stories-status") || {}).value || "all",
      sort: (byId("stories-sort") || {}).value || "edited"
    };
  }

  function emptyCard(anyAtAll) {
    var card = el("div", "card empty-state");
    card.appendChild(
      el("h2", null, anyAtAll ? "No story matches that." : "No saved stories yet.")
    );
    if (anyAtAll) {
      card.appendChild(el("p", "muted", "Try a different word, or clear the filters."));
      return card;
    }
    var row = el("div", "row empty-actions");
    /* The one yellow button on this page is New story in the toolbar. */
    var start = el("a", "btn", "Start with a story →");
    start.href = "/requirements/story";
    row.appendChild(start);
    var example = el("a", "btn", "Load an example");
    example.href = "/requirements/story?example=1";
    row.appendChild(example);
    card.appendChild(row);
    return card;
  }

  function render() {
    var list = byId("stories-list");
    if (!list || !store()) return;
    list.textContent = "";
    var all = store().list();
    var options = readOptions();
    var rows = shown(all, options);
    if (!rows.length) {
      list.appendChild(emptyCard(all.length > 0));
      return;
    }
    /* "Open now" is this tab's story, not whichever one another tab has. */
    var open = store().active();
    rows.forEach(function (story) {
      list.appendChild(card(story, open && open.id === story.id, options.sort));
    });
  }

  function card(story, isOpen, how) {
    var card = el("div", "card story-card" + (isOpen ? " story-open" : ""));
    card.setAttribute("data-story-id", story.id);

    var head = el("div", "row story-head");
    head.appendChild(el("span", "chip chip-id", story.label));
    head.appendChild(el("span", "chip", statusWord(story.status)));
    var decision = decisionChip(story.run);
    if (decision) head.appendChild(decision);
    if (isOpen) head.appendChild(el("span", "chip chip-info", "Open now"));
    head.appendChild(el("span", "spacer"));
    head.appendChild(el("span", "muted small", edited(story, how)));
    card.appendChild(head);

    var title = el("p", "story-title", story.title || "No story written yet");
    card.appendChild(title);
    card.appendChild(el("p", "story-facts", factsLine(story.run)));

    var actions = el("div", "row story-actions");
    /* The one yellow button on this page is "New story". Opening a story is
     * the row's own action, not the page's. */
    actions.appendChild(button("Open", function () {
      /* The story this tab has open is saved into its own id first, then
       * this one is opened and the page is drawn again from it. */
      store().saveLive();
      store().open(story.id);
      global.location.href = "/requirements/story";
    }));
    actions.appendChild(button("Rename", function () {
      openRename(card, story);
    }));
    actions.appendChild(statusPicker(story));
    actions.appendChild(button("Duplicate", function () {
      store().duplicate(story.id);
      render();
    }));
    actions.appendChild(button("Delete", function () {
      openDelete(card, story);
    }, "btn btn-sm btn-danger"));
    card.appendChild(actions);
    return card;
  }

  function button(words, onClick, className) {
    var node = el("button", className || "btn btn-sm", words);
    node.type = "button";
    node.addEventListener("click", onClick);
    return node;
  }

  function openRename(card, story) {
    var box = el("div", "row story-inline");
    var input = el("input", "mono");
    input.type = "text";
    input.value = story.label;
    input.maxLength = 24;
    input.setAttribute("aria-label", "New ID for " + story.label);
    box.appendChild(input);
    var say = el("span", "muted small");
    box.appendChild(
      button("Save", function () {
        var problem = store().rename(story.id, input.value);
        if (problem === "bad-label") {
          say.textContent = store().LABEL_RULE;
          return;
        }
        if (problem === "duplicate-label") {
          say.textContent = store().takenMessage(input.value);
          return;
        }
        render();
      })
    );
    box.appendChild(button("Cancel", render));
    box.appendChild(say);
    card.appendChild(box);
    input.focus();
  }

  function statusPicker(story) {
    var picker = el("select", "ctl story-status");
    picker.setAttribute("aria-label", "Status of " + story.label);
    store().STATUSES.forEach(function (status) {
      var option = el("option", null, statusWord(status));
      option.value = status;
      if (status === story.status) option.selected = true;
      picker.appendChild(option);
    });
    picker.addEventListener("change", function () {
      store().setStatus(story.id, picker.value);
      render();
    });
    return picker;
  }

  /* Deleting asks with the story's own id in the question, so nobody
   * deletes the wrong one by reflex. */
  function openDelete(card, story) {
    var box = el("div", "row story-inline");
    box.appendChild(el("span", "small", "Delete " + story.label + "?"));
    box.appendChild(
      button("Yes, delete it", function () {
        /* remove() clears the tab's story and its run when the deleted one
         * was this tab's, so nothing here can draw the old content again. */
        var wasOpen = store().tabStory() === story.id;
        store().remove(story.id);
        render();
        paintRail();
        if (wasOpen) global.location.href = "/requirements/story";
      }, "btn btn-sm btn-danger")
    );
    box.appendChild(button("No", render));
    card.appendChild(box);
  }

  function paintRail() {
    if (global.QAGStoriesUI) global.QAGStoriesUI.paint();
  }

  /* ---------- export, import, delete all ---------- */

  function say(words) {
    var line = byId("stories-io-status");
    if (line) line.textContent = words;
  }

  function exportAll() {
    var text = store().exportAll();
    var blob = new Blob([text], { type: "application/json" });
    var url = URL.createObjectURL(blob);
    var link = document.createElement("a");
    link.href = url;
    link.download = "qa-genius-stories.json";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    say("Saved " + store().count() + " stories to a file.");
  }

  function importFile(file) {
    var reader = new FileReader();
    reader.onload = function () {
      var result = store().importAll(String(reader.result || ""));
      var parts = [];
      if (result.added) parts.push(result.added + " added");
      if (result.updated) parts.push(result.updated + " updated");
      if (result.skipped) parts.push(result.skipped + " skipped");
      say(
        (parts.length ? parts.join(" · ") : "Nothing to bring in") +
          (result.errors.length ? " — " + result.errors.join(" ") : "")
      );
      render();
      paintRail();
    };
    reader.onerror = function () {
      say("That file could not be read.");
    };
    reader.readAsText(file);
  }

  function wire() {
    ["stories-search", "stories-status", "stories-sort"].forEach(function (id) {
      var node = byId(id);
      if (node) {
        node.addEventListener("input", render);
        node.addEventListener("change", render);
      }
    });
    var fresh = byId("stories-new");
    if (fresh) {
      fresh.addEventListener("click", function () {
        /* Save the story this tab has open into its own id, then make a
         * new one. The old story keeps everything it had. */
        store().saveLive();
        var made = store().create({ run: {} });
        if (made.error) {
          say(
            made.error === "full-count"
              ? "You already have " + store().MAX_STORIES + " stories. Delete one first."
              : "Couldn't save — browser storage is full."
          );
          return;
        }
        if (global.QAGRun) global.QAGRun.write(store().bound(made.story));
        global.location.href = "/requirements/story";
      });
    }
    var out = byId("stories-export");
    if (out) out.addEventListener("click", exportAll);
    var pick = byId("stories-import");
    var file = byId("stories-file");
    if (pick && file) {
      pick.addEventListener("click", function () {
        file.click();
      });
      file.addEventListener("change", function () {
        if (file.files && file.files[0]) importFile(file.files[0]);
        file.value = "";
      });
    }
    var danger = byId("stories-delete-all");
    var box = byId("delete-all-box");
    if (danger && box) {
      danger.addEventListener("click", function () {
        box.hidden = false;
        var word = byId("delete-all-word");
        if (word) {
          word.value = "";
          word.focus();
        }
      });
    }
    var cancel = byId("delete-all-cancel");
    if (cancel && box) {
      cancel.addEventListener("click", function () {
        box.hidden = true;
      });
    }
    var go = byId("delete-all-go");
    if (go) {
      go.addEventListener("click", function () {
        var word = byId("delete-all-word");
        if (!word || word.value.trim() !== "DELETE") {
          say("Type DELETE to confirm.");
          return;
        }
        store().removeAll();
        if (box) box.hidden = true;
        say("All your stories are gone from this browser.");
        render();
        paintRail();
      });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!store()) return;
    wire();
    render();
  });
})(typeof window !== "undefined" ? window : globalThis);
