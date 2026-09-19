import { h } from "../dom.js";
import { icon } from "../icons.js";
import { T } from "../i18n.js";

// Promise based dialogs that replace tkinter's messagebox.
// showModal resolves with the `value` of the clicked button (or `cancelValue` on Escape).
export function showModal({ title, message, kind = "info", buttons, cancelValue = null }) {
  return new Promise((resolve) => {
    const previous = document.activeElement;
    const finish = (value) => {
      document.removeEventListener("keydown", onKey, true);
      overlay.remove();
      if (previous && previous.focus) previous.focus();
      resolve(value);
    };
    const onKey = (ev) => {
      if (ev.key === "Escape") {
        ev.stopPropagation();
        finish(cancelValue);
      }
    };

    const buttonEls = buttons.map((b) =>
      h("button", { class: `btn ${b.kind || "neutral"}`, type: "button", onClick: () => finish(b.value) }, b.label),
    );
    const overlay = h(
      "div",
      { class: "modal-overlay" },
      h(
        "div",
        { class: "modal", role: "dialog", "aria-modal": "true" },
        h("div", { class: `modal-head ${kind}` }, icon(kind === "warning" || kind === "error" ? "warning" : "info"), h("span", {}, title)),
        h("div", { class: "modal-body" }, message),
        h("div", { class: "modal-actions" }, buttonEls),
      ),
    );
    document.addEventListener("keydown", onKey, true);
    document.body.append(overlay);
    (buttonEls[buttonEls.length - 1] || overlay).focus();
  });
}

export function alertModal(title, message, kind = "info") {
  return showModal({
    title,
    message,
    kind,
    buttons: [{ label: T("btn_ok"), value: true, kind: "accent" }],
  });
}

export function confirmModal(title, message) {
  return showModal({
    title,
    message,
    kind: "warning",
    cancelValue: false,
    buttons: [
      { label: T("btn_no"), value: false, kind: "neutral" },
      { label: T("btn_yes"), value: true, kind: "danger" },
    ],
  });
}
