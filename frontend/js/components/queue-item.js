import { h } from "../dom.js";
import { icon } from "../icons.js";

// One row of the download queue. `task` is the serialized task from Python:
// {id, service, name, status, label, progress, error}. All text goes in as text nodes.
export function createQueueItem(task, glyph) {
  const name = h("div", { class: "qi-name" }, task.name);
  const status = h("div", { class: "qi-status" }, task.label);
  const fill = h("div", { class: "qi-fill" });
  const el = h(
    "div",
    { class: "queue-item", dataset: { id: task.id, status: task.status } },
    h("div", { class: "qi-glyph" }, icon(glyph)),
    name,
    status,
    h("div", { class: "qi-bar" }, fill),
  );

  function update(next) {
    if (next.name != null) name.textContent = next.name;
    if (next.label != null) status.textContent = next.label;
    if (next.status != null) el.dataset.status = next.status;
    if (typeof next.progress === "number") {
      fill.style.width = `${Math.round(Math.min(1, Math.max(0, next.progress)) * 1000) / 10}%`;
    }
  }
  update(task);
  return { el, id: task.id, update, isFinished: () => el.dataset.status === "DONE" || el.dataset.status === "ERROR" };
}
