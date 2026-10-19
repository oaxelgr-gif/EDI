import { $ } from "./dom.js";

export function toast(message, kind = "info", ms = 3200) {
  const t = document.createElement("div");
  t.className = `toast ${kind}`;
  t.textContent = message;
  $("#toasts").append(t);
  setTimeout(() => t.remove(), ms);
}
