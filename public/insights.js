/* QA-Genius v2: the Quality insights desk.
 * Picks the report files, keeps the chosen list in step with the file input,
 * and hands a failure group to the Bug desk. Only server HTML is inserted;
 * everything this file writes goes in through textContent. */
(function () {
  "use strict";

  var MAX_FILES = 5;
  var MAX_BYTES = 2 * 1024 * 1024;
  var MAX_TOTAL = 4 * 1024 * 1024;
  var PREFILL_KEY = "qag.bug_prefill";
  var RUN_KEY = "qag.run";
  var PREFILL_LIMIT = 3000;

  function byId(id) {
    return document.getElementById(id);
  }

  function setStatus(text) {
    var line = byId("insights-file-status");
    if (line) line.textContent = text;
  }

  function sizeText(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }

  /* ---------- the chosen files ---------- */

  /* The file input owns the list; this array is only what we show. */
  var chosen = [];

  function writeInput() {
    var input = byId("insights-file");
    if (!input || typeof DataTransfer === "undefined") return;
    var box = new DataTransfer();
    for (var i = 0; i < chosen.length; i++) box.items.add(chosen[i]);
    input.files = box.files;
  }

  function totalBytes() {
    var total = 0;
    for (var i = 0; i < chosen.length; i++) total += chosen[i].size;
    return total;
  }

  function drawList() {
    var list = byId("insights-file-list");
    if (!list) return;
    while (list.firstChild) list.removeChild(list.firstChild);
    for (var i = 0; i < chosen.length; i++) {
      var file = chosen[i];
      var row = document.createElement("li");
      row.className = "file-row";
      var name = document.createElement("span");
      name.className = "file-name";
      name.textContent = file.name;
      var size = document.createElement("span");
      size.className = "muted small";
      size.textContent = sizeText(file.size);
      var spacer = document.createElement("span");
      spacer.className = "spacer";
      var remove = document.createElement("button");
      remove.type = "button";
      remove.className = "btn btn-small btn-danger";
      remove.textContent = "Remove";
      remove.setAttribute("data-index", String(i));
      remove.setAttribute("aria-label", "Remove " + file.name);
      remove.addEventListener("click", onRemove);
      row.appendChild(name);
      row.appendChild(size);
      row.appendChild(spacer);
      row.appendChild(remove);
      list.appendChild(row);
    }
    /* With files on the list the drop zone has said its piece. */
    var zone = byId("insights-drop");
    if (zone) zone.hidden = chosen.length > 0;
  }

  function onRemove(event) {
    var index = parseInt(event.currentTarget.getAttribute("data-index"), 10);
    if (isNaN(index)) return;
    chosen.splice(index, 1);
    writeInput();
    drawList();
    setStatus(chosen.length ? "" : "No files chosen.");
  }

  function already(file) {
    for (var i = 0; i < chosen.length; i++) {
      if (chosen[i].name === file.name && chosen[i].size === file.size) return true;
    }
    return false;
  }

  function add(files) {
    if (!files) return;
    var refused = [];
    for (var i = 0; i < files.length; i++) {
      var file = files[i];
      if (chosen.length >= MAX_FILES) {
        refused.push("only " + MAX_FILES + " files at a time");
        break;
      }
      if (file.size > MAX_BYTES) {
        refused.push(file.name + " is over 2 MB");
        continue;
      }
      if (totalBytes() + file.size > MAX_TOTAL) {
        refused.push("that would pass 4 MB in total");
        break;
      }
      if (!already(file)) chosen.push(file);
    }
    writeInput();
    drawList();
    setStatus(refused.length ? "Not added: " + refused.join(", ") + "." : "");
  }

  /* ---------- the facts the Explain button posts back ---------- */

  function readJson(id) {
    var holder = byId(id);
    if (!holder) return null;
    try {
      return JSON.parse(holder.textContent);
    } catch (e) {
      return null;
    }
  }

  function fillFacts() {
    var field = byId("insights-facts-input");
    var holder = byId("insights-facts");
    if (field && holder) field.value = holder.textContent;
  }

  /* Ship check asks "how did the last run go?". A test run is not tied to a
   * story, so whatever was analysed last is the answer, even when the run in
   * sessionStorage belongs to another feature. */
  function saveInsightsToRun() {
    var facts = readJson("insights-facts");
    if (!facts) return;
    var run = null;
    try {
      var raw = sessionStorage.getItem(RUN_KEY);
      run = raw ? JSON.parse(raw) : null;
    } catch (e) {
      return;
    }
    if (!run || typeof run !== "object") run = {};
    run.insights = facts;
    try {
      sessionStorage.setItem(RUN_KEY, JSON.stringify(run));
    } catch (e) {
      /* storage blocked: the page still works, Ship check just won't see it */
    }
  }

  function onResultSwap() {
    fillFacts();
    saveInsightsToRun();
  }

  function copyStatus(text) {
    var line = byId("insights-copy-status");
    if (line) line.textContent = text;
  }

  function copyMarkdown() {
    var text = readJson("insights-md");
    if (!text) {
      copyStatus("Nothing to copy.");
      return;
    }
    if (!navigator.clipboard || !navigator.clipboard.writeText) {
      copyStatus("Could not copy");
      return;
    }
    navigator.clipboard.writeText(text).then(
      function () {
        copyStatus("Copied");
      },
      function () {
        copyStatus("Could not copy");
      }
    );
  }

  /* ---------- hand a group to the Bug desk ---------- */

  function draftBug(button) {
    var parts = [button.getAttribute("data-message") || "A test run failure."];
    var tests = button.getAttribute("data-tests");
    if (tests) parts.push("Failing tests: " + tests);
    var runs = button.getAttribute("data-runs");
    if (runs) parts.push("Seen in: " + runs);
    var notes = parts.join("\n\n").slice(0, PREFILL_LIMIT);
    try {
      sessionStorage.setItem(PREFILL_KEY, JSON.stringify({ notes: notes }));
    } catch (e) {
      /* a browser with storage switched off still gets to the Bug desk */
    }
    window.location.href = "/bugs";
  }

  /* ---------- wiring ---------- */

  document.addEventListener("click", function (event) {
    var target = event.target;
    if (!target || !target.closest) return;
    if (target.closest("#insights-pick")) {
      var input = byId("insights-file");
      if (input) input.click();
      return;
    }
    if (target.closest("#insights-copy-md")) {
      copyMarkdown();
      return;
    }
    var draft = target.closest(".insights-draft-bug");
    if (draft) draftBug(draft);
  });

  document.addEventListener("change", function (event) {
    if (event.target && event.target.id === "insights-file") {
      /* The browser replaced the input's list with just this pick; add it to ours. */
      var picked = event.target.files;
      var fresh = [];
      for (var i = 0; i < picked.length; i++) fresh.push(picked[i]);
      add(fresh);
    }
  });

  function onDragOver(event) {
    event.preventDefault();
    var zone = byId("insights-drop");
    if (zone) zone.classList.add("over");
  }

  function onDragLeave() {
    var zone = byId("insights-drop");
    if (zone) zone.classList.remove("over");
  }

  function onDrop(event) {
    var zone = byId("insights-drop");
    if (!zone) return;
    event.preventDefault();
    zone.classList.remove("over");
    if (event.dataTransfer && event.dataTransfer.files) add(event.dataTransfer.files);
  }

  document.addEventListener("DOMContentLoaded", function () {
    var zone = byId("insights-drop");
    if (zone) {
      zone.addEventListener("dragover", onDragOver);
      zone.addEventListener("dragleave", onDragLeave);
      zone.addEventListener("drop", onDrop);
    }
    fillFacts();
  });

  /* Every result card arrives as a server swap; the facts come with it. */
  document.body.addEventListener("htmx:afterSwap", onResultSwap);
})();
