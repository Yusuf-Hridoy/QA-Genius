/* QA-Genius v2: the Risk radar page (FMEA over the current run).
 * The run lives in sessionStorage under "qag.run", the same key the
 * Requirements flow uses. Nothing is stored on the server: every request
 * carries the story, the criteria and the test cases the browser holds. */
(function () {
  "use strict";

  var RUN_KEY = "qag.run";
  var RESCORE_DELAY = 400;
  var rescoreTimer = null;

  function readRun() {
    try {
      var raw = sessionStorage.getItem(RUN_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  }

  function writeRun(run) {
    try {
      sessionStorage.setItem(RUN_KEY, JSON.stringify(run));
    } catch (e) {
      /* Storage blocked: the page still works, the run just does not survive. */
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

  function emptyState(root) {
    var card = el("div", "card");
    card.appendChild(el("h2", null, "Start from a story"));
    card.appendChild(
      el(
        "p",
        "muted",
        "Risk radar reads the story, the acceptance criteria and the test " +
          "cases from your current run."
      )
    );
    var link = el("a", "btn btn-primary", "Go to Requirements");
    link.setAttribute("href", "/requirements/story");
    var actions = el("div", "row");
    actions.appendChild(link);
    actions.appendChild(exampleButton());
    card.appendChild(actions);
    root.appendChild(card);
  }

  function exampleButton() {
    var example = el("button", "btn", "Load example");
    example.setAttribute("type", "button");
    example.setAttribute("hx-get", "/risks/example");
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
      return;
    }
    var criteria = criteriaTexts(run);
    var cases = currentCases(run);

    var card = el("div", "card");
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

    var actions = el("div", "row");
    var find = el("button", "btn btn-primary");
    find.id = "risk-find";
    find.type = "submit";
    find.appendChild(el("span", "btn-label", "Find risks"));
    actions.appendChild(find);
    actions.appendChild(exampleButton());
    form.appendChild(actions);

    var progress = el(
      "p",
      "htmx-indicator muted",
      "Thinking about how this can fail…"
    );
    progress.id = "risk-progress";
    form.appendChild(progress);
    card.appendChild(form);
    root.appendChild(card);

    if (window.htmx) window.htmx.process(root);

    /* Always send what sessionStorage holds right now. */
    form.addEventListener("htmx:configRequest", function (event) {
      var latest = readRun() || run;
      event.detail.parameters.user_story = latest.story || "";
      event.detail.parameters.criteria_json = JSON.stringify(
        criteriaTexts(latest)
      );
      event.detail.parameters.cases_json = JSON.stringify(currentCases(latest));
    });
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

  function rememberDisplayed() {
    var shown = displayedData();
    if (!shown) return;
    var run = readRun() || {};
    run.risk_analysis = shown;
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
        : shown.criteria || []
    };
  }

  function showResult(html) {
    var target = document.getElementById("risk-output");
    if (!target) return;
    target.innerHTML = html;
    if (window.htmx) window.htmx.process(target);
    rememberDisplayed();
  }

  function rescore(analysis) {
    var body = rescoreBody(analysis);
    if (!body.analysis.failure_modes || !body.analysis.failure_modes.length) {
      return;
    }
    fetch("/risks/rescore", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    })
      .then(function (response) {
        if (!response.ok) throw new Error("rescore failed");
        return response.text();
      })
      .then(showResult)
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

  /* Hand the untested high risks to step 3, which writes the test cases. */
  function writeTests() {
    var data = displayedData();
    var button = document.getElementById("risk-write-tests");
    if (!data || !data.analysis || !button) return;
    var ids = (button.getAttribute("data-risk-ids") || "")
      .split(",")
      .filter(Boolean);
    var picked = (data.analysis.failure_modes || [])
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
    if (!picked.length) return;
    var run = readRun() || {};
    run.pending_risks = picked;
    writeRun(run);
    window.location.href = "/requirements/test-cases";
  }

  document.addEventListener("click", function (event) {
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
      writeTests();
    }
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
  });

  document.addEventListener("DOMContentLoaded", function () {
    renderPage();
    /* Coming back from step 3: re-score against the test cases that exist now,
     * so a case tagged risk:R1 shows as verified straight away. */
    var analysis = savedAnalysis();
    if (analysis) rescore(analysis);
  });
})();
