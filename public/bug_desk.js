/* QA-Genius v2: the Bug desk form.
 * The screenshot is resized in the browser and travels with this one request.
 * It is never stored, and the keys header is added by app.js like everywhere else. */
(function () {
  "use strict";

  var MAX_SIDE = 1600;
  var RESIZE_OVER = 1.5 * 1024 * 1024;
  var MAX_BYTES = 2 * 1024 * 1024;
  var JPEG_QUALITY = 0.85;
  var TYPES = ["image/png", "image/jpeg", "image/webp"];

  function byId(id) {
    return document.getElementById(id);
  }

  /* ---------- notes counter ---------- */

  function updateNotes() {
    var box = byId("bug-notes");
    var count = byId("bug-notes-count");
    if (box && count) count.textContent = String(box.value.length);
  }

  /* ---------- attempts ---------- */

  /* Same rule as reproducibility_text in qagenius/bug_report.py. */
  function reproText(total, happened) {
    if (happened <= 0) return "Not reproduced yet";
    if (happened >= total) return "Always";
    return "Intermittent (" + happened + " of " + total + ")";
  }

  function number(box, fallback) {
    var value = parseInt(box ? box.value : "", 10);
    return isNaN(value) ? fallback : value;
  }

  function updateAttempts() {
    var line = byId("bug-repro");
    var run = byId("bug-run");
    if (!line) return;
    var total = number(byId("bug-total"), 1);
    var happened = number(byId("bug-happened"), 0);
    if (happened > total) {
      line.textContent = "Happened can't be more than Tried";
      line.className = "small bad-line";
      if (run) run.disabled = true;
      return;
    }
    line.textContent = reproText(total, happened);
    line.className = "muted small";
    if (run) run.disabled = false;
  }

  /* ---------- screenshot ---------- */

  function setStatus(text) {
    var status = byId("bug-shot-status");
    if (status) status.textContent = text;
  }

  function clearShot() {
    var mime = byId("bug-shot-mime");
    var data = byId("bug-shot-data");
    var preview = byId("bug-shot-preview");
    var thumb = byId("bug-shot-thumb");
    if (mime) mime.value = "";
    if (data) data.value = "";
    if (thumb) thumb.removeAttribute("src");
    if (preview) preview.hidden = true;
  }

  function decodedSize(base64) {
    var padding = 0;
    if (base64.charAt(base64.length - 1) === "=") padding += 1;
    if (base64.charAt(base64.length - 2) === "=") padding += 1;
    return Math.floor((base64.length * 3) / 4) - padding;
  }

  function store(mime, dataUrl) {
    var base64 = dataUrl.slice(dataUrl.indexOf(",") + 1);
    var bytes = decodedSize(base64);
    if (bytes > MAX_BYTES) {
      clearShot();
      setStatus("Screenshot is too large");
      return;
    }
    byId("bug-shot-mime").value = mime;
    byId("bug-shot-data").value = base64;
    var thumb = byId("bug-shot-thumb");
    if (thumb) thumb.src = "data:" + mime + ";base64," + base64;
    var size = byId("bug-shot-size");
    if (size) size.textContent = Math.round(bytes / 1024) + " KB";
    var preview = byId("bug-shot-preview");
    if (preview) preview.hidden = false;
    setStatus("");
  }

  /* Big images are drawn onto a canvas first, so only a small one is sent. */
  function shrink(file, dataUrl) {
    var image = new Image();
    image.onload = function () {
      var longest = Math.max(image.width, image.height);
      if (longest <= MAX_SIDE && file.size <= RESIZE_OVER) {
        store(file.type, dataUrl);
        return;
      }
      var scale = Math.min(1, MAX_SIDE / longest);
      var canvas = document.createElement("canvas");
      canvas.width = Math.round(image.width * scale);
      canvas.height = Math.round(image.height * scale);
      var context = canvas.getContext("2d");
      if (!context) {
        store(file.type, dataUrl);
        return;
      }
      context.drawImage(image, 0, 0, canvas.width, canvas.height);
      store("image/jpeg", canvas.toDataURL("image/jpeg", JPEG_QUALITY));
    };
    image.onerror = function () {
      setStatus("That image could not be read.");
    };
    image.src = dataUrl;
  }

  function attach(file) {
    if (!file) return;
    if (TYPES.indexOf(file.type) === -1) {
      setStatus("Pick a PNG, JPG or WebP image.");
      return;
    }
    setStatus("Preparing the screenshot…");
    var reader = new FileReader();
    reader.onload = function () {
      shrink(file, String(reader.result));
    };
    reader.onerror = function () {
      setStatus("That image could not be read.");
    };
    reader.readAsDataURL(file);
  }

  /* ---------- copying the report out ---------- */

  function exportText(kind) {
    var holder = byId("bug-export");
    if (!holder) return "";
    try {
      return JSON.parse(holder.textContent)[kind] || "";
    } catch (e) {
      return "";
    }
  }

  function copyStatus(text) {
    var status = byId("bug-copy-status");
    if (status) status.textContent = text;
  }

  function copyOut(kind) {
    var text = exportText(kind);
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

  function downloadMarkdown() {
    var text = exportText("markdown");
    if (!text) return;
    var blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var link = document.createElement("a");
    link.href = url;
    link.download = "bug-report.md";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    copyStatus("");
  }

  /* The thumbnail comes from the form, never back from the server. */
  function showSentScreenshot() {
    var holder = byId("bug-shot-shown");
    var data = byId("bug-shot-data");
    var mime = byId("bug-shot-mime");
    if (!holder || !data || !mime || !data.value) return;
    holder.textContent = "";
    var figure = document.createElement("figure");
    figure.className = "shot-shown";
    var image = document.createElement("img");
    image.className = "shot-thumb";
    image.src = "data:" + mime.value + ";base64," + data.value;
    image.alt = "Screenshot sent with the request";
    var caption = document.createElement("figcaption");
    caption.textContent = "Screenshot sent with the request";
    figure.appendChild(image);
    figure.appendChild(caption);
    holder.appendChild(figure);
  }

  /* ---------- wiring ---------- */

  document.addEventListener("input", function (event) {
    var target = event.target;
    if (!target || !target.id) return;
    if (target.id === "bug-notes") updateNotes();
    if (target.id === "bug-total" || target.id === "bug-happened") updateAttempts();
  });

  document.addEventListener("change", function (event) {
    var target = event.target;
    if (!target) return;
    if (target.id === "bug-file" && target.files && target.files.length) {
      attach(target.files[0]);
    }
    if (target.id === "bug-total" || target.id === "bug-happened") updateAttempts();
  });

  document.addEventListener("click", function (event) {
    var target = event.target;
    if (!target || !target.closest) return;
    if (target.closest("#bug-pick")) {
      var picker = byId("bug-file");
      if (picker) picker.click();
      return;
    }
    if (target.closest("#bug-shot-remove")) {
      var picker2 = byId("bug-file");
      if (picker2) picker2.value = "";
      clearShot();
      setStatus("");
      return;
    }
    if (target.closest("#copy-markdown")) {
      copyOut("markdown");
      return;
    }
    if (target.closest("#copy-jira")) {
      copyOut("jira");
      return;
    }
    if (target.closest("#download-md")) {
      downloadMarkdown();
    }
  });

  document.addEventListener("htmx:afterSwap", function (event) {
    var detail = event.detail;
    var path = detail && detail.pathInfo ? detail.pathInfo.requestPath : "";
    if (path.indexOf("/bugs/run") !== -1) showSentScreenshot();
  });

  /* Ctrl+V anywhere on the page attaches the image on the clipboard. */
  document.addEventListener("paste", function (event) {
    if (!byId("bug-drop")) return;
    var items = event.clipboardData ? event.clipboardData.items : null;
    if (!items) return;
    for (var i = 0; i < items.length; i += 1) {
      if (items[i].kind === "file") {
        var file = items[i].getAsFile();
        if (file) {
          attach(file);
          event.preventDefault();
          return;
        }
      }
    }
  });

  function onDragOver(event) {
    event.preventDefault();
    var zone = byId("bug-drop");
    if (zone) zone.classList.add("over");
  }

  function onDragLeave() {
    var zone = byId("bug-drop");
    if (zone) zone.classList.remove("over");
  }

  function onDrop(event) {
    var zone = byId("bug-drop");
    if (!zone) return;
    event.preventDefault();
    zone.classList.remove("over");
    var files = event.dataTransfer ? event.dataTransfer.files : null;
    if (files && files.length) attach(files[0]);
  }

  document.addEventListener("DOMContentLoaded", function () {
    var zone = byId("bug-drop");
    if (zone) {
      zone.addEventListener("dragover", onDragOver);
      zone.addEventListener("dragleave", onDragLeave);
      zone.addEventListener("drop", onDrop);
    }
    updateNotes();
    updateAttempts();
  });
})();
