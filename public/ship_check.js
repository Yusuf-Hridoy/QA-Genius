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
  var MAX_OWNER = 60;
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

  /* ---------- what the server is asked to judge ---------- */

  function body(run) {
    /* The context carries limits the criteria do not, so Ship check reads
     * it the same way the test-cases desk does. */
    var payload = { story: run.story || "", context: run.context || "" };
    /* The story's own id and status travel with it, so the report and the
     * Markdown behind it both say which story they are about. */
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
      /* Story clarity is judged against the criteria, so they travel even
       * before step 3 has turned them into test cases. */
      var texts = criteriaTexts(run).filter(function (text) {
        return text.trim() !== "";
      });
      if (texts.length) payload.criteria = texts;
    }
    if (run.risk_analysis && run.risk_analysis.analysis) {
      payload.risk_analysis = run.risk_analysis;
    }
    if (run.automation && run.automation.script) payload.automation = run.automation;
    if (run.insights) payload.insights = run.insights;
    /* The test matrix says which browsers and devices the runs cover. */
    if (run.matrix && run.matrix.runs) payload.matrix = run.matrix;
    payload.acceptances = run.ship_acceptances || {};
    /* A risk accepted on the Risk radar counts here too. */
    payload.risk_acceptances = run.risk_acceptances || {};
    /* Which checks were built from work the run has since moved past. */
    payload.stale_inputs = staleChecks(run);
    return payload;
  }

  /* Desk -> the checks it feeds. Test cases feed two of them. */
  var STALE_CHECKS = {
    risks: ["risks"],
    matrix: ["matrix"],
    automation: ["automation"],
    test_cases: ["coverage", "depth"]
  };

  function staleChecks(run) {
    if (!window.QAGRun) return [];
    var checks = [];
    window.QAGRun.staleInputs(run).forEach(function (desk) {
      (STALE_CHECKS[desk] || []).forEach(function (check) {
        if (checks.indexOf(check) === -1) checks.push(check);
      });
    });
    return checks;
  }

  function criteriaTexts(run) {
    return (run && run.criteria ? run.criteria : []).map(function (one) {
      return typeof one === "string" ? one : (one && one.text) || "";
    });
  }

  /* ---------- the page header ---------- */

  /* "04 · SHIP CHECK · CART-204 · Ready for review". Which story the
   * verdict is about belongs at the top of the screen, not halfway down. */
  function paintEyebrow(run) {
    var mark = byId("page-eyebrow");
    if (!mark) return;
    var parts = ["04 · Ship check"];
    var label = run && run.story_label ? String(run.story_label).trim() : "";
    if (label) parts.push(label);
    var word =
      window.QAGStoriesUI && run && run.story_status
        ? window.QAGStoriesUI.statusWord(run.story_status)
        : "";
    if (word) parts.push(word);
    mark.textContent = parts.join(" · ");
  }

  /* ---------- the empty state ---------- */

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

    /* With a story in hand there is nothing to say here: the report
     * carries the story card itself, at the bottom where it belongs. */
  }

  /* While the report is being worked out, the shape of it. A blank page
   * for a second reads as a page that failed. */
  function skeleton() {
    var output = byId("ship-output");
    if (!output || output.querySelector(".ship-banner")) return;
    output.textContent = "";
    var card = el("div", "ship-banner ship-working");
    var words = el("div", "ship-banner-words");
    words.appendChild(el("span", "ship-banner-label", "Decided by rules"));
    words.appendChild(el("p", "skeleton skeleton-title"));
    words.appendChild(el("p", "skeleton skeleton-line"));
    words.appendChild(el("p", "skeleton skeleton-line short"));
    card.appendChild(words);
    card.appendChild(el("div", "skeleton skeleton-circle"));
    card.setAttribute("role", "status");
    card.setAttribute("aria-label", "Working out the verdict");
    output.appendChild(card);
  }

  /* ---------- running the check ---------- */

  function show(html) {
    var output = byId("ship-output");
    if (output) output.innerHTML = html;
    liftBanner();
  }

  /* The decision belongs directly under the page title, and the line that
   * says how fresh it is belongs inside it. Both are moved rather than
   * rendered twice, so there is still one of each on the page. */
  function liftBanner() {
    var slot = document.querySelector("#ship-output #source-card-slot");
    var card = byId("source-card");
    var home = byId("source-card-home");
    if (!card) return;
    if (!slot) {
      /* No decision on screen: the card goes back where it started. */
      if (home && card.parentNode !== home) home.appendChild(card);
      card.classList.remove("source-in-banner");
      return;
    }
    if (card.parentNode !== slot) {
      card.classList.add("source-in-banner");
      slot.appendChild(card);
    }
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
    paintEyebrow(run);
    storyLine(run);
    if (!run) {
      var output = byId("ship-output");
      if (output) output.textContent = "";
      return;
    }
    skeleton();
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
    fetch("/ship/example", { method: "POST" })
      .then(function (response) {
        return response.text();
      })
      .then(function (text) {
        /* The example is a whole finished run, so the card asking the
         * reader to start one goes away while they are looking at it. */
        var root = byId("ship-root");
        if (root) root.textContent = "";
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

  /* A problem belongs under the field it is about, and the cursor belongs
   * in that field. A line beside the Save button left the reader hunting
   * for which box was wrong. */
  function sayUnderField(box, words) {
    if (!box) return;
    var line = document.getElementById(box.id + "-error");
    if (line) {
      line.textContent = words;
      line.hidden = !words;
    }
    if (words) {
      box.setAttribute("aria-invalid", "true");
      box.focus();
    } else {
      box.removeAttribute("aria-invalid");
    }
  }

  function saveAcceptance(checkId) {
    var form = formFor(checkId);
    if (!form) return;
    var box = form.querySelector(".ship-reason");
    var status = form.querySelector(".ship-accept-status");
    var reason = box ? box.value.trim() : "";
    if (reason.length < MIN_REASON || reason.length > MAX_REASON) {
      sayUnderField(
        box,
        "Write between " + MIN_REASON + " and " + MAX_REASON + " characters."
      );
      if (status) status.textContent = "";
      return;
    }
    sayUnderField(box, "");
    var owner = form.querySelector(".ship-owner");
    var review = form.querySelector(".ship-review");
    var run = readRun();
    if (!run) return;
    if (!run.ship_acceptances) run.ship_acceptances = {};
    /* Who owns it and when to look again are both optional, and both are
     * kept beside the reason rather than in a second place. */
    run.ship_acceptances[checkId] = {
      reason: reason,
      owner: owner ? owner.value.trim().slice(0, MAX_OWNER) : "",
      review_date: review ? review.value : ""
    };
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

  /* Two ways in, one panel: the circle itself, and the line of words under
   * it that says what the letter is for. */
  function gradeButtons() {
    return [byId("grade-circle"), byId("grade-open")].filter(Boolean);
  }

  function toggleGradeWhy() {
    var panel = byId("grade-why");
    var buttons = gradeButtons();
    if (!panel || !buttons.length) return;
    var open = !panel.hidden;
    panel.hidden = open;
    buttons.forEach(function (button) {
      button.setAttribute("aria-expanded", open ? "false" : "true");
    });
  }

  function closeGradeWhy() {
    var panel = byId("grade-why");
    if (!panel || panel.hidden) return;
    panel.hidden = true;
    gradeButtons().forEach(function (button) {
      button.setAttribute("aria-expanded", "false");
    });
  }

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") closeGradeWhy();
  });

  /* source_card.js rewrites its card whenever the run changes, so the card
   * is put back in the banner after it does. */
  if (window.QAGRun) {
    window.addEventListener(window.QAGRun.CHANGED_EVENT, liftBanner);
  }

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
    /* The grade circle, and the line under it, both open the sums behind
     * the letter and both close them again. */
    if (target.closest("#grade-circle") || target.closest("#grade-open")) {
      toggleGradeWhy();
      return;
    }
    if (!target.closest("#grade-why")) closeGradeWhy();
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
