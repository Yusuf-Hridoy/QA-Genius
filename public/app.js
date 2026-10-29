/* QA-Genius v2: keys live in the browser (localStorage), never on the server.
 * Every HTMX request carries them in the X-QAG-Keys header as
 * [{provider, key}] in the user's order. Labels and test results stay local. */
(function () {
  "use strict";

  var STORE_KEY = "qag.keys";

  var NOT_A_KEY = "This looks like an email or password, not an API key.";

  /* An API key is one run of characters. An @ or a space means the browser
   * or the person put a login in the box. */
  function looksLikeKey(text) {
    var value = String(text == null ? "" : text).trim();
    return value !== "" && value.indexOf("@") === -1 && !/\s/.test(value);
  }

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
    if (!chip || !text) {
      return;
    }
    var keys = loadKeys();
    if (keys.length > 0) {
      chip.classList.remove("empty");
      if (dot) {
        dot.hidden = false;
      }
      var word = keys.length === 1 ? "1 key" : keys.length + " keys";
      /* "connected" is a claim about a key that really answered. A key
       * whose last result was a failure says so instead: a run showed
       * "connected" over two keys that had both just been refused. */
      var working = null;
      var failed = false;
      keys.forEach(function (entry) {
        var last = entry.lastTest;
        if (!last || typeof last.ok !== "boolean") return;
        if (last.ok) {
          if (!working) working = entry;
        } else {
          failed = true;
        }
      });
      if (working) {
        var model = shortModel(working.model);
        text.textContent =
          providerName(working.provider) +
          (model ? " · " + model : "") +
          " connected · " +
          word;
      } else if (failed) {
        text.textContent = "Key problem — open to check";
      } else {
        var first = shortModel(keys[0].model);
        text.textContent =
          providerName(keys[0].provider) +
          (first ? " · " + first : "") +
          " · " +
          word;
      }
    } else {
      chip.classList.add("empty");
      if (dot) {
        dot.hidden = true;
      }
      text.textContent = "Add AI key";
    }
    /* On a narrow phone the words are hidden, so the chip carries them. */
    chip.setAttribute("aria-label", text.textContent);
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
    /* A panel that opens behind the keyboard is a panel a keyboard user
     * cannot reach. Focus always moves into it: the key box when that is
     * what was asked for, the first field otherwise. */
    var into =
      document.getElementById(focusAdd ? "drawer-key" : "drawer-provider") ||
      document.getElementById("drawer-key");
    if (into && into.focus) {
      into.focus();
    }
  }

  function closeDrawer() {
    var drawer = document.getElementById("keys-drawer");
    if (!drawer || !drawerOpen) {
      return;
    }
    drawerOpen = false;
    // Never leave a key on screen for the next time the panel opens.
    var keyBox = document.getElementById("drawer-key");
    var showKey = document.getElementById("drawer-key-show");
    if (keyBox && !keyBox.classList.contains("masked")) {
      keyBox.classList.add("masked");
      if (showKey) {
        showKey.setAttribute("aria-pressed", "false");
        showKey.textContent = "Show";
      }
    }
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
    /* And it goes back where it came from. The chip is the way in, so it
     * is the fallback whenever what opened the panel has since gone. */
    var chip = document.getElementById("key-chip");
    var back = lastFocused && lastFocused.focus && lastFocused.isConnected
      ? lastFocused
      : chip;
    lastFocused = null;
    if (back && back.focus) {
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
    return el("span", "pill bad", "failed · " + reason);
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
    // Nothing to test with no keys, so the button does not sit there greyed.
    var testRow = document.getElementById("test-all-row");
    if (testRow) {
      testRow.hidden = keys.length === 0;
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

      /* Five small buttons in a 430px drawer wrapped onto three lines and
       * the row stopped reading as a row. Test and Delete stay out; the
       * three that are used once in a key's life go under More. */
      var actions = el("div", "row key-actions");
      function keyButton(action, words, className) {
        var btn = el("button", className || "btn btn-small", words);
        btn.type = "button";
        btn.dataset.action = action;
        btn.dataset.id = entry.id;
        return btn;
      }
      actions.appendChild(keyButton("test", "Test"));
      var menu = el("div", "more-menu");
      var more = el("button", "btn btn-small", "More ▾");
      more.type = "button";
      more.dataset.action = "more";
      more.dataset.id = entry.id;
      more.setAttribute("aria-expanded", "false");
      menu.appendChild(more);
      var list = el("div", "more-list");
      list.hidden = true;
      if (idx > 0) list.appendChild(keyButton("first", "Make first", "btn btn-ghost"));
      list.appendChild(keyButton("model", "Change model", "btn btn-ghost"));
      list.appendChild(keyButton("edit", "Edit", "btn btn-ghost"));
      menu.appendChild(list);
      actions.appendChild(menu);
      actions.appendChild(keyButton("delete", "Delete", "btn btn-small btn-danger"));
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
    var select = el("select", "ctl");
    if (master) {
      select.innerHTML = master.innerHTML;
    }
    select.value = entry.provider;
    select.setAttribute("aria-label", "Provider");
    form.appendChild(select);

    var labelInput = el("input", "ctl");
    labelInput.type = "text";
    labelInput.value = entry.label || "";
    labelInput.maxLength = 60;
    labelInput.placeholder = "Label (optional)";
    labelInput.setAttribute("aria-label", "Label");
    form.appendChild(labelInput);

    /* Masked by CSS, not a password field, for the same reason as the add
     * form: browsers fill password fields with saved logins. */
    var keyInput = el("input", "ctl masked");
    keyInput.type = "text";
    keyInput.value = "";
    keyInput.placeholder = "Key (empty = keep current key)";
    keyInput.setAttribute("aria-label", "API key, empty keeps the current key");
    keyInput.autocomplete = "off";
    keyInput.name = "qag-api-key-edit";
    keyInput.spellcheck = false;
    keyInput.setAttribute("data-lpignore", "true");
    keyInput.setAttribute("data-1p-ignore", "");
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
      if (newKey && !looksLikeKey(newKey)) {
        keyInput.setAttribute("aria-invalid", "true");
        keyInput.placeholder = NOT_A_KEY;
        keyInput.focus();
        return;
      }
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
        var select = el("select", "ctl");
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
      var other = el("input", "ctl");
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
    var yes = el("button", "btn btn-small btn-danger", "Yes");
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

    /* The href follows the provider; the words stay the same, so the line
     * does not grow a provider's whole name every time you switch. */
    function syncLink() {
      var opt = select.options[select.selectedIndex];
      if (link && opt && opt.dataset.keyUrl) {
        link.href = opt.dataset.keyUrl;
      }
    }
    select.addEventListener("change", syncLink);
    syncLink();

    /* The key field is masked by CSS rather than by being a password field,
     * so a shoulder or a screen share cannot read it and no password manager
     * tries to fill it; Show is there for checking a paste. */
    var showKey = document.getElementById("drawer-key-show");
    if (showKey && keyInput) {
      showKey.addEventListener("click", function () {
        var shown = !keyInput.classList.contains("masked");
        keyInput.classList.toggle("masked", shown);
        showKey.setAttribute("aria-pressed", shown ? "false" : "true");
        showKey.textContent = shown ? "Show" : "Hide";
        keyInput.focus();
      });
    }

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
      if (action === "more") {
        var menu = btn.parentNode.querySelector(".more-list");
        if (menu) {
          menu.hidden = !menu.hidden;
          btn.setAttribute("aria-expanded", menu.hidden ? "false" : "true");
        }
        return;
      }
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

    var keyError = document.getElementById("drawer-key-error");

    function showKeyError(message) {
      if (!keyError) {
        return;
      }
      keyError.textContent = message || "";
      keyError.hidden = !message;
    }

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var provider = select.value;
      var key = keyInput.value.trim();
      showKeyError("");
      if (!key) {
        /* The box was empty and Save did nothing at all, which reads as a
         * broken button rather than as a missing key. */
        showKeyError("Paste your key first.");
        keyInput.focus();
        return;
      }
      if (!provider) {
        select.focus();
        return;
      }
      /* A browser that filled the box anyway, or a hurried paste from a
       * password manager, puts a login here. No key looks like that. */
      if (!looksLikeKey(key)) {
        showKeyError(NOT_A_KEY);
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
        /* Reachable, not finished: a step you can open still shows its
         * number. Only a step behind you shows a tick. */
        li.classList.add("ready");
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

  /* The top bar is fixed, so the thing being scrolled to has to stop below
   * it rather than under it. */
  var ANSWER_OFFSET = 78;

  /* The line that names the answer. Scrolling to the card is not the same
   * as scrolling to its title: a card that starts with a banner or a row of
   * stats put the sentence a reader wants three screens down. */
  function answerTitle(node) {
    return (
      node.querySelector("h1, h2, h3, .ship-verdict-label, .card-title") || node
    );
  }

  function easeOrNot() {
    var ask = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)");
    return ask && ask.matches ? "auto" : "smooth";
  }

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
      /* Folding the form above changes where everything below it sits, so
       * the position is read on the next frame, after the browser has laid
       * the page out again. Measuring before that is what sent the page
       * past the answer and down to the bottom. */
      var goTo = answerTitle(node);
      window.requestAnimationFrame(function () {
        var top = goTo.getBoundingClientRect().top + window.scrollY - ANSWER_OFFSET;
        window.scrollTo({ top: top > 0 ? top : 0, behavior: easeOrNot() });
        /* And the keyboard goes with the eye: the next Tab carries on from
         * the answer rather than from the form the reader has left. */
        if (!goTo.hasAttribute("tabindex")) goTo.setAttribute("tabindex", "-1");
        try {
          goTo.focus({ preventScroll: true });
        } catch (e) {
          goTo.focus();
        }
      });
    });
  }

  /* ---------- shared form behaviour ---------- */

  /* One counter for every field that declares one. The markup comes from
   * _form_fields.html and the JS-built forms copy it, so no desk counts its
   * own characters any more and they all read "n / max". */
  function paintCounter(counter) {
    var id = counter.getAttribute("data-for");
    var box = id ? document.getElementById(id) : null;
    var max = parseInt(counter.getAttribute("data-max"), 10);
    if (!box || !max) {
      return;
    }
    var used = box.value.length;
    counter.textContent = used + " / " + max;
    counter.classList.toggle("near", used >= max * 0.9 && used <= max);
    counter.classList.toggle("over", used > max);
  }

  function initCounters(scope) {
    var counters = (scope || document).querySelectorAll(".counter[data-for]");
    Array.prototype.forEach.call(counters, paintCounter);
  }

  /* The hint above a control and the help line under it describe it, so a
   * screen reader reads them with the control and not as loose text. */
  function describeFields(scope) {
    var fields = (scope || document).querySelectorAll(".field");
    Array.prototype.forEach.call(fields, function (field) {
      var control = field.querySelector(
        "input:not([type=hidden]), select, textarea"
      );
      if (!control || !control.id || control.getAttribute("aria-describedby")) {
        return;
      }
      var ids = [];
      [control.id + "-hint", control.id + "-help"].forEach(function (id) {
        var node = document.getElementById(id);
        if (node && node.textContent.trim()) {
          ids.push(id);
        }
      });
      if (ids.length) {
        control.setAttribute("aria-describedby", ids.join(" "));
      }
    });
  }

  function initFields(scope) {
    initCounters(scope);
    describeFields(scope);
  }

  /* A paste longer than the box loses its tail without a word: the browser
   * cuts it to maxlength and says nothing. A run pasted a long story and
   * then worked from one that stopped mid-sentence. */
  var CUT_CLASS = "paste-cut-note";

  function withCommas(number) {
    var digits = String(number);
    var out = "";
    for (var i = 0; i < digits.length; i++) {
      if (i > 0 && (digits.length - i) % 3 === 0) out += ",";
      out += digits.charAt(i);
    }
    return out;
  }

  function cutNote(box, max) {
    var holder = box.parentNode;
    if (!holder) {
      return;
    }
    var note = holder.querySelector("." + CUT_CLASS);
    if (!note) {
      note = document.createElement("p");
      note.className = CUT_CLASS + " field-error";
      note.setAttribute("role", "status");
      holder.insertBefore(note, box.nextSibling);
    }
    note.textContent =
      "Only the first " + withCommas(max) + " characters were kept.";
    note.hidden = false;
  }

  function clearCutNote(box) {
    var holder = box.parentNode;
    var note = holder ? holder.querySelector("." + CUT_CLASS) : null;
    if (note) {
      note.hidden = true;
    }
  }

  /* True when this paste would not fit, so the browser is about to cut it. */
  function pasteWouldBeCut(box, pasted) {
    var max = box.maxLength;
    if (!max || max < 0) {
      return false;
    }
    var current = String(box.value || "");
    var selected = (box.selectionEnd || 0) - (box.selectionStart || 0);
    return current.length - selected + String(pasted || "").length > max;
  }

  document.addEventListener("paste", function (event) {
    var box = event.target;
    if (!box || !box.maxLength) {
      return;
    }
    var data = event.clipboardData || window.clipboardData;
    if (!data || !data.getData) {
      return;
    }
    if (pasteWouldBeCut(box, data.getData("text"))) {
      cutNote(box, box.maxLength);
    } else {
      clearCutNote(box);
    }
  });

  /* Any HTML the server swaps in brings its own fields with it. */
  document.body.addEventListener("htmx:afterSwap", function (event) {
    if (event.target) {
      initFields(event.target);
    }
  });

  document.addEventListener("input", function (event) {
    var id = event.target ? event.target.id : "";
    if (!id) {
      return;
    }
    var counter = document.querySelector('.counter[data-for="' + id + '"]');
    if (counter) {
      paintCounter(counter);
    }
    // Typing the box back under its limit answers the warning.
    var box = event.target;
    if (box.maxLength && box.value.length < box.maxLength) {
      clearCutNote(box);
    }
  });

  /* While a request runs, the button that started it says so. What that
   * looks like lives in busy.js, which the source card and the hand-written
   * fetches use as well, so every button behaves the same way. */
  function busyButton(node) {
    if (!node || !node.tagName) {
      return null;
    }
    if (node.tagName === "BUTTON") {
      return node;
    }
    if (node.tagName === "FORM") {
      return node.querySelector("button[type=submit]");
    }
    return null;
  }

  document.body.addEventListener("htmx:beforeRequest", function (event) {
    if (window.QAGBusy) {
      window.QAGBusy.start(busyButton(event.detail.elt));
    }
  });

  /* What the server's AI calls just did to each key, by position. The
   * server never sees a key or remembers one, so a real run is the only
   * way the panel can know a key still works -- otherwise it kept saying
   * "working" from a Test press hours ago. */
  var KEY_RESULTS_HEADER = "X-QAG-Key-Results";

  function applyKeyResults(raw) {
    if (!raw) return;
    var results = null;
    try {
      results = JSON.parse(raw);
    } catch (err) {
      return;
    }
    if (!results || !results.length) return;
    var keys = loadKeys();
    var changed = false;
    results.forEach(function (one) {
      var at = one && one.index;
      if (typeof at !== "number" || !keys[at]) return;
      keys[at].lastTest = {
        ok: one.ok === true,
        at: Date.now(),
        reason: one.ok === true ? "" : String(one.reason || "failed"),
      };
      changed = true;
    });
    if (!changed) return;
    storeKeys(keys);
    renderDrawer();
  }

  document.body.addEventListener("htmx:afterRequest", function (event) {
    var xhr = event.detail && event.detail.xhr;
    if (!xhr || !xhr.getResponseHeader) return;
    applyKeyResults(xhr.getResponseHeader(KEY_RESULTS_HEADER));
  });

  /* "Add a key" is the wrong thing to ask of a reader who has one, so a
   * saved example reads differently once there is a key to run it with. */
  function freshenExampleCaptions() {
    if (!loadKeys().length) return;
    var captions = document.querySelectorAll(".example-caption[data-with-keys]");
    Array.prototype.forEach.call(captions, function (node) {
      node.textContent = node.getAttribute("data-with-keys");
    });
  }

  document.body.addEventListener("htmx:afterSwap", freshenExampleCaptions);

  /* Stop on the answer and on the error alike, and stop every button this
   * click made busy: a source card's button starts the desk's own button,
   * and the two have to go back to normal together. */
  ["htmx:afterRequest", "htmx:responseError", "htmx:sendError", "htmx:timeout"].forEach(
    function (name) {
      document.body.addEventListener(name, function () {
        if (window.QAGBusy) window.QAGBusy.stopAll();
      });
    }
  );

  /* On a phone the rail is a scrolling strip. The desk you are on is scrolled
   * into view, so it is never half a word cut off at the edge. */
  function initNavScroll() {
    var rail = document.querySelector(".sidebar");
    var active = rail ? rail.querySelector(".nav a.active") : null;
    if (!rail || !active || rail.scrollWidth <= rail.clientWidth + 2) {
      return;
    }
    active.scrollIntoView({ inline: "center", block: "nearest" });
  }

  /* The Overview offers "Load an example" for a reader with no story yet.
   * It cannot run the example itself - the example lives on the Story desk -
   * so it links here with ?example=1 and this presses the button. */
  function initExampleLink() {
    if (new URLSearchParams(window.location.search).get("example") !== "1") return;
    var button = document.getElementById("load-example");
    if (button) button.click();
  }

  /* "Show all" on a list that was cut to five. One handler on the document,
   * because the list arrives with an HTMX swap long after this runs. */
  function initShowAll() {
    document.addEventListener("click", function (event) {
      var button = event.target;
      while (button && button !== document) {
        if (button.id === "reasons-show-all") break;
        button = button.parentNode;
      }
      if (!button || button === document || !button.id) return;
      var card = button.parentNode;
      var hidden = card.querySelectorAll(".reason-more");
      Array.prototype.forEach.call(hidden, function (one) {
        one.hidden = false;
      });
      button.hidden = true;
    });
  }

  /* The outlined pill beside a page title. A desk calls this once it knows
   * its own numbers; an empty text hides the pill again. */
  function setPagePill(text) {
    var pill = document.getElementById("page-pill");
    if (!pill) return;
    pill.textContent = text || "";
    pill.hidden = !text;
  }

  function initHomeKeyButton() {
    var btn = document.getElementById("home-add-key");
    if (!btn) {
      return;
    }
    /* "Add an API key" beside a browser that already holds two of them is
     * the page telling the reader something it can see is untrue. */
    if (loadKeys().length) btn.textContent = "Your API keys";
    btn.addEventListener("click", function () {
      openDrawer(true);
    });
  }

  /* A key added, edited or deleted in another tab is still this browser's
   * key, so the chip up here says so without waiting for a reload. */
  function watchKeysElsewhere() {
    if (!window.addEventListener) {
      return;
    }
    window.addEventListener("storage", function (event) {
      if (event && event.key && event.key !== STORE_KEY) {
        return;
      }
      updateChip();
      renderDrawer();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    updateChip();
    freshenExampleCaptions();
    initDrawer();
    initTheme();
    initToTop();
    initStepLocks();
    initInputCards();
    initScrollToAnswer();
    initHomeKeyButton();
    watchKeysElsewhere();
    initExampleLink();
    initShowAll();
    initFields();
    initNavScroll();
  });

  /* Only the calls that really reach a model carry the keys. An example, a
   * rebuild and an export are all worked out on the server from what was
   * posted, and a key has no business on those wires. */
  var AI_PATHS = [
    "/requirements/story/run",
    "/requirements/story/duel",
    "/requirements/test-cases/run",
    "/requirements/test-cases/refine",
    "/requirements/automation/run",
    "/requirements/matrix/suggest",
    "/risks/run",
    "/bugs/run",
    "/insights/explain",
  ];

  function callsTheAi(path) {
    var url = String(path || "").split("?")[0];
    for (var i = 0; i < AI_PATHS.length; i++) {
      if (url.indexOf(AI_PATHS[i]) !== -1) {
        return true;
      }
    }
    return false;
  }

  document.body.addEventListener("htmx:configRequest", function (event) {
    var detail = event.detail || {};
    if (!callsTheAi(detail.path)) {
      if (detail.headers) delete detail.headers["X-QAG-Keys"];
      return;
    }
    detail.headers["X-QAG-Keys"] = JSON.stringify(headerKeys());
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
    setPagePill: setPagePill,
    NOT_A_KEY: NOT_A_KEY,
    looksLikeKey: looksLikeKey,
    callsTheAi: callsTheAi,
    pasteWouldBeCut: pasteWouldBeCut,
    initInputCards: initInputCards,
    initFields: initFields,
    loadKeys: loadKeys,
    storeKeys: storeKeys,
    headerKeys: headerKeys,
    updateChip: updateChip,
    maskKey: maskKey,
    openDrawer: openDrawer,
    closeDrawer: closeDrawer,
  };
})();
