/* QA-Genius v2: keys live in the browser (localStorage), never on the server.
 * Every HTMX request carries them in the X-QAG-Keys header as
 * [{provider, key}] in the user's order. Labels are never sent. */
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
    updateKeyPill();
  }

  function headerKeys() {
    return loadKeys().map(function (entry) {
      return { provider: entry.provider, key: entry.key };
    });
  }

  function updateKeyPill() {
    var pill = document.getElementById("key-status");
    if (!pill) {
      return;
    }
    var count = loadKeys().length;
    if (count > 0) {
      pill.className = "pill ok";
      pill.textContent = count === 1 ? "1 key ready" : count + " keys ready";
    } else {
      pill.className = "pill warn";
      pill.textContent = "No key yet — examples only";
    }
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

  function providerName(select, id) {
    var options = select.querySelectorAll("option");
    for (var i = 0; i < options.length; i++) {
      if (options[i].value === id) {
        return options[i].textContent;
      }
    }
    return id;
  }

  function renderKeyList(listNode, form, select) {
    while (listNode.firstChild) {
      listNode.removeChild(listNode.firstChild);
    }
    var keys = loadKeys();
    var empty = document.getElementById("key-empty");
    if (empty) {
      empty.style.display = keys.length ? "none" : "";
    }
    keys.forEach(function (entry) {
      var li = el("li", "key-row");
      li.dataset.id = entry.id;

      var main = el("div", "key-main");
      main.appendChild(el("strong", null, providerName(select, entry.provider)));
      if (entry.label) {
        main.appendChild(el("span", "muted", " · " + entry.label));
      }
      var code = el("code", "mono", " " + maskKey(entry.key));
      main.appendChild(code);
      var result = el("span", "key-test-result");
      result.id = "test-" + entry.id;
      main.appendChild(result);
      li.appendChild(main);

      var actions = el("div", "row");
      var buttons = [
        ["test", "Test"],
        ["up", "↑"],
        ["down", "↓"],
        ["edit", "Edit"],
        ["delete", "Delete"],
      ];
      buttons.forEach(function (pair) {
        var btn = el("button", "btn btn-small", pair[1]);
        btn.type = "button";
        btn.dataset.action = pair[0];
        btn.dataset.id = entry.id;
        if (pair[0] === "test") {
          btn.setAttribute("aria-label", "Test key");
        }
        actions.appendChild(btn);
      });
      li.appendChild(actions);
      listNode.appendChild(li);
    });
  }

  function showTestResult(id, ok, message) {
    var node = document.getElementById("test-" + id);
    if (!node) {
      return;
    }
    while (node.firstChild) {
      node.removeChild(node.firstChild);
    }
    var pill = el("span", ok ? "pill ok" : "pill bad", message);
    node.appendChild(pill);
  }

  function testEntry(entry, button) {
    button.disabled = true;
    showTestResult(entry.id, false, "…");
    fetch("/api/keys/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: entry.provider, key: entry.key }),
    })
      .then(function (resp) {
        return resp.json();
      })
      .then(function (data) {
        if (data && data.ok) {
          showTestResult(entry.id, true, "OK");
        } else {
          showTestResult(entry.id, false, (data && data.error) || "Failed");
        }
      })
      .catch(function () {
        showTestResult(entry.id, false, "Network error");
      })
      .finally(function () {
        button.disabled = false;
      });
  }

  var editingId = null;

  function initKeysPage() {
    var listNode = document.getElementById("key-list");
    var form = document.getElementById("key-form");
    var select = document.getElementById("key-provider");
    if (!listNode || !form || !select) {
      return;
    }
    var labelInput = document.getElementById("key-label");
    var keyInput = document.getElementById("key-value");
    var link = document.getElementById("provider-key-link");
    var submitBtn = document.getElementById("key-save");

    function syncLink() {
      var opt = select.options[select.selectedIndex];
      if (link && opt && opt.dataset.keyUrl) {
        link.href = opt.dataset.keyUrl;
        link.textContent = "Get a free " + opt.textContent + " key";
      }
    }
    select.addEventListener("change", syncLink);
    syncLink();

    renderKeyList(listNode, form, select);

    listNode.addEventListener("click", function (event) {
      var btn = event.target.closest("button[data-action]");
      if (!btn) {
        return;
      }
      var keys = loadKeys();
      var pos = -1;
      for (var i = 0; i < keys.length; i++) {
        if (keys[i].id === btn.dataset.id) {
          pos = i;
          break;
        }
      }
      if (pos === -1) {
        return;
      }
      var action = btn.dataset.action;
      if (action === "delete") {
        keys.splice(pos, 1);
        if (editingId === btn.dataset.id) {
          editingId = null;
          form.reset();
          syncLink();
          submitBtn.textContent = "Save key";
        }
        storeKeys(keys);
        renderKeyList(listNode, form, select);
      } else if (action === "up" && pos > 0) {
        var tmp = keys[pos - 1];
        keys[pos - 1] = keys[pos];
        keys[pos] = tmp;
        storeKeys(keys);
        renderKeyList(listNode, form, select);
      } else if (action === "down" && pos < keys.length - 1) {
        var tmp2 = keys[pos + 1];
        keys[pos + 1] = keys[pos];
        keys[pos] = tmp2;
        storeKeys(keys);
        renderKeyList(listNode, form, select);
      } else if (action === "edit") {
        var entry = keys[pos];
        select.value = entry.provider;
        labelInput.value = entry.label || "";
        keyInput.value = entry.key;
        editingId = entry.id;
        submitBtn.textContent = "Save changes";
        syncLink();
        keyInput.focus();
      } else if (action === "test") {
        testEntry(keys[pos], btn);
      }
    });

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var provider = select.value;
      var label = labelInput.value.trim();
      var key = keyInput.value.trim();
      if (!provider || !key) {
        return;
      }
      var keys = loadKeys();
      if (editingId) {
        for (var i = 0; i < keys.length; i++) {
          if (keys[i].id === editingId) {
            keys[i] = { id: editingId, provider: provider, label: label, key: key };
            break;
          }
        }
        editingId = null;
        submitBtn.textContent = "Save key";
      } else {
        keys.push({ id: newId(), provider: provider, label: label, key: key });
      }
      storeKeys(keys);
      form.reset();
      syncLink();
      renderKeyList(listNode, form, select);
    });
  }

  function saveKeyAndResubmit(providerSelectId, keyInputId, formId) {
    var select = document.getElementById(providerSelectId);
    var keyInput = document.getElementById(keyInputId);
    var form = document.getElementById(formId);
    if (!select || !keyInput || !form) {
      return;
    }
    var key = keyInput.value.trim();
    if (!select.value || !key) {
      keyInput.focus();
      return;
    }
    var keys = loadKeys();
    keys.push({ id: newId(), provider: select.value, label: "", key: key });
    storeKeys(keys);
    if (typeof form.requestSubmit === "function") {
      form.requestSubmit();
    } else {
      form.submit();
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    updateKeyPill();
    initKeysPage();
  });

  document.body.addEventListener("htmx:configRequest", function (event) {
    event.detail.headers["X-QAG-Keys"] = JSON.stringify(headerKeys());
  });

  window.QAG = {
    loadKeys: loadKeys,
    storeKeys: storeKeys,
    headerKeys: headerKeys,
    updateKeyPill: updateKeyPill,
    maskKey: maskKey,
    saveKeyAndResubmit: saveKeyAndResubmit,
  };
})();
