/* The /report page: a whole report, read out of the address bar.
 *
 * Everything after the `#` stays in this browser. It is never sent with the
 * request, so the server has never seen this report and has nothing to
 * forget. That is the whole design: no account, no database, no link that
 * stops working because a row was deleted.
 *
 * Every string in here was written somewhere else — by Claude, by whoever
 * typed the story — so nothing is ever put on the page as HTML. `text()`
 * and `textContent` are the only ways anything reaches the screen.
 */
(function (global) {
  "use strict";

  var PREFIX = "v1.";
  /* The same cap the server uses. A link that inflates past a report is
   * not a report. */
  var MAX_UNPACKED = 2 * 1024 * 1024;
  var BROKEN =
    "This report link is broken or incomplete. Ask Claude to run the check again.";
  var STORY_LINES = 3;

  /* ---------- reading the link ---------- */

  function fromBase64Url(text) {
    var padded = String(text || "").replace(/-/g, "+").replace(/_/g, "/");
    while (padded.length % 4) padded += "=";
    var binary = global.atob(padded);
    var bytes = new Uint8Array(binary.length);
    for (var i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return bytes;
  }

  /* Raw deflate, the way the server wrote it. DecompressionStream is in
   * every browser this app supports; a browser without it gets the
   * friendly page rather than a stack trace in the console. */
  function inflateRaw(bytes) {
    if (typeof global.DecompressionStream !== "function") {
      return Promise.reject(new Error("no DecompressionStream"));
    }
    var stream = new global.DecompressionStream("deflate-raw");
    var writer = stream.writable.getWriter();
    /* Rubbish after the `#` makes the stream error, and these two reject
     * with it. The reading side below rejects with the same thing and is
     * where the answer comes from, so these are swallowed on purpose —
     * left alone they surface as an unhandled rejection in the console
     * while the page is already showing its friendly message. */
    var quiet = function () {};
    writer.write(bytes).catch(quiet);
    writer.close().catch(quiet);
    return new global.Response(stream.readable).arrayBuffer().then(function (buffer) {
      if (buffer.byteLength > MAX_UNPACKED) throw new Error("too big");
      return new TextDecoder().decode(buffer);
    });
  }

  function unpack(hash) {
    var said = String(hash || "");
    if (said.charAt(0) === "#") said = said.slice(1);
    if (said.indexOf(PREFIX) !== 0) return Promise.reject(new Error("no prefix"));
    return inflateRaw(fromBase64Url(said.slice(PREFIX.length))).then(function (text) {
      var found = JSON.parse(text);
      if (!found || typeof found !== "object" || Array.isArray(found)) {
        throw new Error("not a report");
      }
      return found;
    });
  }

  /* ---------- building the page ---------- */

  function el(tag, className, text) {
    var node = global.document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function add(parent, tag, className, text) {
    var node = el(tag, className, text);
    parent.appendChild(node);
    return node;
  }

  function list(value) {
    return Array.isArray(value) ? value : [];
  }

  function text(value) {
    return value === undefined || value === null ? "" : String(value);
  }

  function count(value, word) {
    var n = Number(value) || 0;
    return n === 1 ? n + " " + word : n + " " + word + "s";
  }

  /* 1. Header -------------------------------------------------------- */

  function header(root, data) {
    var head = add(root, "div", "page-head report-head");
    var label = text(data.story_label).trim();
    add(
      head,
      "span",
      "eyebrow",
      "REPORT FROM CLAUDE · " + (label ? label.toUpperCase() : "NO ID")
    );
    var story = text(data.story).trim();
    add(head, "h1", "page-title report-story", story || "A report with no story in it");
    add(
      head,
      "p",
      "muted small report-nothing-stored",
      "Nothing stored — the data is in this link."
    );
    head.querySelector(".report-story").style.webkitLineClamp = String(STORY_LINES);
  }

  /* 2. Decision card ------------------------------------------------- */

  var DECISION_TONE = {
    Ready: "ok",
    "Release with known risks": "warn",
    "Not ready": "bad"
  };

  function decision(root, data) {
    if (!text(data.decision)) return;
    var card = add(root, "div", "ship-banner ship-" + (DECISION_TONE[data.decision] || "warn"));
    var words = add(card, "div", "ship-banner-words");
    add(words, "span", "ship-banner-label", "Decided by rules");
    add(words, "h2", "ship-verdict-label", text(data.decision));

    var first = list(data.path_to_ready)[0];
    var line = add(words, "p", "ship-fix-first");
    if (first) {
      add(line, "span", "ship-fix-label", "Fix first:");
      line.appendChild(global.document.createTextNode(" "));
      add(line, "strong", null, text(first));
    } else {
      line.textContent = list(data.notes)[0] || "Every check that ran came back fine.";
    }

    var grade = data.grade;
    if (grade && text(grade.letter)) {
      var holder = add(card, "div", "grade-holder");
      var circle = add(holder, "div", "grade-circle-static");
      add(circle, "span", "grade-letter", text(grade.letter));
      add(
        holder,
        "p",
        "grade-points",
        (Number(grade.points) || 0) + " of " + (Number(grade.max) || 0) + " points"
      );
    }
  }

  /* 3. Stat row ------------------------------------------------------ */

  function stat(row, number, label) {
    var one = add(row, "div", "stat");
    add(one, "div", "num", String(number));
    add(one, "div", "lbl", label);
  }

  function stats(root, data) {
    var row = add(root, "div", "stat-row stat-row-4 stat-row-tight");
    stat(row, list(data.criteria).length, "Criteria");
    stat(row, list(data.test_cases).length, "Tests");
    stat(row, list(data.fixed_since_last_check).length, "Fixed by Claude");
    stat(row, list(data.problems).length, "Still open");
  }

  /* 4. What the senior tester found ---------------------------------- */

  var LEVEL_WORD = { high: "High", medium: "Medium", low: "Low" };

  function problems(root, data) {
    var fixed = list(data.fixed_since_last_check);
    var open = list(data.problems);
    var unchecked = list(data.not_checked_in_this_call);
    if (!fixed.length && !open.length && !unchecked.length) return;

    var card = add(root, "section", "card report-problems");
    add(card, "h2", "card-title", "What the senior tester found, and what happened");

    var rows = add(card, "ul", "report-rows");
    /* Open first: the list is a to-do list before it is a record. */
    open.forEach(function (problem) {
      var row = add(rows, "li", "report-row report-open");
      add(row, "span", "report-mark report-mark-open", "!");
      var body = add(row, "div", "report-row-body");
      add(body, "p", "report-says", text(problem.says));
      add(body, "p", "report-fix muted small", text(problem.fix));
      var meta = add(body, "p", "report-meta mono small");
      meta.textContent =
        text(problem.id) +
        " · " +
        (LEVEL_WORD[problem.level] || text(problem.level)) +
        " · Still open";
    });
    /* Fixed, and only fixed: every id here came from the same check being
     * run again and no longer finding it. A problem some other tool found
     * is in the list below instead, because nobody checked it this time
     * and saying "Fixed" would be a claim we cannot stand behind. */
    if (fixed.length) {
      var said =
        data.fixed_said && typeof data.fixed_said === "object"
          ? data.fixed_said
          : {};
      add(
        card,
        "h3",
        "report-subhead",
        fixed.length === 1
          ? "Fixed since the last check"
          : fixed.length + " fixed since the last check"
      );
      var done = add(card, "ul", "report-rows");
      fixed.forEach(function (id) {
        var row = add(done, "li", "report-row report-fixed");
        add(row, "span", "report-mark report-mark-fixed", "✓");
        var body = add(row, "div", "report-row-body");
        /* What it used to say, when the previous report carried it. An id
         * on its own is a row nobody can check. */
        add(body, "p", "report-says", text(said[id]) || "No longer reported.");
        add(body, "p", "report-meta mono small", text(id) + " · Fixed");
      });
    }

    if (unchecked.length) {
      add(
        card,
        "h3",
        "report-subhead",
        unchecked.length + " not checked in this call"
      );
      add(
        card,
        "p",
        "muted small",
        "A different check found these. This one does not look for them, " +
          "so they are neither fixed nor still open — nobody checked."
      );
      var skipped = add(card, "ul", "report-rows");
      unchecked.forEach(function (id) {
        var row = add(skipped, "li", "report-row report-unchecked");
        add(row, "span", "report-mark report-mark-unchecked", "–");
        var body = add(row, "div", "report-row-body");
        add(body, "p", "report-meta mono small", text(id) + " · Not checked");
      });
    }

    var asked = list(data.ask_the_po);
    if (asked.length) {
      var note = add(card, "div", "note note-ask");
      add(note, "h3", "note-title", "Ask your PO");
      var questions = add(note, "ul", "report-asks");
      asked.forEach(function (one) {
        add(questions, "li", null, text(one));
      });
    }
  }

  /* 5. The sections that are only there sometimes -------------------- */

  function risks(root, data) {
    var rows = list(data.risks);
    if (!rows.length) return;
    var card = add(root, "section", "card");
    add(card, "h2", "card-title", "Risks");
    var table = add(card, "table", "table");
    var head = add(add(table, "thead"), "tr");
    ["Risk", "Score", "Level", "Tested"].forEach(function (name) {
      add(head, "th", null, name);
    });
    var body = add(table, "tbody");
    rows.forEach(function (risk) {
      var row = add(body, "tr");
      add(row, "td", null, text(risk.id) + " " + text(risk.title));
      add(
        row,
        "td",
        "mono",
        (Number(risk.score) || 0) + "/" + (Number(risk.max_score) || 125)
      );
      add(row, "td", null, LEVEL_WORD[risk.level] || text(risk.level));
      add(row, "td", null, text(risk.coverage));
    });
  }

  function matrix(root, data) {
    var rows = list(data.runs);
    if (!rows.length) return;
    var card = add(root, "section", "card");
    add(card, "h2", "card-title", "Test matrix");
    add(
      card,
      "p",
      "muted small",
      text(data.summary) ||
        (Number(data.pairs_covered) || 0) + " of " + (Number(data.pairs_possible) || 0) + " pairs"
    );
    var names = Object.keys(rows[0].values || {});
    var table = add(card, "table", "table");
    var head = add(add(table, "thead"), "tr");
    names.forEach(function (name) {
      add(head, "th", null, name);
    });
    add(head, "th", null, "New pairs");
    add(head, "th", null, "Automated");
    var body = add(table, "tbody");
    rows.forEach(function (run) {
      var row = add(body, "tr");
      names.forEach(function (name) {
        add(row, "td", null, text((run.values || {})[name]));
      });
      add(row, "td", "mono", String(Number(run.new_pairs) || 0));
      add(row, "td", null, run.manual_only ? "By hand" : "Yes");
    });
  }

  function codeChecks(root, data) {
    var rows = list(data.findings);
    if (!rows.length) return;
    var card = add(root, "section", "card");
    add(card, "h2", "card-title", "Code checks");
    var ul = add(card, "ul", "report-rows");
    rows.forEach(function (finding) {
      var row = add(ul, "li", "report-row");
      add(
        row,
        "span",
        "report-mark " + (finding.level === "error" ? "report-mark-open" : "report-mark-warn"),
        finding.level === "error" ? "!" : "•"
      );
      var body = add(row, "div", "report-row-body");
      add(body, "p", "report-says", text(finding.says));
      add(
        body,
        "p",
        "report-meta mono small",
        text(finding.file) + (Number(finding.line) ? ":" + finding.line : "")
      );
    });
  }

  function notes(root, data) {
    var lines = list(data.notes);
    var note = text(data.report_note);
    if (!lines.length && !note) return;
    var card = add(root, "section", "card");
    add(card, "h2", "card-title", "Notes");
    var ul = add(card, "ul", "report-asks");
    if (note) add(ul, "li", null, note);
    lines.forEach(function (one) {
      add(ul, "li", null, text(one));
    });
  }

  /* 6. Buttons -------------------------------------------------------- */

  /* What the desks read out of a run.
   *
   * Every key here is one some page actually looks for, in the shape it
   * looks for it — `criteria` is {id, text} objects because the Criteria
   * desk renumbers them, `test_cases` is {result, criteria} because the
   * Test cases desk reads `.result.test_cases`, and so on. Getting the
   * shape nearly right means a desk that opens empty, which is worse than
   * one that was never filled.
   *
   * Only the parts this report carries are set: a report with no risks
   * must not plant an empty analysis for the Risk radar to open. */
  function runFrom(data) {
    var run = {
      story: text(data.story),
      story_type: text(data.story_type) || "User story",
      context: text(data.context)
    };

    var criteria = list(data.criteria);
    var texts = criteria.map(function (one) {
      return text(one.text);
    });
    if (criteria.length) {
      /* Ids follow position on every desk, so they are written that way
       * here rather than carried over from whatever the agent chose. */
      run.criteria = texts.map(function (one, index) {
        return { id: "AC-" + (index + 1), text: one };
      });
    }

    var cases = list(data.test_cases).map(toCase);
    if (cases.length) {
      run.test_cases = {
        result: { test_cases: cases, summary: emptySummary(cases.length) },
        criteria: texts
      };
    }

    /* The risks as they were sent in, with their own scores — not the
     * worked-out list, which has no effect, cause or scores on it. */
    var risks = list(data.risks_in);
    if (risks.length) {
      run.risk_analysis = {
        analysis: { failure_modes: risks.map(toRisk) },
        cases: cases,
        criteria: texts
      };
    }

    var matrix = matrixFrom(data);
    if (matrix) run.matrix = matrix;
    return run;
  }

  /* The Test matrix desk redraws itself from the factors and rules, so
   * that is what travels. The runs themselves are worked out again from
   * them, and would be ignored here anyway. */
  function matrixFrom(data) {
    var asked = data.matrix_input;
    if (!asked || typeof asked !== "object") return null;
    var factors = list(asked.factors)
      .map(function (one) {
        return {
          name: text(one.name),
          values: list(one.options).map(text),
          reason: ""
        };
      })
      .filter(function (one) {
        return one.name && one.values.length >= 2;
      });
    if (factors.length < 2) return null;
    return {
      factors: factors,
      rules: list(asked.rules).map(ruleFrom).filter(Boolean),
      pinned: list(asked.pinned),
      reasons: {},
      from_ai: false,
      suggested: []
    };
  }

  function ruleFrom(one) {
    var left = text(one.a).split("=");
    var right = text(one.b).split("=");
    if (left.length < 2 || right.length < 2) return null;
    return {
      if_factor: left[0].trim(),
      if_value: left.slice(1).join("=").trim(),
      then_factor: right[0].trim(),
      then_value: right.slice(1).join("=").trim(),
      reason: text(one.reason),
      source: "ai"
    };
  }

  var KIND_CATEGORY = {
    normal: "Functional",
    "wrong input": "Negative",
    "at the limit": "Boundary",
    unusual: "Edge Case"
  };

  function toCase(one) {
    return {
      id: text(one.id),
      title: text(one.title),
      category: KIND_CATEGORY[one.kind] || "Functional",
      pre_conditions: "",
      steps: list(one.steps).map(text),
      expected_result: text(one.expected),
      priority: "Medium",
      test_data: text(one.test_data),
      bdd_scenario: null,
      automation_feasibility: "Medium",
      automation_effort: "Medium",
      tags: [],
      traceability: list(one.covers).map(text).join(", ")
    };
  }

  function score(value) {
    var n = Number(value);
    return n >= 1 && n <= 5 ? Math.round(n) : 3;
  }

  function toRisk(one) {
    return {
      id: text(one.id),
      title: text(one.title),
      category: text(one.category) || "functional",
      effect: text(one.effect),
      cause: text(one.cause),
      severity: score(one.how_bad),
      likelihood: score(one.how_likely),
      detectability: score(one.how_hard_to_notice),
      severity_reason: "",
      likelihood_reason: "",
      detectability_reason: "",
      related_criteria: list(one.linked_criteria).map(text),
      covered_by: list(one.tested_by).map(text),
      test_idea: text(one.test_idea),
      source: "ai",
      covered_if: []
    };
  }

  function emptySummary(total) {
    return {
      total_generated: total,
      category_breakdown: [],
      priority_breakdown: [],
      automation_coverage_potential: "",
      coverage_gaps: [],
      recommendations: []
    };
  }

  function openInDesks(data) {
    var stories = global.QAGStories;
    if (!stories || !stories.create) return { error: "no-store" };
    var made = stories.create({ run: runFrom(data) });
    if (!made || !made.story) return made || { error: "failed" };
    /* Saving the story is only half of it. Every desk reads the run out of
     * sessionStorage, not out of the story list, so a story that is saved
     * and not opened leaves all four desks blank. `open` is what points
     * this tab at it and writes the run where the desks look. */
    if (stories.open) {
      stories.open(made.story.id);
    } else {
      stories.setTabStory(made.story.id);
      if (stories.setTabRev) stories.setTabRev(made.story.revision);
    }
    return made;
  }

  function buttons(root, data) {
    var row = add(root, "div", "report-actions");
    var open = add(row, "button", "btn btn-primary", "Open in QA-Genius desks");
    open.type = "button";
    open.id = "report-open";
    var excel = add(row, "button", "btn", "Download Excel");
    excel.type = "button";
    excel.id = "report-excel";
    var copy = add(row, "button", "btn", "Copy as Markdown");
    copy.type = "button";
    copy.id = "report-copy";

    open.addEventListener("click", function () {
      var made = openInDesks(data);
      if (made && made.story) {
        global.location.href = "/requirements/test-cases";
      } else {
        open.textContent = "Could not open — this browser is full";
      }
    });

    copy.addEventListener("click", function () {
      var markdown = toMarkdown(data);
      if (global.navigator && global.navigator.clipboard) {
        global.navigator.clipboard.writeText(markdown).then(function () {
          copy.textContent = "Copied";
        });
      }
    });

    excel.addEventListener("click", function () {
      post("/requirements/test-cases/export.xlsx", {
        result: runFrom(data).test_cases
          ? runFrom(data).test_cases.result
          : { test_cases: [], summary: emptySummary(0) },
        criteria: list(data.criteria).map(function (one) {
          return text(one.text);
        })
      });
    });
  }

  function post(url, body) {
    global
      .fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      })
      .then(function (response) {
        return response.ok ? response.blob() : null;
      })
      .then(function (blob) {
        if (!blob) return;
        var href = global.URL.createObjectURL(blob);
        var link = global.document.createElement("a");
        link.href = href;
        link.download = "qa-genius.xlsx";
        link.click();
        global.URL.revokeObjectURL(href);
      });
  }

  function toMarkdown(data) {
    var lines = ["# QA-Genius report", ""];
    if (text(data.story)) lines.push("> " + text(data.story), "");
    if (text(data.decision)) lines.push("**Decision:** " + text(data.decision), "");
    lines.push("- " + count(list(data.criteria).length, "criterion").replace("criterions", "criteria"));
    lines.push("- " + count(list(data.test_cases).length, "test"));
    lines.push("- " + count(list(data.problems).length, "problem still open"));
    lines.push("");
    list(data.problems).forEach(function (problem) {
      lines.push(
        "- **" + text(problem.id) + "** (" + text(problem.level) + ") " + text(problem.says)
      );
      lines.push("  - " + text(problem.fix));
    });
    if (list(data.ask_the_po).length) {
      lines.push("", "## Ask your PO", "");
      list(data.ask_the_po).forEach(function (one) {
        lines.push("- " + text(one));
      });
    }
    return lines.join("\n");
  }

  /* ---------- drawing it ---------- */

  function broken(root, message) {
    root.textContent = "";
    var card = add(root, "section", "card report-broken");
    add(card, "h2", "card-title", "This report cannot be read");
    add(card, "p", null, message || BROKEN);
    var row = add(card, "div", "report-actions");
    var home = add(row, "a", "btn btn-primary", "Go to the desks");
    home.href = "/requirements/story";
  }

  function draw(root, data) {
    root.textContent = "";
    header(root, data);
    decision(root, data);
    stats(root, data);
    problems(root, data);
    risks(root, data);
    matrix(root, data);
    codeChecks(root, data);
    notes(root, data);
    buttons(root, data);
  }

  function start() {
    var root = global.document.getElementById("report-root");
    if (!root) return;
    var hash = global.location.hash || "";
    if (!hash || hash === "#") {
      broken(root, BROKEN);
      return;
    }
    unpack(hash).then(
      function (data) {
        try {
          draw(root, data);
        } catch (e) {
          broken(root, BROKEN);
        }
      },
      function () {
        broken(root, BROKEN);
      }
    );
  }

  if (global.document) {
    if (global.document.readyState === "loading") {
      global.document.addEventListener("DOMContentLoaded", start);
    } else {
      start();
    }
  }

  global.QAGReport = {
    unpack: unpack,
    runFrom: runFrom,
    openInDesks: openInDesks,
    toMarkdown: toMarkdown,
    draw: draw,
    broken: broken,
    BROKEN: BROKEN
  };
})(typeof window !== "undefined" ? window : globalThis);
