/* QA-Genius v2: Ship check.
 * Reads the run out of sessionStorage, posts it to /ship/report and shows the
 * verdict the server computed. No key is read and no AI is called: the route
 * only does arithmetic on results the other desks already produced.
 * Only server HTML is inserted; everything this file writes goes in through
 * textContent. */
(function () {
  "use strict";

  var RUN_KEY = "qag.run";
  var STORY_IN_LINE = 120;
  var MIN_REASON = 10;
  var MAX_REASON = 300;

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
      /* storage blocked: the verdict still shows, the acceptance just will not
       * survive the next navigation */
    }
  }

  /* ---------- what the server is asked to judge ---------- */

  function body(run) {
    var payload = { story: run.story || "" };
    if (run.story_analysis) payload.story_analysis = run.story_analysis;
    if (run.duel_summary) payload.duel_summary = run.duel_summary;
    if (run.test_cases && run.test_cases.result) {
      payload.test_cases = {
        result: run.test_cases.result,
        criteria: run.test_cases.criteria || criteriaTexts(run)
      };
    }
    if (run.risk_analysis && run.risk_analysis.analysis) {
      payload.risk_analysis = run.risk_analysis;
    }
    if (run.automation && run.automation.script) payload.automation = run.automation;
    if (run.insights) payload.insights = run.insights;
    payload.acceptances = run.ship_acceptances || {};
    return payload;
  }

  function criteriaTexts(run) {
    return (run && run.criteria ? run.criteria : []).map(function (one) {
      return typeof one === "string" ? one : (one && one.text) || "";
    });
  }

  /* ---------- the line above the verdict ---------- */

  function storyLine(run) {
    var root = byId("ship-root");
    if (!root) return;
    root.textContent = "";
    var story = String(run && run.story ? run.story : "").trim();

    var card = el("div", "card ship-story");
    if (!story) {
      card.className = "card ship-story card-form";
      card.appendChild(el("h2", null, "Start from a story"));
      card.appendChild(
        el(
          "p",
          "muted",
          "Ship check reads what the other desks found. Check a story first, " +
            "or look at a finished run."
        )
      );
      var row = el("div", "empty-actions");
      var start = el("a", "btn btn-primary", "Go to Requirements");
      start.href = "/requirements/story";
      row.appendChild(start);
      var example = el("button", "btn", "Load example");
      example.type = "button";
      example.id = "ship-example";
      row.appendChild(example);
      card.appendChild(row);
      root.appendChild(card);
      return;
    }

    var shown = story.length > STORY_IN_LINE ? story.slice(0, STORY_IN_LINE) + "…" : story;
    card.appendChild(el("span", "eyebrow", "Your story"));
    card.appendChild(el("p", "ship-story-text", shown));
    var line = el("div", "row");
    var change = el("a", "small", "Change story");
    change.href = "/requirements/story";
    line.appendChild(change);
    card.appendChild(line);
    root.appendChild(card);
  }

  /* ---------- running the check ---------- */

  function show(html) {
    var output = byId("ship-output");
    if (output) output.innerHTML = html;
  }

  function failed(message) {
    var output = byId("ship-output");
    if (!output) return;
    output.textContent = "";
    var card = el("div", "card");
    card.appendChild(el("p", "muted", message));
    output.appendChild(card);
  }

  function runCheck() {
    var run = readRun();
    storyLine(run);
    if (!run) {
      var output = byId("ship-output");
      if (output) output.textContent = "";
      return;
    }
    fetch("/ship/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body(run))
    })
      .then(function (response) {
        return response.text().then(function (text) {
          show(text);
        });
      })
      .catch(function () {
        failed("Could not work out the verdict. Reload the page and try again.");
      });
  }

  function loadExample() {
    fetch("/ship/example")
      .then(function (response) {
        return response.text();
      })
      .then(function (text) {
        show(text);
      })
      .catch(function () {
        failed("Could not load the example.");
      });
  }

  /* ---------- risk acceptance ---------- */

  function formFor(checkId) {
    var forms = document.querySelectorAll('.ship-accept-form[data-check="' + checkId + '"]');
    return forms.length ? forms[0] : null;
  }

  function openAcceptForm(checkId) {
    var form = formFor(checkId);
    if (!form) return;
    form.hidden = false;
    var box = form.querySelector(".ship-reason");
    if (box) {
      box.focus();
    }
  }

  function closeAcceptForm(checkId) {
    var form = formFor(checkId);
    if (!form) return;
    form.hidden = true;
    var box = form.querySelector(".ship-reason");
    if (box) box.value = "";
    var status = form.querySelector(".ship-accept-status");
    if (status) status.textContent = "";
  }

  function saveAcceptance(checkId) {
    var form = formFor(checkId);
    if (!form) return;
    var box = form.querySelector(".ship-reason");
    var status = form.querySelector(".ship-accept-status");
    var reason = box ? box.value.trim() : "";
    if (reason.length < MIN_REASON || reason.length > MAX_REASON) {
      if (status) {
        status.textContent =
          "Write between " + MIN_REASON + " and " + MAX_REASON + " characters.";
      }
      return;
    }
    var run = readRun();
    if (!run) return;
    if (!run.ship_acceptances) run.ship_acceptances = {};
    run.ship_acceptances[checkId] = reason;
    writeRun(run);
    runCheck();
  }

  function removeAcceptance(checkId) {
    var run = readRun();
    if (!run || !run.ship_acceptances) return;
    delete run.ship_acceptances[checkId];
    writeRun(run);
    runCheck();
  }

  /* ---------- copy and print ---------- */

  function copyStatus(text) {
    var line = byId("ship-copy-status");
    if (line) line.textContent = text;
  }

  function copyMarkdown() {
    var holder = byId("ship-md");
    var markdown = null;
    if (holder) {
      try {
        markdown = JSON.parse(holder.textContent);
      } catch (e) {
        markdown = null;
      }
    }
    if (!markdown) {
      copyStatus("Nothing to copy.");
      return;
    }
    if (!navigator.clipboard || !navigator.clipboard.writeText) {
      copyStatus("Could not copy");
      return;
    }
    navigator.clipboard.writeText(markdown).then(
      function () {
        copyStatus("Copied");
      },
      function () {
        copyStatus("Could not copy");
      }
    );
  }

  /* Print wants every detail open; the screen wants them closed again after. */
  function printReport() {
    var opened = [];
    var blocks = document.querySelectorAll(".ship-details");
    Array.prototype.forEach.call(blocks, function (block) {
      if (!block.open) {
        block.open = true;
        opened.push(block);
      }
    });
    document.body.classList.add("ship-print");
    window.print();
    document.body.classList.remove("ship-print");
    opened.forEach(function (block) {
      block.open = false;
    });
  }

  /* ---------- wiring ---------- */

  document.addEventListener("click", function (event) {
    var target = event.target;
    if (!target || !target.closest) return;

    if (target.closest("#ship-example")) {
      loadExample();
      return;
    }
    if (target.closest("#ship-copy-md")) {
      copyMarkdown();
      return;
    }
    if (target.closest("#ship-print")) {
      printReport();
      return;
    }
    var accept = target.closest(".ship-accept");
    if (accept) {
      openAcceptForm(accept.getAttribute("data-check"));
      return;
    }
    var save = target.closest(".ship-accept-save");
    if (save) {
      saveAcceptance(save.getAttribute("data-check"));
      return;
    }
    var cancel = target.closest(".ship-accept-cancel");
    if (cancel) {
      closeAcceptForm(cancel.getAttribute("data-check"));
      return;
    }
    var remove = target.closest(".ship-unaccept");
    if (remove) removeAcceptance(remove.getAttribute("data-check"));
  });

  document.addEventListener("DOMContentLoaded", runCheck);
})();
