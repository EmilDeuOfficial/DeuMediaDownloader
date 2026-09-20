import { h } from "../dom.js";
import { icon } from "../icons.js";
import { T } from "../i18n.js";
import { actionsFor } from "../task-actions.js";

// One row of the download queue. `task` is the serialized task from Python:
// {id, service, name, format, ext, status, label, progress, error}. All text goes in as text nodes.
// `handlers` = {onPause(id), onResume(id), onCancel(id)}.
export function createQueueItem(task, glyph, handlers = {}) {
  const title = h("span", { class: "qi-title" });
  const ext = h("span", { class: "qi-ext" });
  const name = h("div", { class: "qi-name" }, title, ext);
  const status = h("div", { class: "qi-status" }, task.label);
  const fill = h("div", { class: "qi-fill" });

  const toggleBtn = h("button", { class: "qi-btn", type: "button", dataset: { action: "toggle" }, onClick: onToggle });
  const cancelBtn = h(
    "button",
    { class: "qi-btn cancel", type: "button", dataset: { action: "cancel" }, title: T("tip_cancel"), "aria-label": T("tip_cancel"), onClick: () => handlers.onCancel?.(task.id) },
    icon("close"),
  );
  const actions = h("div", { class: "qi-actions" }, toggleBtn, cancelBtn);

  const el = h(
    "div",
    { class: "queue-item", dataset: { id: task.id, status: task.status } },
    h("div", { class: "qi-glyph" }, icon(glyph)),
    name,
    status,
    actions,
    h("div", { class: "qi-bar" }, fill),
  );

  function onToggle() {
    if (el.dataset.status === "PAUSED") handlers.onResume?.(task.id);
    else handlers.onPause?.(task.id);
  }

  function renderActions(statusName) {
    const a = actionsFor(statusName);
    actions.hidden = !a;
    if (!a) return;
    const resume = a.toggle === "resume";
    const tip = T(resume ? "tip_resume" : "tip_pause");
    toggleBtn.replaceChildren(icon(resume ? "play" : "pause"));
    toggleBtn.title = tip;
    toggleBtn.setAttribute("aria-label", tip);
    toggleBtn.disabled = a.disabled;
    cancelBtn.disabled = a.disabled;
  }

  function update(next) {
    if (next.name != null) {
      title.textContent = next.name;
      name.title = next.name;
    }
    if (next.ext != null) {
      ext.textContent = next.ext.toUpperCase();
      ext.title = next.format || next.ext;
      ext.hidden = !next.ext;
    }
    if (next.label != null) {
      status.textContent = next.label;
      status.title = next.error || next.label;   // full error text on hover
    }
    if (next.status != null) {
      el.dataset.status = next.status;
      renderActions(next.status);
    }
    if (typeof next.progress === "number") {
      fill.style.width = `${Math.round(Math.min(1, Math.max(0, next.progress)) * 1000) / 10}%`;
    }
  }
  update(task);
  return { el, id: task.id, update, isFinished: () => ["DONE", "ERROR", "CANCELLED"].includes(el.dataset.status) };
}
