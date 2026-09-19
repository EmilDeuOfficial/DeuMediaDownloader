import { h } from "../dom.js";
import { T } from "../i18n.js";

const MAX_LINES = 1000;

function timestamp() {
  const d = new Date();
  return [d.getHours(), d.getMinutes(), d.getSeconds()].map((n) => String(n).padStart(2, "0")).join(":");
}

export function createLogPanel() {
  const box = h("div", { class: "log-box", tabIndex: 0 });
  const el = h(
    "section",
    { class: "panel log-panel" },
    h(
      "div",
      { class: "panel-head" },
      h("span", { class: "panel-title" }, T("log_panel")),
      h("span", { class: "tb-spacer" }),
      h("button", { class: "btn neutral small", type: "button", onClick: clear }, T("clear_log")),
    ),
    box,
  );

  function append(msg) {
    const stick = box.scrollTop + box.clientHeight >= box.scrollHeight - 8;
    box.append(h("div", { class: "log-line" }, `[${timestamp()}] ${msg}`));
    while (box.childElementCount > MAX_LINES) box.firstElementChild.remove();
    if (stick) box.scrollTop = box.scrollHeight;
  }

  function clear() {
    box.replaceChildren();
  }

  return { el, append, clear };
}
