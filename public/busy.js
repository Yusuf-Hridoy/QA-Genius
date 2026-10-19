/* QA-Genius v2: one answer to "is it doing anything?".
 *
 * Every button that starts a model call goes through here, whether HTMX sends
 * the request or a hand-written fetch does. While it runs the button says so
 * (aria-busy, a spinner, a working label), it cannot be pressed twice, and a
 * calm line under its card says how long this usually takes.
 *
 * Nothing here knows which desk it is on. The caller passes the working
 * label, or puts it on the button as data-busy-label. */
(function () {
  "use strict";

  /* The one promise the line makes. Said once, under the card that is busy. */
  var WAIT_LINE = "This takes about 20–40 seconds. You can stay on this page.";
  var NOTE_ID = "qag-busy-note";

  /* Every button currently working. Usually one; two when a source card
   * presses the desk's own button and both have to look busy. */
  var working = [];

  function labelNode(button) {
    var inner = button.querySelector ? button.querySelector(".btn-label") : null;
    return inner || button;
  }

  /* The card the line belongs under: the one this button sits in. */
  function cardOf(button) {
    if (!button.closest) return null;
    return button.closest(".source-card") || button.closest(".card") || null;
  }

  function docOf(button) {
    if (button && button.ownerDocument) return button.ownerDocument;
    return typeof document === "undefined" ? null : document;
  }

  function showNote(button) {
    var doc = docOf(button);
    var card = cardOf(button);
    if (!doc || !card || !card.parentNode || doc.getElementById(NOTE_ID)) return;
    var note = doc.createElement("p");
    note.id = NOTE_ID;
    note.className = "busy-note";
    note.setAttribute("role", "status");
    note.textContent = WAIT_LINE;
    card.parentNode.insertBefore(note, card.nextSibling);
  }

  function hideNote(button) {
    var doc = docOf(button);
    var note = doc ? doc.getElementById(NOTE_ID) : null;
    if (note && note.parentNode) note.parentNode.removeChild(note);
  }

  function isBusy(button) {
    return !!button && button.getAttribute("aria-busy") === "true";
  }

  /* Start: returns false when there was nothing to do, so a second click on a
   * button that is already working can stop right there. */
  function start(button, label) {
    if (!button || isBusy(button)) return false;
    if (button.getBoundingClientRect && button.style) {
      var width = button.getBoundingClientRect().width;
      // The label is about to get longer; the row must not jump.
      if (width) button.style.minWidth = Math.ceil(width) + "px";
    }
    button.setAttribute("aria-busy", "true");
    // A button the page had already switched off -- the bug desk does it
    // while the numbers disagree -- must still be off when this is over.
    if (button.disabled) button.setAttribute("data-was-off", "yes");
    else button.disabled = true;
    var busyLabel = label || button.getAttribute("data-busy-label");
    if (busyLabel) {
      var node = labelNode(button);
      button.setAttribute("data-idle-label", node.textContent);
      node.textContent = busyLabel;
    }
    if (working.indexOf(button) === -1) working.push(button);
    showNote(button);
    return true;
  }

  function stop(button) {
    if (!button) return;
    var at = working.indexOf(button);
    if (at !== -1) working.splice(at, 1);
    button.removeAttribute("aria-busy");
    if (button.getAttribute("data-was-off")) button.removeAttribute("data-was-off");
    else button.disabled = false;
    if (button.style) button.style.minWidth = "";
    var idle = button.getAttribute("data-idle-label");
    if (idle !== null && idle !== undefined) {
      labelNode(button).textContent = idle;
      button.removeAttribute("data-idle-label");
    }
    // The line belongs to the work, not to one button: it goes when the last
    // button working goes.
    if (!working.length) hideNote(button);
  }

  function stopAll() {
    working.slice().forEach(stop);
  }

  window.QAGBusy = {
    WAIT_LINE: WAIT_LINE,
    NOTE_ID: NOTE_ID,
    start: start,
    stop: stop,
    stopAll: stopAll,
    isBusy: isBusy,
    working: function () {
      return working.slice();
    }
  };
})();
