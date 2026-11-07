import { h } from "../dom.js";
import { icon } from "../icons.js";
import { T } from "../i18n.js";
import { actionsFor, statusText } from "../task-actions.js";
import { openContextMenu } from "./context-menu.js";

// One row of the download queue. `task` is the serialized task from Python:
// {id, service, name, format, ext, status, label, progress, error, url}. All text goes in as
// text nodes.
// `handlers` = {onPause(id), onResume(id), onCancel(id), onReveal(id), onCopyLink(url)}.
// A finished entry opens Explorer with its file on click; a right click shows a small menu.
export function createQueueItem(task, glyph, handlers = {}) {
  let canPause = task.can_pause !== false;
  let label = task.label || "";
  let progress = task.progress;
  let url = task.url || "";
  const title = h("span", { class: "qi-title" });
  const ext = h("span", { class: "qi-ext" });
  const name = h("div", { class: "qi-name" }, title, ext);
  const status = h("div", { class: "qi-status" }, label);
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

  const isDone = () => el.dataset.status === "DONE";

  el.addEventListener("click", (ev) => {
    if (isDone() && !ev.target.closest("button")) handlers.onReveal?.(task.id);
  });
  el.addEventListener("keydown", (ev) => {
    if (isDone() && (ev.key === "Enter" || ev.key === " ") && ev.target === el) {
      ev.preventDefault();
      handlers.onReveal?.(task.id);
    }
  });
  el.addEventListener("contextmenu", (ev) => {
    ev.preventDefault();
    openContextMenu(ev.clientX, ev.clientY, [
      { label: T("ctx_copy_link"), icon: "link", disabled: !url, onSelect: () => handlers.onCopyLink?.(url) },
      { label: T("ctx_show_file"), icon: "folder", disabled: !isDone(), onSelect: () => handlers.onReveal?.(task.id) },
    ], el);
  });

  function onToggle() {
    if (el.dataset.status === "PAUSED") handlers.onResume?.(task.id);
    else handlers.onPause?.(task.id);
  }

  function renderActions(statusName) {
    const a = actionsFor(statusName, canPause);
    actions.hidden = !a;
    if (!a) return;
    toggleBtn.hidden = !a.toggle;
    const resume = a.toggle === "resume";
    const tip = T(resume ? "tip_resume" : "tip_pause");
    toggleBtn.replaceChildren(icon(resume ? "play" : "pause"));
    toggleBtn.title = tip;
    toggleBtn.setAttribute("aria-label", tip);
    toggleBtn.disabled = a.disabled;
    cancelBtn.disabled = a.cancelDisabled;
  }

  function renderStatus() {
    status.textContent = statusText(label, el.dataset.status, progress);
  }

  function renderDone() {
    const done = isDone();
    el.classList.toggle("openable", done);
    el.tabIndex = done ? 0 : -1;
    if (done) el.title = T("tip_show_file");
    else el.removeAttribute("title");
  }

  function update(next) {
    if (next.can_pause != null) canPause = next.can_pause;
    if (next.url != null) url = next.url;
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
      label = next.label;
      status.title = next.error || next.label;   // full error text on hover
    }
    if (next.status != null) {
      el.dataset.status = next.status;
      renderActions(next.status);
      renderDone();
    }
    if (typeof next.progress === "number") {
      progress = next.progress;
      fill.style.width = `${Math.round(Math.min(1, Math.max(0, next.progress)) * 1000) / 10}%`;
    }
    renderStatus();
  }
  update(task);
  return { el, id: task.id, update, isFinished: () => ["DONE", "ERROR", "CANCELLED"].includes(el.dataset.status) };
}
