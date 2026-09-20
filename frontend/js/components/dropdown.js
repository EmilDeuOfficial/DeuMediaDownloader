import { h } from "../dom.js";
import { icon } from "../icons.js";

// Custom select styled like the entry fields. The popup lives on <body> so it is never
// clipped by scroll containers; it closes on outside click, Escape and window blur.
export function createDropdown({ values, value, width = 210, onChange }) {
  let items = [...values];
  let current = value;
  let popup = null;
  let activeIndex = -1;

  const label = h("span", { class: "dd-label" }, current);
  const arrow = h("span", { class: "dd-arrow" }, icon("chevron-down"));
  const el = h(
    "div",
    { class: "dropdown", style: { width: `${width}px`, maxWidth: "100%" }, tabIndex: 0, role: "combobox", "aria-expanded": "false" },
    h("div", { class: "dd-inner" }, label, arrow),
  );

  function setValue(next, notify = false) {
    current = next;
    label.textContent = next;
    if (notify && onChange) onChange(next);
  }

  function close() {
    if (!popup) return;
    popup.remove();
    popup = null;
    el.classList.remove("open");
    el.setAttribute("aria-expanded", "false");
    document.removeEventListener("pointerdown", onOutside, true);
    window.removeEventListener("blur", close);
    window.removeEventListener("resize", close);
  }

  function onOutside(ev) {
    if (popup && !popup.contains(ev.target) && !el.contains(ev.target)) close();
  }

  function highlight(index) {
    activeIndex = index;
    [...popup.children].forEach((row, i) => row.classList.toggle("active", i === index));
    popup.children[index]?.scrollIntoView({ block: "nearest" });
  }

  function choose(index) {
    setValue(items[index], true);
    close();
    el.focus();
  }

  function open() {
    if (popup) return;
    const rect = el.getBoundingClientRect();
    popup = h(
      "div",
      { class: "dd-popup", style: { left: `${rect.left}px`, top: `${rect.bottom + 4}px`, width: `${rect.width}px` } },
      items.map((item, i) =>
        h(
          "div",
          {
            class: `dd-item${item === current ? " selected" : ""}`,
            role: "option",
            onClick: () => choose(i),
            onMouseenter: () => highlight(i),
          },
          h("span", { class: "dd-text" }, item),
          h("span", { class: "dd-check" }, icon("check")),
        ),
      ),
    );
    // The popup lives on <body>, so carry the service accent over explicitly.
    const service = el.closest("[data-service]");
    if (service) popup.dataset.service = service.dataset.service;
    document.body.append(popup);
    const maxHeight = window.innerHeight - rect.bottom - 16;
    popup.style.maxHeight = `${Math.max(120, maxHeight)}px`;
    el.classList.add("open");
    el.setAttribute("aria-expanded", "true");
    document.addEventListener("pointerdown", onOutside, true);
    window.addEventListener("blur", close);
    window.addEventListener("resize", close);
    highlight(Math.max(0, items.indexOf(current)));
  }

  el.addEventListener("click", () => (popup ? close() : open()));
  el.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") {
      close();
    } else if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
      ev.preventDefault();
      if (!popup) return open();
      const step = ev.key === "ArrowDown" ? 1 : -1;
      highlight((activeIndex + step + items.length) % items.length);
    } else if (ev.key === "Enter" || ev.key === " ") {
      ev.preventDefault();
      if (!popup) open();
      else choose(activeIndex);
    }
  });

  return {
    el,
    getValue: () => current,
    setValue: (next) => setValue(next, false),
    setValues(nextValues, nextValue) {
      items = [...nextValues];
      setValue(nextValue, false);
    },
    close,
  };
}
