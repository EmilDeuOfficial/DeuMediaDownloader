import { h } from "../dom.js";
import { api } from "../bridge.js";
import { T } from "../i18n.js";
import { app } from "../state.js";
import { icon } from "../icons.js";
import { SETTINGS_SCHEMA, UNINSTALL_ROWS, RATE_OPTIONS } from "../settings-schema.js";
import { createDropdown } from "./dropdown.js";
import { alertModal, confirmModal } from "./modal.js";

// Schema driven settings dialog (Settings tab + Uninstall tab) for one service.
export function openSettings(serviceId) {
  const schema = SETTINGS_SCHEMA[serviceId];
  const { config, options } = app.get();
  const controls = new Map(); // key -> {get, setEnabled?}
  const title = T(schema.titleKey);

  // ------------------------------------------------------------------ fields
  function optionPairs(name) {
    return name === "rate" ? RATE_OPTIONS : options[name] || [];
  }

  function current(field) {
    const value = config[field.key];
    return value === undefined ? field.default : value;
  }

  function buildField(field) {
    switch (field.type) {
      case "link":
        return h(
          "a",
          { class: "sm-link", href: "#", onClick: (ev) => { ev.preventDefault(); api.open_url(field.url).catch(() => {}); } },
          icon("link"),
          h("span", {}, T(field.labelKey)),
        );

      case "readonly":
        return h(
          "div",
          { class: "sm-field" },
          h("div", { class: "sm-hint" }, T(field.labelKey)),
          h("input", { class: "entry sm-entry", type: "text", readOnly: true, value: field.value }),
        );

      case "note":
        return h("div", { class: "sm-note" }, T(field.textKey));

      case "text": {
        const input = h("input", {
          class: "entry sm-entry",
          type: field.secret ? "password" : "text",
          value: current(field) || "",
          placeholder: field.placeholderKey ? T(field.placeholderKey) : "",
          spellcheck: false,
          autocomplete: "off",
        });
        controls.set(field.key, {
          get: () => input.value.trim(),
          setEnabled: (on) => { input.disabled = !on; },
        });
        return h("div", { class: "sm-field" }, h("div", { class: "sm-label" }, T(field.labelKey)), input);
      }

      case "toggle": {
        const input = h("input", { type: "checkbox", checked: !!current(field) });
        controls.set(field.key, { get: () => input.checked, input });
        return h(
          "div",
          { class: "sm-toggle" },
          h("div", { class: "sm-toggle-text" }, h("div", { class: "sm-label" }, T(field.labelKey)), h("div", { class: "sm-desc" }, T(field.descKey))),
          h("label", { class: "switch" }, input, h("span", { class: "switch-track" })),
        );
      }

      case "slider": {
        const value = h("span", { class: "sm-slider-value" }, String(current(field)));
        const input = h("input", { type: "range", min: field.min, max: field.max, step: 1, value: current(field), class: "sm-slider" });
        const ticks = [];
        for (let n = field.min; n <= field.max; n++) ticks.push(h("span", {}, String(n)));
        // The track is filled up to the thumb through --f (0..1); the active tick is highlighted.
        const sync = () => {
          const n = Number(input.value);
          input.style.setProperty("--f", String((n - field.min) / (field.max - field.min)));
          value.textContent = String(n);
          ticks.forEach((tick, i) => tick.classList.toggle("active", field.min + i === n));
        };
        input.addEventListener("input", sync);
        sync();
        controls.set(field.key, { get: () => Number(input.value) });
        return h(
          "div",
          { class: "sm-row" },
          field.labelKey ? h("span", { class: "sm-label" }, T(field.labelKey)) : null,
          h("div", { class: "slider-wrap" }, input, h("div", { class: "slider-ticks" }, ticks)),
          value,
        );
      }

      case "select": {
        const pairs = optionPairs(field.options);
        const labels = pairs.map(([, key]) => T(key));
        const idx = Math.max(0, pairs.findIndex(([v]) => v === current(field)));
        const dd = createDropdown({ values: labels, value: labels[idx], width: field.width });
        controls.set(field.key, { get: () => pairs[Math.max(0, labels.indexOf(dd.getValue()))][0] });
        return h("div", { class: "sm-row" }, field.labelKey ? h("span", { class: "sm-label" }, T(field.labelKey)) : null, dd.el);
      }

      case "file": {
        const input = h("input", { class: "entry sm-entry", type: "text", readOnly: true, value: current(field) || "", placeholder: T(field.placeholderKey) });
        controls.set(field.key, { get: () => input.value });
        const browse = async () => {
          try {
            const path = await api.pick_file("cookies");
            if (path) input.value = path;
          } catch (err) {
            alertModal(title, err.message, "error");
          }
        };
        return h(
          "div",
          { class: "sm-field" },
          h("div", { class: "sm-label" }, T(field.labelKey)),
          h("div", { class: "sm-desc" }, T(field.descKey)),
          h(
            "div",
            { class: "sm-file-row" },
            input,
            h("button", { class: "btn neutral", type: "button", onClick: browse }, T("browse")),
            h("button", { class: "btn neutral", type: "button", onClick: () => { input.value = ""; } }, T(field.clearKey)),
          ),
        );
      }

      default:
        return h("div", {}, `Unknown field type: ${field.type}`);
    }
  }

  function buildSection(section) {
    const card = h("div", { class: "sm-card" });
    if (section.inside) card.append(h("div", { class: "sm-card-title" }, T(section.titleKey)));
    for (const field of section.fields) card.append(buildField(field));
    return h("div", { class: "sm-section" }, section.inside ? null : h("div", { class: "sm-section-title" }, T(section.titleKey)), card);
  }

  const settingsPane = h("div", { class: "sm-scroll" }, schema.sections.map(buildSection));

  // enabledBy: a field is only editable while another toggle is on
  for (const section of schema.sections) {
    for (const field of section.fields) {
      if (!field.enabledBy) continue;
      const master = controls.get(field.enabledBy);
      const slave = controls.get(field.key);
      const sync = () => slave.setEnabled(master.get());
      master.input.addEventListener("change", sync);
      sync();
    }
  }

  // --------------------------------------------------------------- uninstall
  async function runUninstall(row) {
    if (!(await confirmModal(title, T(row.confirmKey)))) return;
    try {
      await api[row.action]();
    } catch (err) {
      await alertModal(title, err.message, "error");
      return;
    }
    if (row.doneKey) await alertModal(title, T(row.doneKey), "info");
    close();
  }

  const uninstallPane = h(
    "div",
    { class: "sm-scroll" },
    h("div", { class: "sm-danger-title" }, T("uninstall_section")),
    UNINSTALL_ROWS.map((row) =>
      h(
        "div",
        { class: `sm-uninstall${row.danger ? " danger" : ""}` },
        h("span", { class: "sm-uninstall-icon" }, icon(row.icon)),
        h("div", { class: "sm-uninstall-text" }, h("div", { class: "sm-label bold" }, T(row.titleKey)), h("div", { class: "sm-desc" }, T(row.descKey))),
        h("button", { class: `btn ${row.danger ? "danger" : "neutral"} small-wide`, type: "button", onClick: () => runUninstall(row) }, T(row.titleKey)),
      ),
    ),
  );

  // ------------------------------------------------------------------- shell
  async function save() {
    const partial = {};
    for (const [key, control] of controls) partial[key] = control.get();
    try {
      await api.save_settings(serviceId, partial);
    } catch (err) {
      await alertModal(title, err.message, "error");
      return;
    }
    app.set({ config: { ...app.get().config, ...partial } });
    close();
  }

  const tabSettings = h("button", { class: "seg-btn wide active", type: "button", onClick: () => selectTab("settings") }, T("tab_settings"));
  const tabUninstall = h("button", { class: "seg-btn wide", type: "button", onClick: () => selectTab("uninstall") }, T("tab_uninstall"));
  const actions = h(
    "div",
    { class: "sm-actions" },
    h("button", { class: "btn accent", type: "button", onClick: save }, T("save_btn")),
    h("button", { class: "btn neutral", type: "button", onClick: () => close() }, T("cancel_btn")),
  );

  function selectTab(name) {
    const isSettings = name === "settings";
    tabSettings.classList.toggle("active", isSettings);
    tabUninstall.classList.toggle("active", !isSettings);
    settingsPane.hidden = !isSettings;
    actions.hidden = !isSettings;
    uninstallPane.hidden = isSettings;
  }
  uninstallPane.hidden = true;

  const dialog = h(
    "div",
    { class: "settings-modal", role: "dialog", "aria-modal": "true", style: { height: `min(${schema.height}px, calc(100vh - 24px))` } },
    h(
      "div",
      { class: "sm-head" },
      h("span", { class: "sm-head-icon" }, icon("gear")),
      h("span", { class: "sm-head-title" }, title),
      h("span", { class: "tb-spacer" }),
      h("button", { class: "tb-btn danger", type: "button", "aria-label": T("tip_close"), title: T("tip_close"), onClick: () => close() }, icon("close")),
    ),
    h("div", { class: "sm-body" }, h("div", { class: "segmented sm-tabs" }, tabSettings, tabUninstall), settingsPane, uninstallPane, actions),
  );
  const overlay = h("div", { class: "modal-overlay", dataset: { service: serviceId } }, dialog);

  function onKey(ev) {
    if (ev.key !== "Escape") return;
    const overlays = document.querySelectorAll(".modal-overlay");
    if (overlays[overlays.length - 1] === overlay) close();
  }

  function close() {
    document.removeEventListener("keydown", onKey, true);
    overlay.remove();
  }

  document.addEventListener("keydown", onKey, true);
  document.body.append(overlay);
}
