/* QA-Genius v2: "is this built from my latest work?", answered the same way
 * on every desk.
 *
 * One card, three states — not built yet, out of date, up to date — each with
 * a colour, an icon and words, never colour alone. The card's button is the
 * page's primary action when there is something to do, so the desk hides its
 * own duplicate button rather than competing with it.
 *
 * Nothing here calls a model. It reads the run, renders, and clicks the
 * button the desk already has. */
(function () {
  "use strict";

  var MINUTE = 60000;

  /* desk -> what its primary action is called, and the button that does it. */
  var ACTIONS = {
    risks: { build: "Find risks for this", update: "Update to my latest work", button: "#risk-find,#risk-paste-find" },
    matrix: { build: "Build matrix for this", update: "Update to my latest work", button: "#matrix-suggest" },
    test_cases: { build: "Generate test cases", update: "Update to my latest work", button: "#tc-generate" },
    automation: { build: "Generate automation", update: "Update to my latest work", button: "#automation-generate" }
  };
  /* What the card's own button says while the desk it pressed is working. */
  var BUSY_LABELS = {
    risks: "Finding risks…",
    matrix: "Building…",
    test_cases: "Writing tests…",
    automation: "Writing code…"
  };
  var UPDATE_LABEL = "Updating…";
  var DESK_NAMES = {
    risks: "Risk radar",
    matrix: "Test matrix",
    test_cases: "Test cases",
    automation: "Automation"
  };
  /* The desk's own Load example button, which the card borrows. */
  var EXAMPLES = {
    risks: "#risk-example",
    matrix: "#matrix-example"
  };
  var DESK_LINKS = {
    risks: "/risks",
    matrix: "/requirements/matrix",
    test_cases: "/requirements/test-cases",
    automation: "/requirements/automation"
  };

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function icon(paths, className) {
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "2");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    svg.setAttribute("aria-hidden", "true");
    if (className) svg.setAttribute("class", className);
    paths.forEach(function (d) {
      var path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", d);
      svg.appendChild(path);
    });
    return svg;
  }

  var ICONS = {
    none: ["M12 3v4M12 17v4M3 12h4M17 12h4", "M7.5 7.5 10 10M16.5 16.5 14 14M16.5 7.5 14 10M7.5 16.5 10 14"],
    stale: ["M10.3 3.9 1.9 18a2 2 0 0 0 1.7 3h16.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z", "M12 9v4M12 17h.01"],
    fresh: ["M20 7 9.5 17.5 4 12"]
  };

  /* ---------- the words ---------- */

  function latestLine(latest) {
    var parts = [];
    if (latest.storyTitle) parts.push("“" + latest.storyTitle + "”");
    parts.push(
      latest.criteriaCount === 1 ? "1 criterion" : latest.criteriaCount + " criteria"
    );
    parts.push(
      latest.caseCount === 1 ? "1 test case" : latest.caseCount + " test cases"
    );
    return parts.join(" · ");
  }

  /* Each desk claims only what it is actually built from: the matrix depends
   * on the story, so promising it matches your criteria would be a lie. */
  var DEPENDS_ON_STORY_ONLY = { matrix: true };

  function freshLine(desk, latest, builtAt) {
    var when = window.QAGRun.timeAgo(builtAt);
    var built = when ? " · built " + when : "";
    if (DEPENDS_ON_STORY_ONLY[desk]) {
      return "Matches your latest story" + built;
    }
    return (
      "Matches your latest story, " +
      latest.criteriaCount +
      (latest.criteriaCount === 1 ? " criterion" : " criteria") +
      " and " +
      latest.caseCount +
      (latest.caseCount === 1 ? " test case" : " test cases") +
      built +
      "."
    );
  }

  /* ---------- clicking what the desk already has ---------- */

  function pressDesk(desk) {
    var spec = ACTIONS[desk];
    if (!spec) return;
    var button = document.querySelector(spec.button);
    if (button) {
      button.click();
      return;
    }
    // The desk has not drawn its form yet; try again once it has.
    setTimeout(function () {
      var later = document.querySelector(spec.button);
      if (later) later.click();
    }, 300);
  }

  /* The desk's own button would be a second primary, so it steps down while
   * the card is offering the same action. This is a flag on <body> and a CSS
   * rule rather than a class on the button, because the desk draws its form
   * after this runs and would get its primary look straight back. */
  function demoteDeskButton(desk, cardHasPrimary) {
    if (!ACTIONS[desk]) return;
    if (cardHasPrimary) document.body.setAttribute("data-card-primary", desk);
    else document.body.removeAttribute("data-card-primary");
  }

  /* ---------- the card ---------- */

  function buildNotYet(card, desk, latest, run) {
    card.className = "source-card none";
    card.appendChild(icon(ICONS.none, "source-mark"));
    var body = el("div", "source-body");
    body.appendChild(el("p", "source-title", "Your latest work"));
    if (!latest.storyTitle) {
      body.appendChild(el("p", "source-detail", "Start with a story in Requirements."));
      card.appendChild(body);
      var go = el("a", "btn", "Go to Requirements");
      go.setAttribute("href", "/requirements/story");
      card.appendChild(go);
      return false;
    }
    body.appendChild(el("p", "source-detail", latestLine(latest)));
    card.appendChild(body);
    var actions = el("div", "source-actions");
    var action = el("button", "btn btn-primary source-action", ACTIONS[desk].build);
    action.type = "button";
    actions.appendChild(action);
    addExampleLink(actions, desk);
    card.appendChild(actions);
    return true;
  }

  /* The desk's own "Load example" button is hidden with its card, so the link
   * to it moves in here rather than disappearing. */
  function addExampleLink(actions, desk) {
    if (!EXAMPLES[desk]) return;
    var link = el("button", "btn btn-small source-example", "Load example");
    link.type = "button";
    actions.appendChild(link);
  }

  /* A sample is on screen: say so, and offer to do the real thing. */
  function buildExample(card, desk, latest) {
    card.className = "source-card none example";
    card.appendChild(icon(ICONS.none, "source-mark"));
    var body = el("div", "source-body");
    body.appendChild(el("p", "source-title", "Showing a sample."));
    body.appendChild(
      el(
        "p",
        "source-detail",
        latest.storyTitle
          ? "Your latest work: " + latestLine(latest)
          : "Start with a story in Requirements."
      )
    );
    card.appendChild(body);
    if (!latest.storyTitle) {
      var go = el("a", "btn", "Go to Requirements");
      go.setAttribute("href", "/requirements/story");
      card.appendChild(go);
      return false;
    }
    var actions = el("div", "source-actions");
    var action = el("button", "btn btn-primary source-action", ACTIONS[desk].build);
    action.type = "button";
    actions.appendChild(action);
    card.appendChild(actions);
    return true;
  }

  function buildStale(card, desk, latest, status) {
    card.className = "source-card stale";
    card.appendChild(icon(ICONS.stale, "source-mark"));
    var body = el("div", "source-body");
    var title = el("p", "source-title");
    title.appendChild(el("strong", null, "Old — your work changed."));
    if (status.changes.length) {
      title.appendChild(document.createTextNode(" " + status.changes[0] + "."));
    }
    body.appendChild(title);
    status.changes.slice(1).forEach(function (line) {
      body.appendChild(el("p", "source-extra", line + "."));
    });
    body.appendChild(el("p", "source-detail", "Latest: " + latestLine(latest)));
    card.appendChild(body);

    var actions = el("div", "source-actions");
    var update = el("button", "btn btn-primary source-action", ACTIONS[desk].update);
    update.type = "button";
    update.setAttribute("data-update", "yes");
    actions.appendChild(update);
    addExampleLink(actions, desk);
    if (desk === "matrix") {
      // The factors may have been hand-edited; keeping them costs no AI call.
      var keep = el("button", "btn source-keep", "Keep what I have");
      keep.type = "button";
      actions.appendChild(keep);
    }
    card.appendChild(actions);
  }

  function buildFresh(card, desk, latest, status, run) {
    card.className = "source-card fresh";
    card.appendChild(icon(ICONS.fresh, "source-mark"));
    var body = el("div", "source-body");
    body.appendChild(el("p", "source-title", freshLine(desk, latest, status.built_at)));
    /* Either the recheck is still pending (auto) or it has just run and left
     * its record; both are worth saying, because neither cost a key. */
    var rechecked = run && run.risk_analysis_rechecked;
    var justRechecked =
      desk === "risks" && rechecked && rechecked.cases === latest.caseCount;
    if ((status.auto && status.changes.length) || justRechecked) {
      body.appendChild(
        el(
          "p",
          "source-extra",
          "Checked again against your " +
            latest.caseCount +
            " newest test cases — no AI needed."
        )
      );
    }
    card.appendChild(body);
  }

  function buildShip(card, run, status) {
    card.className = "source-card fresh";
    card.appendChild(icon(ICONS.fresh, "source-mark"));
    var body = el("div", "source-body");
    body.appendChild(
      el("p", "source-title", "Worked out just now from your latest results.")
    );
    if (status.changes.length) {
      var warn = el("div", "source-older");
      warn.appendChild(
        el("span", null, "Some of this is older than your latest work: ")
      );
      status.changes.forEach(function (desk, index) {
        var reason = window.QAGRun.statusOf(desk, run).changes[0] || "";
        var link = el("a", null, DESK_NAMES[desk] || desk);
        link.setAttribute("href", DESK_LINKS[desk] || "/");
        warn.appendChild(link);
        // "Risk radar — your criteria changed just now (6 → 7)", with the
        // only brackets being the ones the sentence itself needs.
        if (reason) {
          warn.appendChild(
            el("span", "muted", " — " + reason.charAt(0).toLowerCase() + reason.slice(1))
          );
        }
        warn.appendChild(
          document.createTextNode(index === status.changes.length - 1 ? "." : "; ")
        );
      });
      body.appendChild(warn);
    }
    card.appendChild(body);
  }

  /* ---------- the sidebar ---------- */

  /* A dot or a tick beside each desk, so the state is known before clicking.
   * Colour alone would say nothing to a colour-blind reader, so each one
   * carries a shape and a word only a screen reader hears. */
  function renderNav() {
    var slots = document.querySelectorAll(".nav-status[data-desk]");
    if (!slots.length || !window.QAGRun) return;
    var run = window.QAGRun.read();
    Array.prototype.forEach.call(slots, function (slot) {
      var desk = slot.getAttribute("data-desk");
      var status = window.QAGRun.statusOf(desk, run);
      var stale = desk === "ship" ? status.changes.length > 0 : status.state === "stale";
      slot.textContent = "";
      slot.removeAttribute("title");
      if (stale) {
        var reason =
          desk === "ship"
            ? "Old — some of this is older than your latest work"
            : "Old — " + (status.changes[0] || "your work changed").toLowerCase();
        slot.appendChild(el("span", "dot-stale"));
        slot.appendChild(el("span", "sr-only", "out of date"));
        slot.setAttribute("title", reason);
        slot.setAttribute("aria-label", reason);
        return;
      }
      if (desk !== "ship" && status.state === "fresh") {
        slot.appendChild(icon(ICONS.fresh, "tick-fresh"));
        slot.appendChild(el("span", "sr-only", "matches your latest work"));
        slot.setAttribute("title", "Matches your latest work");
        slot.setAttribute("aria-label", "Matches your latest work");
        return;
      }
      slot.removeAttribute("aria-label");
    });
  }

  /* ---------- the "next" strip on a result ---------- */

  var STATE_WORDS = { none: "Not built yet", stale: "Old", fresh: "Matches your work" };

  function renderNext() {
    var chips = document.querySelectorAll("#next-strip .next-chip[data-desk]");
    if (!chips.length || !window.QAGRun) return;
    var run = window.QAGRun.read();
    Array.prototype.forEach.call(chips, function (chip) {
      var desk = chip.getAttribute("data-desk");
      var status = window.QAGRun.statusOf(desk, run);
      var state =
        desk === "ship"
          ? status.changes.length
            ? "stale"
            : "fresh"
          : status.state;
      var slot = chip.querySelector(".next-state");
      if (!slot) return;
      slot.textContent = STATE_WORDS[state] || "";
      chip.setAttribute("data-state", state);
      var mark = chip.querySelector(".next-mark");
      if (mark) mark.parentNode.removeChild(mark);
      if (state === "stale") {
        var dot = el("span", "next-mark dot-stale");
        chip.insertBefore(dot, chip.firstChild);
      } else if (state === "fresh") {
        var tick = icon(ICONS.fresh, "next-mark tick-fresh");
        chip.insertBefore(tick, chip.firstChild);
      }
    });
  }

  function render() {
    var card = document.getElementById("source-card");
    if (!card || !window.QAGRun) return;
    var desk = card.getAttribute("data-desk");
    if (!desk) return;

    var run = window.QAGRun.read();
    var status = window.QAGRun.statusOf(desk, run);
    var latest = window.QAGRun.describeLatest(run);

    card.textContent = "";
    if (desk === "ship") {
      buildShip(card, run, status);
      demoteDeskButton(desk, false);
      return;
    }
    /* Only demote the desk's own button when the card really is offering the
     * same action: with no story at all the card only points at Requirements,
     * and taking the page's primary away would leave nothing to press. */
    var cardHasPrimary = false;
    if (status.state === "none") {
      cardHasPrimary = buildNotYet(card, desk, latest, run) === true;
    } else if (status.state === "example") {
      cardHasPrimary = buildExample(card, desk, latest) === true;
    } else if (status.state === "stale") {
      buildStale(card, desk, latest, status);
      cardHasPrimary = true;
    } else {
      buildFresh(card, desk, latest, status, run);
    }

    demoteDeskButton(desk, cardHasPrimary);
    // The card is the desk's summary now; the old one would just repeat it.
    document.body.setAttribute("data-source-state", status.state);
    document.body.setAttribute(
      "data-has-story",
      latest.storyTitle ? "yes" : "no"
    );
    dimStaleResult(desk, status.state);
  }

  /* An out-of-date answer is still an answer: it stays on screen, dimmed and
   * labelled, so nobody loses work while deciding whether to rebuild. */
  var DIMMED = { risks: "risk-output", matrix: "matrix-output" };

  function dimStaleResult(desk, state) {
    var target = document.getElementById(DIMMED[desk]);
    if (!target) return;
    var old = target.previousElementSibling;
    if (old && old.classList && old.classList.contains("stale-result-note")) {
      old.parentNode.removeChild(old);
    }
    target.classList.remove("stale-result");
    if (state !== "stale" || !target.firstElementChild) return;
    target.classList.add("stale-result");
    var note = el(
      "p",
      "stale-result-note muted small",
      desk === "matrix"
        ? "Built from an older story — press update"
        : "Built from older criteria — press update"
    );
    target.parentNode.insertBefore(note, target);
  }

  /* ---------- wiring ---------- */

  document.addEventListener("click", function (event) {
    var card = document.getElementById("source-card");
    if (!card || !event.target || !event.target.closest) return;
    var desk = card.getAttribute("data-desk");

    var action = event.target.closest(".source-action");
    if (action) {
      /* The card's button is the one that was pressed, so it is the one that
       * has to look busy — the desk's own button says so too, through the
       * same helper. A second press while it runs does nothing. */
      if (window.QAGBusy) {
        var label = action.getAttribute("data-update") === "yes"
          ? UPDATE_LABEL
          : BUSY_LABELS[desk];
        if (!window.QAGBusy.start(action, label)) return;
      }
      pressDesk(desk);
      return;
    }
    if (event.target.closest(".source-example")) {
      var example = document.querySelector(EXAMPLES[desk]);
      if (example) example.click();
      return;
    }
    if (event.target.closest(".source-keep")) {
      var run = window.QAGRun.read();
      window.QAGRun.markBuilt(run, "matrix");
      window.QAGRun.write(run);
    }
  });

  function drawAll() {
    render();
    renderNav();
    renderNext();
  }

  function start() {
    if (!window.QAGRun) return;
    drawAll();
    window.addEventListener(window.QAGRun.CHANGED_EVENT, drawAll);
    // A desk's result can land after this card has drawn.
    window.addEventListener(window.QAGRun.RESULT_EVENT, drawAll);
    // Another tab moved the run on.
    window.addEventListener("storage", function (event) {
      if (!event.key || event.key === window.QAGRun.RUN_KEY) drawAll();
    });
    // The strip arrives with HTMX-swapped result HTML.
    document.body.addEventListener("htmx:afterSwap", drawAll);
    // "3 min ago" has to keep up with the clock.
    setInterval(drawAll, MINUTE);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
