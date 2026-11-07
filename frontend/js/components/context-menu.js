import { h } from "../dom.js";
import { icon } from "../icons.js";

// A small menu at the mouse position (right click). `items` = [{label, icon, onSelect, disabled}].
// It closes on a click elsewhere, Escape, scrolling, resizing or when the window loses focus.
let current = null;

export function closeContextMenu() {
  if (!current) return;
  current();
  current = null;
}

export function openContextMenu(x, y, items, serviceEl = null) {
  closeContextMenu();
  const rows = items.map((item) =>
    h(
      "button",
      {
        class: "ctx-item",
        type: "button",
        role: "menuitem",
        disabled: !!item.disabled,
        onClick: () => {
          closeContextMenu();
          item.onSelect?.();
        },
      },
      item.icon ? icon(item.icon) : null,
      h("span", { class: "ctx-text" }, item.label),
    ),
  );
  const menu = h("div", { class: "ctx-menu", role: "menu" }, rows);
  // The accent colour follows the downloader the menu belongs to.
  const service = serviceEl?.closest("[data-service]")?.dataset.service;
  if (service) menu.dataset.service = service;
  document.body.append(menu);

  // keep the menu inside the window
  const r = menu.getBoundingClientRect();
  menu.style.left = `${Math.max(4, Math.min(x, innerWidth - r.width - 4))}px`;
  menu.style.top = `${Math.max(4, Math.min(y, innerHeight - r.height - 4))}px`;

  const onPointer = (ev) => { if (!menu.contains(ev.target)) closeContextMenu(); };
  const onKey = (ev) => {
    if (ev.key === "Escape") {
      ev.stopPropagation();
      closeContextMenu();
    }
  };
  setTimeout(() => document.addEventListener("pointerdown", onPointer, true));
  document.addEventListener("keydown", onKey, true);
  window.addEventListener("blur", closeContextMenu);
  window.addEventListener("resize", closeContextMenu);
  document.addEventListener("scroll", closeContextMenu, true);
  current = () => {
    document.removeEventListener("pointerdown", onPointer, true);
    document.removeEventListener("keydown", onKey, true);
    window.removeEventListener("blur", closeContextMenu);
    window.removeEventListener("resize", closeContextMenu);
    document.removeEventListener("scroll", closeContextMenu, true);
    menu.remove();
  };
  rows.find((row) => !row.disabled)?.focus();
}
