/* QA-Genius v2: several stories, kept in this browser.
 *
 * The run itself still lives in sessionStorage under "qag.run" and still
 * disappears with the tab. What changes here is that a copy of it is kept in
 * localStorage, which stays until the reader deletes it, so a story can be
 * opened again tomorrow and a second story can be started without losing the
 * first. Every screen that offers this says so in those words.
 *
 * Which story a tab is editing lives in the tab, never in localStorage.
 * localStorage held one "active_id" shared by every tab at once, so opening
 * a second story in a second tab pointed both tabs at it and the first tab's
 * next auto-save wrote its work over the other story. The id is in
 * sessionStorage ("qag.tab_story") and inside the run ("_story_id") now, and
 * every save names the story it is for. localStorage keeps only
 * "last_opened_id", which answers one question: which story a brand new tab
 * should open. Nothing ever saves through it.
 *
 * Every saved story carries a revision that goes up by one on every real
 * write. A tab that loaded revision 4 cannot save over revision 5: the write
 * is refused and the page offers to reload or to keep its own copy. No tab
 * ever overwrites another one in silence.
 *
 * Nothing is sent anywhere. There is no account, no server and no database:
 * one key in one browser, and a Delete all button that really deletes.
 *
 * Every storage call is wrapped, because a private window, a full disk and a
 * blocked origin all throw here, and none of them should break the page. */
