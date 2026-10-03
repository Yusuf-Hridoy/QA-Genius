// Task 4 wires this up: localStorage keys + X-QAG-Keys header + status pill.
// Task 2 stub: show the default "no keys" pill on every page load.
document.addEventListener("DOMContentLoaded", function () {
  var pill = document.getElementById("key-status");
  if (pill) {
    pill.className = "pill warn";
    pill.textContent = "No key yet — examples only";
  }
});
