import { h, debounce } from "../dom.js";
import { icon } from "../icons.js";
import { T } from "../i18n.js";
import { trapFocus } from "../focus-trap.js";
import { animateOut } from "../motion.js";
import { filterEntries, rangeBetween, sortedSelection } from "../selection.js";

// The entries of a playlist, profile or channel with a checkbox each. Resolves with the picked
// positions (list order), or null if the dialog was closed without choosing.
//   entries: [{index, title}]
export function chooseEntries({ service, entries }) {
  return new Promise((resolve) => {
    const selected = new Set(entries.map((entry) => entry.index));   // everything starts ticked
    const rows = new Map();                                          // index -> {row, box}
    let visible = entries;
    let lastClicked = null;
    let releaseFocus = () => {};

    const isTop = () => {
      const all = document.querySelectorAll(".modal-overlay:not(.leaving)");
      return all[all.length - 1] === overlay;
    };
    const finish = (value) => {
      document.removeEventListener("keydown", onKey, true);
      releaseFocus();
      resolve(value);
      animateOut(overlay);
    };
    const onKey = (ev) => {
      if (ev.key === "Escape" && isTop()) {
        ev.stopPropagation();
        finish(null);
      }
    };

    const count = h("span", { class: "sel-count" });
    const downloadBtn = h("button", { class: "btn accent", type: "button", onClick: () => finish(sortedSelection(selected)) });
    const cancelBtn = h("button", { class: "btn neutral", type: "button", onClick: () => finish(null) }, T("cancel_btn"));

    function paint() {
      for (const [index, { box }] of rows) box.checked = selected.has(index);
      count.textContent = T("sel_count", selected.size, entries.length);
      downloadBtn.textContent = T("sel_download_n", selected.size);
      downloadBtn.disabled = selected.size === 0;
    }

    function toggle(index, on, shift) {
      const targets = shift && lastClicked != null ? rangeBetween(visible, lastClicked, index) : [{ index }];
      for (const entry of targets) {
        if (on) selected.add(entry.index);
        else selected.delete(entry.index);
      }
      lastClicked = index;
      paint();
    }

    const list = h("div", { class: "sel-list", role: "group", "aria-label": T("sel_title") });
    entries.forEach((entry, position) => {
      const box = h("input", { type: "checkbox", class: "sel-box" });
      const row = h(
        "label",
        { class: "sel-row", title: entry.title },
        box,
        h("span", { class: "sel-num" }, String(position + 1)),
        h("span", { class: "sel-title" }, entry.title),
      );
      // The click that toggles the box also reports the shift key, so ranges work without extra code.
      box.addEventListener("click", (ev) => toggle(entry.index, box.checked, ev.shiftKey));
      rows.set(entry.index, { row, box });
      list.append(row);
    });

    const setAll = (on) => {
      for (const entry of visible) {
        if (on) selected.add(entry.index);
        else selected.delete(entry.index);
      }
      paint();
    };

    const filter = h("input", { class: "entry sel-filter", type: "text", placeholder: T("sel_filter_ph"), "aria-label": T("sel_filter_ph"), spellcheck: false, autocomplete: "off" });
    filter.addEventListener(
      "input",
      debounce(() => {
        visible = filterEntries(entries, filter.value);
        const shown = new Set(visible.map((entry) => entry.index));
        for (const [index, { row }] of rows) row.hidden = !shown.has(index);
        lastClicked = null;
      }, 120),
    );

    const overlay = h(
      "div",
      { class: "modal-overlay", dataset: { service } },
      h(
        "div",
        { class: "modal selection-modal", role: "dialog", "aria-modal": "true" },
        h("div", { class: "modal-head info" }, icon("info"), h("span", {}, T("sel_title"))),
        h("div", { class: "sel-intro" }, T("sel_found", entries.length)),
        h(
          "div",
          { class: "sel-tools" },
          filter,
          h("button", { class: "btn neutral small", type: "button", onClick: () => setAll(true) }, T("sel_all")),
          h("button", { class: "btn neutral small", type: "button", onClick: () => setAll(false) }, T("sel_none")),
        ),
        list,
        h("div", { class: "sel-footer" }, count, h("span", { class: "tb-spacer" }), cancelBtn, downloadBtn),
      ),
    );
    document.addEventListener("keydown", onKey, true);
    document.body.append(overlay);
    paint();
    releaseFocus = trapFocus(overlay, isTop);
    downloadBtn.focus();
  });
}
