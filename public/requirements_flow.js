/* QA-Genius v2: the Requirements flow (story -> criteria -> test cases).
 * The run lives in sessionStorage under "qag.run" and never reaches the
 * server as stored state. Criterion ids are always recomputed from position,
 * so AC-1..AC-n follow the order on screen. */
(function () {
  "use strict";

  var RUN_KEY = "qag.run";
  var FOCUS_OPTIONS = ["Functional", "Negative", "Boundary", "Edge Case"];

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
      /* A private window with storage blocked: the page still works, the
       * run just does not survive the next navigation. */
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

  function closest(target, selector) {
    if (!target || !target.closest) return null;
    return target.closest(selector);
  }

  /* ---------- step 1: carry the story and its criteria to step 2 ---------- */

  function fieldValue(name) {
    var node = document.querySelector('#story-form [name="' + name + '"]');
    return node ? node.value : "";
  }

  function useCriteria() {
    var holder = document.getElementById("story-criteria");
    var texts = [];
    if (holder) {
      try {
        texts = JSON.parse(holder.textContent) || [];
      } catch (e) {
        texts = [];
      }
    }
    writeRun({
      story: fieldValue("user_story"),
      story_type: fieldValue("story_type") || "User story",
      context: fieldValue("context"),
      criteria: renumber(texts),
      autorun_test_cases: false
    });
    window.location.href = "/requirements/criteria";
  }

  /* ---------- shared empty state ---------- */

  function emptyState(root, onSaved) {
    var card = el("div", "card");
    card.appendChild(el("h2", null, "No story yet"));
    card.appendChild(
      el("p", "muted", "Check a story first, or paste one here to carry on.")
    );

    var link = el("a", "btn", "Check a story first");
    link.setAttribute("href", "/requirements/story");
    card.appendChild(link);

    var storyField = el("div", "field");
    var storyLabel = el("label", null, "Story");
    storyLabel.setAttribute("for", "paste-story");
    var storyBox = el("textarea");
    storyBox.id = "paste-story";
    storyBox.setAttribute("rows", "4");
    storyBox.setAttribute("maxlength", "3000");
    storyBox.setAttribute("placeholder", "As a shopper, I want…");
    storyField.appendChild(storyLabel);
    storyField.appendChild(storyBox);

    var acField = el("div", "field");
    var acLabel = el("label", null, "Acceptance criteria");
    acLabel.setAttribute("for", "paste-criteria");
    var acBox = el("textarea");
    acBox.id = "paste-criteria";
    acBox.setAttribute("rows", "6");
    acBox.setAttribute("placeholder", "One criterion per block, separated by a blank line.");
    acField.appendChild(acLabel);
    acField.appendChild(acBox);
    acField.appendChild(
      el("span", "hint", "Separate criteria with a blank line.")
    );

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
    card.appendChild(storyField);
    card.appendChild(acField);
    card.appendChild(save);
    root.appendChild(card);
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
    actions.appendChild(generate);
    if (nonEmpty(run).length === 0) {
      actions.appendChild(el("p", "muted small", "Add at least one criterion"));
    }
    root.appendChild(actions);
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

    var remove = el("button", "btn btn-small", "Delete");
    remove.setAttribute("type", "button");
    remove.setAttribute("aria-label", "Delete " + criterion.id);
    remove.addEventListener("click", function () {
      buttons.textContent = "";
      buttons.appendChild(el("span", "small", "Remove " + criterion.id + "?"));
      var yes = el("button", "btn btn-small", "Yes");
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

    var focus = el("fieldset", "field");
    focus.appendChild(el("legend", "hint", "Coverage focus"));
    FOCUS_OPTIONS.forEach(function (option, i) {
      var wrap = el("label", "check");
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

    var actions = el("div", "row");
    var generate = el("button", "btn btn-primary");
    generate.id = "tc-generate";
    generate.type = "submit";
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
      "htmx-indicator muted",
      "Writing test cases for " + criteria.length + " criteria…"
    );
    progress.id = "tc-progress";
    form.appendChild(progress);

    card.appendChild(form);
    root.appendChild(card);

    if (window.htmx) window.htmx.process(root);

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
      other.classList.toggle("now", other === chip);
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

  document.addEventListener("click", function (event) {
    if (closest(event.target, "#use-criteria")) {
      useCriteria();
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
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    renderCriteria();
    renderTestCases();
  });
})();
