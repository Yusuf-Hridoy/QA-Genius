/* QA-Genius v2: the Overview.
 *
 * Nothing here decides anything. The step bar reads the freshness run_state.js
 * already works out, and "What needs attention" is the Ship check report --
 * fetched from the same /ship/report route the Ship desk posts to, so there is
 * one decision in the app and one place that computes it.
 *
 * The helpers at the top touch no DOM, so they can be unit tested on their
 * own. Everything below them writes through textContent. */
(function (global) {
  "use strict";

  var MAX_ATTENTION = 3;
  var STORY_IN_CARD = 220;

  /* ---------- the one open question ---------- */

  var SEVERITY = { high: 0, High: 0, medium: 1, Medium: 1, low: 2, Low: 2 };

  function rank(phrase) {
    var level = phrase && phrase.severity;
    return level in SEVERITY ? SEVERITY[level] : 1;
  }

  function firstText(list) {
    for (var at = 0; at < (list || []).length; at++) {
      var line = String(list[at] || "").trim();
      if (line) return line;
    }
    return "";
  }

  /* What to answer next, in the order a tester would pick it up:
   * a limit nobody has decided, then a story that is really several, then
   * the worst unclear word. Nothing open means no strip at all. */
  function topQuestion(run) {
    var notes = (run && run.story_notes) || {};
    var limit = firstText(notes.limit_notes);
    if (limit) {
      return { text: limit, href: "/requirements/criteria", label: "Answer it" };
    }
    if (notes.epic && (notes.epic.title || notes.epic.advice)) {
      return {
        text: String(notes.epic.title || notes.epic.advice).trim(),
        href: "/requirements/story#recommended-split",
        label: "See the split"
      };
    }
    var analysis = (run && run.story_analysis) || {};
    var phrases = (analysis.vague_phrases || []).filter(function (one) {
      return one && String(one.phrase || "").trim();
    });
    if (!phrases.length) return null;
    var worst = phrases.slice().sort(function (a, b) {
      return rank(a) - rank(b);
    })[0];
    var say = String(worst.replacement || worst.suggestion || "").trim();
    return {
      text: '"' + String(worst.phrase).trim() + '" is not something anyone can test' +
        (say ? ". Say " + say + " instead" : ""),
      href: "/requirements/story",
      label: "Answer it"
    };
  }

  /* ---------- what needs attention ---------- */

  var DESK_WORDS = {
    risks: "Risk radar",
    matrix: "Test matrix",
    test_cases: "Test cases",
    automation: "Automation"
  };

  var DESK_LINKS = {
    risks: "/risks",
    matrix: "/requirements/matrix",
    test_cases: "/requirements/test-cases",
    automation: "/requirements/automation"
  };

  /* Needs fixing first, then check this, then a desk built from older work.
   * `statuses` is desk -> the state run_state.js reports for it. */
  function attentionItems(report, statuses) {
    var items = [];
    var checks = (report && report.items) || [];

    function take(status, tone, icon) {
      checks.forEach(function (check) {
        if (check.status !== status) return;
        items.push({
          title: check.title,
          detail: check.summary,
          href: check.link,
          tone: tone,
          icon: icon,
          kind: status
        });
      });
    }

    take("fail", "bad", "alert-triangle");
    take("warn", "warn", "alert-triangle");

    Object.keys(statuses || {}).forEach(function (desk) {
      if (statuses[desk] !== "stale") return;
      var word = DESK_WORDS[desk];
      if (!word) return;
      items.push({
        title: word + " is out of date",
        detail: "It was built from work you have since changed.",
        href: DESK_LINKS[desk],
        tone: "info",
        icon: "refresh",
        kind: "stale"
      });
    });

    return items;
  }

  /* ---------- how clear the story is ---------- */

  function clarityOf(run) {
    var analysis = (run && run.story_analysis) || null;
    if (!analysis || typeof analysis.ambiguity_score !== "number") return null;
    var score = Math.max(0, Math.min(100, 100 - analysis.ambiguity_score));
    return { score: score };
  }

  var api = {
    otherStoriesLine: otherStoriesLine,
    needsAttention: needsAttention,
    topQuestion: topQuestion,
    attentionItems: attentionItems,
    clarityOf: clarityOf,
    MAX_ATTENTION: MAX_ATTENTION
  };
  global.QAGHome = api;

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

  function icon(name) {
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "1.5");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    svg.setAttribute("aria-hidden", "true");
    var paths = {
      "alert-triangle": [
        "M10.3 3.9 2.6 17.1a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
        "M12 9v4M12 17h.01"
      ],
      refresh: [
        "M20 11a8 8 0 0 0-13.7-5.3L4 8",
        "M4 4v4h4",
        "M4 13a8 8 0 0 0 13.7 5.3L20 16",
        "M20 20v-4h-4"
      ],
      "chevron-right": ["m9 6 6 6-6 6"]
    };
    (paths[name] || paths["chevron-right"]).forEach(function (d) {
      var path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", d);
      svg.appendChild(path);
    });
    return svg;
  }

  function readRun() {
    if (global.QAGRun) return global.QAGRun.read();
    return {};
  }

  /* ---------- step bar ---------- */

  var STATE_WORDS = {
    none: "Not built yet",
    unchecked: "Not checked yet",
    stale: "Old",
    fresh: "Matches your work",
    example: "Example",
    /* Ship is the one step with a verdict rather than a freshness, and the
     * three verdicts are three different answers. A green tick beside
     * "Not ready" was the bar saying the opposite of the decision. */
    ship_ready: "Ready to release",
    ship_risks: "Release with known risks",
    ship_not: "Not ready"
  };

  var DECISION_STATES = {
    ship: "ship_ready",
    ship_with_risks: "ship_risks",
    dont_ship: "ship_not"
  };

  /* Green tick only for Ready. Amber when there are known risks, red when
   * the answer is no, and nothing at all before the check has run. */
  function shipState(run, states) {
    var decided = DECISION_STATES[run && run.ship_decision];
    if (decided) return decided;
    return states.risks === "fresh" || states.matrix === "fresh" ? "fresh" : "none";
  }

  function storyState(run) {
    if (!run || !String(run.story || "").trim()) return "none";
    /* Written but never checked is not the same as nothing at all, and the
     * step bar beside a story the reader can see should say which. */
    if (!run.story_analysis) return "unchecked";
    if (run.story_analysis_is_example) return "example";
    var built = (run.story_analysis_built_from || {}).story;
    var now = (run.fp || {}).story;
    if (!built || !now) return "fresh";
    return built.hash === now.hash ? "fresh" : "stale";
  }

  function deskStates(run) {
    var states = { story: storyState(run) };
    ["risks", "matrix", "test_cases", "automation"].forEach(function (desk) {
      states[desk] = global.QAGRun ? global.QAGRun.statusOf(desk, run).state : "none";
    });
    states.ship = shipState(run, states);
    return states;
  }

  function paintSteps(run, states) {
    var list = byId("overview-steps");
    if (!list) return;
    var forStep = {
      story: states.story,
      risks: states.risks,
      matrix: states.matrix,
      ship: states.ship
    };
    Array.prototype.forEach.call(list.children, function (item) {
      var desk = item.getAttribute("data-desk");
      var state = forStep[desk] || "none";
      var where = item.querySelector(".step-state");
      if (where) where.textContent = STATE_WORDS[state] || STATE_WORDS.none;
      var settled = state === "fresh" || state === "ship_ready";
      item.classList.toggle("done", settled);
      item.classList.toggle("step-warn", state === "ship_risks");
      item.classList.toggle("step-bad", state === "ship_not");
      item.classList.toggle("now", !settled && state !== "ship_risks" &&
        state !== "ship_not");
    });
    /* Only the first unfinished step is the one you are on. */
    var pending = list.querySelectorAll("li.now");
    Array.prototype.forEach.call(pending, function (item, at) {
      if (at > 0) item.classList.remove("now");
    });
  }

  /* ---------- the workbench card ---------- */

  function paintBench(run) {
    var body = byId("bench-body");
    if (!body) return;
    var story = String((run && run.story) || "").trim();
    body.textContent = "";
    if (!story) {
      body.appendChild(el("p", "bench-story bench-empty", "No story yet"));
      body.appendChild(
        el(
          "p",
          "bench-sub",
          "Check a story and this is where it lives, with its score and the " +
            "one question still open."
        )
      );
      var row = el("div", "row bench-actions");
      var example = el("a", "btn", "Load an example");
      example.href = "/requirements/story?example=1";
      example.id = "bench-example";
      row.appendChild(example);
      body.appendChild(row);
      return;
    }

    var type = String((run && run.story_type) || "").trim();
    if (type) {
      var chips = el("div", "bench-chips");
      chips.appendChild(el("span", "chip bench-chip", type));
      body.appendChild(chips);
    }
    var shown = story.length > STORY_IN_CARD ? story.slice(0, STORY_IN_CARD) + "…" : story;
    body.appendChild(el("p", "bench-story", shown));

    /* What this story already has, from the run the tab is actually on.
     * The card used to say nothing about the criteria, so a story with
     * eight of them read exactly like one with none. */
    var latest = global.QAGRun ? global.QAGRun.describeLatest(run) : null;
    if (latest) {
      var facts = [
        latest.criteriaCount +
          (latest.criteriaCount === 1 ? " criterion" : " criteria"),
        latest.caseCount + (latest.caseCount === 1 ? " test" : " tests")
      ];
      body.appendChild(el("p", "bench-facts", facts.join(" · ")));
    }

    var clarity = clarityOf(run);
    if (clarity) {
      var line = el("div", "bench-score");
      line.appendChild(el("span", "bench-score-label", "How clear"));
      var num = el("span", "bench-score-num", String(clarity.score));
      num.appendChild(el("span", "bench-score-of", "/100"));
      line.appendChild(num);
      body.appendChild(line);
      var track = el("div", "bench-bar");
      var fill = el("span", "bench-bar-fill");
      fill.style.width = clarity.score + "%";
      track.appendChild(fill);
      body.appendChild(track);
    }

    var question = topQuestion(run);
    if (question) {
      var strip = el("div", "bench-strip");
      strip.appendChild(el("span", "bench-strip-text", question.text));
      var link = el("a", "bench-strip-link", question.label + " →");
      link.href = question.href;
      strip.appendChild(link);
      body.appendChild(strip);
    }
  }

  /* ---------- what needs attention ---------- */

  function paintAttention(items, hasStory) {
    var list = byId("attention-list");
    var count = byId("attention-count");
    if (!list) return;
    list.textContent = "";
    if (count) {
      count.hidden = items.length === 0;
      count.textContent = String(items.length);
    }
    if (!items.length) {
      list.appendChild(
        el(
          "p",
          "muted",
          hasStory
            ? "Nothing is waiting on you. Every check that ran came back fine."
            : "Nothing to see yet. Check a story and the gaps show up here."
        )
      );
      return;
    }
    items.slice(0, MAX_ATTENTION).forEach(function (item) {
      var row = el("a", "attention-row");
      row.href = item.href;
      var tile = el("span", "icon-tile tile-" + item.tone);
      tile.appendChild(icon(item.icon));
      row.appendChild(tile);
      var words = el("span", "attention-words");
      words.appendChild(el("span", "attention-title", item.title));
      words.appendChild(el("span", "attention-detail", item.detail));
      row.appendChild(words);
      var chev = icon("chevron-right");
      chev.setAttribute("class", "row-chevron");
      row.appendChild(chev);
      list.appendChild(row);
    });
  }

  /* ---------- switching between stories ---------- */

  function stories() {
    return global.QAGStories || null;
  }

  /* "‹ Story 2 of 5 ›", the id and status, and a way to start another one.
   * Switching saves what is open first, so nothing is lost on the way. */
  function paintSlot() {
    var slot = byId("bench-slot");
    var store = stories();
    if (!slot || !store) return;
    var all = store.list();
    slot.textContent = "";
    if (!all.length) {
      slot.hidden = true;
      return;
    }
    slot.hidden = false;
    var open = store.active();
    var at = 0;
    all.forEach(function (one, index) {
      if (open && one.id === open.id) at = index;
    });

    if (all.length > 1) {
      slot.appendChild(stepButton("‹", "Open the story before this one", all, at - 1));
      slot.appendChild(
        el("span", "bench-count", "Story " + (at + 1) + " of " + all.length)
      );
      slot.appendChild(stepButton("›", "Open the next story", all, at + 1));
    }
    if (open) {
      var words = global.QAGStoriesUI
        ? global.QAGStoriesUI.statusWord(open.status)
        : "Draft";
      slot.appendChild(el("span", "chip bench-chip", open.label + " · " + words));
    }
    var fresh = el("button", "btn btn-sm bench-new", "New story");
    fresh.type = "button";
    fresh.addEventListener("click", newStory);
    slot.appendChild(fresh);
  }

  function stepButton(mark, label, all, wanted) {
    var button = el("button", "btn btn-sm bench-step", mark);
    button.type = "button";
    button.setAttribute("aria-label", label);
    var at = (wanted + all.length) % all.length;
    button.addEventListener("click", function () {
      switchTo(all[at].id);
    });
    return button;
  }

  /* Save the story this tab has open into its own id, bind the tab to the
   * other one, copy its run in, then draw the page again from scratch so
   * every card and every freshness line is the new story's. */
  function switchTo(id) {
    var store = stories();
    if (!store) return;
    store.saveLive();
    if (!store.open(id)) return;
    global.location.reload();
  }

  /* A new story is a new story: the one that was open keeps its text, its
   * criteria and its results, and this tab moves to an empty one. */
  function newStory() {
    var store = stories();
    if (!store) return;
    store.saveLive();
    var made = store.create({ run: {} });
    if (made.error === "full-count") {
      paintOthers("You already have " + store.MAX_STORIES + " stories. Delete one first.");
      return;
    }
    if (made.error) {
      paintOthers("Couldn't save — browser storage is full.");
      return;
    }
    if (global.QAGRun) global.QAGRun.write(store.bound(made.story));
    global.location.href = "/requirements/story";
  }

  /* How many other stories are waiting on somebody. */
  function otherStoriesLine() {
    var store = stories();
    if (!store) return "";
    var open = store.active();
    var waiting = 0;
    store.list().forEach(function (one) {
      if (open && one.id === open.id) return;
      if (needsAttention(one.run)) waiting += 1;
    });
    if (!waiting) return "";
    return waiting === 1
      ? "1 other story needs attention"
      : waiting + " other stories need attention";
  }

  /* A saved story is waiting on somebody when its last Ship check said Not
   * ready, or when one of its desks was built from work it has moved past. */
  function needsAttention(run) {
    if (!run) return false;
    if (run.ship_decision === "dont_ship") return true;
    if (!global.QAGRun) return false;
    return global.QAGRun.staleInputs(run).length > 0;
  }

  function paintOthers(words) {
    var line = byId("bench-others");
    if (!line) return;
    var text = words || otherStoriesLine();
    line.textContent = text;
    line.hidden = !text;
  }

  /* ---------- the hero ---------- */

  function paintHero(run) {
    var go = byId("hero-go");
    if (!go) return;
    var label = go.querySelector(".btn-label");
    var story = String((run && run.story) || "").trim();
    if (label) label.textContent = story ? "Continue your story" : "Start with a story";
  }

  /* ---------- the Ship check report ---------- */

  var STALE_FOR_SHIP = {
    risks: "risks",
    matrix: "matrix",
    automation: "automation",
    test_cases: "coverage"
  };

  function shipBody(run) {
    var payload = { story: run.story || "", context: run.context || "" };
    if (run.story_label) payload.story_label = run.story_label;
    if (run.story_status) payload.story_status = run.story_status;
    if (run.story_analysis) payload.story_analysis = run.story_analysis;
    if (run.duel_summary) payload.duel_summary = run.duel_summary;
    if (run.test_cases && run.test_cases.result) {
      payload.test_cases = {
        result: run.test_cases.result,
        criteria: run.test_cases.criteria || criteriaTexts(run)
      };
    } else {
      var texts = criteriaTexts(run).filter(function (text) {
        return text.trim() !== "";
      });
      if (texts.length) payload.criteria = texts;
    }
    if (run.risk_analysis && run.risk_analysis.analysis) payload.risk_analysis = run.risk_analysis;
    if (run.automation && run.automation.script) payload.automation = run.automation;
    if (run.insights) payload.insights = run.insights;
    if (run.matrix && run.matrix.runs) payload.matrix = run.matrix;
    payload.acceptances = run.ship_acceptances || {};
    payload.risk_acceptances = run.risk_acceptances || {};
    payload.stale_inputs = (global.QAGRun ? global.QAGRun.staleInputs(run) : [])
      .map(function (desk) {
        return STALE_FOR_SHIP[desk];
      })
      .filter(Boolean);
    return payload;
  }

  function criteriaTexts(run) {
    return (run && run.criteria ? run.criteria : []).map(function (one) {
      return typeof one === "string" ? one : (one && one.text) || "";
    });
  }

  /* The route answers with the Ship desk's HTML; the facts travel inside it
   * as one JSON block, which is what this page reads. */
  function reportFrom(html) {
    try {
      var holder = document.createElement("div");
      holder.innerHTML = html;
      var block = holder.querySelector("#ship-data");
      return block ? JSON.parse(block.textContent) : null;
    } catch (e) {
      return null;
    }
  }

  function loadAttention(run, states) {
    var story = String((run && run.story) || "").trim();
    if (!story) {
      paintAttention([], false);
      return;
    }
    var stale = {};
    Object.keys(states).forEach(function (desk) {
      stale[desk] = states[desk];
    });
    fetch("/ship/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(shipBody(run))
    })
      .then(function (response) {
        return response.text();
      })
      .then(function (html) {
        var report = reportFrom(html);
        rememberDecision(report);
        paintAttention(attentionItems(report, stale), true);
      })
      .catch(function () {
        paintAttention(attentionItems(null, stale), true);
      });
  }

  /* The last decision is kept with the run, so "2 other stories need
   * attention" can be answered without re-running every check. */
  function rememberDecision(report) {
    if (!report || !global.QAGRun) return;
    var run = global.QAGRun.read();
    if (run.ship_decision === report.decision) return;
    run.ship_decision = report.decision;
    global.QAGRun.write(run);
  }

  function paint() {
    var run = readRun();
    var states = deskStates(run);
    paintHero(run);
    paintSteps(run, states);
    paintBench(run);
    paintSlot();
    paintOthers("");
    loadAttention(run, states);
  }

  document.addEventListener("DOMContentLoaded", paint);
  if (global.QAGRun) {
    global.addEventListener(global.QAGRun.CHANGED_EVENT, paint);
  }
})(typeof window !== "undefined" ? window : globalThis);
