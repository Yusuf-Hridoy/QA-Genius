/* QA-Genius v2: the Risk radar page (FMEA over the current run).
 * The run lives in sessionStorage under "qag.run", the same key the
 * Requirements flow uses. Nothing is stored on the server: every request
 * carries the story, the criteria and the test cases the browser holds. */
(function () {
  "use strict";

  var RUN_KEY = "qag.run";
  var RESCORE_DELAY = 400;
  /* The same limits the server checks, so a reason is never written twice. */
  var MIN_REASON = 10;
  var MAX_REASON = 300;
  var MAX_OWNER = 60;
  var rescoreTimer = null;

  function readRun() {
    try {
      var raw = sessionStorage.getItem(RUN_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  }

  /* Set while this desk is the one writing. Saving our own result tells
   * every card the run moved on, and that echo used to start a second
   * recheck - which relabelled a hand-adjusted score as a code recheck. */
  var writingOurOwn = false;

  /* One writer for the whole app: run_state.js stamps the fingerprints and
   * tells every card and the sidebar that the run moved on. */
  function writeRun(run) {
    if (typeof window !== "undefined" && window.QAGRun) {
      writingOurOwn = true;
      try {
        window.QAGRun.write(run);
      } finally {
        writingOurOwn = false;
      }
      return;
    }
    try {
      sessionStorage.setItem(RUN_KEY, JSON.stringify(run));
    } catch (e) {
      /* storage blocked: the page still works, the run just will not survive */
    }
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function closest(target, selector) {
    if (!target || !target.closest) return null;
    return target.closest(selector);
  }

  function criteriaTexts(run) {
    return (run && run.criteria ? run.criteria : [])
      .map(function (c) {
        return typeof c === "string" ? c : (c && c.text) || "";
      })
      .filter(function (text) {
        return text.trim() !== "";
      });
  }

  /* The test cases the user last accepted on step 3, which is what the
   * coverage check must run against. */
  function currentCases(run) {
    if (run && run.test_cases && run.test_cases.result) {
      return run.test_cases.result.test_cases || [];
    }
    return [];
  }

  function savedAnalysis() {
    var run = readRun();
    if (!run || !run.risk_analysis || !run.risk_analysis.analysis) return null;
    return run.risk_analysis.analysis;
  }

  /* ---------- the page ---------- */

  /* One criterion per blank-line-separated block, the same rule step 2's
   * paste form uses. That one lives inside requirements_flow.js and is not
   * shared, so the rule is repeated here rather than reached across for. */
  function criteriaBlocks(text) {
    return (text || "").split(/\n\s*\n/).filter(function (block) {
      return block.trim() !== "";
    });
  }

  function labelledBox(id, labelText, rows, placeholder, hint, options) {
    var opts = options || {};
    var field = el("div", "field");
    var label = el("label", null, labelText);
    label.setAttribute("for", id);
    if (opts.optional) {
      label.appendChild(document.createTextNode(" "));
      label.appendChild(el("span", "opt", "(optional)"));
    }
    field.appendChild(label);
    if (hint) {
      var hintLine = el("p", "hint", hint);
      hintLine.id = id + "-hint";
      field.appendChild(hintLine);
    }
    var box = el("textarea");
    box.id = id;
    box.setAttribute("rows", String(rows));
    box.setAttribute("placeholder", placeholder);
    field.appendChild(box);
    if (opts.max) {
      var under = el("div", "field-under");
      var help = el("span", null, "");
      help.id = id + "-help";
      under.appendChild(help);
      var counter = el("span", "counter", "0 / " + opts.max);
      counter.setAttribute("data-for", id);
      counter.setAttribute("data-max", String(opts.max));
      counter.setAttribute("aria-live", "polite");
      under.appendChild(counter);
      field.appendChild(under);
    }
    return { field: field, box: box };
  }

  /* Risk radar used to dead-end here with two links off the page. It is a
   * desk of its own now: paste a story and run, no Requirements visit. */
  function emptyState(root) {
    var card = el("div", "card card-form");
    card.setAttribute("data-input-card", "Your story");
    card.appendChild(el("h2", null, "How can this feature fail?"));
    card.appendChild(
      el(
        "p",
        "muted",
        "Paste a story and its acceptance criteria, or start in Requirements."
      )
    );

    var form = el("form");
    form.id = "risk-paste-form";
    form.setAttribute("hx-post", "/risks/run");
    form.setAttribute("hx-target", "#risk-output");
    form.setAttribute("hx-swap", "innerHTML");
    form.setAttribute("hx-indicator", "#risk-paste-progress");

    var body = el("div", "form-body");

    var story = labelledBox(
      "risk-paste-story",
      "User story",
      4,
      "As a shopper, I want…",
      "",
      { max: 3000 }
    );
    story.box.setAttribute("maxlength", "3000");
    story.box.required = true;
    body.appendChild(story.field);

    var criteria = labelledBox(
      "risk-paste-criteria",
      "Acceptance criteria",
      6,
      "One criterion per block, separated by a blank line.",
      "One criterion per block. Risk radar runs without them.",
      { optional: true }
    );
    body.appendChild(criteria.field);
    form.appendChild(body);

    ["user_story", "criteria_json", "cases_json"].forEach(function (name) {
      var input = el("input");
      input.type = "hidden";
      input.name = name;
      form.appendChild(input);
    });

    var actions = el("div", "form-actions");
    var find = el("button", "btn btn-primary");
    find.id = "risk-paste-find";
    find.type = "submit";
    find.setAttribute("data-busy-label", "Finding risks…");
    find.appendChild(el("span", "btn-label", "Find risks"));
    actions.appendChild(find);
    actions.appendChild(exampleButton());
    var link = el("a", "btn btn-ghost", "Start in Requirements");
    link.setAttribute("href", "/requirements/story");
    actions.appendChild(link);
    body.appendChild(actions);

    var progress = el("p", "htmx-indicator working", "Thinking about how this can fail…");
    progress.insertBefore(el("span", "spin"), progress.firstChild);
    progress.id = "risk-paste-progress";
    body.appendChild(progress);

    card.appendChild(form);
    root.appendChild(card);
    if (window.QAG && window.QAG.initFields) window.QAG.initFields(root);

    /* What is pasted becomes the run, exactly as a checked story would:
     * a new story owns the run, so nothing from an older one survives. */
    form.addEventListener("htmx:configRequest", function (event) {
      /* HTMX events bubble, so Load example - a button that happens to sit
       * inside this form - used to be cancelled by the empty-story guard
       * below and silently do nothing. Only the form's own submit is ours. */
      if (event.detail.elt !== form) return;
      var text = story.box.value.trim();
      if (!text) {
        event.preventDefault();
        story.box.focus();
        return;
      }
      var blocks = criteriaBlocks(criteria.box.value);
      writeRun({
        story: text,
        story_type: "User story",
        context: "",
        criteria: blocks.map(function (block, index) {
          return { id: "AC-" + (index + 1), text: block };
        }),
        autorun_test_cases: false
      });
      event.detail.parameters.user_story = text;
      event.detail.parameters.criteria_json = JSON.stringify(blocks);
      event.detail.parameters.cases_json = "[]";
    });
  }

  function exampleButton() {
    var example = el("button", "btn", "Load example");
    example.id = "risk-example";
    example.setAttribute("type", "button");
    example.setAttribute("hx-post", "/risks/example");
    example.setAttribute("hx-target", "#risk-output");
    example.setAttribute("hx-swap", "innerHTML");
    return example;
  }

  function renderPage() {
    var root = document.getElementById("risk-root");
    if (!root) return;
    root.textContent = "";
    var run = readRun();
    if (!run || !run.story) {
      emptyState(root);
      if (window.htmx) window.htmx.process(root);
      if (window.QAG && window.QAG.initInputCards) window.QAG.initInputCards(root);
      return;
    }
    var criteria = criteriaTexts(run);
    var cases = currentCases(run);

    var card = el("div", "card");
    card.setAttribute("data-input-card", "Your run");
    card.appendChild(el("h2", null, "How can this feature fail?"));
    card.appendChild(el("p", "muted", (run.story || "").slice(0, 120)));
    var line = el("p", "muted small");
    line.appendChild(
      document.createTextNode(
        criteria.length +
          " criteria · " +
          cases.length +
          " test cases · "
      )
    );
    var edit = el("a", null, "Edit in Requirements");
    edit.setAttribute("href", "/requirements/story");
    line.appendChild(edit);
    card.appendChild(line);

    var form = el("form", "risk-form");
    form.id = "risk-form";
    form.setAttribute("hx-post", "/risks/run");
    form.setAttribute("hx-target", "#risk-output");
    form.setAttribute("hx-swap", "innerHTML");
    form.setAttribute("hx-indicator", "#risk-progress");

    ["user_story", "criteria_json", "cases_json"].forEach(function (name) {
      var input = el("input");
      input.type = "hidden";
      input.name = name;
      form.appendChild(input);
    });

    var actions = el("div", "form-actions");
    var find = el("button", "btn btn-primary");
    find.id = "risk-find";
    find.type = "submit";
    find.setAttribute("data-busy-label", "Finding risks…");
    find.appendChild(el("span", "btn-label", "Find risks"));
    actions.appendChild(find);
    actions.appendChild(exampleButton());
    form.appendChild(actions);

    var progress = el(
      "p",
      "htmx-indicator working",
      "Thinking about how this can fail…"
    );
    progress.insertBefore(el("span", "spin"), progress.firstChild);
    progress.id = "risk-progress";
    form.appendChild(progress);
    card.appendChild(form);
    root.appendChild(card);

    if (window.htmx) window.htmx.process(root);
    if (window.QAG && window.QAG.initInputCards) window.QAG.initInputCards(root);

    /* Always send what sessionStorage holds right now. */
    form.addEventListener("htmx:configRequest", function (event) {
      var latest = readRun() || run;
      event.detail.parameters.user_story = latest.story || "";
      event.detail.parameters.criteria_json = JSON.stringify(
        criteriaTexts(latest)
      );
      event.detail.parameters.cases_json = JSON.stringify(currentCases(latest));
    });

    /* Arrived from "Find risks" on the story result: run once, then clear the
     * flag so a refresh does not spend another AI call. */
    if (run.autorun_risks) {
      run.autorun_risks = false;
      writeRun(run);
      if (window.htmx) window.htmx.trigger(form, "submit");
    }
  }

  /* ---------- the result card ---------- */

  function displayedData() {
    var holder = document.getElementById("risk-data");
    if (!holder) return null;
    try {
      return JSON.parse(holder.textContent);
    } catch (e) {
      return null;
    }
  }

  /* Test cases changing is code's problem, not the model's: coverage is
   * re-scored here and the analysis is marked current again, with no AI call
   * and no click. Story or criteria changing is a different matter - that
   * needs the user to press Update. */
  function autoRecheck() {
    if (!window.QAGRun) return;
    var run = window.QAGRun.read();
    var status = window.QAGRun.statusOf("risks", run);
    var analysis = savedAnalysis();
    if (!analysis) return;
    /* Anything but a fresh analysis with new test cases is only redrawn: the
     * page shows what you had (dimmed, when it is out of date) and leaves the
     * decision to rebuild to you. */
    if (status.state !== "fresh" || !status.auto) {
      rescore(analysis, null, true, "code");
      return;
    }
    rescore(
      analysis,
      function () {
        var latest = window.QAGRun.read();
        latest.risk_analysis_rechecked = {
          at: new Date().toISOString(),
          cases: currentCases(latest).length
        };
        window.QAGRun.markBuilt(latest, "risk_analysis");
        writeRun(latest);
      },
      false,
      "code"
    );
  }

  /* A loaded sample is kept so the page keeps working, but flagged so the
   * freshness card calls it a sample rather than your latest work. */
  function markExample(run, key, scope) {
    var sample = (scope || document).querySelector("[data-is-example]");
    if (sample) run[key + "_is_example"] = true;
    else delete run[key + "_is_example"];
    return run;
  }

  function rememberDisplayed() {
    var shown = displayedData();
    if (!shown) return;
    var run = readRun() || {};
    run.risk_analysis = shown;
    markExample(run, "risk_analysis", document.getElementById("risk-output"));
    writeRun(run);
  }

  /* The body every risk request takes: the analysis plus the run it belongs to. */
  function rescoreBody(analysis) {
    var run = readRun() || {};
    var shown = displayedData() || {};
    var cases = currentCases(run);
    return {
      analysis: analysis || shown.analysis || { failure_modes: [] },
      cases: cases.length ? cases : shown.cases || [],
      criteria: criteriaTexts(run).length
        ? criteriaTexts(run)
        : shown.criteria || [],
      /* The register carries what was accepted, so a downloaded file says
       * why a risk with no test was signed off and who is watching it. */
      risk_acceptances: run.risk_acceptances || {}
    };
  }

  /* `remember` is false when the analysis is only being redrawn: writing it
   * back would re-stamp the fingerprints and call an out-of-date desk current. */
  function showResult(html, remember) {
    var target = document.getElementById("risk-output");
    if (!target) return;
    target.innerHTML = html;
    if (window.htmx) window.htmx.process(target);
    if (remember !== false) rememberDisplayed();
    /* The first risk is the one on screen until someone picks another, and
     * any risk already accepted says so on its card. */
    pickFirstRisk();
    paintAcceptances();
    paintPagePill();
    // The card may need to dim what just landed.
    if (window.QAGRun) window.QAGRun.announceResult();
  }

  /* `by` is what the footer will say: "code" for the automatic recheck,
   * "scores" when someone moved a score themselves. */
  function rescore(analysis, done, quiet, by) {
    var body = rescoreBody(analysis);
    if (!body.analysis.failure_modes || !body.analysis.failure_modes.length) {
      return;
    }
    fetch("/risks/rescore?by=" + (by || "scores"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    })
      .then(function (response) {
        if (!response.ok) throw new Error("rescore failed");
        return response.text();
      })
      .then(function (html) {
        showResult(html, !quiet);
        if (done) done();
      })
      .catch(function () {
        /* Leave what is on screen alone; the saved run is still intact. */
      });
  }

  /* An edited score goes back to the server, which owns the formula. */
  function editedAnalysis() {
    var data = displayedData();
    if (!data || !data.analysis) return null;
    var analysis = JSON.parse(JSON.stringify(data.analysis));
    var inputs = document.querySelectorAll(".score-input");
    Array.prototype.forEach.call(inputs, function (input) {
      var riskId = input.getAttribute("data-risk-id");
      var field = input.getAttribute("data-field");
      (analysis.failure_modes || []).forEach(function (risk) {
        if (risk.id === riskId) risk[field] = input.value;
      });
    });
    return analysis;
  }

  function queueRescore() {
    if (rescoreTimer) window.clearTimeout(rescoreTimer);
    rescoreTimer = window.setTimeout(function () {
      rescoreTimer = null;
      var analysis = editedAnalysis();
      if (analysis) rescore(analysis);
    }, RESCORE_DELAY);
  }

  function filterTo(ids) {
    var cards = document.querySelectorAll("#risk-list .risk-card");
    Array.prototype.forEach.call(cards, function (card) {
      var id = card.getAttribute("data-risk-id");
      card.hidden = ids !== null && ids.indexOf(id) === -1;
    });
    var cells = document.querySelectorAll(".heat-cell");
    Array.prototype.forEach.call(cells, function (cell) {
      cell.classList.remove("picked");
    });
    var link = document.getElementById("risk-show-all");
    if (link) link.hidden = ids === null;
  }

  function pickCell(cell) {
    var raw = cell.getAttribute("data-ids") || "";
    var ids = raw ? raw.split(",") : [];
    if (!ids.length) return;
    filterTo(ids);
    cell.classList.add("picked");
  }

  function download(kind, filename) {
    var body = rescoreBody(null);
    fetch("/risks/export." + kind, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    })
      .then(function (response) {
        if (!response.ok) throw new Error("export failed");
        return response.blob();
      })
      .then(function (blob) {
        var url = URL.createObjectURL(blob);
        var link = document.createElement("a");
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      })
      .catch(function () {
        /* Nothing downloaded; the page is unchanged. */
      });
  }

  /* ---------- Write a test ---------- */

  /* It used to send the reader to the test-cases desk and leave them to work
   * out whether anything had been written for the risk they pressed on. The
   * call happens here now, and the answer lands at the top of that risk's
   * own panel: the ids that were added, or why none were. */

  var HISTORY_MAX = 5;

  function riskIdsOn(button) {
    return (button.getAttribute("data-risk-ids") || "").split(",").filter(Boolean);
  }

  function pickedRisks(data, ids) {
    return (data.analysis.failure_modes || [])
      .filter(function (risk) {
        return ids.indexOf(risk.id) !== -1;
      })
      .map(function (risk) {
        return {
          id: risk.id,
          category: risk.category,
          title: risk.title,
          test_idea: risk.test_idea || ""
        };
      });
  }

  function savedCases(run) {
    if (run && run.test_cases) return run.test_cases;
    return { result: { test_cases: [], summary: "" }, criteria: [] };
  }

  function caseIds(payload) {
    var cases = payload && payload.result ? payload.result.test_cases || [] : [];
    return cases.map(function (one) {
      return one && one.id;
    });
  }

  /* The ids in the proposal that the saved list does not already have. */
  function addedIds(before, after) {
    var had = caseIds(before);
    return caseIds(after).filter(function (id) {
      return id && had.indexOf(id) === -1;
    });
  }

  /* The panel beside the list, for the risk the button belongs to. */
  function panelFor(riskId) {
    var panels = document.querySelectorAll("#risk-trace .risk-detail");
    var found = null;
    Array.prototype.forEach.call(panels, function (panel) {
      if (panel.getAttribute("data-risk-id") === riskId) found = panel;
    });
    return found;
  }

  /* One line at the top of that panel, where the reader is already looking.
   * It replaces whatever the last press left there. */
  function sayOnRisk(riskId, words, tone, link) {
    var panel = panelFor(riskId);
    if (!panel) return;
    var old = panel.querySelector(".risk-written");
    if (old) panel.removeChild(old);
    var note = el("p", "risk-written note note-" + tone, words);
    note.setAttribute("role", "status");
    if (link) {
      note.appendChild(document.createTextNode(" "));
      var go = el("a", "risk-written-link", "View on Test cases →");
      go.setAttribute("href", "/requirements/test-cases");
      note.appendChild(go);
    }
    panel.insertBefore(note, panel.firstChild);
    pickRisk(riskId);
  }

  function busyOn(button, on) {
    button.disabled = on;
    button.setAttribute("aria-busy", on ? "true" : "false");
    if (on) {
      button.setAttribute("data-said", button.textContent);
      button.textContent = "Writing…";
    } else {
      button.textContent = button.getAttribute("data-said") || "Write a test";
    }
  }

  /* The proposal the refine route returns, read out of the HTML it sends. */
  function proposalIn(html) {
    try {
      var holder = document.createElement("div");
      holder.innerHTML = html;
      var block = holder.querySelector("#tc-proposed");
      return block ? JSON.parse(block.textContent) : null;
    } catch (e) {
      return null;
    }
  }

  /* The plain words out of whatever card the route sent back instead. */
  function reasonIn(html) {
    try {
      var holder = document.createElement("div");
      holder.innerHTML = html;
      var line = holder.querySelector("p");
      return line ? line.textContent.trim() : "";
    } catch (e) {
      return "";
    }
  }

  function keyHeader() {
    var headers = { "X-QAG-Keys": "[]" };
    if (window.QAG && window.QAG.headerKeys) {
      headers["X-QAG-Keys"] = JSON.stringify(window.QAG.headerKeys());
    }
    return headers;
  }

  function nothingWritten(ids) {
    return (
      "The AI didn't return a test for " +
      ids.join(", ") +
      ". Try again, or write one yourself on the Test cases page."
    );
  }

  function addedWords(added) {
    return (
      "Added " +
      added.length +
      " test" +
      (added.length === 1 ? "" : "s") +
      ": " +
      added.join(", ") +
      "."
    );
  }

  function writeTests(button) {
    var data = displayedData();
    button = button || document.getElementById("risk-write-tests");
    if (!data || !data.analysis || !button) return;
    var ids = riskIdsOn(button);
    var picked = pickedRisks(data, ids);
    if (!picked.length) return;
    var first = ids[0];
    var run = readRun() || {};
    var before = savedCases(run);

    /* Nothing to refine yet: the desk that writes the first list is step 3,
     * and that is where the reader is taken, with the risks in hand. */
    if (!caseIds(before).length) {
      run.pending_risks = picked;
      writeRun(run);
      window.location.href = "/requirements/test-cases";
      return;
    }

    var body = new FormData();
    body.append("mode", "risks");
    body.append("risks_json", JSON.stringify(picked));
    body.append("user_story", String(run.story || ""));
    body.append("context", String(run.context || ""));
    body.append(
      "criteria_json",
      JSON.stringify(before.criteria || criteriaTexts(run))
    );
    body.append("current_json", JSON.stringify(before.result || {}));

    busyOn(button, true);
    fetch("/requirements/test-cases/refine", {
      method: "POST",
      headers: keyHeader(),
      body: body
    })
      .then(function (response) {
        return response.text();
      })
      .then(function (html) {
        var proposal = proposalIn(html);
        if (!proposal) {
          /* No key, or the model refused: the card the route sent says
           * which, in its own words, and that is what is shown. */
          sayOnRisk(first, reasonIn(html) || nothingWritten(ids), "warn", false);
          return;
        }
        var added = addedIds(before, proposal);
        if (!added.length) {
          /* "+0 added" is not a success and is never dressed up as one. */
          sayOnRisk(first, nothingWritten(ids), "warn", false);
          return;
        }
        keepProposal(proposal);
        sayOnRisk(first, addedWords(added), "ok", true);
      })
      .catch(function () {
        sayOnRisk(first, nothingWritten(ids), "warn", false);
      })
      .then(function () {
        busyOn(button, false);
      });
  }

  /* The new list, with the old one on the undo stack the test-cases desk
   * reads, so Undo there brings back exactly what was there before. */
  function keepProposal(proposal) {
    var run = readRun() || {};
    var history = run.test_cases_history || [];
    if (run.test_cases) {
      history.push(run.test_cases);
      while (history.length > HISTORY_MAX) history.shift();
    }
    run.test_cases_history = history;
    run.test_cases = proposal;
    writeRun(run);
  }

  /* The counts beside the page title, read off what is on screen. */
  function paintPagePill() {
    if (!window.QAG || !window.QAG.setPagePill) return;
    var cards = document.querySelectorAll("#risk-list .risk-card");
    if (!cards.length) {
      window.QAG.setPagePill("");
      return;
    }
    var untested = 0;
    Array.prototype.forEach.call(cards, function (card) {
      /* The same bucket the stat card counts: a high risk with no test, and
       * one whose only evidence is a claim the words do not back. */
      var coverage = card.getAttribute("data-coverage");
      if (
        card.getAttribute("data-level") === "high" &&
        (coverage === "none" || coverage === "weak")
      ) {
        untested += 1;
      }
    });
    window.QAG.setPagePill(
      cards.length + " risks · " + untested + " high with no test"
    );
  }

  /* ---------- picking a risk, and accepting one ---------- */

  /* The card you picked, and the evidence panel beside it, are one choice. */
  function pickRisk(riskId) {
    var cards = document.querySelectorAll("#risk-list .risk-card");
    Array.prototype.forEach.call(cards, function (card) {
      card.classList.toggle("picked", card.getAttribute("data-risk-id") === riskId);
    });
    var details = document.querySelectorAll("#risk-trace .risk-detail");
    Array.prototype.forEach.call(details, function (detail) {
      detail.hidden = detail.getAttribute("data-risk-id") !== riskId;
    });
  }

  /* The first risk is shown until someone picks another one. */
  function pickFirstRisk() {
    var first = document.querySelector("#risk-list .risk-card");
    if (first) pickRisk(first.getAttribute("data-risk-id"));
  }

  function acceptances() {
    var run = readRun() || {};
    return run.risk_acceptances || {};
  }

  function acceptanceFor(riskId) {
    var one = acceptances()[riskId];
    if (!one) return null;
    if (typeof one === "string") return { reason: one, owner: "", review_date: "" };
    return one;
  }

  function datePassed(text) {
    if (!text) return false;
    var today = new Date();
    var day = new Date(text + "T00:00:00");
    if (isNaN(day.getTime())) return false;
    today.setHours(0, 0, 0, 0);
    return day < today;
  }

  /* What an accepted risk says on the card and in the panel. */
  function paintAcceptances() {
    var cards = document.querySelectorAll("#risk-list .risk-card");
    Array.prototype.forEach.call(cards, function (card) {
      var riskId = card.getAttribute("data-risk-id");
      var one = acceptanceFor(riskId);
      var chip = card.querySelector(".risk-accepted-chip");
      if (chip) {
        chip.hidden = !one;
        var passed = one && datePassed(one.review_date);
        chip.textContent = passed ? "Review date passed" : "Accepted";
        chip.className =
          "chip risk-accepted-chip " + (passed ? "chip-bad" : "chip-ok");
      }
      var box = document.querySelector('.risk-accept[data-risk-id="' + riskId + '"]');
      if (!box) return;
      var line = box.querySelector(".risk-accepted-line");
      var open = box.querySelector(".risk-accept-open");
      var remove = box.querySelector(".risk-accept-remove");
      if (line) {
        line.hidden = !one;
        if (one) {
          var parts = ["Accepted: " + one.reason];
          if (one.owner) parts.push("Owner: " + one.owner);
          if (one.review_date) {
            parts.push(
              (datePassed(one.review_date) ? "Review date passed " : "Review by ") +
                one.review_date
            );
          }
          line.textContent = parts.join(" · ");
        }
      }
      if (open) open.textContent = one ? "Change" : "Accept this risk";
      if (remove) remove.hidden = !one;
    });
  }

  function acceptForm(riskId) {
    return document.querySelector('.risk-accept-form[data-risk-id="' + riskId + '"]');
  }

  function openAccept(riskId) {
    var form = acceptForm(riskId);
    if (!form) return;
    var one = acceptanceFor(riskId);
    var reason = form.querySelector(".risk-reason");
    var owner = form.querySelector(".risk-owner");
    var review = form.querySelector(".risk-review");
    if (one) {
      if (reason) reason.value = one.reason || "";
      if (owner) owner.value = one.owner || "";
      if (review) review.value = one.review_date || "";
    }
    form.hidden = false;
    if (reason) reason.focus();
  }

  function saveAccept(riskId) {
    var form = acceptForm(riskId);
    if (!form) return;
    var reason = form.querySelector(".risk-reason");
    var status = form.querySelector(".risk-accept-status");
    var text = reason ? reason.value.trim() : "";
    if (text.length < MIN_REASON || text.length > MAX_REASON) {
      if (status) {
        status.textContent =
          "Write between " + MIN_REASON + " and " + MAX_REASON + " characters.";
      }
      return;
    }
    var owner = form.querySelector(".risk-owner");
    var review = form.querySelector(".risk-review");
    var run = readRun() || {};
    if (!run.risk_acceptances) run.risk_acceptances = {};
    run.risk_acceptances[riskId] = {
      reason: text,
      owner: owner ? owner.value.trim().slice(0, MAX_OWNER) : "",
      review_date: review ? review.value : ""
    };
    writeRun(run);
    form.hidden = true;
    if (status) status.textContent = "";
    paintAcceptances();
  }

  function removeAccept(riskId) {
    var run = readRun() || {};
    if (run.risk_acceptances) delete run.risk_acceptances[riskId];
    writeRun(run);
    var form = acceptForm(riskId);
    if (form) form.hidden = true;
    paintAcceptances();
  }

  document.addEventListener("click", function (event) {
    var acceptOpen = closest(event.target, ".risk-accept-open");
    if (acceptOpen) {
      openAccept(acceptOpen.getAttribute("data-risk-id"));
      return;
    }
    var acceptSave = closest(event.target, ".risk-accept-save");
    if (acceptSave) {
      saveAccept(acceptSave.getAttribute("data-risk-id"));
      return;
    }
    var acceptCancel = closest(event.target, ".risk-accept-cancel");
    if (acceptCancel) {
      var shut = acceptForm(acceptCancel.getAttribute("data-risk-id"));
      if (shut) shut.hidden = true;
      return;
    }
    var acceptRemove = closest(event.target, ".risk-accept-remove");
    if (acceptRemove) {
      removeAccept(acceptRemove.getAttribute("data-risk-id"));
      return;
    }
    var writeOne = closest(event.target, ".risk-write-one");
    if (writeOne) {
      writeTests(writeOne);
      return;
    }
    var card = closest(event.target, ".risk-card");
    if (card) {
      pickRisk(card.getAttribute("data-risk-id"));
      return;
    }
    var cell = closest(event.target, ".heat-cell");
    if (cell) {
      pickCell(cell);
      return;
    }
    if (closest(event.target, "#risk-show-all")) {
      event.preventDefault();
      filterTo(null);
      return;
    }
    if (closest(event.target, "#risk-download-csv")) {
      download("csv", "qa-genius-risk-register.csv");
      return;
    }
    if (closest(event.target, "#risk-download-xlsx")) {
      download("xlsx", "qa-genius-risk-register.xlsx");
      return;
    }
    if (closest(event.target, "#risk-write-tests")) {
      writeTests(null);
    }
  });

  /* A card is a button, so the keyboard picks one the same way. */
  document.addEventListener("keydown", function (event) {
    if (event.key !== "Enter" && event.key !== " ") return;
    var card = closest(event.target, ".risk-card");
    if (!card) return;
    event.preventDefault();
    pickRisk(card.getAttribute("data-risk-id"));
  });

  document.addEventListener("input", function (event) {
    if (!closest(event.target, ".score-input")) return;
    queueRescore();
  });

  document.addEventListener("change", function (event) {
    if (!closest(event.target, ".score-input")) return;
    queueRescore();
  });

  document.addEventListener("htmx:afterSwap", function (event) {
    var detail = event.detail;
    var path = detail && detail.pathInfo ? detail.pathInfo.requestPath : "";
    if (!path && detail && detail.xhr) path = detail.xhr.responseURL || "";
    if (path.indexOf("/risks/") === -1) return;
    rememberDisplayed();
    pickFirstRisk();
    paintAcceptances();
    paintPagePill();
  });

  document.addEventListener("DOMContentLoaded", function () {
    renderPage();
    /* Coming back from step 3: re-score against the test cases that exist now,
     * so a case tagged risk:R1 shows as verified straight away. */
    autoRecheck();
  });

  /* Another tab, or step 3 in this one, moved the run on. Our own saves
   * are not news, so they do not start a recheck. */
  if (window.QAGRun) {
    window.addEventListener(window.QAGRun.CHANGED_EVENT, function () {
      if (writingOurOwn) return;
      autoRecheck();
    });
  }

  /* The pure parts of "Write a test", for the unit tests in tests/js. What
   * counts as added, and the exact words said about it either way, are
   * worth pinning down away from a browser. */
  if (typeof window !== "undefined") {
    window.QAGRisks = {
      caseIds: caseIds,
      addedIds: addedIds,
      addedWords: addedWords,
      nothingWritten: nothingWritten
    };
  }
})();
