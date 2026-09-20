import { h } from "../dom.js";
import { icon } from "../icons.js";
import { T } from "../i18n.js";

function barButton(iconName, title, onClick, extraClass = "", action = "") {
  return h("button", { class: `tb-btn ${extraClass}`.trim(), type: "button", title, "aria-label": title, dataset: { action }, onClick }, icon(iconName));
}

// Launcher variant: 40 px bar with title and close button.
export function createLauncherBar({ title, onMinimize, onClose }) {
  return h(
    "div",
    { class: "titlebar launcher-bar pywebview-drag-region" },
    h("span", { class: "tb-title" }, title),
    h("span", { class: "tb-group" }, barButton("minimize", T("tip_minimize"), onMinimize, "", "minimize"), barButton("close", T("tip_close"), onClose, "danger", "close")),
  );
}

// Tool variant: 46 px bar with back, brand icon, title, settings, minimize, maximize, close.
export function createToolBar({ title, service, onBack, onSettings, onMinimize, onMaximize, onClose }) {
  const maxBtn = barButton("maximize", T("tip_maximize"), onMaximize, "", "maximize");
  const bar = h(
    "div",
    { class: "titlebar tool-bar pywebview-drag-region" },
    onBack ? barButton("back", T("tip_back"), onBack, "", "back") : null,
    h("span", { class: `brand-icon brand-${service}`, style: { width: "22px", height: "22px" } }),
    h("span", { class: "tb-title" }, title),
    h("span", { class: "tb-spacer" }),
    barButton("gear", T("tip_settings"), onSettings, "", "settings"),
    barButton("minimize", T("tip_minimize"), onMinimize, "", "minimize"),
    maxBtn,
    barButton("close", T("tip_close"), onClose, "danger", "close"),
  );
  bar.addEventListener("dblclick", (ev) => {
    if (!ev.target.closest("button")) onMaximize();
  });
  return {
    el: bar,
    setMaximized(isMax) {
      maxBtn.replaceChildren(icon(isMax ? "restore" : "maximize"));
      maxBtn.title = isMax ? T("tip_restore") : T("tip_maximize");
      maxBtn.setAttribute("aria-label", maxBtn.title);
    },
  };
}
