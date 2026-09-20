import { h, debounce } from "../dom.js";
import { api, on } from "../bridge.js";
import { T } from "../i18n.js";
import { app, saveConfig } from "../state.js";
import { AUDIO_DEFAULT, VIDEO_DEFAULT } from "../services.js";
import { createToolBar } from "../components/titlebar.js";
import { createDropdown } from "../components/dropdown.js";
import { createQueueItem } from "../components/queue-item.js";
import { createLogPanel } from "../components/log-panel.js";
import { alertModal, showModal } from "../components/modal.js";
import { setResizable } from "../components/resize-handles.js";
import { icon } from "../icons.js";
import { initialSelection, resolveQuality, qualityText } from "../formats.js";

const label = (text, cls = "") => h("span", { class: `field-label ${cls}`.trim() }, text);

// One generic downloader screen. `service` is a descriptor from services.js.
export function createToolView(service, { onBack, onSettings }) {
  const cfgKeys = service.cfg;
  const cfg = () => app.get().config;
  const options = () => app.get().options;

  // ---- state helpers ------------------------------------------------------
  // The user picks a format and a quality; the downloaders and the config use the flat name
  // of that pair (for example "MP3 (320 kbps)"), which is what selection.quality.name is.
  const groupsFor = (kind) => (kind === "Audio" ? options().audio_groups : options().video_groups);
  const configKey = (kind) => (service.mediaToggle ? (kind === "Audio" ? cfgKeys.formatAudio : cfgKeys.formatVideo) : cfgKeys.format);
  const defaultName = (kind) => (kind === "Audio" ? AUDIO_DEFAULT : VIDEO_DEFAULT);

  let mediaType = service.mediaToggle ? cfg()[cfgKeys.mediaType] || cfgKeys.mediaDefault : "Audio";
  if (mediaType !== "Audio" && mediaType !== "Video") mediaType = cfgKeys.mediaDefault || "Audio";

  let selection = null;
  const loadSelection = (kind) => {
    selection = initialSelection(groupsFor(kind), cfg()[configKey(kind)], defaultName(kind));
  };
  loadSelection(mediaType);
  const currentName = () => selection.quality.name;
  const qualityTexts = () => selection.group.qualities.map((q) => qualityText(q, T));

  function persistSelection() {
    const patch = { [configKey(mediaType)]: currentName() };
    if (service.mediaToggle) patch[cfgKeys.mediaType] = mediaType;
    saveConfig(patch);
  }

  // ---- header -------------------------------------------------------------
  let maximized = false;
  const bar = createToolBar({
    title: app.get().appName,
    service: service.id,
    onBack,
    onSettings: () => onSettings(service.id),
    onMinimize: () => api.minimize().catch(() => {}),
    onMaximize: toggleMaximize,
    onClose: () => api.close().catch(() => {}),
  });

  async function toggleMaximize() {
    try {
      maximized = await api.toggle_maximize();   // the backend knows the real window state
      bar.setMaximized(maximized);
      setResizable(!maximized);
    } catch (err) {
      console.error(err);
    }
  }

  // ---- URL panel ----------------------------------------------------------
  const urlInput = h("input", {
    class: "entry url-entry",
    type: "text",
    placeholder: T(service.urlPlaceholderKey),
    "aria-label": T(service.urlLabelKey),
    spellcheck: false,
    autocomplete: "off",
  });
  urlInput.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") start();
  });
  const inputPanel = h(
    "section",
    { class: "panel input-panel" },
    h("div", { class: "input-label" }, T(service.urlLabelKey)),
    h(
      "div",
      { class: "input-row" },
      urlInput,
      h("button", { class: "btn neutral", type: "button", style: { minWidth: "72px" }, onClick: paste }, T("paste")),
      h("button", { class: "btn neutral", type: "button", style: { minWidth: "66px" }, onClick: () => { urlInput.value = ""; urlInput.focus(); } }, T("clear")),
    ),
  );

  async function paste() {
    try {
      const text = await api.paste();
      if (text) urlInput.value = text;
    } catch (err) {
      console.error(err);
    }
  }

  // ---- options panel ------------------------------------------------------
  const persistOutDir = debounce((value) => saveConfig({ [cfgKeys.outDir]: value }), 300);
  const outInput = h("input", {
    class: "entry out-entry",
    type: "text",
    value: cfg()[cfgKeys.outDir] || "",
    "aria-label": T("save_to"),
    spellcheck: false,
  });
  outInput.addEventListener("input", () => persistOutDir(outInput.value));

  const formatDropdown = createDropdown({
    values: groupsFor(mediaType).map((g) => g.format),
    value: selection.group.format,
    width: "100%",
    onChange(format) {
      const group = groupsFor(mediaType).find((g) => g.format === format);
      selection = { group, quality: resolveQuality(group, selection.quality.label) };
      syncQuality();
      persistSelection();
    },
  });

  const qualityDropdown = createDropdown({
    values: qualityTexts(),
    value: qualityText(selection.quality, T),
    width: "100%",
    onChange(text) {
      const quality = selection.group.qualities.find((q) => qualityText(q, T) === text);
      if (quality) selection = { group: selection.group, quality };
      persistSelection();
    },
  });

  // Quality list follows the format; a format with one quality (Lossless) cannot be changed.
  function syncQuality() {
    qualityDropdown.setValues(qualityTexts(), qualityText(selection.quality, T));
    qualityDropdown.setDisabled(selection.group.qualities.length < 2);
  }
  syncQuality();

  const browseBtn = h("button", { class: "btn neutral browse", type: "button", onClick: browse }, T("browse"));
  const dlBtn = h("button", { class: "btn accent download", type: "button", onClick: start }, T("download").trim());
  const actions = h("div", { class: "a-actions" }, browseBtn, dlBtn);
  const outWrap = h("div", { class: "a-out" }, outInput);

  async function browse() {
    try {
      const dir = await api.pick_folder(outInput.value);
      if (dir) {
        outInput.value = dir;
        saveConfig({ [cfgKeys.outDir]: dir });
      }
    } catch (err) {
      console.error(err);
    }
  }

  const formatCell = h("div", { class: "a-dd" }, formatDropdown.el);
  const qualityCell = h("div", { class: "a-dd" }, qualityDropdown.el);

  let audioBtn = null;
  let videoBtn = null;
  let optionsPanel;
  if (service.mediaToggle) {
    audioBtn = h("button", { class: "seg-btn", type: "button", onClick: () => setMediaType("Audio") }, icon("note"), T("audio_btn"));
    videoBtn = h("button", { class: "seg-btn", type: "button", onClick: () => setMediaType("Video") }, icon("play"), T("video_btn"));
    optionsPanel = h(
      "section",
      { class: "panel options-panel" },
      label(T("type")),
      h(
        "div",
        { class: "opt-selectors" },
        h("div", { class: "segmented" }, audioBtn, videoBtn),
        label(T("format")),
        formatCell,
        label(T("quality")),
        qualityCell,
      ),
      label(T("save_to")),
      h("div", { class: "opt-path" }, outWrap, actions),
    );
    paintMediaType();
  } else {
    optionsPanel = h(
      "section",
      { class: "panel options-panel" },
      label(T("format")),
      h("div", { class: "opt-selectors" }, formatCell, label(T("quality")), qualityCell),
      label(T("save_to")),
      h("div", { class: "opt-path" }, outWrap, actions),
    );
  }

  function paintMediaType() {
    audioBtn.classList.toggle("active", mediaType === "Audio");
    videoBtn.classList.toggle("active", mediaType === "Video");
  }

  function setMediaType(kind) {
    mediaType = kind;
    paintMediaType();
    loadSelection(kind);
    formatDropdown.setValues(groupsFor(kind).map((g) => g.format), selection.group.format);
    syncQuality();
    saveConfig({ [cfgKeys.mediaType]: kind });
  }

  // ---- queue panel --------------------------------------------------------
  const items = new Map();
  const queueEmpty = h("div", { class: "queue-empty" }, T("queue_empty"));
  const queueList = h("div", { class: "queue-list" }, queueEmpty);
  const countLabel = h("span", { class: "queue-count" });
  const queuePanel = h(
    "section",
    { class: "panel queue-panel" },
    h(
      "div",
      { class: "panel-head" },
      h("span", { class: "panel-title" }, T("download_queue")),
      countLabel,
      h("span", { class: "tb-spacer" }),
      h("button", { class: "btn neutral small", type: "button", style: { minWidth: "90px" }, title: T("tip_clear_done"), onClick: clearDone }, T("clear_done")),
    ),
    queueList,
  );

  function updateCount() {
    const n = items.size;
    countLabel.textContent = n ? T(n === 1 ? "queue_count_one" : "queue_count_many", n) : "";
    queueEmpty.hidden = n > 0;
  }

  function addTask(task) {
    if (items.has(task.id)) return;
    const item = createQueueItem(task, service.queueGlyph, {
      onPause: (id) => control(api.pause_task, id),
      onResume: (id) => control(api.resume_task, id),
      onCancel: (id) => control(api.cancel_task, id),
    });
    items.set(task.id, item);
    queueList.append(item.el);
    updateCount();
  }

  async function control(method, taskId) {
    try {
      await method(service.id, taskId);
    } catch (err) {
      console.error(err);
    }
  }

  async function clearDone() {
    try {
      const removed = await api.clear_done(service.id);
      for (const id of removed) {
        items.get(id)?.el.remove();
        items.delete(id);
      }
      updateCount();
    } catch (err) {
      console.error(err);
    }
  }

  // ---- log panel ----------------------------------------------------------
  const log = createLogPanel();

  // ---- download flow ------------------------------------------------------
  function setBusy(busy) {
    dlBtn.disabled = busy;
    dlBtn.textContent = (busy ? T("loading") : T("download")).trim();
  }

  async function start() {
    if (dlBtn.disabled) return;
    setBusy(true);
    try {
      await api.submit(service.id, urlInput.value, outInput.value, currentName());
      urlInput.value = "";
    } catch (err) {
      setBusy(false);
      await alertModal(err.title || T("mb_error_title"), err.message, "warning");
    }
  }

  // ---- events (filtered to this service) ----------------------------------
  const mine = (fn) => (payload) => {
    if (payload && payload.service === service.id) fn(payload);
  };
  on("log", mine((p) => log.append(p.msg)));
  on("task_added", mine(addTask));
  on("task_status", mine((task) => items.get(task.id)?.update(task)));
  on("task_progress", mine((p) => items.get(p.id)?.update({ progress: p.progress })));
  on("resolve_done", mine(() => setBusy(false)));
  on("resolve_error", mine((p) => {
    setBusy(false);
    if (el.hidden) return;
    if (p.kind === "api") {
      // Missing Spotify credentials: offer to open the settings right away.
      showModal({
        title: T("mb_api_title"),
        message: p.message,
        kind: "error",
        cancelValue: false,
        buttons: [
          { label: T("btn_ok"), value: false, kind: "neutral" },
          { label: T("tip_settings"), value: true, kind: "accent" },
        ],
      }).then((openSettings) => openSettings && onSettings(service.id));
    } else {
      alertModal(T("mb_error_title"), p.message, "error");
    }
  }));

  // ---- assemble -----------------------------------------------------------
  const el = h(
    "div",
    { class: "view tool-view", dataset: { service: service.id } },
    bar.el,
    h("div", { class: "tool-body" }, inputPanel, optionsPanel, queuePanel, log.el),
  );

  return {
    el,
    restoreTasks(tasks) {
      for (const task of tasks || []) addTask(task);
    },
    setMaximized(value) {
      maximized = value;
      bar.setMaximized(value);
    },
    focus() {
      urlInput.focus();
    },
    /** Called when the view becomes visible again: pick up config changed elsewhere (settings). */
    refresh() {
      outInput.value = cfg()[cfgKeys.outDir] || "";
    },
  };
}
