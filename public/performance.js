/* QA-Genius v2: the Performance desk.
 * Builds the budget from the run in sessionStorage, and measures one public
 * page through the server's PageSpeed call. No AI key is read here and no AI
 * is called; the PageSpeed key lives in localStorage and never enters the run.
 * Only server HTML is inserted; everything this file writes goes in through
 * textContent. */
(function () {
  "use strict";

  var RUN_KEY = "qag.run";
  var PSI_KEY = "qag.psi_key";
  var STORY_IN_LINE = 120;

  function byId(id) {
    return document.getElementById(id);
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function readRun() {
    try {
      var raw = sessionStorage.getItem(RUN_KEY);
      var run = raw ? JSON.parse(raw) : null;
      return run && typeof run === "object" ? run : null;
    } catch (e) {
      return null;
    }
  }

  function writeRun(run) {
    try {
      sessionStorage.setItem(RUN_KEY, JSON.stringify(run));
    } catch (e) {
      /* storage blocked: the table still shows, Ship check just will not
       * remember this measurement */
    }
  }

  /* The PageSpeed key is this browser's, like the AI keys: never in the run,
   * never sent anywhere but our own measure route. */
  function readKey() {
    try {
      return localStorage.getItem(PSI_KEY) || "";
    } catch (e) {
      return "";
    }
  }

  function saveKey(value) {
    try {
      if (value) localStorage.setItem(PSI_KEY, value);
      else localStorage.removeItem(PSI_KEY);
    } catch (e) {
      /* nothing to do: the key simply will not be remembered */
    }
  }

  function criteriaTexts(run) {
    if (run && run.test_cases && run.test_cases.criteria) {
      return run.test_cases.criteria;
    }
    return ((run && run.criteria) || []).map(function (one) {
      return typeof one === "string" ? one : (one && one.text) || "";
    });
  }

  function currentCases(run) {
    if (run && run.test_cases && run.test_cases.result) {
      return run.test_cases.result.test_cases || [];
    }
    return [];
  }

  function riskAnalysis(run) {
    if (run && run.risk_analysis && run.risk_analysis.analysis) {
      return run.risk_analysis.analysis;
    }
    return null;
  }

  function runBody(run) {
    var payload = { criteria: criteriaTexts(run), cases: currentCases(run) };
    var risks = riskAnalysis(run);
    if (risks) payload.risk_analysis = risks;
    return payload;
  }

  /* ---------- the page ---------- */

  function show(html) {
    var output = byId("performance-output");
    if (!output) return;
    output.innerHTML = html;
    if (window.htmx) window.htmx.process(output);
    if (window.QAG && window.QAG.initFields) window.QAG.initFields(output);
    rememberMeasurement();
  }

  function failed(message) {
    var output = byId("performance-output");
    if (!output) return;
    output.textContent = "";
    var card = el("div", "card error-card");
    card.appendChild(el("p", null, message));
    output.appendChild(card);
  }

  function summaryLine(run) {
    var card = el("div", "card perf-summary");
    var story = String((run && run.story) || "").trim();
    if (story) {
      card.appendChild(el("span", "eyebrow", "Your story"));
      card.appendChild(
        el(
          "p",
          "perf-story",
          story.length > STORY_IN_LINE
            ? story.slice(0, STORY_IN_LINE) + "…"
            : story
        )
      );
    }
    var criteria = criteriaTexts(run).filter(function (text) {
      return String(text || "").trim() !== "";
    });
    var risks = riskAnalysis(run);
    var modes = risks && risks.failure_modes ? risks.failure_modes.length : 0;
    var line = el("div", "row");
    line.appendChild(
      el(
        "span",
        "muted small",
        criteria.length +
          (criteria.length === 1 ? " criterion · " : " criteria · ") +
          modes +
          (modes === 1 ? " risk" : " risks")
      )
    );
    var edit = el("a", "small", "Edit in Requirements");
    edit.setAttribute("href", "/requirements/story");
    line.appendChild(edit);
    card.appendChild(line);
    return card;
  }

  function choice(name, value, label, checked) {
    var wrap = el("label", "choice");
    var input = el("input");
    input.type = "radio";
    input.name = name;
    input.value = value;
    input.checked = !!checked;
    wrap.appendChild(input);
    wrap.appendChild(document.createTextNode(" " + label));
    return wrap;
  }

  /* The field shape _form_fields.html writes, built with DOM methods. */
  function fieldBox(id, labelText, options) {
    var opts = options || {};
    var box = el("div", "field");
    var label = el("label", null, labelText);
    label.setAttribute("for", id);
    if (opts.optional) {
      label.appendChild(document.createTextNode(" "));
      label.appendChild(el("span", "opt", "(optional)"));
    }
    box.appendChild(label);
    if (opts.hint) {
      var hint = el("p", "hint", opts.hint);
      hint.id = id + "-hint";
      box.appendChild(hint);
    }
    return box;
  }

  function measureForm() {
    var card = el("div", "card card-form");
    card.appendChild(el("h2", null, "Measure the live page"));

    var body = el("div", "form-body");

    var urlField = fieldBox("perf-url", "Page to measure", {
      hint: "A public page — PageSpeed can't reach localhost or private staging."
    });
    var url = el("input");
    url.id = "perf-url";
    url.type = "url";
    url.required = true;
    url.setAttribute("placeholder", "https://example.com/pricing");
    urlField.appendChild(url);
    body.appendChild(urlField);

    var device = el("fieldset", "field");
    var legend = el("legend", "label", "Device");
    device.appendChild(legend);
    device.appendChild(choice("perf-strategy", "mobile", "Mobile", true));
    device.appendChild(choice("perf-strategy", "desktop", "Desktop", false));
    body.appendChild(device);

    var details = document.createElement("details");
    details.id = "perf-key-box";
    var summary = el("summary", null, "PageSpeed API key ");
    summary.appendChild(el("span", "opt", "(optional)"));
    details.appendChild(summary);
    details.appendChild(
      el(
        "p",
        "hint",
        "Google's keyless quota is zero, so a free key from Google Cloud is " +
          "what makes Measure work. Saved in this browser only."
      )
    );
    var keyRow = el("div", "secret-row");
    var key = el("input");
    key.id = "perf-key";
    key.type = "password";
    key.setAttribute("autocomplete", "off");
    key.setAttribute("spellcheck", "false");
    key.setAttribute("placeholder", "Paste your PageSpeed key");
    key.value = readKey();
    var showKey = el("button", "btn btn-small", "Show");
    showKey.type = "button";
    showKey.id = "perf-key-show";
    showKey.setAttribute("aria-pressed", "false");
    showKey.setAttribute("aria-controls", "perf-key");
    keyRow.appendChild(key);
    keyRow.appendChild(showKey);
    details.appendChild(keyRow);
    body.appendChild(details);

    var actions = el("div", "form-actions");
    var run = el("button", "btn btn-primary");
    run.id = "perf-measure";
    run.type = "button";
    run.setAttribute("data-busy-label", "Measuring — up to a minute…");
    run.appendChild(el("span", "btn-label", "Measure live page"));
    actions.appendChild(run);
    var example = el("button", "btn", "Load example");
    example.type = "button";
    example.id = "perf-example";
    actions.appendChild(example);
    body.appendChild(actions);

    body.appendChild(
      el(
        "p",
        "form-note",
        "The page is measured by Google, not by this server. Nothing is stored."
      )
    );
    var progress = el(
      "p",
      "htmx-indicator working",
      "Measuring with PageSpeed — this can take up to a minute…"
    );
    progress.id = "perf-progress";
    progress.insertBefore(el("span", "spin"), progress.firstChild);
    body.appendChild(progress);

    card.appendChild(body);
    return card;
  }

  function emptyState(root) {
    var card = el("div", "card card-form");
    card.appendChild(el("h2", null, "Start from a story"));
    card.appendChild(
      el(
        "p",
        "muted",
        "The budget is built from your acceptance criteria and risks. Check a " +
          "story first, or look at a finished run."
      )
    );
    var actions = el("div", "empty-actions");
    var start = el("a", "btn btn-primary", "Go to Requirements");
    start.setAttribute("href", "/requirements/story");
    actions.appendChild(start);
    var example = el("button", "btn", "Load example");
    example.type = "button";
    example.id = "perf-example";
    actions.appendChild(example);
    card.appendChild(actions);
    root.appendChild(card);
  }

  /* ---------- talking to the server ---------- */

  function post(path, payload) {
    return fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).then(function (response) {
      return response.text();
    });
  }

  function loadBudget(run) {
    post("/performance/budget", runBody(run))
      .then(show)
      .catch(function () {
        failed("Could not build the budget. Reload the page and try again.");
      });
  }

  function busy(button, on) {
    if (!button) return;
    var label = button.querySelector(".btn-label");
    if (on) {
      button.style.minWidth = Math.ceil(button.getBoundingClientRect().width) + "px";
      button.setAttribute("aria-busy", "true");
      if (label) {
        button.setAttribute("data-idle-label", label.textContent);
        label.textContent = button.getAttribute("data-busy-label") || "Working…";
      }
      return;
    }
    button.removeAttribute("aria-busy");
    button.style.minWidth = "";
    var idle = button.getAttribute("data-idle-label");
    if (label && idle !== null) {
      label.textContent = idle;
      button.removeAttribute("data-idle-label");
    }
  }

  function strategy() {
    var picked = document.querySelector('input[name="perf-strategy"]:checked');
    return picked ? picked.value : "mobile";
  }

  function measure() {
    var run = readRun() || {};
    var box = byId("perf-url");
    var url = box ? box.value.trim() : "";
    if (!url) {
      if (box) box.focus();
      return;
    }
    var key = byId("perf-key");
    var value = key ? key.value.trim() : "";
    saveKey(value);

    var button = byId("perf-measure");
    var progress = byId("perf-progress");
    var payload = runBody(run);
    payload.url = url;
    payload.strategy = strategy();
    if (value) payload.psi_key = value;

    busy(button, true);
    if (progress) progress.classList.add("htmx-request");
    post("/performance/measure", payload)
      .then(show)
      .catch(function () {
        failed("Could not reach the server. Try again.");
      })
      .then(function () {
        busy(button, false);
        if (progress) progress.classList.remove("htmx-request");
      });
  }

  function loadExample() {
    fetch("/performance/example")
      .then(function (response) {
        return response.text();
      })
      .then(show)
      .catch(function () {
        failed("Could not load the example. Try again.");
      });
  }

  /* What Ship check reads: the lines, their verdicts and when they were taken. */
  function rememberMeasurement() {
    var holder = byId("performance-data");
    if (!holder) return;
    var data;
    try {
      data = JSON.parse(holder.textContent);
    } catch (e) {
      return;
    }
    if (!data || !data.url) return; // a budget with no measurement yet
    var run = readRun();
    if (!run) return;
    run.performance = data;
    writeRun(run);
  }

  function download(path, filename) {
    var status = byId("performance-download-status");
    if (status) status.textContent = "Building the file…";
    post(path, runBody(readRun() || {}))
      .then(function (text) {
        var blob = new Blob([text], { type: "text/plain" });
        var link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(link.href);
        if (status) status.textContent = "";
      })
      .catch(function () {
        if (status) status.textContent = "Could not build the file. Try again.";
      });
  }

  /* ---------- wiring ---------- */

  document.addEventListener("click", function (event) {
    var target = event.target;
    if (!target || !target.closest) return;
    if (target.closest("#perf-measure")) {
      measure();
      return;
    }
    if (target.closest("#perf-example")) {
      loadExample();
      return;
    }
    if (target.closest("#download-budget-json")) {
      download("/performance/export/lighthouse", "budget.json");
      return;
    }
    if (target.closest("#download-k6")) {
      download("/performance/export/k6", "k6-thresholds.js");
      return;
    }
    var toggle = target.closest("#perf-key-show");
    if (toggle) {
      var key = byId("perf-key");
      if (!key) return;
      var shown = key.type === "text";
      key.type = shown ? "password" : "text";
      toggle.setAttribute("aria-pressed", shown ? "false" : "true");
      toggle.textContent = shown ? "Show" : "Hide";
      key.focus();
    }
  });

  function render() {
    var root = byId("performance-root");
    if (!root) return;
    root.textContent = "";
    var run = readRun();
    if (!run || !String(run.story || "").trim()) {
      emptyState(root);
      return;
    }
    root.appendChild(summaryLine(run));
    root.appendChild(measureForm());
    if (window.QAG && window.QAG.initFields) window.QAG.initFields(root);
    // A run with no criteria still gets the published defaults.
    loadBudget(run);
  }

  document.addEventListener("DOMContentLoaded", render);
})();
