import { h } from "../dom.js";
import { icon } from "../icons.js";

function barButton(iconName, title, onClick, extraClass = "") {
  return h("button", { class: `tb-btn ${extraClass}`.trim(), type: "button", title, "aria-label": title, onClick }, icon(iconName));
}

// Launcher variant: 40 px bar with title and close button.
export function createLauncherBar({ title, onClose }) {
  return h(
    "div",
    { class: "titlebar launcher-bar pywebview-drag-region" },
    h("span", { class: "tb-title" }, title),
    barButton("close", "Close", onClose, "danger"),
  );
}

// Tool variant: 46 px bar with back, brand icon, title, settings, minimize, maximize, close.
export function createToolBar({ title, service, onBack, onSettings, onMinimize, onMaximize, onClose }) {
  const maxBtn = barButton("maximize", "Maximize", onMaximize);
  const bar = h(
    "div",
    { class: "titlebar tool-bar pywebview-drag-region" },
    onBack ? barButton("back", "Back", onBack) : null,
    h("span", { class: `brand-icon brand-${service}`, style: { width: "22px", height: "22px" } }),
    h("span", { class: "tb-title" }, title),
    h("span", { class: "tb-spacer" }),
    barButton("gear", "Settings", onSettings),
    barButton("minimize", "Minimize", onMinimize),
    maxBtn,
    barButton("close", "Close", onClose, "danger"),
  );
  bar.addEventListener("dblclick", (ev) => {
    if (!ev.target.closest("button")) onMaximize();
  });
  return {
    el: bar,
    setMaximized(isMax) {
      maxBtn.replaceChildren(icon(isMax ? "restore" : "maximize"));
      maxBtn.title = isMax ? "Restore" : "Maximize";
    },
  };
}
