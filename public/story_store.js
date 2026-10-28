/* QA-Genius v2: several stories, kept in this browser.
 *
 * The run itself still lives in sessionStorage under "qag.run" and still
 * disappears with the tab. What changes here is that a copy of it is kept in
 * localStorage, which stays until the reader deletes it, so a story can be
 * opened again tomorrow and a second story can be started without losing the
 * first. Every screen that offers this says so in those words.
 *
 * Nothing is sent anywhere. There is no account, no server and no database:
 * one key in one browser, and a Delete all button that really deletes.
 *
 * Every storage call is wrapped, because a private window, a full disk and a
 * blocked origin all throw here, and none of them should break the page. */
(function (global) {
  "use strict";

  var KEY = "qag.stories.v1";
  var VERSION = 1;
  var MAX_STORIES = 25;
  /* Above this the browser is close to refusing the write, and a refusal
   * halfway through would lose work. We stop before that, loudly. */
  var MAX_BYTES = 4 * 1024 * 1024;
  var TITLE_MAX = 80;
  var LABEL_MAX = 24;
  var SAVE_DELAY = 600;
  var STATUSES = ["draft", "review", "done"];
  var STATUS_WORDS = { draft: "Draft", review: "Ready for review", done: "Done" };
  var LABEL_OK = /^[A-Za-z0-9_-]{1,24}$/;
  var CHANGED_EVENT = "qag:stories-changed";

  /* ---------- storage ---------- */

  function empty() {
    return { version: VERSION, active_id: "", stories: [] };
  }

  function readAll() {
    try {
      var raw = global.localStorage.getItem(KEY);
      var data = raw ? JSON.parse(raw) : null;
      if (!data || typeof data !== "object" || !Array.isArray(data.stories)) {
        return empty();
      }
      return {
        version: VERSION,
        active_id: typeof data.active_id === "string" ? data.active_id : "",
        stories: data.stories.filter(isStory)
      };
    } catch (e) {
      return empty();
    }
  }

  /* Returns "" when the write went through, or why it did not. */
  function writeAll(data) {
    var text;
    try {
      text = JSON.stringify(data);
    } catch (e) {
      return "That story could not be saved.";
    }
    if (text.length > MAX_BYTES) return "full";
    try {
      global.localStorage.setItem(KEY, text);
    } catch (e) {
      return "full";
    }
    announce();
    return "";
  }

  function announce() {
    if (!global.dispatchEvent || !global.CustomEvent) return;
    try {
      global.dispatchEvent(new global.CustomEvent(CHANGED_EVENT));
    } catch (e) {
      /* a browser too old for CustomEvent still has its stories */
    }
  }

  function isStory(one) {
    return (
      one &&
      typeof one === "object" &&
      typeof one.id === "string" &&
      one.id !== "" &&
      one.run &&
      typeof one.run === "object"
    );
  }

  /* ---------- names and ids ---------- */

  function newId() {
    var letters = "abcdefghijklmnopqrstuvwxyz0123456789";
    var out = "s_";
    for (var at = 0; at < 10; at++) {
      out += letters.charAt(Math.floor(Math.random() * letters.length));
    }
    return out;
  }

  /* S-001, S-002… the next number nothing else is using. */
  function nextLabel(stories) {
    var used = {};
    (stories || []).forEach(function (one) {
      var match = /^S-(\d+)$/.exec(String(one.label || ""));
      if (match) used[parseInt(match[1], 10)] = true;
    });
    var number = 1;
    while (used[number]) number++;
    return "S-" + String(number).padStart(3, "0");
  }

  function validLabel(label) {
    return LABEL_OK.test(String(label || "").trim());
  }

  function titleOf(run) {
    var story = String((run && run.story) || "").replace(/\s+/g, " ").trim();
    return story.slice(0, TITLE_MAX);
  }

  function now() {
    return new Date().toISOString();
  }

  /* A run that is only showing a sample is nobody's story. */
  function isExample(run) {
    if (!run || typeof run !== "object") return false;
    if (run._is_example || run.story_is_example) return true;
    return false;
  }

  /* ---------- reading ---------- */

  function list() {
    return readAll().stories;
  }

  function get(id) {
    var found = null;
    readAll().stories.forEach(function (one) {
      if (one.id === id) found = one;
    });
    return found;
  }

  function active() {
    var data = readAll();
    return get(data.active_id);
  }

  function count() {
    return readAll().stories.length;
  }

  /* ---------- writing ---------- */

  function create(options) {
    var opts = options || {};
    var data = readAll();
    if (data.stories.length >= MAX_STORIES) {
      return { error: "full-count", story: null };
    }
    var label = String(opts.label || "").trim();
    if (label && !validLabel(label)) return { error: "bad-label", story: null };
    var run = opts.run && typeof opts.run === "object" ? opts.run : {};
    var story = {
      id: newId(),
      label: label || nextLabel(data.stories),
      title: titleOf(run),
      status: STATUSES.indexOf(opts.status) === -1 ? "draft" : opts.status,
      created_at: now(),
      updated_at: now(),
      run: run
    };
    data.stories.push(story);
    data.active_id = story.id;
    var problem = writeAll(data);
    if (problem) return { error: problem, story: null };
    return { error: "", story: story };
  }

  /* Copy a story's run into the live run and make it the one being edited. */
  function open(id) {
    var story = get(id);
    if (!story) return null;
    var data = readAll();
    data.active_id = id;
    writeAll(data);
    if (global.QAGRun) global.QAGRun.write(copy(story.run));
    return story;
  }

  function copy(value) {
    try {
      return JSON.parse(JSON.stringify(value));
    } catch (e) {
      return {};
    }
  }

  /* The live run, written back over the story it belongs to. */
  function saveActive(run) {
    if (isExample(run)) return "example";
    var data = readAll();
    var at = indexOf(data, data.active_id);
    if (at === -1) return "no-active";
    var story = data.stories[at];
    story.run = copy(run);
    story.title = titleOf(run);
    if (run && run.story_label && validLabel(run.story_label)) {
      story.label = String(run.story_label).trim();
    }
    if (run && STATUSES.indexOf(run.story_status) !== -1) {
      story.status = run.story_status;
    }
    story.updated_at = now();
    return writeAll(data);
  }

  function indexOf(data, id) {
    for (var at = 0; at < data.stories.length; at++) {
      if (data.stories[at].id === id) return at;
    }
    return -1;
  }

  function change(id, work) {
    var data = readAll();
    var at = indexOf(data, id);
    if (at === -1) return "not-found";
    var problem = work(data.stories[at], data);
    if (problem) return problem;
    data.stories[at].updated_at = now();
    return writeAll(data);
  }

  function rename(id, label) {
    var wanted = String(label || "").trim();
    if (!validLabel(wanted)) return "bad-label";
    return change(id, function (story) {
      story.label = wanted;
      return "";
    });
  }

  function setStatus(id, status) {
    if (STATUSES.indexOf(status) === -1) return "bad-status";
    return change(id, function (story) {
      story.status = status;
      return "";
    });
  }

  function duplicate(id) {
    var story = get(id);
    if (!story) return { error: "not-found", story: null };
    return create({ run: copy(story.run), status: story.status });
  }

  function remove(id) {
    var data = readAll();
    var at = indexOf(data, id);
    if (at === -1) return "not-found";
    data.stories.splice(at, 1);
    if (data.active_id === id) {
      data.active_id = data.stories.length ? data.stories[0].id : "";
    }
    return writeAll(data);
  }

  function removeAll() {
    try {
      global.localStorage.removeItem(KEY);
    } catch (e) {
      return "full";
    }
    announce();
    return "";
  }

  function setActive(id) {
    var data = readAll();
    if (indexOf(data, id) === -1) return "not-found";
    data.active_id = id;
    return writeAll(data);
  }

  /* ---------- carrying stories in and out ---------- */

  function exportAll() {
    var data = readAll();
    return JSON.stringify(
      { version: VERSION, exported_at: now(), stories: data.stories },
      null,
      2
    );
  }

  /* The same shape rules the server uses: strings are strings, lists are
   * lists, and nothing is unreasonably long. A story that fails is skipped
   * with a reason rather than quietly dropped. */
  function runLooksRight(run) {
    if (!run || typeof run !== "object" || Array.isArray(run)) return "not a run";
    if (run.story !== undefined && typeof run.story !== "string") {
      return "the story is not text";
    }
    if (String(run.story || "").length > 20000) return "the story is too long";
    if (run.criteria !== undefined && !Array.isArray(run.criteria)) {
      return "the criteria are not a list";
    }
    if ((run.criteria || []).length > 200) return "too many criteria";
    try {
      if (JSON.stringify(run).length > MAX_BYTES) return "that story is too big";
    } catch (e) {
      return "that story could not be read";
    }
    return "";
  }

  function importAll(text) {
    var result = { added: 0, updated: 0, skipped: 0, errors: [] };
    var parsed;
    try {
      parsed = JSON.parse(text);
    } catch (e) {
      result.errors.push("That file is not the one QA-Genius writes.");
      return result;
    }
    if (!parsed || parsed.version !== VERSION || !Array.isArray(parsed.stories)) {
      result.errors.push("That file is not the one QA-Genius writes.");
      return result;
    }
    var data = readAll();
    parsed.stories.forEach(function (one, at) {
      var where = one && one.label ? one.label : "story " + (at + 1);
      if (!isStory(one)) {
        result.skipped++;
        result.errors.push(where + ": it is not a story.");
        return;
      }
      var wrong = runLooksRight(one.run);
      if (wrong) {
        result.skipped++;
        result.errors.push(where + ": " + wrong + ".");
        return;
      }
      var mine = indexOf(data, one.id);
      if (mine === -1) {
        if (data.stories.length >= MAX_STORIES) {
          result.skipped++;
          result.errors.push(where + ": you already have " + MAX_STORIES + " stories.");
          return;
        }
        data.stories.push(clean(one));
        result.added++;
        return;
      }
      /* The same story twice: the newer copy wins, and only then. */
      if (newer(one, data.stories[mine])) {
        data.stories[mine] = clean(one);
        result.updated++;
      } else {
        result.skipped++;
      }
    });
    var problem = writeAll(data);
    if (problem) result.errors.push("There was no room to save them.");
    return result;
  }

  function newer(one, other) {
    return String(one.updated_at || "") > String(other.updated_at || "");
  }

  function clean(one) {
    return {
      id: one.id,
      label: validLabel(one.label) ? String(one.label).trim() : "",
      title: String(one.title || titleOf(one.run)).slice(0, TITLE_MAX),
      status: STATUSES.indexOf(one.status) === -1 ? "draft" : one.status,
      created_at: String(one.created_at || now()),
      updated_at: String(one.updated_at || now()),
      run: copy(one.run)
    };
  }

  /* ---------- the first visit ---------- */

  /* A reader who already had a story in this tab keeps it: it becomes the
   * first saved story instead of disappearing the next time they close it. */
  function migrate(run) {
    var data = readAll();
    if (data.stories.length) return null;
    if (!run || !String(run.story || "").trim() || isExample(run)) return null;
    var made = create({ run: run });
    return made.story;
  }

  /* ---------- saving as you work ---------- */

  var timer = null;
  var listening = false;

  function saveSoon(onDone) {
    if (timer) global.clearTimeout(timer);
    timer = global.setTimeout(function () {
      timer = null;
      var run = global.QAGRun ? global.QAGRun.read() : null;
      var problem = run ? saveActive(run) : "no-run";
      if (onDone) onDone(problem);
    }, SAVE_DELAY);
  }

  /* Every write to the run is followed, 600ms later, by one write here. */
  function listen(onDone) {
    if (listening || !global.QAGRun || !global.addEventListener) return;
    listening = true;
    global.addEventListener(global.QAGRun.CHANGED_EVENT, function () {
      saveSoon(onDone);
    });
  }

  global.QAGStories = {
    KEY: KEY,
    VERSION: VERSION,
    MAX_STORIES: MAX_STORIES,
    MAX_BYTES: MAX_BYTES,
    SAVE_DELAY: SAVE_DELAY,
    STATUSES: STATUSES,
    STATUS_WORDS: STATUS_WORDS,
    CHANGED_EVENT: CHANGED_EVENT,
    list: list,
    get: get,
    active: active,
    count: count,
    create: create,
    open: open,
    saveActive: saveActive,
    setActive: setActive,
    rename: rename,
    setStatus: setStatus,
    duplicate: duplicate,
    remove: remove,
    removeAll: removeAll,
    exportAll: exportAll,
    importAll: importAll,
    migrate: migrate,
    validLabel: validLabel,
    nextLabel: nextLabel,
    titleOf: titleOf,
    isExample: isExample,
    saveSoon: saveSoon,
    listen: listen
  };
})(typeof window !== "undefined" ? window : globalThis);