(function (global) {
  "use strict";

  var KEY = "qag.stories.v1";
  /* The tab's own story. sessionStorage is per tab, which is the whole
   * point: two tabs, two ids, two stories. */
  var TAB_KEY = "qag.tab_story";
  /* Set when this tab's story was deleted under it. A tab with no story has
   * never had one and may make itself one from the first words typed; a tab
   * that has just lost one must not, or Delete would quietly undo itself. */
  var GONE_KEY = "qag.tab_story_gone";
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
  var LABEL_RULE = "Use letters, numbers, - or _ (max 24).";
  var CHANGED_EVENT = "qag:stories-changed";
  /* Another tab saved, deleted or created something. */
  var ELSEWHERE_EVENT = "qag:stories-elsewhere";

  /* ---------- storage ---------- */

  function empty() {
    return { version: VERSION, last_opened_id: "", stories: [] };
  }

  function readAll() {
    try {
      var raw = global.localStorage.getItem(KEY);
      var data = raw ? JSON.parse(raw) : null;
      if (!data || typeof data !== "object" || !Array.isArray(data.stories)) {
        return empty();
      }
      /* Files written before the id moved into the tab carry "active_id".
       * It is read once, as the last story opened, and never written back. */
      var last =
        typeof data.last_opened_id === "string"
          ? data.last_opened_id
          : typeof data.active_id === "string"
            ? data.active_id
            : "";
      return {
        version: VERSION,
        last_opened_id: last,
        stories: data.stories.filter(isStory).map(withRevision)
      };
    } catch (e) {
      return empty();
    }
  }

  /* A story saved before revisions existed starts at nought, so the first
   * save from any tab is accepted and the one after it is checked. */
  function withRevision(one) {
    if (typeof one.revision !== "number" || one.revision < 0) one.revision = 0;
    if (typeof one.opened_at !== "string") one.opened_at = one.updated_at || "";
    return one;
  }

  /* Returns "" when the write went through, or why it did not. */
  function writeAll(data) {
    var text;
    try {
      text = JSON.stringify({
        version: VERSION,
        last_opened_id: data.last_opened_id || "",
        stories: data.stories
      });
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

  /* ---------- the tab's own story ---------- */

  function tabStory() {
    try {
      return String(global.sessionStorage.getItem(TAB_KEY) || "");
    } catch (e) {
      return "";
    }
  }

  function setTabStory(id) {
    try {
      if (id) {
        global.sessionStorage.setItem(TAB_KEY, String(id));
        global.sessionStorage.removeItem(GONE_KEY);
      } else {
        global.sessionStorage.removeItem(TAB_KEY);
      }
    } catch (e) {
      /* storage blocked: the tab still works, it just forgets on reload */
    }
    rememberLastOpened(id ? String(id) : "");
  }

  function clearTabStory() {
    setTabStory("");
  }

  function storyWasDeleted() {
    try {
      return global.sessionStorage.getItem(GONE_KEY) === "1";
    } catch (e) {
      return false;
    }
  }

  function markDeleted() {
    try {
      global.sessionStorage.setItem(GONE_KEY, "1");
    } catch (e) {
      /* storage blocked: the worst case is one story made by accident */
    }
  }

  /* The only thing localStorage still says about "which story": the one a
   * brand new tab should start on. Never read when saving. */
  function rememberLastOpened(id) {
    var data = readAll();
    if (data.last_opened_id === id) return;
    data.last_opened_id = id;
    writeAll(data);
  }

  function lastOpenedId() {
    return readAll().last_opened_id || "";
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

  /* An id belongs to one story. Two stories called CHK-101 is one story
   * nobody can find again. */
  function labelTaken(stories, label, exceptId) {
    var wanted = String(label || "").trim().toLowerCase();
    if (!wanted) return false;
    var taken = false;
    (stories || []).forEach(function (one) {
      if (one.id === exceptId) return;
      if (String(one.label || "").trim().toLowerCase() === wanted) taken = true;
    });
    return taken;
  }

  function takenMessage(label) {
    return String(label).trim() + " is already used by another story.";
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

  /* The story this tab is editing. Never "whatever another tab opened". */
  function active() {
    return get(tabStory());
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
    if (label && labelTaken(data.stories, label, "")) {
      return { error: "duplicate-label", story: null, message: takenMessage(label) };
    }
    var run = opts.run && typeof opts.run === "object" ? copy(opts.run) : {};
    var story = {
      id: newId(),
      label: label || nextLabel(data.stories),
      title: titleOf(run),
      status: STATUSES.indexOf(opts.status) === -1 ? "draft" : opts.status,
      created_at: now(),
      updated_at: now(),
      opened_at: now(),
      revision: 1,
      run: run
    };
    story.run._story_id = story.id;
    delete story.run._story_rev;
    data.stories.push(story);
    data.last_opened_id = story.id;
    var problem = writeAll(data);
    if (problem) return { error: problem, story: null };
    /* The new story is this tab's. Other tabs keep the story they had. */
    setTabStory(story.id);
    return { error: "", story: story };
  }

  /* Copy a story's run into the live run and make it the one this tab edits. */
  function open(id) {
    var story = get(id);
    if (!story) return null;
    setTabStory(id);
    touchOpened(id);
    if (global.QAGRun) {
      global.QAGRun.write(bound(story));
      /* run_state.js stamps fingerprints on every write, so the run in the
       * tab is now a hair different from the one in storage. Put that copy
       * back without touching "Last edited" or the revision: opening a
       * story is not editing it, and the next auto-save must find nothing
       * to do rather than bumping the story to the top of the list. */
      restamp(id);
    }
    return story;
  }

  function restamp(id) {
    var data = readAll();
    var at = indexOf(data, id);
    if (at === -1) return;
    var run = global.QAGRun.read();
    if (!run || run._story_id !== id) return;
    var wanted = copy(run);
    delete wanted._story_rev;
    if (same(data.stories[at].run, wanted)) return;
    data.stories[at].run = wanted;
    writeAll(data);
  }

  /* The saved run, stamped with the story it came from and the revision this
   * tab has seen. Both travel with the run so no save can go astray. */
  function bound(story) {
    var run = copy(story.run);
    run._story_id = story.id;
    run._story_rev = story.revision || 0;
    return run;
  }

  /* Opening is not editing: it moves "Last opened" and leaves "Last edited". */
  function touchOpened(id) {
    var data = readAll();
    var at = indexOf(data, id);
    if (at === -1) return;
    data.stories[at].opened_at = now();
    data.last_opened_id = id;
    writeAll(data);
  }

  function copy(value) {
    try {
      return JSON.parse(JSON.stringify(value));
    } catch (e) {
      return {};
    }
  }

  /* The one writer. A run is saved into the story it names and nowhere else.
   *
   * "" saved · "same" nothing had changed · "deleted" that story is gone ·
   * "stale" another tab saved a newer copy · "example" a sample is nobody's
   * story · "no-id" the caller did not say which story · "full" no room. */
  function saveStory(storyId, run) {
    var id = String(storyId || "");
    if (!id) return "no-id";
    if (isExample(run)) return "example";
    var data = readAll();
    var at = indexOf(data, id);
    if (at === -1) return "deleted";
    var story = data.stories[at];
    var seen = run && typeof run._story_rev === "number" ? run._story_rev : null;
    if (seen !== null && seen < (story.revision || 0)) return "stale";

    var wanted = copy(run);
    wanted._story_id = id;
    delete wanted._story_rev;
    var label = story.label;
    if (run && run.story_label && validLabel(run.story_label)) {
      var typed = String(run.story_label).trim();
      /* A duplicate is refused where it is typed, not here: auto-save keeps
       * the id the story already had rather than stopping the save. */
      if (!labelTaken(data.stories, typed, id)) label = typed;
    }
    var status = story.status;
    if (run && STATUSES.indexOf(run.story_status) !== -1) status = run.story_status;

    /* Opening a story writes its own run straight back. That is not an edit,
     * and "Last edited" must not move for it. */
    if (label === story.label && status === story.status && same(story.run, wanted)) {
      return "same";
    }

    story.run = wanted;
    story.title = titleOf(run);
    story.label = label;
    story.status = status;
    story.updated_at = now();
    story.revision = (story.revision || 0) + 1;
    var problem = writeAll(data);
    if (problem) return problem;
    carryRevision(id, story.revision);
    return "";
  }

  function same(one, other) {
    try {
      return JSON.stringify(one) === JSON.stringify(other);
    } catch (e) {
      return false;
    }
  }

  /* The tab has just written revision n, so the run it holds has seen it.
   * Written straight into sessionStorage: announcing it would start the
   * save timer again and the two would chase each other for ever. */
  function carryRevision(id, revision) {
    bindSession(id, revision, true);
  }

  /* Tie the run in this tab to a story, quietly. `onlyIfMine` is for the
   * ordinary case of recording a revision we have just written: it leaves a
   * run that belongs to some other story alone. */
  function bindSession(id, revision, onlyIfMine) {
    if (!global.QAGRun) return;
    try {
      var raw = global.sessionStorage.getItem(global.QAGRun.RUN_KEY);
      var run = raw ? JSON.parse(raw) : null;
      if (!run || typeof run !== "object") return;
      if (onlyIfMine && run._story_id !== id) return;
      run._story_id = id;
      run._story_rev = revision;
      global.sessionStorage.setItem(global.QAGRun.RUN_KEY, JSON.stringify(run));
    } catch (e) {
      /* storage blocked: the next save simply checks against what it has */
    }
  }

  /* Save the run into the story the run itself names.
   *
   * A run with words in it and no story behind it is somebody typing on a
   * fresh tab before anything has been created. It gets a story rather than
   * being dropped: "nothing typed is lost" has to hold from the first key. */
  function saveRun(run) {
    if (!run || typeof run !== "object") return "no-id";
    if (!run._story_id) {
      var mine = tabStory();
      if (mine) {
        run._story_id = mine;
        bindSession(mine, (get(mine) || {}).revision || 0);
      } else {
        return startFrom(run);
      }
    }
    return saveStory(run._story_id, run);
  }

  /* The first words typed on a tab that has no story yet. */
  function startFrom(run) {
    /* Unless the tab had one a moment ago: Delete must stay deleted. */
    if (storyWasDeleted()) return "deleted";
    if (isExample(run)) return "example";
    if (!String(run.story || "").trim()) return "no-id";
    var wanted = String(run.story_label || "").trim();
    if (!validLabel(wanted) || labelTaken(readAll().stories, wanted, "")) wanted = "";
    var made = create({ run: run, label: wanted });
    if (made.error) return made.error;
    bindSession(made.story.id, made.story.revision);
    return "";
  }

  /* Save the live run, whatever page is asking. Used on the way out of a
   * page: switching, creating, opening another story. */
  function saveLive() {
    if (!global.QAGRun) return "no-run";
    return saveRun(global.QAGRun.read());
  }

  /* "Keep mine": this tab's copy wins over a newer one from another tab.
   * Only ever called behind a confirm the reader answered. */
  function forceSave(storyId, run) {
    var story = get(storyId);
    if (!story) return "deleted";
    var mine = copy(run);
    mine._story_rev = story.revision || 0;
    mine._story_id = storyId;
    /* A forced save is always a real write, even when the words match. */
    var problem = saveStory(storyId, mine);
    return problem === "same" ? "" : problem;
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
    data.stories[at].revision = (data.stories[at].revision || 0) + 1;
    var wrote = writeAll(data);
    if (!wrote) carryRevision(id, data.stories[at].revision);
    return wrote;
  }

  function rename(id, label) {
    var wanted = String(label || "").trim();
    if (!validLabel(wanted)) return "bad-label";
    if (labelTaken(readAll().stories, wanted, id)) return "duplicate-label";
    return change(id, function (story) {
      story.label = wanted;
      if (story.run && typeof story.run === "object") {
        story.run.story_label = wanted;
      }
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

  /* Deleting the story this tab is on leaves the tab with no story at all:
   * the next save has nowhere to go, which is exactly right. */
  function remove(id) {
    var data = readAll();
    var at = indexOf(data, id);
    if (at === -1) return "not-found";
    data.stories.splice(at, 1);
    if (data.last_opened_id === id) {
      data.last_opened_id = data.stories.length ? data.stories[0].id : "";
    }
    var problem = writeAll(data);
    if (problem) return problem;
    if (tabStory() === id) forgetOpenStory();
    return "";
  }

  /* No story on this tab, and no run to save into one. Nothing this tab
   * does afterwards writes anywhere until a story is opened or started. */
  function forgetOpenStory() {
    clearTabStory();
    markDeleted();
    if (global.QAGRun) global.QAGRun.write({});
  }

  function removeAll() {
    try {
      global.localStorage.removeItem(KEY);
    } catch (e) {
      return "full";
    }
    forgetOpenStory();
    announce();
    return "";
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
      /* That id already belongs to a different story: two CHK-101s is one
       * story nobody can find again. */
      if (labelTaken(data.stories, one.label, one.id)) {
        result.skipped++;
        result.errors.push(takenMessage(one.label));
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
      opened_at: String(one.opened_at || one.updated_at || now()),
      revision: typeof one.revision === "number" ? one.revision : 1,
      run: copy(one.run)
    };
  }

  /* ---------- the first visit, and every new tab ---------- */

  /* A reader who already had a story in this tab keeps it: it becomes the
   * first saved story instead of disappearing the next time they close it. */
  function migrate(run) {
    var data = readAll();
    if (data.stories.length) return null;
    if (!run || !String(run.story || "").trim() || isExample(run)) return null;
    var made = create({ run: run });
    return made.story;
  }

  /* A tab that has no story of its own picks one up: the story it already
   * holds a run for, else the last one opened anywhere, else nothing. This
   * is the only place last_opened_id is used, and it never saves. */
  function adopt() {
    if (tabStory()) return active();
    /* The story this tab was on was deleted. Picking up the next one along
     * would be the tab quietly opening somebody else's story and, 600ms
     * later, typing over it. It waits to be told which story instead. */
    if (storyWasDeleted()) return null;
    var run = global.QAGRun ? global.QAGRun.read() : {};
    var mine = run && run._story_id ? get(run._story_id) : null;
    if (mine) {
      setTabStory(mine.id);
      if (global.QAGRun) global.QAGRun.write(bound(mine));
      return mine;
    }
    /* A run with words in it but no story behind it becomes one. */
    var made = migrate(run);
    if (made) return made;
    var last = get(lastOpenedId());
    if (!last) last = newest();
    if (!last) return null;
    return open(last.id);
  }

  /* The story edited most recently. The one a reader means by "my story"
   * when this tab has never opened one and nothing says otherwise. */
  function newest() {
    var best = null;
    readAll().stories.forEach(function (one) {
      if (!best || String(one.updated_at || "") > String(best.updated_at || "")) {
        best = one;
      }
    });
    return best;
  }

  /* ---------- saving as you work ---------- */

  var timer = null;
  var listening = false;

  function saveSoon(onDone) {
    if (timer) global.clearTimeout(timer);
    timer = global.setTimeout(function () {
      timer = null;
      var run = global.QAGRun ? global.QAGRun.read() : null;
      var problem = run ? saveRun(run) : "no-run";
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

  /* ---------- another tab moved first ---------- */

  /* What this tab should do about a change made somewhere else:
   * "" nothing to say · "deleted" the story this tab shows is gone ·
   * "changed" the same story was saved by another tab. */
  function elsewhere() {
    var id = tabStory();
    if (!id) return "";
    var story = get(id);
    if (!story) return "deleted";
    var run = global.QAGRun ? global.QAGRun.read() : {};
    var seen = run && typeof run._story_rev === "number" ? run._story_rev : null;
    if (seen === null) return "";
    return (story.revision || 0) > seen ? "changed" : "";
  }

  /* The browser fires "storage" in every other tab, never in the one that
   * wrote. One listener, one event out, so every page can answer it. */
  function watch() {
    if (!global.addEventListener) return;
    global.addEventListener("storage", function (event) {
      if (event && event.key && event.key !== KEY) return;
      var what = elsewhere();
      if (!what) return;
      if (!global.dispatchEvent || !global.CustomEvent) return;
      try {
        global.dispatchEvent(
          new global.CustomEvent(ELSEWHERE_EVENT, { detail: { state: what } })
        );
      } catch (e) {
        /* a browser too old for CustomEvent still refuses the stale save */
      }
    });
  }

  global.QAGStories = {
    KEY: KEY,
    TAB_KEY: TAB_KEY,
    VERSION: VERSION,
    MAX_STORIES: MAX_STORIES,
    MAX_BYTES: MAX_BYTES,
    LABEL_MAX: LABEL_MAX,
    LABEL_RULE: LABEL_RULE,
    SAVE_DELAY: SAVE_DELAY,
    STATUSES: STATUSES,
    STATUS_WORDS: STATUS_WORDS,
    CHANGED_EVENT: CHANGED_EVENT,
    ELSEWHERE_EVENT: ELSEWHERE_EVENT,
    list: list,
    get: get,
    active: active,
    count: count,
    create: create,
    open: open,
    bound: bound,
    tabStory: tabStory,
    setTabStory: setTabStory,
    storyWasDeleted: storyWasDeleted,
    clearTabStory: clearTabStory,
    forgetOpenStory: forgetOpenStory,
    lastOpenedId: lastOpenedId,
    saveStory: saveStory,
    saveRun: saveRun,
    saveLive: saveLive,
    forceSave: forceSave,
    rename: rename,
    setStatus: setStatus,
    duplicate: duplicate,
    remove: remove,
    removeAll: removeAll,
    exportAll: exportAll,
    importAll: importAll,
    migrate: migrate,
    adopt: adopt,
    elsewhere: elsewhere,
    watch: watch,
    validLabel: validLabel,
    labelTaken: labelTaken,
    takenMessage: takenMessage,
    nextLabel: nextLabel,
    titleOf: titleOf,
    isExample: isExample,
    saveSoon: saveSoon,
    listen: listen
  };
})(typeof window !== "undefined" ? window : globalThis);
