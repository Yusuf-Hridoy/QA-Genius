/* QA-Genius v2: the Requirements flow (story -> criteria -> test cases -> automation).
 * The run lives in sessionStorage under "qag.run" and never reaches the
 * server as stored state. Criterion ids are always recomputed from position,
 * so AC-1..AC-n follow the order on screen. */
(function () {
  "use strict";

  var RUN_KEY = "qag.run";
  var FOCUS_OPTIONS = ["Functional", "Negative", "Boundary", "Edge Case"];
  var HISTORY_MAX = 5;
  var MAX_SELECTED = 12;
  /* These must match FRAMEWORK_OPTIONS, STRUCTURE_OPTIONS and BROWSER_OPTIONS
   * in qagenius/automation.py; the server refuses anything else. */
  var FRAMEWORK_CHOICES = [
    "Playwright · TypeScript",
    "Playwright · JavaScript",
    "Playwright · Python",
    "Cypress · JavaScript",
    "Selenium · Python"
  ];
  var STRUCTURE_CHOICES = ["Page Object Model", "Flat scripts"];
  var BROWSER_CHOICES = ["chromium", "firefox", "webkit"];

  function readRun() {
    try {
      var raw = sessionStorage.getItem(RUN_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  }

  /* One writer for the whole app: run_state.js stamps the fingerprints and
   * tells every card and the sidebar that the run moved on. */
  function writeRun(run) {
    if (typeof window !== "undefined" && window.QAGRun) {
      window.QAGRun.write(run);
      return;
    }
    try {
      sessionStorage.setItem(RUN_KEY, JSON.stringify(run));
    } catch (e) {
      /* storage blocked: the page still works, the run just will not survive */
    }
  }

  /* Ids follow position, always. Accepts plain strings or {id, text}. */
  function renumber(items) {
    var out = [];
    (items || []).forEach(function (item) {
      var text = typeof item === "string" ? item : (item && item.text) || "";
      out.push({ id: "AC-" + (out.length + 1), text: text });
    });
    return out;
  }

  function criteriaTexts(run) {
    return (run && run.criteria ? run.criteria : []).map(function (c) {
      return c.text;
    });
  }

  function nonEmpty(run) {
    return criteriaTexts(run).filter(function (text) {
      return text.trim() !== "";
    });
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  /* The shape _form_fields.html writes, built with DOM methods so no user
   * text ever goes near innerHTML: label, hint, control, then the help and
   * counter line. The server forms and these JS forms must not drift. */
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

  function fieldUnder(id, help, max) {
    var under = el("div", "field-under");
    var left = el("span", null, help || "");
    left.id = id + "-help";
    under.appendChild(left);
    if (max) {
      var counter = el("span", "counter", "0 / " + max);
      counter.setAttribute("data-for", id);
      counter.setAttribute("data-max", String(max));
      counter.setAttribute("aria-live", "polite");
      under.appendChild(counter);
    }
    return under;
  }

  function groupBox(labelText, options) {
    var opts = options || {};
    var box = el("fieldset", "field");
    var legend = el("legend", "label", labelText);
    if (opts.optional) {
      legend.appendChild(document.createTextNode(" "));
      legend.appendChild(el("span", "opt", "(optional)"));
    }
    box.appendChild(legend);
    if (opts.hint) box.appendChild(el("p", "hint", opts.hint));
    return box;
  }

  /* Counters and descriptions for a form this file just built. */
  function fieldsReady(scope) {
    if (window.QAG && window.QAG.initFields) window.QAG.initFields(scope);
  }

  function closest(target, selector) {
    if (!target || !target.closest) return null;
    return target.closest(selector);
  }

  /* ---------- step 1: carry the story and its criteria to step 2 ---------- */

  function fieldValue(name) {
    var node = document.querySelector('#story-form [name="' + name + '"]');
    return node ? node.value : "";
  }

  /* The criteria the story check drafted, as plain strings. */
  function storyCriteriaTexts() {
    var holder = document.getElementById("story-criteria");
    if (!holder) return [];
    try {
      return JSON.parse(holder.textContent) || [];
    } catch (e) {
      return [];
    }
  }

  /* The checked story becomes the run as soon as its result is on screen, so
   * the other desks - Risk radar above all - can see it without the user
   * having to press "Use these criteria" first.
   *
   * A different story replaces the run outright: the test cases, risks and
   * automation selection in it belong to the old story. The same story is
   * left alone, because the criteria may have been edited on step 2 since. */
  function saveStoryResultToRun() {
    /* Only a real result counts. "Add an API key" and the error card carry no
     * #story-criteria block, and clearing a run over a call that never ran
     * would throw away the test cases the old story earned. */
    if (!document.getElementById("story-criteria")) return null;
    var story = fieldValue("user_story").trim();
    if (!story) return null;
    var texts = storyCriteriaTexts();
    var run = readRun();
    if (run && String(run.story || "").trim() === story) {
      if (!nonEmpty(run).length && texts.length) {
        run.criteria = renumber(texts);
        writeRun(run);
      }
      return run;
    }
    /* A new story used to throw the whole run away. It is kept now, and the
     * freshness cards say which parts were built from the older story -- the
     * user decides what to rebuild and what still stands. */
    var fresh = {};
    Object.keys(run || {}).forEach(function (key) {
      fresh[key] = run[key];
    });
    fresh.story = fieldValue("user_story");
    fresh.story_type = fieldValue("story_type") || "User story";
    fresh.context = fieldValue("context");
    fresh.criteria = renumber(texts);
    fresh.autorun_test_cases = false;
    writeRun(fresh);
    return fresh;
  }

  /* ---------- what Ship check reads back ---------- */

  function readJsonBlock(id) {
    var holder = document.getElementById(id);
    if (!holder) return null;
    try {
      return JSON.parse(holder.textContent);
    } catch (e) {
      return null;
    }
  }

  /* A result only belongs to the run when it was made from the run's story.
   * Check the example while a real story sits in the run and the two must
   * not mix. */
  function sameStory(run) {
    var shown = fieldValue("user_story").trim();
    return !!run && !!shown && String(run.story || "").trim() === shown;
  }

  function saveStoryAnalysis() {
    var analysis = readJsonBlock("story-analysis-data");
    if (!analysis) return;
    var run = readRun();
    if (!sameStory(run)) return;
    run.story_analysis = analysis;
    writeRun(run);
  }

  function saveDuelSummary() {
    var duel = readJsonBlock("duel-data");
    if (!duel) return;
    var run = readRun();
    if (!sameStory(run)) return;
    run.duel_summary = duel;
    writeRun(run);
  }

  function saveAutomationToRun() {
    var data = readJsonBlock("automation-data");
    if (!data || !data.script) return;
    var run = readRun();
    if (!run) return;
    run.automation = {
      script: data.script,
      selected_ids: data.selected_ids || []
    };
    writeRun(run);
  }

  function useCriteria() {
    saveStoryResultToRun();
    window.location.href = "/requirements/criteria";
  }

  /* Straight from the story result to Risk radar, which runs on arrival. */
  function findRisks() {
    var run = saveStoryResultToRun();
    if (!run) return;
    run.autorun_risks = true;
    writeRun(run);
    window.location.href = "/risks";
  }

  /* ---------- shared empty state ---------- */

  function emptyState(root, onSaved) {
    var card = el("div", "card card-form");
    card.appendChild(el("h2", null, "No story yet"));
    card.appendChild(
      el("p", "muted", "Check a story first, or paste one here to carry on.")
    );

    var link = el("a", "btn", "Check a story first");
    link.setAttribute("href", "/requirements/story");

    var body = el("div", "form-body");

    var storyField = fieldBox("paste-story", "Story");
    var storyBox = el("textarea", "short");
    storyBox.id = "paste-story";
    storyBox.setAttribute("rows", "4");
    storyBox.setAttribute("maxlength", "3000");
    storyBox.setAttribute("placeholder", "As a shopper, I want…");
    storyField.appendChild(storyBox);
    storyField.appendChild(fieldUnder("paste-story", "", 3000));

    var acField = fieldBox("paste-criteria", "Acceptance criteria", {
      hint: "One criterion per block, separated by a blank line."
    });
    var acBox = el("textarea");
    acBox.id = "paste-criteria";
    acBox.setAttribute("rows", "6");
    acBox.setAttribute("placeholder", "One criterion per block, separated by a blank line.");
    acField.appendChild(acBox);

    var save = el("button", "btn btn-primary", "Save and continue");
    save.setAttribute("type", "button");
    save.addEventListener("click", function () {
      var story = storyBox.value.trim();
      if (!story) {
        storyBox.focus();
        return;
      }
      var blocks = acBox.value.split(/\n\s*\n/).filter(function (block) {
        return block.trim() !== "";
      });
      writeRun({
        story: story,
        story_type: "User story",
        context: "",
        criteria: renumber(blocks),
        autorun_test_cases: false
      });
      onSaved();
    });

    card.appendChild(el("h3", null, "Paste a story and criteria"));
    body.appendChild(storyField);
    body.appendChild(acField);
    var pasteActions = el("div", "form-actions");
    pasteActions.appendChild(save);
    pasteActions.appendChild(link);
    body.appendChild(pasteActions);
    card.appendChild(body);
    root.appendChild(card);
    fieldsReady(root);
  }

  function storyDetails(run) {
    var details = document.createElement("details");
    details.appendChild(el("summary", null, "Story"));
    details.appendChild(el("p", null, run.story || ""));
    var edit = el("a", null, "Edit story");
    edit.setAttribute("href", "/requirements/story");
    details.appendChild(edit);
    return details;
  }

  /* ---------- step 2: the acceptance criteria editor ---------- */

  function growTextarea(box) {
    box.style.height = "auto";
    box.style.height = box.scrollHeight + "px";
  }

  function renderCriteria() {
    var root = document.getElementById("criteria-root");
    if (!root) return;
    root.textContent = "";
    var run = readRun();
    if (!run || !run.story) {
      emptyState(root, renderCriteria);
      return;
    }
    run.criteria = renumber(run.criteria);

    var card = el("div", "card");
    card.appendChild(el("h2", "", "Acceptance criteria"));
    card.appendChild(
      el("p", "muted", "From your story. Edit freely — ids follow the order.")
    );

    var list = el("div", "ac-list");
    run.criteria.forEach(function (criterion, index) {
      list.appendChild(criterionRow(run, criterion, index));
    });
    card.appendChild(list);

    var add = el("button", "btn", "+ Add criterion");
    add.setAttribute("type", "button");
    add.addEventListener("click", function () {
      run.criteria.push({ id: "", text: "" });
      run.criteria = renumber(run.criteria);
      writeRun(run);
      renderCriteria();
      var boxes = document.querySelectorAll("#criteria-root .ac-row textarea");
      if (boxes.length) boxes[boxes.length - 1].focus();
    });
    card.appendChild(add);
    card.appendChild(storyDetails(run));
    root.appendChild(card);

    var actions = el("div", "card");
    var actionBar = el("div", "form-actions");
    var generate = el("button", "btn btn-primary", "Generate test cases →");
    generate.setAttribute("type", "button");
    if (nonEmpty(run).length === 0) {
      generate.disabled = true;
      generate.setAttribute("aria-disabled", "true");
    }
    generate.addEventListener("click", function () {
      var current = readRun() || run;
      current.autorun_test_cases = true;
      writeRun(current);
      window.location.href = "/requirements/test-cases";
    });
    actionBar.appendChild(generate);
    actions.appendChild(actionBar);
    /* A disabled button says why, and not only in a title attribute. */
    if (nonEmpty(run).length === 0) {
      actions.appendChild(
        el("p", "form-note", "Add at least one criterion to generate test cases.")
      );
    }
    root.appendChild(actions);
    fieldsReady(root);
  }

  function criterionRow(run, criterion, index) {
    var row = el("div", "ac-row");
    row.appendChild(el("span", "pill mono", criterion.id));

    var box = el("textarea");
    box.setAttribute("rows", "3");
    box.setAttribute("aria-label", "Text of " + criterion.id);
    box.value = criterion.text;
    box.addEventListener("input", function () {
      run.criteria[index].text = box.value;
      run.criteria = renumber(run.criteria);
      writeRun(run);
      growTextarea(box);
    });
    row.appendChild(box);

    var buttons = el("div", "row ac-actions");
    buttons.appendChild(
      moveButton(run, index, -1, "↑", "Move " + criterion.id + " up")
    );
    buttons.appendChild(
      moveButton(run, index, 1, "↓", "Move " + criterion.id + " down")
    );

    var remove = el("button", "btn btn-small btn-danger", "Delete");
    remove.setAttribute("type", "button");
    remove.setAttribute("aria-label", "Delete " + criterion.id);
    remove.addEventListener("click", function () {
      buttons.textContent = "";
      buttons.appendChild(el("span", "small", "Remove " + criterion.id + "?"));
      var yes = el("button", "btn btn-small btn-danger", "Yes");
      yes.setAttribute("type", "button");
      yes.addEventListener("click", function () {
        run.criteria.splice(index, 1);
        run.criteria = renumber(run.criteria);
        writeRun(run);
        renderCriteria();
      });
      var no = el("button", "btn btn-small", "No");
      no.setAttribute("type", "button");
      no.addEventListener("click", renderCriteria);
      buttons.appendChild(yes);
      buttons.appendChild(no);
      yes.focus();
    });
    buttons.appendChild(remove);
    row.appendChild(buttons);

    setTimeout(function () {
      growTextarea(box);
    }, 0);
    return row;
  }

  function moveButton(run, index, step, label, aria) {
    var button = el("button", "btn btn-small", label);
    button.setAttribute("type", "button");
    button.setAttribute("aria-label", aria);
    var target = index + step;
    if (target < 0 || target >= run.criteria.length) {
      button.disabled = true;
      button.setAttribute("aria-disabled", "true");
      return button;
    }
    button.addEventListener("click", function () {
      var moved = run.criteria.splice(index, 1)[0];
      run.criteria.splice(target, 0, moved);
      run.criteria = renumber(run.criteria);
      writeRun(run);
      renderCriteria();
    });
    return button;
  }

  /* ---------- step 3: the test cases page ---------- */

  function renderTestCases() {
    var root = document.getElementById("test-cases-root");
    if (!root) return;
    root.textContent = "";
    var run = readRun();
    if (!run || !run.story) {
      emptyState(root, renderTestCases);
      root.appendChild(exampleOnlyCard());
      return;
    }
    var criteria = nonEmpty(run);

    var card = el("div", "card");
    card.setAttribute("data-input-card", "Your criteria");
    card.appendChild(el("h2", null, "Test cases"));
    var preview = (run.story || "").slice(0, 120);
    card.appendChild(el("p", "muted", preview));
    var line = el("p", "muted small");
    line.appendChild(
      document.createTextNode(criteria.length + " acceptance criteria · ")
    );
    var edit = el("a", null, "Edit criteria");
    edit.setAttribute("href", "/requirements/criteria");
    line.appendChild(edit);
    card.appendChild(line);

    var form = el("form", "tc-form");
    form.id = "tc-form";
    form.setAttribute("hx-post", "/requirements/test-cases/run");
    form.setAttribute("hx-target", "#test-cases-output");
    form.setAttribute("hx-swap", "innerHTML");
    form.setAttribute("hx-indicator", "#tc-progress");

    var storyInput = el("input");
    storyInput.type = "hidden";
    storyInput.name = "user_story";
    storyInput.value = run.story || "";
    form.appendChild(storyInput);

    var criteriaInput = el("input");
    criteriaInput.type = "hidden";
    criteriaInput.name = "criteria_json";
    criteriaInput.value = JSON.stringify(criteria);
    form.appendChild(criteriaInput);

    var focus = groupBox("Coverage focus", {
      hint: "The kinds of case this run should write."
    });
    FOCUS_OPTIONS.forEach(function (option, i) {
      var wrap = el("label", "choice");
      var input = el("input");
      input.type = "checkbox";
      input.name = "coverage_focus";
      input.value = option;
      input.checked = true;
      input.id = "focus-" + i;
      wrap.appendChild(input);
      wrap.appendChild(document.createTextNode(" " + option));
      focus.appendChild(wrap);
    });
    form.appendChild(focus);

    var actions = el("div", "form-actions");
    var generate = el("button", "btn btn-primary");
    generate.id = "tc-generate";
    generate.type = "submit";
    generate.setAttribute("data-busy-label", "Writing tests…");
    generate.appendChild(el("span", "btn-label", "Generate test cases"));
    actions.appendChild(generate);

    var example = el("button", "btn", "Load example");
    example.setAttribute("type", "button");
    example.setAttribute("hx-get", "/requirements/test-cases/example");
    example.setAttribute("hx-target", "#test-cases-output");
    example.setAttribute("hx-swap", "innerHTML");
    actions.appendChild(example);
    form.appendChild(actions);

    var progress = el(
      "p",
      "htmx-indicator working",
      "Writing test cases for " + criteria.length + " criteria…"
    );
    progress.insertBefore(el("span", "spin"), progress.firstChild);
    progress.id = "tc-progress";
    form.appendChild(progress);

    card.appendChild(form);
    root.appendChild(card);
    fieldsReady(root);

    if (window.htmx) window.htmx.process(root);
    if (window.QAG && window.QAG.initInputCards) window.QAG.initInputCards(root);

    /* Always send what sessionStorage holds right now. */
    form.addEventListener("htmx:configRequest", function (event) {
      var latest = readRun() || run;
      event.detail.parameters.user_story = latest.story || "";
      event.detail.parameters.criteria_json = JSON.stringify(nonEmpty(latest));
    });

    if (run.autorun_test_cases) {
      run.autorun_test_cases = false;
      writeRun(run);
      if (window.htmx) window.htmx.trigger(form, "submit");
    } else if (run.test_cases && run.test_cases.result) {
      /* A refresh keeps whatever list the user last accepted. */
      renderList(run.test_cases);
    }
  }

  function exampleOnlyCard() {
    var card = el("div", "card");
    card.appendChild(
      el("p", "muted", "You can still look at a saved example.")
    );
    var example = el("button", "btn", "Load example");
    example.setAttribute("type", "button");
    example.setAttribute("hx-get", "/requirements/test-cases/example");
    example.setAttribute("hx-target", "#test-cases-output");
    example.setAttribute("hx-swap", "innerHTML");
    card.appendChild(example);
    if (window.htmx) window.htmx.process(card);
    return card;
  }

  /* ---------- result card: filters and downloads ---------- */

  function applyFilter(chip) {
    var filter = chip.getAttribute("data-filter");
    var chips = document.querySelectorAll("#tc-filters .chip");
    Array.prototype.forEach.call(chips, function (other) {
      var on = other === chip;
      other.classList.toggle("now", on);
      other.setAttribute("aria-pressed", on ? "true" : "false");
    });
    var cards = document.querySelectorAll("#tc-list .tc-card");
    Array.prototype.forEach.call(cards, function (card) {
      var category = card.getAttribute("data-category");
      card.hidden = !(filter === "all" || category === filter);
    });
  }

  function download(kind, filename) {
    var holder = document.getElementById("tc-data");
    var status = document.getElementById("download-status");
    if (!holder) return;
    if (status) status.textContent = "Building the file…";
    var payload;
    try {
      payload = JSON.parse(holder.textContent);
    } catch (e) {
      if (status) status.textContent = "Could not read the test cases.";
      return;
    }
    fetch("/requirements/test-cases/export." + kind, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
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
        if (status) status.textContent = "";
      })
      .catch(function () {
        if (status) status.textContent = "Could not build the file. Try again.";
      });
  }

  /* ---------- step 4: settings, the generated project, the ZIP ---------- */

  function selectEl(name, options, value) {
    var box = el("select");
    box.name = name;
    box.id = name;
    options.forEach(function (option) {
      var item = el("option", null, option);
      item.value = option;
      if (option === value) item.selected = true;
      box.appendChild(item);
    });
    return box;
  }

  function labelled(text, control, options) {
    var field = fieldBox(control.id, text, options);
    field.appendChild(control);
    return field;
  }

  function selectedCasesCard(cases) {
    var card = el("div", "card");
    card.appendChild(el("h2", null, "Selected test cases"));
    card.appendChild(
      el("p", "muted", cases.length + " test case" + (cases.length === 1 ? "" : "s"))
    );
    var list = el("ul", "picked-cases");
    cases.forEach(function (one) {
      list.appendChild(el("li", null, one.id + " · " + one.title));
    });
    card.appendChild(list);
    var change = el("a", null, "Change selection");
    change.setAttribute("href", "/requirements/test-cases");
    var line = el("p", "muted small");
    line.appendChild(change);
    card.appendChild(line);
    return card;
  }

  /* Browsers only mean something for Playwright. */
  function toggleBrowsers(form) {
    var choice = form.querySelector('[name="framework_choice"]');
    var box = form.querySelector("#browser-field");
    if (!choice || !box) return;
    box.hidden = choice.value.indexOf("Playwright") !== 0;
  }

  function settingsCard() {
    var card = el("div", "card");
    card.appendChild(el("h2", null, "Settings"));
    card.appendChild(
      labelled(
        "Framework & language",
        selectEl("framework_choice", FRAMEWORK_CHOICES, FRAMEWORK_CHOICES[0])
      )
    );
    card.appendChild(
      labelled(
        "Structure",
        selectEl("structure_choice", STRUCTURE_CHOICES, STRUCTURE_CHOICES[0])
      )
    );

    var browsers = groupBox("Browsers");
    browsers.id = "browser-field";
    BROWSER_CHOICES.forEach(function (name, index) {
      var wrap = el("label", "choice");
      var input = el("input");
      input.type = "checkbox";
      input.name = "browsers";
      input.value = name;
      input.checked = index === 0;
      wrap.appendChild(input);
      wrap.appendChild(document.createTextNode(" " + name));
      browsers.appendChild(wrap);
    });
    card.appendChild(browsers);

    var url = el("input");
    url.type = "url";
    url.name = "base_url";
    url.id = "base_url";
    url.maxLength = 200;
    url.placeholder = "https://staging.aurora-shop.dev";
    card.appendChild(
      labelled("Base URL", url, {
        optional: true,
        hint: "Where the generated tests should start."
      })
    );
    return card;
  }

  function exampleButton() {
    var example = el("button", "btn", "Load example");
    example.setAttribute("type", "button");
    example.setAttribute("hx-get", "/requirements/automation/example");
    example.setAttribute("hx-target", "#automation-output");
    example.setAttribute("hx-swap", "innerHTML");
    return example;
  }

  function renderAutomation() {
    var root = document.getElementById("automation-root");
    if (!root) return;
    root.textContent = "";
    var run = readRun() || {};
    var cases = run.automation_cases || [];

    if (!cases.length) {
      var empty = el("div", "card card-form");
      empty.appendChild(el("h2", null, "No test cases selected"));
      empty.appendChild(
        el("p", "muted", "Pick the cases you want automated on step 3.")
      );
      var pick = el("a", "btn", "Pick test cases");
      pick.setAttribute("href", "/requirements/test-cases");
      var actions = el("div", "empty-actions");
      actions.appendChild(pick);
      actions.appendChild(exampleButton());
      empty.appendChild(actions);
      root.appendChild(empty);
      if (window.htmx) window.htmx.process(root);
    if (window.QAG && window.QAG.initInputCards) window.QAG.initInputCards(root);
      return;
    }

    root.appendChild(selectedCasesCard(cases));

    var form = el("form", "tc-form");
    form.id = "automation-form";
    form.setAttribute("hx-post", "/requirements/automation/run");
    form.setAttribute("hx-target", "#automation-output");
    form.setAttribute("hx-swap", "innerHTML");
    form.setAttribute("hx-indicator", "#automation-progress");

    var selected = el("input");
    selected.type = "hidden";
    selected.name = "selected_json";
    selected.value = JSON.stringify(cases);
    form.appendChild(selected);

    form.appendChild(settingsCard());

    var actions = el("div", "form-actions");
    var generate = el("button", "btn btn-primary");
    generate.id = "automation-generate";
    generate.type = "submit";
    generate.setAttribute("data-busy-label", "Writing code…");
    generate.appendChild(el("span", "btn-label", "Generate automation"));
    actions.appendChild(generate);
    actions.appendChild(exampleButton());
    form.appendChild(actions);

    var progress = el(
      "p",
      "htmx-indicator working",
      "Writing tests for " + cases.length + " test case" +
        (cases.length === 1 ? "" : "s") + "…"
    );
    progress.insertBefore(el("span", "spin"), progress.firstChild);
    progress.id = "automation-progress";
    form.appendChild(progress);

    root.appendChild(form);
    fieldsReady(root);
    if (window.htmx) window.htmx.process(root);
    if (window.QAG && window.QAG.initInputCards) window.QAG.initInputCards(root);
    toggleBrowsers(form);

    /* Always send what sessionStorage holds right now. */
    form.addEventListener("htmx:configRequest", function (event) {
      var latest = readRun() || run;
      event.detail.parameters.selected_json = JSON.stringify(
        latest.automation_cases || cases
      );
    });
  }

  /* Show one file of the generated project. */
  function showFile(tab) {
    var wanted = tab.getAttribute("data-file");
    var tabs = document.querySelectorAll(".file-tab");
    Array.prototype.forEach.call(tabs, function (other) {
      other.classList.toggle("now", other === tab);
    });
    var bodies = document.querySelectorAll(".file-body");
    Array.prototype.forEach.call(bodies, function (body) {
      body.hidden = body.getAttribute("data-file") !== wanted;
    });
  }

  function copyText(text, statusId) {
    var status = document.getElementById(statusId);
    function done(message) {
      if (status) status.textContent = message;
    }
    if (!text) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(
        function () {
          done("Copied");
        },
        function () {
          done("Could not copy");
        }
      );
      return;
    }
    done("Could not copy");
  }

  function visibleCode() {
    var bodies = document.querySelectorAll(".file-body");
    for (var i = 0; i < bodies.length; i += 1) {
      if (!bodies[i].hidden) return bodies[i].textContent;
    }
    return "";
  }

  function downloadZip() {
    var holder = document.getElementById("automation-data");
    var status = document.getElementById("automation-status");
    if (!holder) return;
    if (status) status.textContent = "Building the ZIP…";
    var payload;
    try {
      payload = JSON.parse(holder.textContent);
    } catch (e) {
      if (status) status.textContent = "Could not read the project.";
      return;
    }
    fetch("/requirements/automation/export.zip", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    })
      .then(function (response) {
        if (!response.ok) throw new Error("export failed");
        return response.blob();
      })
      .then(function (blob) {
        var url = URL.createObjectURL(blob);
        var link = document.createElement("a");
        link.href = url;
        link.download = "qa-genius-automation.zip";
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
        if (status) status.textContent = "";
      })
      .catch(function () {
        if (status) status.textContent = "Could not build the ZIP. Try again.";
      });
  }

  /* ---------- choosing test cases to automate (step 3 -> step 4) ---------- */

  function caseBoxes() {
    return document.querySelectorAll("#tc-list .tc-select");
  }

  /* The ids ticked on screen right now, in list order. */
  function readSelection() {
    var ids = [];
    Array.prototype.forEach.call(caseBoxes(), function (box) {
      if (box.checked) ids.push(box.getAttribute("data-case-id"));
    });
    return ids;
  }

  function saveSelection(ids) {
    var run = readRun() || {};
    run.automation_selection = ids;
    writeRun(run);
  }

  function updateSelectionUi() {
    var ids = readSelection();
    var count = document.getElementById("selected-count");
    var button = document.getElementById("automate-selected");
    var hint = document.getElementById("select-hint");
    if (count) count.textContent = ids.length + " selected";
    if (button) button.disabled = ids.length === 0 || ids.length > MAX_SELECTED;
    if (hint) {
      if (ids.length > MAX_SELECTED) {
        hint.textContent = "Select up to " + MAX_SELECTED + " test cases.";
      } else if (ids.length === 0) {
        hint.textContent = "Tick at least one test case to automate it.";
      } else {
        hint.textContent = "";
      }
    }
    var bar = document.getElementById("tc-select-bar");
    // The hint line comes and goes, so the bar is not always one height.
    if (bar) barHeight(bar);
  }

  /* ---------- the selection bar while it is stuck ---------- */

  /* The bar is sticky, so "is it stuck?" is not a scroll position: the list
   * it belongs to starts somewhere down the page. One pixel of nothing above
   * it answers the question — when that leaves the top of the window, the
   * bar is holding the top of the list. */
  function barHeight(bar) {
    var height = Math.ceil(bar.getBoundingClientRect().height);
    if (height) {
      document.documentElement.style.setProperty("--tc-bar-h", height + "px");
    }
  }

  function watchSelectBar() {
    var bar = document.getElementById("tc-select-bar");
    if (!bar || bar.getAttribute("data-watched") === "yes") return;
    barHeight(bar);
    if (!window.IntersectionObserver || !bar.parentNode) return;
    bar.setAttribute("data-watched", "yes");
    var sentinel = document.createElement("div");
    sentinel.className = "tc-stick-sentinel";
    sentinel.setAttribute("aria-hidden", "true");
    bar.parentNode.insertBefore(sentinel, bar);
    // The same number the CSS sticks the bar at, read from the bar itself.
    var top = parseInt(window.getComputedStyle(bar).top, 10) || 0;
    new IntersectionObserver(
      function (entries) {
        bar.classList.toggle("is-stuck", !entries[0].isIntersecting);
      },
      { rootMargin: "-" + (top + 1) + "px 0px 0px 0px", threshold: 0 }
    ).observe(sentinel);
  }

  /* Tick what the run remembers, and forget ids this list no longer has. */
  function restoreSelection() {
    var boxes = caseBoxes();
    if (!boxes.length) return;
    var run = readRun() || {};
    var wanted = run.automation_selection || [];
    Array.prototype.forEach.call(boxes, function (box) {
      box.checked = wanted.indexOf(box.getAttribute("data-case-id")) !== -1;
    });
    saveSelection(readSelection());
    updateSelectionUi();
  }

  function setAllSelected(on) {
    Array.prototype.forEach.call(caseBoxes(), function (box) {
      box.checked = on;
    });
    saveSelection(readSelection());
    updateSelectionUi();
  }

  /* Hand the chosen cases to step 4. They travel in sessionStorage, never the server. */
  function automateSelected() {
    var ids = readSelection();
    if (!ids.length || ids.length > MAX_SELECTED) return;
    var shown = displayedList();
    var all = shown && shown.result ? shown.result.test_cases || [] : [];
    var chosen = all.filter(function (one) {
      return ids.indexOf(one.id) !== -1;
    });
    if (!chosen.length) return;
    var run = readRun() || {};
    run.automation_selection = ids;
    run.automation_cases = chosen;
    writeRun(run);
    window.location.href = "/requirements/automation";
  }

  /* ---------- the displayed list, its history, and proposals ---------- */

  /* Read the list the result card is showing right now. */
  function displayedList() {
    var holder = document.getElementById("tc-data");
    if (!holder) return null;
    try {
      return JSON.parse(holder.textContent);
    } catch (e) {
      return null;
    }
  }

  function proposedList() {
    var holder = document.getElementById("tc-proposed");
    if (!holder) return null;
    try {
      return JSON.parse(holder.textContent);
    } catch (e) {
      return null;
    }
  }

  /* Remember what is on screen. A fresh list starts its history over. */
  function rememberDisplayed(fresh) {
    var shown = displayedList();
    if (!shown) return;
    var run = readRun() || {};
    run.test_cases = shown;
    if (fresh) run.test_cases_history = [];
    writeRun(run);
    showUndo();
  }

  function showUndo() {
    var button = document.getElementById("undo-btn");
    if (!button) return;
    var run = readRun() || {};
    var history = run.test_cases_history || [];
    button.hidden = history.length === 0;
  }

  /* Draw a list the browser already holds. The HTML comes from the server. */
  function renderList(payload, after) {
    var target = document.getElementById("test-cases-output");
    if (!target || !payload) return;
    fetch("/requirements/test-cases/render", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    })
      .then(function (response) {
        if (!response.ok) throw new Error("render failed");
        return response.text();
      })
      .then(function (html) {
        target.innerHTML = html;
        if (window.htmx) window.htmx.process(target);
        showUndo();
        restoreSelection();
        if (after) after();
        runPendingRisks();
      })
      .catch(function () {
        /* Leave what is on screen alone; the saved run is still intact. */
      });
  }

  function acceptChanges() {
    var proposal = proposedList();
    if (!proposal) return;
    var run = readRun() || {};
    var history = run.test_cases_history || [];
    if (run.test_cases) {
      history.push(run.test_cases);
      while (history.length > HISTORY_MAX) history.shift();
    }
    run.test_cases_history = history;
    run.test_cases = proposal;
    writeRun(run);
    clearProposal();
    /* The new list replaces the panel, so the way back is added after it. */
    renderList(proposal, backToRiskRadar);
  }

  /* Drop one case from a saved {result, criteria} payload. Returns a new
   * payload, or null when the id is not in it. Pure: the caller stores it. */
  function withoutCase(payload, caseId) {
    if (!payload || !payload.result || !payload.result.test_cases) return null;
    var cases = payload.result.test_cases;
    var kept = [];
    for (var i = 0; i < cases.length; i++) {
      if (cases[i] && cases[i].id === caseId) continue;
      kept.push(cases[i]);
    }
    if (kept.length === cases.length) return null;
    return {
      result: { test_cases: kept, summary: payload.result.summary },
      criteria: payload.criteria
    };
  }

  /* Remove a case the senior tester added. The list before the removal goes on the undo
   * stack, so the Undo button brings it straight back. */
  function removePrincipalCase(caseId) {
    var run = readRun() || {};
    var current = run.test_cases || displayedList();
    var next = withoutCase(current, caseId);
    if (!next) return;
    var history = run.test_cases_history || [];
    history.push(current);
    while (history.length > HISTORY_MAX) history.shift();
    run.test_cases_history = history;
    run.test_cases = next;
    writeRun(run);
    clearProposal();
    renderList(next);
  }

  function undoLastChange() {
    var run = readRun() || {};
    var history = run.test_cases_history || [];
    if (!history.length) return;
    var previous = history.pop();
    run.test_cases_history = history;
    run.test_cases = previous;
    writeRun(run);
    clearProposal();
    renderList(previous);
  }

  /* The Risk radar page saved the risks it wants tests for and sent the user
   * here. Ask for those cases once, then forget the request. */
  function runPendingRisks() {
    var run = readRun();
    if (!run || !run.pending_risks || !run.pending_risks.length) return;
    if (!document.getElementById("tc-proposal") || !window.htmx) return;
    var risks = run.pending_risks;
    delete run.pending_risks;
    run.came_from_risks = true;
    writeRun(run);
    window.htmx.ajax("POST", "/requirements/test-cases/refine", {
      target: "#tc-proposal",
      swap: "innerHTML",
      values: { mode: "risks", risks_json: JSON.stringify(risks) }
    });
  }

  /* After accepting cases written for risks, offer the way back. */
  function backToRiskRadar() {
    var run = readRun() || {};
    var panel = document.getElementById("tc-proposal");
    if (!panel || !run.came_from_risks) return;
    var card = el("div", "card");
    var link = el("a", null, "← Back to Risk radar");
    link.setAttribute("href", "/risks");
    link.id = "back-to-risks";
    card.appendChild(link);
    panel.appendChild(card);
    run.came_from_risks = false;
    writeRun(run);
  }

  function clearProposal() {
    var panel = document.getElementById("tc-proposal");
    if (panel) panel.textContent = "";
  }

  function toggleRefinePanel(open) {
    var panel = document.getElementById("refine-panel");
    if (!panel) return;
    panel.hidden = !open;
    if (open) {
      var box = document.getElementById("refine-instruction");
      if (box) box.focus();
    }
  }

  document.addEventListener("click", function (event) {
    if (closest(event.target, "#use-criteria")) {
      useCriteria();
      return;
    }
    if (closest(event.target, "#find-risks")) {
      findRisks();
      return;
    }
    var chip = closest(event.target, "#tc-filters .chip");
    if (chip) {
      applyFilter(chip);
      return;
    }
    if (closest(event.target, "#download-csv")) {
      download("csv", "qa-genius-test-cases.csv");
      return;
    }
    if (closest(event.target, "#download-xlsx")) {
      download("xlsx", "qa-genius-test-cases.xlsx");
      return;
    }
    var tab = closest(event.target, ".file-tab");
    if (tab) {
      showFile(tab);
      return;
    }
    if (closest(event.target, "#copy-code")) {
      copyText(visibleCode(), "copy-status");
      return;
    }
    if (closest(event.target, "#copy-command")) {
      var command = document.getElementById("run-command");
      copyText(command ? command.textContent : "", "command-status");
      return;
    }
    if (closest(event.target, "#download-zip")) {
      downloadZip();
      return;
    }
    if (closest(event.target, "#select-all-cases")) {
      setAllSelected(true);
      return;
    }
    if (closest(event.target, "#clear-selected-cases")) {
      setAllSelected(false);
      return;
    }
    if (closest(event.target, "#automate-selected")) {
      automateSelected();
      return;
    }
    if (closest(event.target, "#refine-open")) {
      toggleRefinePanel(true);
      return;
    }
    if (closest(event.target, "#refine-cancel")) {
      toggleRefinePanel(false);
      return;
    }
    if (closest(event.target, "#accept-changes")) {
      acceptChanges();
      return;
    }
    if (closest(event.target, "#keep-current")) {
      clearProposal();
      return;
    }
    if (closest(event.target, "#undo-btn")) {
      undoLastChange();
      return;
    }
    var remove = closest(event.target, ".pq-remove");
    if (remove) {
      removePrincipalCase(remove.getAttribute("data-case-id"));
    }
  });

  document.addEventListener("change", function (event) {
    var form = document.getElementById("automation-form");
    if (form && closest(event.target, '[name="framework_choice"]')) {
      toggleBrowsers(form);
      return;
    }
    if (!closest(event.target, "#tc-list .tc-select")) return;
    saveSelection(readSelection());
    updateSelectionUi();
  });

  /* Strengthen and Refine post the list the browser holds, never the server. */
  document.addEventListener("htmx:configRequest", function (event) {
    var detail = event.detail;
    if (!detail || !detail.path) return;
    if (detail.path.indexOf("/requirements/test-cases/refine") === -1) return;
    var run = readRun() || {};
    var current = run.test_cases || displayedList() || {};
    var source = detail.elt ? detail.elt.id : "";
    var instruction = "";
    var box = document.getElementById("refine-instruction");
    if (source === "refine-submit" && box) instruction = box.value;
    detail.parameters.user_story = run.story || "";
    detail.parameters.criteria_json = JSON.stringify(
      current.criteria || nonEmpty(run)
    );
    detail.parameters.current_json = JSON.stringify(current.result || {});
    if (detail.parameters.mode !== "risks") {
      detail.parameters.mode =
        source === "refine-submit" ? "instruction" : "strengthen";
    }
    detail.parameters.instruction = instruction;
    detail.parameters.coverage_focus = checkedFocus();
  });

  function checkedFocus() {
    var boxes = document.querySelectorAll(
      '#tc-form input[name="coverage_focus"]:checked'
    );
    var values = [];
    Array.prototype.forEach.call(boxes, function (box) {
      values.push(box.value);
    });
    return values.length ? values : FOCUS_OPTIONS.slice();
  }

  document.addEventListener("htmx:afterSwap", function (event) {
    var detail = event.detail;
    var path = detail && detail.pathInfo ? detail.pathInfo.requestPath : "";
    if (!path && detail && detail.xhr) path = detail.xhr.responseURL || "";
    if (path.indexOf("/requirements/story/run") !== -1 ||
        path.indexOf("/requirements/story/example") !== -1) {
      saveStoryResultToRun();
      saveStoryAnalysis();
      /* Load example swaps in a duel result alongside the story one. */
      saveDuelSummary();
    }
    if (path.indexOf("/requirements/story/duel") !== -1) {
      saveDuelSummary();
    }
    if (path.indexOf("/requirements/automation/") !== -1) {
      saveAutomationToRun();
    }
    if (path.indexOf("/requirements/test-cases/run") !== -1) {
      rememberDisplayed(true);
    } else if (path.indexOf("/requirements/test-cases/example-strengthen") !== -1) {
      /* A proposal, not a list: nothing to remember. */
    } else if (path.indexOf("/requirements/test-cases/example") !== -1) {
      rememberDisplayed(true);
    } else if (path.indexOf("/requirements/test-cases/render") !== -1) {
      rememberDisplayed(false);
    }
    restoreSelection();
    watchSelectBar();
    runPendingRisks();
  });

  document.addEventListener("DOMContentLoaded", function () {
    renderCriteria();
    renderTestCases();
    renderAutomation();
    watchSelectBar();
  });

  /* The pure helpers the unit tests in tests/js reach for. The page itself
   * never goes through here. */
  if (typeof window !== "undefined") {
    window.QAGFlow = { withoutCase: withoutCase, renumber: renumber };
  }
})();
