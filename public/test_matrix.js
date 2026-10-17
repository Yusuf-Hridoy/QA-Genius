/* QA-Genius v2: the smart test matrix.
 * The AI proposes factors; every row, count and coverage number on this page
 * is computed by the server from qagenius/pairwise.py. Editing a factor, a
 * value, a rule or a pin re-posts to /build only -- no AI runs on an edit.
 * Only server HTML is inserted; everything this file writes goes in through
 * textContent. */
(function () {
  "use strict";

  var RUN_KEY = "qag.run";
  var DEBOUNCE_MS = 300;
  var pinned = [];
  var timer = null;

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

  /* ---------- reading the editor back out of the page ---------- */

  function readFactors() {
    var factors = [];
    var blocks = document.querySelectorAll(".matrix-factor");
    Array.prototype.forEach.call(blocks, function (block) {
      var name = block.querySelector(".matrix-factor-name");
      var values = [];
      var chips = block.querySelectorAll(".chip-value");
      Array.prototype.forEach.call(chips, function (chip) {
        values.push(chip.getAttribute("data-value") || chipText(chip));
      });
      factors.push({ name: name ? name.value : "", values: values });
    });
    return factors;
  }

  /* The chip holds its value plus a × button, so the button's text is cut. */
  function chipText(chip) {
    var text = "";
    Array.prototype.forEach.call(chip.childNodes, function (node) {
      if (node.nodeType === 3) text += node.nodeValue;
    });
    return text.trim();
  }

  function readRules() {
    var rules = [];
    var items = document.querySelectorAll(".matrix-rule");
    Array.prototype.forEach.call(items, function (item) {
      rules.push({
        if_factor: item.getAttribute("data-if-factor") || "",
        if_value: item.getAttribute("data-if-value") || "",
        then_factor: item.getAttribute("data-then-factor") || "",
        then_value: item.getAttribute("data-then-value") || "",
        reason: item.getAttribute("data-reason") || ""
      });
    });
    return rules;
  }

  function editorBody() {
    return { factors: readFactors(), rules: readRules(), pinned: pinned };
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

  function showMatrix(html) {
    var output = byId("matrix-output");
    if (!output) return;
    output.innerHTML = html;
    rememberMatrix();
    if (window.QAGRun) window.QAGRun.announceResult();
  }

  function rebuild() {
    post("/requirements/matrix/build", editorBody())
      .then(showMatrix)
      .catch(function () {
        var output = byId("matrix-output");
        if (!output) return;
        output.textContent = "";
        var card = el("div", "card error-card");
        card.appendChild(el("p", null, "Could not rebuild the matrix. Try again."));
        output.appendChild(card);
      });
  }

  function queueRebuild() {
    if (timer) clearTimeout(timer);
    timer = setTimeout(rebuild, DEBOUNCE_MS);
  }

  function showEditor(html) {
    var root = byId("matrix-root");
    if (!root) return;
    root.innerHTML = html;
    markRules();
    if (window.QAG && window.QAG.initFields) window.QAG.initFields(root);
    rememberMatrix();
  }

  /* The rule rows carry their parts as data so readRules never parses text. */
  function markRules() {
    var items = document.querySelectorAll(".matrix-rule");
    Array.prototype.forEach.call(items, function (item) {
      if (item.getAttribute("data-if-factor")) return;
      var strong = item.querySelectorAll("strong");
      if (strong.length < 2) return;
      var left = strong[0].textContent.split("=");
      var right = strong[1].textContent.split("=");
      item.setAttribute("data-if-factor", left[0] || "");
      item.setAttribute("data-if-value", left.slice(1).join("=") || "");
      item.setAttribute("data-then-factor", right[0] || "");
      item.setAttribute("data-then-value", right.slice(1).join("=") || "");
    });
    var chips = document.querySelectorAll(".chip-value");
    Array.prototype.forEach.call(chips, function (chip) {
      if (!chip.getAttribute("data-value")) {
        chip.setAttribute("data-value", chipText(chip));
      }
    });
  }

  /* `saved` keeps the factors this browser already holds, so reopening the
   * page costs no AI call and never overwrites hand-edited factors. */
  function suggest(saved) {
    var run = readRun() || {};
    var form = new FormData();
    form.append("user_story", String(run.story || ""));
    form.append("criteria_json", JSON.stringify(criteriaTexts(run)));
    form.append("cases_json", JSON.stringify(currentCases(run)));
    if (saved) {
      form.append("saved_json", JSON.stringify(saved));
      pinned = saved.pinned || [];
    } else {
      pinned = [];
    }
    fetch("/requirements/matrix/suggest", { method: "POST", body: form })
      .then(function (response) {
        return response.text();
      })
      .then(showEditor)
      .catch(function () {
        var root = byId("matrix-root");
        if (!root) return;
        root.textContent = "";
        var card = el("div", "card error-card");
        card.appendChild(el("p", null, "Could not suggest factors. Reload and try again."));
        root.appendChild(card);
      });
  }

  function loadExample() {
    pinned = [];
    fetch("/requirements/matrix/example")
      .then(function (response) {
        return response.text();
      })
      .then(showEditor)
      .catch(function () {});
  }

  /* ---------- what Ship check reads ---------- */

  function rememberMatrix() {
    var holder = byId("matrix-data");
    if (!holder) return;
    var data;
    try {
      data = JSON.parse(holder.textContent);
    } catch (e) {
      return;
    }
    if (!data || !data.runs) return;
    var run = readRun();
    if (!run) return;
    run.matrix = data;
    /* A loaded sample keeps working, but is never your latest work. */
    if (byId("matrix-root").querySelector("[data-is-example]")) {
      run.matrix_is_example = true;
    } else {
      delete run.matrix_is_example;
    }
    writeRun(run);
  }

  function download(path, filename) {
    var status = byId("matrix-download-status");
    if (status) status.textContent = "Building the file…";
    fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(editorBody())
    })
      .then(function (response) {
        if (!response.ok) throw new Error("bad matrix");
        return response.blob();
      })
      .then(function (blob) {
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
        if (status) status.textContent = "Could not build the file. Fix the factors first.";
      });
  }

  /* ---------- editing ---------- */

  function addFactor() {
    var list = byId("matrix-factor-list");
    if (!list) return;
    var block = el("div", "matrix-factor");
    var head = el("div", "row matrix-factor-head");
    var name = el("input", "ctl matrix-factor-name");
    name.setAttribute("aria-label", "Factor name");
    name.setAttribute("maxlength", "40");
    name.value = "New factor";
    head.appendChild(name);
    var remove = el("button", "btn btn-small btn-danger matrix-remove-factor", "Remove factor");
    remove.type = "button";
    head.appendChild(remove);
    block.appendChild(head);
    var values = el("div", "matrix-values");
    ["A", "B"].forEach(function (value) {
      values.appendChild(valueChip(value));
    });
    var add = el("input", "ctl matrix-add-value");
    add.setAttribute("placeholder", "add value");
    add.setAttribute("maxlength", "40");
    add.setAttribute("aria-label", "Add a value");
    values.appendChild(add);
    block.appendChild(values);
    list.appendChild(block);
    name.focus();
    name.select();
    queueRebuild();
  }

  function valueChip(value) {
    var chip = el("span", "chip-value", value);
    chip.setAttribute("data-value", value);
    var remove = el("button", "btn btn-icon-tiny matrix-remove-value", "×");
    remove.type = "button";
    remove.setAttribute("aria-label", "Remove " + value);
    chip.appendChild(remove);
    return chip;
  }

  function addRule() {
    var factors = readFactors().filter(function (one) {
      return one.values.length > 0;
    });
    if (factors.length < 2) return;
    var list = byId("matrix-rule-list");
    if (!list) return;

    var item = el("li", "matrix-rule matrix-rule-new");
    var left = pickers(factors, "if");
    var right = pickers(factors, "then");
    item.appendChild(left.factor);
    item.appendChild(left.value);
    item.appendChild(el("span", "muted small", "never with"));
    item.appendChild(right.factor);
    item.appendChild(right.value);
    var save = el("button", "btn btn-small matrix-save-rule", "Add");
    save.type = "button";
    item.appendChild(save);
    var cancel = el("button", "btn btn-small btn-danger matrix-remove-rule", "Cancel");
    cancel.type = "button";
    item.appendChild(cancel);
    list.appendChild(item);
    var empty = byId("matrix-no-rules");
    if (empty) empty.hidden = true;
  }

  function pickers(factors, side) {
    var factor = el("select", "ctl matrix-rule-" + side + "-factor");
    factor.setAttribute("aria-label", side === "if" ? "First factor" : "Second factor");
    var value = el("select", "ctl matrix-rule-" + side + "-value");
    value.setAttribute("aria-label", side === "if" ? "First value" : "Second value");
    factors.forEach(function (one) {
      var option = el("option", null, one.name);
      option.value = one.name;
      factor.appendChild(option);
    });
    if (side === "then" && factors.length > 1) factor.selectedIndex = 1;

    function fillValues() {
      value.textContent = "";
      var chosen = factors.filter(function (one) {
        return one.name === factor.value;
      })[0];
      ((chosen && chosen.values) || []).forEach(function (one) {
        var option = el("option", null, one);
        option.value = one;
        value.appendChild(option);
      });
    }
    factor.addEventListener("change", fillValues);
    fillValues();
    return { factor: factor, value: value };
  }

  function saveRule(item) {
    var ifFactor = item.querySelector(".matrix-rule-if-factor");
    var ifValue = item.querySelector(".matrix-rule-if-value");
    var thenFactor = item.querySelector(".matrix-rule-then-factor");
    var thenValue = item.querySelector(".matrix-rule-then-value");
    if (!ifFactor || !thenFactor) return;
    if (ifFactor.value === thenFactor.value) return;

    var row = el("li", "matrix-rule");
    row.setAttribute("data-if-factor", ifFactor.value);
    row.setAttribute("data-if-value", ifValue.value);
    row.setAttribute("data-then-factor", thenFactor.value);
    row.setAttribute("data-then-value", thenValue.value);
    var line = el("span");
    line.appendChild(el("strong", null, ifFactor.value + "=" + ifValue.value));
    line.appendChild(document.createTextNode(" never with "));
    line.appendChild(el("strong", null, thenFactor.value + "=" + thenValue.value));
    row.appendChild(line);
    row.appendChild(el("span", "spacer"));
    var remove = el("button", "btn btn-small btn-danger matrix-remove-rule", "Remove");
    remove.type = "button";
    row.appendChild(remove);
    item.parentNode.replaceChild(row, item);
    queueRebuild();
  }

  function togglePin(button) {
    var row = parseInt(button.getAttribute("data-run"), 10);
    var table = document.querySelectorAll(".matrix-table tr");
    if (isNaN(row) || !table.length) return;
    var cells = table[row + 1] ? table[row + 1].querySelectorAll("td") : [];
    var names = [];
    var headers = table[0].querySelectorAll("th");
    Array.prototype.forEach.call(headers, function (header) {
      names.push(header.textContent.trim());
    });
    var entry = {};
    for (var i = 1; i < cells.length - 2; i++) {
      entry[names[i]] = cells[i].textContent.trim();
    }
    var key = JSON.stringify(entry);
    var at = -1;
    pinned.forEach(function (one, index) {
      if (JSON.stringify(one) === key) at = index;
    });
    if (at === -1) pinned.push(entry);
    else pinned.splice(at, 1);
    rebuild();
  }

  /* ---------- wiring ---------- */

  document.addEventListener("click", function (event) {
    var target = event.target;
    if (!target || !target.closest) return;

    if (target.closest("#matrix-suggest")) {
      // An explicit click is the one time the model is asked.
      suggest();
      return;
    }
    if (target.closest("#matrix-example")) {
      loadExample();
      return;
    }
    if (target.closest("#matrix-add-factor")) {
      addFactor();
      return;
    }
    if (target.closest("#matrix-add-rule")) {
      addRule();
      return;
    }
    if (target.closest("#download-matrix-config")) {
      download("/requirements/matrix/export/playwright", "playwright.matrix.config.ts");
      return;
    }
    if (target.closest("#download-matrix-csv")) {
      download("/requirements/matrix/export/csv", "test-matrix.csv");
      return;
    }
    var save = target.closest(".matrix-save-rule");
    if (save) {
      saveRule(save.closest(".matrix-rule"));
      return;
    }
    var pin = target.closest(".matrix-pin");
    if (pin) {
      togglePin(pin);
      return;
    }
    var removeFactor = target.closest(".matrix-remove-factor");
    if (removeFactor) {
      var block = removeFactor.closest(".matrix-factor");
      if (block) block.parentNode.removeChild(block);
      queueRebuild();
      return;
    }
    var removeValue = target.closest(".matrix-remove-value");
    if (removeValue) {
      var chip = removeValue.closest(".chip-value");
      if (chip) chip.parentNode.removeChild(chip);
      queueRebuild();
      return;
    }
    var removeRule = target.closest(".matrix-remove-rule");
    if (removeRule) {
      var item = removeRule.closest(".matrix-rule");
      var wasNew = item && item.classList.contains("matrix-rule-new");
      if (item) item.parentNode.removeChild(item);
      if (!wasNew) queueRebuild();
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Enter") return;
    var box = event.target;
    if (!box || !box.classList || !box.classList.contains("matrix-add-value")) return;
    event.preventDefault();
    var value = box.value.trim();
    if (!value) return;
    box.parentNode.insertBefore(valueChip(value), box);
    box.value = "";
    queueRebuild();
  });

  document.addEventListener("input", function (event) {
    var box = event.target;
    if (box && box.classList && box.classList.contains("matrix-factor-name")) {
      queueRebuild();
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    if (!byId("matrix-root")) return;
    var run = readRun() || {};
    var saved = run.matrix;
    // Only ask the model when this browser has nothing to show.
    if (saved && saved.factors && saved.factors.length >= 2) suggest(saved);
    else suggest();
  });
})();
