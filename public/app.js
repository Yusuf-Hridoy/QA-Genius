/* QA-Genius v2: keys live in the browser (localStorage), never on the server.
 * Every HTMX request carries them in the X-QAG-Keys header as
 * [{provider, key}] in the user's order. Labels and test results stay local. */
(function () {
  "use strict";

  var STORE_KEY = "qag.keys";

  function loadKeys() {
    var raw = null;
    try {
      raw = localStorage.getItem(STORE_KEY);
    } catch (err) {
      return [];
    }
    if (!raw) {
      return [];
    }
    var parsed = null;
    try {
      parsed = JSON.parse(raw);
    } catch (err) {
      return [];
    }
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter(function (entry) {
      return (
        entry &&
        typeof entry.provider === "string" &&
        typeof entry.key === "string" &&
        entry.key.length > 0
      );
    });
  }

  function storeKeys(keys) {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(keys));
    } catch (err) {
      return;
    }
    updateChip();
  }

  function headerKeys() {
    return loadKeys().map(function (entry) {
      var item = { provider: entry.provider, key: entry.key };
      if (entry.model) {
        item.model = entry.model;
      }
      return item;
    });
  }

  function shortModel(model) {
    if (!model) {
      return "";
    }
    return model.length <= 22 ? model : model.slice(0, 22) + "…";
  }

  function maskKey(key) {
    if (key.length > 8) {
      return key.slice(0, 4) + "…" + key.slice(-4);
    }
    if (key.length > 4) {
      return key.slice(0, 2) + "…" + key.slice(-2);
    }
    return "••••";
  }

  function newId() {
    return "k" + Date.now().toString(36) + Math.floor(Math.random() * 1296).toString(36);
  }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) {
      node.className = cls;
    }
    if (text !== undefined && text !== null) {
      node.textContent = text;
    }
    return node;
  }

  function providerName(id) {
    var select = document.getElementById("drawer-provider");
    if (select) {
      var options = select.querySelectorAll("option");
      for (var i = 0; i < options.length; i++) {
        if (options[i].value === id) {
          return options[i].textContent;
        }
      }
    }
    return id;
  }

  function timeAgo(ts) {
    var diff = Date.now() - ts;
    if (diff < 60000) {
      return "just now";
    }
    if (diff < 3600000) {
      var mins = Math.floor(diff / 60000);
      return mins + " min ago";
    }
    if (diff < 86400000) {
      var hours = Math.floor(diff / 3600000);
      return hours + " h ago";
    }
    return new Date(ts).toLocaleDateString();
  }

  function updateChip() {
    var chip = document.getElementById("key-chip");
    var text = document.getElementById("key-chip-text");
    var dot = chip ? chip.querySelector(".dot") : null;
    var icon = document.getElementById("key-chip-icon");
    if (!chip || !text) {
      return;
    }
    var keys = loadKeys();
    if (keys.length > 0) {
      chip.classList.remove("empty");
      if (dot) {
        dot.hidden = false;
      }
      if (icon) {
        icon.hidden = true;
      }
      var word = keys.length === 1 ? "1 key" : keys.length + " keys";
      var first = shortModel(keys[0].model);
      text.textContent =
        providerName(keys[0].provider) +
        (first ? " · " + first : "") +
        " connected · " +
        word;
    } else {
      chip.classList.add("empty");
      if (dot) {
        dot.hidden = true;
      }
      if (icon) {
        icon.hidden = false;
      }
      text.textContent = "Add API key";
    }
  }

  var drawerOpen = false;
  var closeTimer = null;
  var lastFocused = null;
  var testingId = null;
  var pendingStorySubmit = false;

  function openDrawer(focusAdd) {
    var drawer = document.getElementById("keys-drawer");
    if (!drawer) {
      return;
    }
    if (closeTimer) {
      clearTimeout(closeTimer);
      closeTimer = null;
    }
    renderDrawer();
    lastFocused = document.activeElement;
    var scrim = document.getElementById("keys-scrim");
    if (scrim) {
      scrim.hidden = false;
      void scrim.offsetWidth;
      scrim.classList.add("open");
    }
    drawer.hidden = false;
    drawer.setAttribute("aria-hidden", "false");
    // Force reflow so the slide transition plays.
    void drawer.offsetWidth;
    drawer.classList.add("open");
    drawerOpen = true;
    if (focusAdd) {
      var keyInput = document.getElementById("drawer-key");
      if (keyInput) {
        keyInput.focus();
      }
    }
  }

  function closeDrawer() {
    var drawer = document.getElementById("keys-drawer");
    if (!drawer || !drawerOpen) {
      return;
    }
    drawerOpen = false;
    drawer.classList.remove("open");
    drawer.setAttribute("aria-hidden", "true");
    var scrim = document.getElementById("keys-scrim");
    if (scrim) {
      scrim.classList.remove("open");
    }
    closeTimer = setTimeout(function () {
      drawer.hidden = true;
      if (scrim) {
        scrim.hidden = true;
      }
    }, 260);
    var back = lastFocused && lastFocused.focus ? lastFocused : document.getElementById("key-chip");
    lastFocused = null;
    if (back) {
      back.focus();
    }
  }

  function statusPill(entry) {
    if (entry.id === testingId) {
      return el("span", "pill neutral", "testing…");
    }
    var last = entry.lastTest;
    if (!last || typeof last.ok !== "boolean") {
      return el("span", "pill neutral", "not tested");
    }
    if (last.ok) {
      return el("span", "pill ok", "working · " + timeAgo(last.at));
    }
    var reason = last.reason ? String(last.reason).slice(0, 80) : "failed";
    return el("span", "pill bad", "failed: " + reason);
  }

  function findPos(keys, id) {
    for (var i = 0; i < keys.length; i++) {
      if (keys[i].id === id) {
        return i;
      }
    }
    return -1;
  }

  function renderDrawer() {
    var listNode = document.getElementById("drawer-key-list");
    if (!listNode) {
      return;
    }
    while (listNode.firstChild) {
      listNode.removeChild(listNode.firstChild);
    }
    var keys = loadKeys();
    var empty = document.getElementById("drawer-key-empty");
    if (empty) {
      empty.style.display = keys.length ? "none" : "";
    }
    keys.forEach(function (entry, idx) {
      var li = el("li", "key-row");
      li.dataset.id = entry.id;

      var main = el("div", "key-main");
      main.appendChild(el("span", "key-num", (idx + 1) + "."));
      main.appendChild(el("strong", null, providerName(entry.provider)));
      if (entry.label) {
        main.appendChild(el("span", "muted", " · " + entry.label));
      }
      main.appendChild(el("code", "mono", " " + maskKey(entry.key)));
      main.appendChild(el("code", "mono", " " + (entry.model || "auto")));
      main.appendChild(statusPill(entry));
      li.appendChild(main);

      var actions = el("div", "row");
      var buttons = [["test", "Test"]];
      if (idx > 0) {
        buttons.push(["first", "Make first"]);
      }
      buttons.push(["model", "Change model"]);
      buttons.push(["edit", "Edit"]);
      buttons.push(["delete", "Delete"]);
      buttons.forEach(function (pair) {
        var btn = el("button", "btn btn-small", pair[1]);
        btn.type = "button";
        btn.dataset.action = pair[0];
        btn.dataset.id = entry.id;
        actions.appendChild(btn);
      });
      li.appendChild(actions);
      listNode.appendChild(li);
    });
  }

  var modelCache = {};

  function fetchModelList(entry) {
    return fetch("/api/keys/models", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: entry.provider, key: entry.key }),
    })
      .then(function (resp) {
        return resp.json();
      })
      .then(function (data) {
        if (data && data.ok && Array.isArray(data.models)) {
          modelCache[entry.id] = {
            models: data.models,
            suggested: data.suggested || "",
          };
          return modelCache[entry.id];
        }
        return null;
      })
      .catch(function () {
        return null;
      });
  }

  function ensureModel(id) {
    var keys = loadKeys();
    var pos = findPos(keys, id);
    if (pos === -1) {
      return Promise.resolve(null);
    }
    if (keys[pos].model && modelCache[id]) {
      return Promise.resolve(keys[pos]);
    }
    return fetchModelList(keys[pos]).then(function () {
      var fresh = loadKeys();
      var at = findPos(fresh, id);
      if (at === -1) {
        return null;
      }
      var cached = modelCache[id];
      if (!fresh[at].model && cached && cached.suggested) {
        fresh[at].model = cached.suggested;
        storeKeys(fresh);
        return fresh[at];
      }
      return fresh[at];
    });
  }

  function runTest(id) {
    testingId = id;
    renderDrawer();
    return ensureModel(id).then(function (entry) {
      if (!entry) {
        testingId = null;
        renderDrawer();
        return false;
      }
      var payload = { provider: entry.provider, key: entry.key };
      if (entry.model) {
        payload.model = entry.model;
      }
      return fetch("/api/keys/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
      .then(function (resp) {
        return resp.json();
      })
      .then(function (data) {
        var fresh = loadKeys();
        var at = findPos(fresh, id);
        if (at !== -1) {
          if (data && data.ok) {
            fresh[at].lastTest = { ok: true, at: Date.now(), reason: "" };
          } else {
            fresh[at].lastTest = {
              ok: false,
              at: Date.now(),
              reason: (data && data.error) || "failed",
            };
          }
          storeKeys(fresh);
        }
        testingId = null;
        renderDrawer();
        return !!(data && data.ok);
      })
      .catch(function () {
        var fresh = loadKeys();
        var at = findPos(fresh, id);
        if (at !== -1) {
          fresh[at].lastTest = { ok: false, at: Date.now(), reason: "Network error" };
          storeKeys(fresh);
        }
        testingId = null;
        renderDrawer();
        return false;
      });
    });
  }

  function maybeResubmitStory() {
    if (!pendingStorySubmit) {
      return;
    }
    if (loadKeys().length === 0) {
      return;
    }
    pendingStorySubmit = false;
    closeDrawer();
    var form = document.getElementById("story-form");
    if (form) {
      if (typeof form.requestSubmit === "function") {
        form.requestSubmit();
      } else {
        form.submit();
      }
    }
  }

  function openEditRow(li, entry) {
    while (li.firstChild) {
      li.removeChild(li.firstChild);
    }
    var form = el("div", "key-edit-form");
    var head = el("div", "key-main");
    head.appendChild(el("strong", null, providerName(entry.provider)));
    if (entry.label) {
      head.appendChild(el("span", "muted", " · " + entry.label));
    }
    head.appendChild(el("code", "mono", " " + maskKey(entry.key)));
    form.appendChild(head);

    var master = document.getElementById("drawer-provider");
    var select = el("select", null);
    if (master) {
      select.innerHTML = master.innerHTML;
    }
    select.value = entry.provider;
    select.setAttribute("aria-label", "Provider");
    form.appendChild(select);

    var labelInput = el("input", null);
    labelInput.type = "text";
    labelInput.value = entry.label || "";
    labelInput.maxLength = 60;
    labelInput.placeholder = "Label (optional)";
    labelInput.setAttribute("aria-label", "Label");
    form.appendChild(labelInput);

    var keyInput = el("input", null);
    keyInput.type = "password";
    keyInput.value = "";
    keyInput.placeholder = "Key (empty = keep current key)";
    keyInput.setAttribute("aria-label", "API key, empty keeps the current key");
    keyInput.autocomplete = "off";
    form.appendChild(keyInput);

    var row = el("div", "row");
    var save = el("button", "btn btn-small", "Save");
    save.type = "button";
    var cancel = el("button", "btn btn-small", "Cancel");
    cancel.type = "button";
    row.appendChild(save);
    row.appendChild(cancel);
    form.appendChild(row);
    li.appendChild(form);

    cancel.addEventListener("click", function () {
      renderDrawer();
    });
    save.addEventListener("click", function () {
      var fresh = loadKeys();
      var at = findPos(fresh, entry.id);
      if (at === -1) {
        renderDrawer();
        return;
      }
      var newKey = keyInput.value.trim();
      if (select.value !== fresh[at].provider) {
        delete fresh[at].model;
        delete modelCache[entry.id];
      }
      fresh[at].provider = select.value;
      fresh[at].label = labelInput.value.trim();
      if (newKey) {
        fresh[at].key = newKey;
        delete fresh[at].lastTest;
      }
      storeKeys(fresh);
      renderDrawer();
    });
    keyInput.focus();
  }

  function openModelEditor(li, entry) {
    while (li.firstChild) {
      li.removeChild(li.firstChild);
    }
    var head = el("div", "key-main");
    head.appendChild(el("strong", null, providerName(entry.provider)));
    head.appendChild(el("code", "mono", " " + (entry.model || "auto")));
    li.appendChild(head);

    var form = el("div", "key-edit-form");
    var loading = el("span", "muted", "Loading models…");
    form.appendChild(loading);
    li.appendChild(form);

    function build(models) {
      while (form.firstChild) {
        form.removeChild(form.firstChild);
      }
      if (!models || !models.length) {
        form.appendChild(
          el("span", "muted", "Could not list models. Type one below.")
        );
      } else {
        var select = el("select", null);
        models.forEach(function (name) {
          var opt = document.createElement("option");
          opt.value = name;
          opt.textContent = name;
          if (name === entry.model) {
            opt.selected = true;
          }
          select.appendChild(opt);
        });
        select.setAttribute("aria-label", "Model");
        form.appendChild(select);
      }
      var other = el("input", null);
      other.type = "text";
      other.value = "";
      other.maxLength = 100;
      other.placeholder = "Other model id (optional)";
      other.setAttribute("aria-label", "Other model id");
      other.autocomplete = "off";
      other.spellcheck = false;
      form.appendChild(other);
      var row = el("div", "row");
      var save = el("button", "btn btn-small", "Save");
      save.type = "button";
      var cancel = el("button", "btn btn-small", "Cancel");
      cancel.type = "button";
      row.appendChild(save);
      row.appendChild(cancel);
      form.appendChild(row);
      cancel.addEventListener("click", function () {
        renderDrawer();
      });
      save.addEventListener("click", function () {
        var chosen = other.value.trim();
        if (!chosen && form.querySelector("select")) {
          chosen = form.querySelector("select").value;
        }
        if (!chosen) {
          other.focus();
          return;
        }
        var fresh = loadKeys();
        var at = findPos(fresh, entry.id);
        if (at === -1) {
          renderDrawer();
          return;
        }
        fresh[at].model = chosen;
        delete fresh[at].lastTest;
        storeKeys(fresh);
        renderDrawer();
      });
      other.focus();
    }

    var cached = modelCache[entry.id];
    if (cached && cached.models) {
      build(cached.models);
    } else {
      fetchModelList(entry).then(function (result) {
        if (findPos(loadKeys(), entry.id) === -1) {
          return;
        }
        build(result ? result.models : []);
      });
    }
  }

  function openDeleteConfirm(li, entry, actions) {
    while (actions.firstChild) {
      actions.removeChild(actions.firstChild);
    }
    actions.appendChild(el("span", "muted", "Delete this key?"));
    var yes = el("button", "btn btn-small", "Yes");
    yes.type = "button";
    var no = el("button", "btn btn-small", "No");
    no.type = "button";
    actions.appendChild(yes);
    actions.appendChild(no);
    no.addEventListener("click", function () {
      renderDrawer();
    });
    yes.addEventListener("click", function () {
      var fresh = loadKeys();
      var at = findPos(fresh, entry.id);
      if (at !== -1) {
        fresh.splice(at, 1);
        storeKeys(fresh);
      }
      delete modelCache[entry.id];
      renderDrawer();
    });
  }

  function initDrawer() {
    var drawer = document.getElementById("keys-drawer");
    var chip = document.getElementById("key-chip");
    if (!drawer || !chip) {
      return;
    }
    var listNode = document.getElementById("drawer-key-list");
    var form = document.getElementById("drawer-key-form");
    var select = document.getElementById("drawer-provider");
    var labelInput = document.getElementById("drawer-label");
    var keyInput = document.getElementById("drawer-key");
    var link = document.getElementById("drawer-key-link");

    chip.addEventListener("click", function () {
      if (drawerOpen) {
        closeDrawer();
      } else {
        openDrawer(false);
      }
    });
    document.getElementById("keys-close").addEventListener("click", closeDrawer);
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        closeDrawer();
        return;
      }
      if (event.key !== "Tab" || !drawerOpen) {
        return;
      }
      // A modal panel keeps the keyboard inside itself.
      var focusable = drawer.querySelectorAll(
        'a[href], button:not([disabled]), input:not([disabled]), select, textarea'
      );
      if (!focusable.length) {
        return;
      }
      var first = focusable[0];
      var last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });
    var scrim = document.getElementById("keys-scrim");
    if (scrim) {
      scrim.addEventListener("click", closeDrawer);
    }

    function syncLink() {
      var opt = select.options[select.selectedIndex];
      if (link && opt && opt.dataset.keyUrl) {
        link.href = opt.dataset.keyUrl;
        link.textContent = "Get a free " + opt.textContent + " key →";
      }
    }
    select.addEventListener("change", syncLink);
    syncLink();

    listNode.addEventListener("click", function (event) {
      var btn = event.target.closest("button[data-action]");
      if (!btn) {
        return;
      }
      var keys = loadKeys();
      var pos = findPos(keys, btn.dataset.id);
      if (pos === -1) {
        return;
      }
      var action = btn.dataset.action;
      var li = btn.closest("li");
      if (action === "test") {
        btn.disabled = true;
        runTest(keys[pos].id).then(function () {
          btn.disabled = false;
        });
      } else if (action === "first" && pos > 0) {
        var moved = keys.splice(pos, 1)[0];
        keys.unshift(moved);
        storeKeys(keys);
        renderDrawer();
      } else if (action === "edit") {
        openEditRow(li, keys[pos]);
      } else if (action === "model") {
        openModelEditor(li, keys[pos]);
      } else if (action === "delete") {
        openDeleteConfirm(li, keys[pos], btn.closest(".row"));
      }
    });

    document.getElementById("test-all").addEventListener("click", function () {
      var ids = loadKeys().map(function (entry) {
        return entry.id;
      });
      ids.reduce(function (chain, id) {
        return chain.then(function () {
          return runTest(id);
        });
      }, Promise.resolve());
    });

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var provider = select.value;
      var key = keyInput.value.trim();
      if (!provider || !key) {
        keyInput.focus();
        return;
      }
      var keys = loadKeys();
      var id = newId();
      keys.push({
        id: id,
        provider: provider,
        label: labelInput.value.trim(),
        key: key,
      });
      storeKeys(keys);
      form.reset();
      syncLink();
      renderDrawer();
      runTest(id).then(function () {
        maybeResubmitStory();
      });
    });

    if (new URLSearchParams(window.location.search).get("keys") === "open") {
      openDrawer(false);
    }
  }


  /* ---------------------------------------------------------------- shell
   * Theme, back-to-top, step locking and "take me to the answer". None of
   * this touches a key or the server; it is all local to the page. */

  var THEME_KEY = "qag.theme";

  function initTheme() {
    var toggle = document.getElementById("theme-toggle");
    if (!toggle) {
      return;
    }
    toggle.addEventListener("click", function () {
      var dark = document.documentElement.getAttribute("data-theme") === "dark";
      var next = dark ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      try {
        localStorage.setItem(THEME_KEY, next);
      } catch (err) {
        /* Private window: the theme just does not survive a reload. */
      }
    });
  }

  function initToTop() {
    var btn = document.getElementById("to-top");
    if (!btn) {
      return;
    }
    btn.addEventListener("click", function () {
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
    var ticking = false;
    window.addEventListener(
      "scroll",
      function () {
        if (ticking) {
          return;
        }
        ticking = true;
        window.requestAnimationFrame(function () {
          btn.classList.toggle("show", window.scrollY > 640);
          ticking = false;
        });
      },
      { passive: true }
    );
  }

  /* A step link that lands on "No story yet" is a dead end. Only unlock the
   * steps the run in sessionStorage actually has data for. */
  function initStepLocks() {
    var list = document.getElementById("flow-steps");
    if (!list) {
      return;
    }
    var run = null;
    try {
      var raw = sessionStorage.getItem("qag.run");
      run = raw ? JSON.parse(raw) : null;
    } catch (err) {
      run = null;
    }
    function has(name) {
      if (!run) {
        return false;
      }
      if (name === "story") {
        return !!(run.story && String(run.story).trim());
      }
      if (name === "criteria") {
        return !!(
          run.criteria &&
          run.criteria.some(function (c) {
            return c && String(c.text || "").trim();
          })
        );
      }
      if (name === "test_cases") {
        return !!(run.test_cases && run.test_cases.result);
      }
      if (name === "automation_cases") {
        return !!(run.automation_cases && run.automation_cases.length);
      }
      return false;
    }
    var here = parseInt(list.dataset.step, 10) || 1;
    Array.prototype.forEach.call(list.children, function (li, idx) {
      var n = idx + 1;
      var link = li.querySelector("a");
      if (!link || n <= here || n === 1) {
        return;
      }
      /* Step n needs whatever the step before it produces. */
      var needs = li.previousElementSibling
        ? li.previousElementSibling.dataset.needs
        : "story";
      if (has(needs)) {
        li.classList.add("done");
        return;
      }
      li.classList.add("locked");
      link.setAttribute("aria-disabled", "true");
      link.title = "Finish step " + (n - 1) + " first";
      var lock = link.querySelector(".step-lock");
      if (lock) {
        lock.hidden = false;
      }
      link.addEventListener("click", function (event) {
        event.preventDefault();
      });
    });
  }

  /* A form you have already filled in folds into one line once its answer
   * arrives, so the answer is what you land on. "Edit" opens it again. */
  function initInputCards(scope) {
    var cards = (scope || document).querySelectorAll(
      "[data-input-card]:not([data-folded])"
    );
    Array.prototype.forEach.call(cards, function (card) {
      card.setAttribute("data-folded", "1");
      card.classList.add("input-card");
      var body = el("div", "input-body");
      while (card.firstChild) {
        body.appendChild(card.firstChild);
      }
      var bar = el("div", "input-bar");
      bar.appendChild(el("span", "what", card.getAttribute("data-input-card")));
      bar.appendChild(el("span", "said", ""));
      var edit = el("button", "btn btn-small", "Edit");
      edit.type = "button";
      edit.addEventListener("click", function () {
        card.classList.remove("collapsed");
        card.scrollIntoView({ behavior: "smooth", block: "start" });
      });
      bar.appendChild(edit);
      card.appendChild(bar);
      card.appendChild(body);
    });
  }

  function foldInputCards() {
    var cards = document.querySelectorAll(".input-card");
    Array.prototype.forEach.call(cards, function (card) {
      var said = card.querySelector(".input-bar .said");
      var source = card.querySelector("textarea, input[type=text]");
      if (said) {
        var text = source && source.value ? source.value.trim() : "";
        said.textContent = text ? text.slice(0, 140) : "";
      }
      card.classList.add("collapsed");
    });
  }

  /* After a run, put the answer on screen instead of leaving the reader
   * below a form they have already filled in. */
  var ANSWER_TARGETS = [
    "story-output",
    "duel-output",
    "bug-output",
    "insights-output",
    "risk-output",
    "test-cases-output",
    "automation-output",
  ];

  function initScrollToAnswer() {
    document.body.addEventListener("htmx:afterSwap", function (event) {
      var node = event.target;
      if (!node || !node.id || ANSWER_TARGETS.indexOf(node.id) === -1) {
        return;
      }
      if (!node.firstElementChild) {
        return;
      }
      /* An error means the input still needs work, so the form stays open. */
      if (!node.querySelector(".error-card")) {
        foldInputCards();
      }
      var top = node.getBoundingClientRect().top + window.scrollY - 78;
      window.scrollTo({ top: top > 0 ? top : 0, behavior: "smooth" });
    });
  }

  function initHomeKeyButton() {
    var btn = document.getElementById("home-add-key");
    if (btn) {
      btn.addEventListener("click", function () {
        openDrawer(true);
      });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    updateChip();
    initDrawer();
    initTheme();
    initToTop();
    initStepLocks();
    initInputCards();
    initScrollToAnswer();
    initHomeKeyButton();
  });

  document.body.addEventListener("htmx:configRequest", function (event) {
    event.detail.headers["X-QAG-Keys"] = JSON.stringify(headerKeys());
  });

  // The server answers "no keys" with an HX-Trigger: open-keys header.
  document.body.addEventListener("open-keys", function () {
    pendingStorySubmit = true;
    openDrawer(true);
  });

  // Ambiguity duel: replace the fork's phrase in the story box.
  document.body.addEventListener("click", function (event) {
    var btn = event.target.closest(".apply-rewrite");
    if (!btn) {
      return;
    }
    if (btn.disabled) {
      return;
    }
    var phrase = btn.getAttribute("data-phrase") || "";
    var rewrite = btn.getAttribute("data-rewrite") || "";
    var box = document.getElementById("story-user-story");
    var status = document.getElementById("duel-status");
    function say(text) {
      if (status) {
        status.textContent = text;
      }
    }
    if (!box || !phrase) {
      say("Couldn't find that phrase in your story.");
      return;
    }
    var at = box.value.toLowerCase().indexOf(phrase.toLowerCase());
    if (at === -1) {
      say("Couldn't find that phrase in your story.");
      return;
    }
    box.value = box.value.slice(0, at) + rewrite + box.value.slice(at + phrase.length);
    box.style.borderColor = "#1F5E46";
    setTimeout(function () {
      box.style.borderColor = "";
    }, 1200);
    say("Story updated — run Check story again.");
    box.focus();
  });

  window.QAG = {
    initInputCards: initInputCards,
    loadKeys: loadKeys,
    storeKeys: storeKeys,
    headerKeys: headerKeys,
    updateChip: updateChip,
    maskKey: maskKey,
    openDrawer: openDrawer,
    closeDrawer: closeDrawer,
  };
})();
