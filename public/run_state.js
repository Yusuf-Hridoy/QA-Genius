/* QA-Genius v2: what the run holds, and whether each desk still matches it.
 *
 * One question runs through the whole app: "is this built from my latest
 * work?" The answer is a fingerprint. Every part of the run that a desk can
 * be built from gets hashed on write; every derived result records the
 * hashes it was built from. Comparing the two is the whole mechanism.
 *
 * Nothing here calls a model or the network. It only reads and writes
 * sessionStorage and says what changed. */
(function (global) {
  "use strict";

  var RUN_KEY = "qag.run";
  var CHANGED_EVENT = "qag:run-changed";
  // A desk finished drawing a result the card may need to dim.
  var RESULT_EVENT = "qag:result-shown";

  /* The parts of a run a desk can be built from. */
  var PARTS = ["story", "criteria", "test_cases", "automation_cases", "automation"];

  /* Derived result -> the parts it was built from. */
  var BUILT_FROM = {
    test_cases: ["story", "criteria"],
    automation: ["automation_cases"],
    risk_analysis: ["story", "criteria", "test_cases"],
    matrix: ["story"],
    story_analysis: ["story"],
    duel_summary: ["story"]
  };

  /* Desk -> the result it shows and the parts that make it stale. */
  var DESKS = {
    test_cases: { key: "test_cases", stale_on: ["story", "criteria"] },
    automation: { key: "automation", stale_on: ["automation_cases"] },
    risks: { key: "risk_analysis", stale_on: ["story", "criteria"], auto_on: ["test_cases"] },
    matrix: { key: "matrix", stale_on: ["story"] }
  };

  /* What a changed part is called in a sentence. */
  /* One sentence per part, and each one names the part it is about. The
   * story line used to say "Your story was edited" for a context change
   * too, and "Your criteria changed" turned up when only the story had. */
  var PART_WORDS = {
    story: "Your story changed after this was built",
    criteria: "Your criteria changed",
    test_cases: "Your test cases changed",
    automation_cases: "Your selected test cases changed",
    automation: "Your automation changed"
  };

  var STORY_TITLE_MAX = 70;

  /* ---------- storage ---------- */

  function read() {
    try {
      var raw = global.sessionStorage.getItem(RUN_KEY);
      var run = raw ? JSON.parse(raw) : null;
      return run && typeof run === "object" ? run : {};
    } catch (e) {
      return {};
    }
  }

  /* Everything write() does to a run except saving it: the fingerprints
   * and the record of what each result was built from. A store that keeps
   * a run of its own hands it through here first, so the copy it holds is
   * the copy a page would write back and opening it changes nothing. */
  function stampRun(run) {
    var saved = run && typeof run === "object" ? run : {};
    /* The revision this tab has seen lives in the tab, beside the story id,
     * never in the run. A page that writes a run copy it read before its
     * own last save would otherwise put the old number back and make its
     * next edit look stale. Writing the run never binds the tab. */
    delete saved._story_rev;
    stampAll(saved);
    recordBuilds(saved);
    return saved;
  }

  function write(run) {
    var saved = stampRun(run);
    try {
      global.sessionStorage.setItem(RUN_KEY, JSON.stringify(saved));
    } catch (e) {
      /* storage blocked: the page still works, the run just will not survive */
    }
    announce();
    return saved;
  }

  function fire(name) {
    if (!global.dispatchEvent || !global.CustomEvent) return;
    try {
      global.dispatchEvent(new global.CustomEvent(name));
    } catch (e) {
      /* a browser too old for CustomEvent still gets the saved run */
    }
  }

  function announce() {
    fire(CHANGED_EVENT);
  }

  function announceResult() {
    fire(RESULT_EVENT);
  }

  /* ---------- fingerprints ---------- */

  /* Sorted keys, no whitespace: the same data hashes the same however the
   * object was built up. */
  function canonical(value) {
    if (value === null || value === undefined) return "null";
    if (Array.isArray(value)) {
      return "[" + value.map(canonical).join(",") + "]";
    }
    if (typeof value === "object") {
      var keys = Object.keys(value).sort();
      return (
        "{" +
        keys
          .map(function (key) {
            return JSON.stringify(key) + ":" + canonical(value[key]);
          })
          .join(",") +
        "}"
      );
    }
    return JSON.stringify(value);
  }

  /* FNV-1a, 32 bit, as 8 hex characters. Short, stable and fast enough to run
   * on every write; this is a change detector, not a security hash. */
  function hash(value) {
    var text = canonical(value);
    var sum = 0x811c9dc5;
    for (var i = 0; i < text.length; i++) {
      sum ^= text.charCodeAt(i);
      sum = (sum + ((sum << 1) + (sum << 4) + (sum << 7) + (sum << 8) + (sum << 24))) >>> 0;
    }
    var hex = sum.toString(16);
    while (hex.length < 8) hex = "0" + hex;
    return hex;
  }

  /* The live criteria, which is what step 2 edits. The copy frozen inside a
   * test-case result is only a fallback for a run that never had its own
   * list: preferring it would hide the very edit this module exists to spot. */
  function criteriaTexts(run) {
    if (run.criteria && run.criteria.length) {
      return run.criteria.map(function (one) {
        return typeof one === "string" ? one : (one && one.text) || "";
      });
    }
    if (run.test_cases && run.test_cases.criteria) return run.test_cases.criteria;
    return [];
  }

  function caseList(run) {
    if (run.test_cases && run.test_cases.result) {
      return run.test_cases.result.test_cases || [];
    }
    return [];
  }

  /* The content of one part: what changing it should change. */
  function partValue(run, part) {
    if (part === "story") {
      return [run.story || "", run.story_type || "", run.context || ""];
    }
    if (part === "criteria") return criteriaTexts(run);
    if (part === "test_cases") return caseList(run);
    if (part === "automation_cases") {
      return (run.automation_cases || []).map(function (one) {
        return (one && one.id) || one;
      });
    }
    if (part === "automation") {
      return (run.automation && run.automation.script) || null;
    }
    return null;
  }

  function partCount(run, part) {
    var value = partValue(run, part);
    return Array.isArray(value) && part !== "story" ? value.length : 0;
  }

  function stamp(run, part) {
    if (!run.fp) run.fp = {};
    run.fp[part] = {
      hash: hash(partValue(run, part)),
      count: partCount(run, part),
      at: new Date().toISOString()
    };
    return run.fp[part];
  }

  /* Only re-stamp what actually changed, so "at" stays the time of the real
   * edit rather than the time of the last unrelated save. */
  function stampAll(run) {
    if (!run.fp) run.fp = {};
    PARTS.forEach(function (part) {
      var current = hash(partValue(run, part));
      var known = run.fp[part];
      if (!known || known.hash !== current) stamp(run, part);
    });
  }

  function sourcesOf(run, parts) {
    var found = {};
    parts.forEach(function (part) {
      var stamped = (run.fp && run.fp[part]) || stamp(run, part);
      found[part] = { hash: stamped.hash, count: stamped.count };
    });
    return found;
  }

  /* A derived result that just changed was built from what the run holds
   * now - unless it is a loaded sample, which was built from nothing of
   * yours and must never be counted as your latest work. */
  function recordBuilds(run) {
    if (!run.fp_derived) run.fp_derived = {};
    Object.keys(BUILT_FROM).forEach(function (key) {
      if (!run[key]) return;
      var current = hash(run[key]);
      if (run.fp_derived[key] === current) return;
      run.fp_derived[key] = current;
      if (run[key + "_is_example"]) {
        delete run[key + "_built_from"];
        delete run[key + "_built_at"];
        return;
      }
      run[key + "_built_from"] = sourcesOf(run, BUILT_FROM[key]);
      run[key + "_built_at"] = new Date().toISOString();
    });
  }

  /* "Keep what I have": the result is declared current without rebuilding it. */
  function markBuilt(run, key) {
    if (!BUILT_FROM[key]) return run;
    run[key + "_built_from"] = sourcesOf(run, BUILT_FROM[key]);
    run[key + "_built_at"] = new Date().toISOString();
    if (!run.fp_derived) run.fp_derived = {};
    if (run[key]) run.fp_derived[key] = hash(run[key]);
    return run;
  }

  /* ---------- freshness ---------- */

  function timeAgo(iso) {
    if (!iso) return "";
    var then = new Date(iso).getTime();
    if (isNaN(then)) return "";
    var diff = Date.now() - then;
    if (diff < 60000) return "just now";
    if (diff < 3600000) {
      var mins = Math.floor(diff / 60000);
      return mins + " min ago";
    }
    if (diff < 86400000) {
      var hours = Math.floor(diff / 3600000);
      return hours + " h ago";
    }
    if (diff < 172800000) return "yesterday";
    return new Date(iso).toLocaleDateString();
  }

  function changeSentence(run, part, before) {
    var now = (run.fp && run.fp[part]) || {};
    var when = timeAgo(now.at);
    var words = PART_WORDS[part] || "Something changed";
    var line = words + (when ? " " + when : "");
    var had = before && typeof before.count === "number" ? before.count : null;
    if (part !== "story" && had !== null && had !== now.count) {
      line += " (" + had + " → " + now.count + ")";
    }
    return line;
  }

  function differing(run, builtFrom, parts) {
    var changed = [];
    parts.forEach(function (part) {
      var before = builtFrom[part];
      var now = (run.fp && run.fp[part]) || {};
      if (!before || before.hash !== now.hash) changed.push(part);
    });
    return changed;
  }

  function statusOf(desk, run) {
    run = run || read();
    if (desk === "ship") return shipStatus(run);

    var spec = DESKS[desk];
    if (!spec) return { state: "none", changes: [], auto: false };
    if (!run[spec.key]) return { state: "none", changes: [], auto: false };
    // A sample on screen is not an answer about your own story.
    if (run[spec.key + "_is_example"]) {
      return { state: "example", changes: [], auto: false, built_at: "" };
    }

    var builtFrom = run[spec.key + "_built_from"] || {};
    var stale = differing(run, builtFrom, spec.stale_on);
    if (stale.length) {
      return {
        state: "stale",
        changes: stale.map(function (part) {
          return changeSentence(run, part, builtFrom[part]);
        }),
        auto: false,
        built_at: run[spec.key + "_built_at"] || ""
      };
    }
    // Work code can redo on its own does not make a desk out of date.
    var auto = spec.auto_on ? differing(run, builtFrom, spec.auto_on) : [];
    return {
      state: "fresh",
      changes: auto.map(function (part) {
        return changeSentence(run, part, builtFrom[part]);
      }),
      auto: auto.length > 0,
      built_at: run[spec.key + "_built_at"] || ""
    };
  }

  /* Ship check is recomputed every time it opens, so it is never out of date
   * itself - but the results it reads can be. */
  function shipStatus(run) {
    var stale = [];
    ["risks", "matrix", "test_cases", "automation"].forEach(function (desk) {
      if (statusOf(desk, run).state === "stale") stale.push(desk);
    });
    return { state: "fresh", changes: stale, auto: true, built_at: "" };
  }

  function staleInputs(run) {
    return shipStatus(run || read()).changes;
  }

  /* ---------- what the run holds ---------- */

  function firstSentence(text) {
    var cleaned = String(text || "").trim().replace(/\s+/g, " ");
    if (!cleaned) return "";
    var stop = cleaned.search(/[.!?](\s|$)/);
    var line = stop > 0 ? cleaned.slice(0, stop) : cleaned;
    if (line.length > STORY_TITLE_MAX) {
      line = line.slice(0, STORY_TITLE_MAX - 1).replace(/\s+\S*$/, "") + "…";
    }
    return line;
  }

  function describeLatest(run) {
    run = run || read();
    return {
      storyTitle: firstSentence(run.story),
      criteriaCount: criteriaTexts(run).filter(function (text) {
        return String(text || "").trim() !== "";
      }).length,
      caseCount: caseList(run).length,
      automationCount: (run.automation_cases || []).length
    };
  }

  global.QAGRun = {
    RUN_KEY: RUN_KEY,
    CHANGED_EVENT: CHANGED_EVENT,
    RESULT_EVENT: RESULT_EVENT,
    announceResult: announceResult,
    PARTS: PARTS,
    DESKS: DESKS,
    read: read,
    write: write,
    stampRun: stampRun,
    stamp: stamp,
    markBuilt: markBuilt,
    statusOf: statusOf,
    staleInputs: staleInputs,
    timeAgo: timeAgo,
    describeLatest: describeLatest,
    hash: hash,
    canonical: canonical
  };
})(typeof window !== "undefined" ? window : globalThis);
