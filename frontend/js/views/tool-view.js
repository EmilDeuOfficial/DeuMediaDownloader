import { h, debounce } from "../dom.js";
import { api, on } from "../bridge.js";
import { T } from "../i18n.js";
import { app, saveConfig } from "../state.js";
import { AUDIO_DEFAULT, VIDEO_DEFAULT } from "../services.js";
import { createToolBar } from "../components/titlebar.js";
import { createDropdown } from "../components/dropdown.js";
import { createQueueItem } from "../components/queue-item.js";
import { createLogPanel } from "../components/log-panel.js";
import { alertModal } from "../components/modal.js";
import { icon } from "../icons.js";

const label = (text, cls = "") => h("span", { class: `field-label ${cls}`.trim() }, text);

// One generic downloader screen. `service` is a descriptor from services.js.
export function createToolView(service, { onBack, onSettings }) {
  const cfgKeys = service.cfg;
  const cfg = () => app.get().config;
  const options = () => app.get().options;

  // ---- state helpers ------------------------------------------------------
  const isAudio = (kind) => kind === "Audio";
  const formatList = (kind) => (isAudio(kind) ? options().audio_formats : options().video_formats);
  const formatKey = (kind) => (isAudio(kind) ? cfgKeys.formatAudio : cfgKeys.formatVideo);

  function savedFormat(kind) {
    if (!service.mediaToggle) {
      const value = cfg()[cfgKeys.format];
      return options().audio_formats.includes(value) ? value : AUDIO_DEFAULT;
    }
    const value = cfg()[formatKey(kind)];
    return formatList(kind).includes(value) ? value : isAudio(kind) ? AUDIO_DEFAULT : VIDEO_DEFAULT;
  }

  let mediaType = service.mediaToggle ? cfg()[cfgKeys.mediaType] || cfgKeys.mediaDefault : "Audio";
  if (mediaType !== "Audio" && mediaType !== "Video") mediaType = cfgKeys.mediaDefault || "Audio";

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
      await api.toggle_maximize();
      maximized = !maximized;
      bar.setMaximized(maximized);
    } catch (err) {
      console.error(err);
    }
  }

  // ---- URL panel ----------------------------------------------------------
  const urlInput = h("input", {
    class: "entry url-entry",
    type: "text",
    placeholder: T(service.urlPlaceholderKey),
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
    spellcheck: false,
  });
  outInput.addEventListener("input", () => persistOutDir(outInput.value));

  const formatDropdown = createDropdown({
    values: service.mediaToggle ? formatList(mediaType) : options().audio_formats,
    value: savedFormat(mediaType),
    width: service.dropdownWidth,
    onChange(value) {
      if (service.mediaToggle) saveConfig({ [formatKey(mediaType)]: value, [cfgKeys.mediaType]: mediaType });
      else saveConfig({ [cfgKeys.format]: value });
    },
  });

  const browseBtn = h("button", { class: "btn neutral browse", type: "button", onClick: browse }, T("browse"));
  const dlBtn = h("button", { class: "btn accent download", type: "button", onClick: start }, T("download").trim());

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

  let audioBtn = null;
  let videoBtn = null;
  let optionsPanel;
  if (service.mediaToggle) {
    audioBtn = h("button", { class: "seg-btn", type: "button", onClick: () => setMediaType("Audio") }, icon("note"), T("audio_btn"));
    videoBtn = h("button", { class: "seg-btn", type: "button", onClick: () => setMediaType("Video") }, icon("play"), T("video_btn"));
    optionsPanel = h(
      "section",
      { class: "panel options-panel media" },
      label(T("type"), "a-type"),
      h("div", { class: "segmented a-toggle" }, audioBtn, videoBtn),
      label(T("format"), "a-fmt"),
      h("div", { class: "a-dd" }, formatDropdown.el),
      dlBtn,
      label(T("save_to"), "a-out-label"),
      outInput,
      browseBtn,
    );
    paintMediaType();
  } else {
    optionsPanel = h(
      "section",
      { class: "panel options-panel single" },
      label(T("format")),
      h("div", { class: "a-dd" }, formatDropdown.el),
      label(T("save_to")),
      outInput,
      browseBtn,
      dlBtn,
    );
  }

  function paintMediaType() {
    audioBtn.classList.toggle("active", mediaType === "Audio");
    videoBtn.classList.toggle("active", mediaType === "Video");
  }

  function setMediaType(kind) {
    mediaType = kind;
    paintMediaType();
    formatDropdown.setValues(formatList(kind), savedFormat(kind));
    saveConfig({ [cfgKeys.mediaType]: kind });
  }

  // ---- queue panel --------------------------------------------------------
  const items = new Map();
  const queueList = h("div", { class: "queue-list" });
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
      h("button", { class: "btn neutral small", type: "button", style: { minWidth: "90px" }, onClick: clearDone }, T("clear_done")),
    ),
    queueList,
  );

  function updateCount() {
    const n = items.size;
    countLabel.textContent = n ? T(n === 1 ? "queue_count_one" : "queue_count_many", n) : "";
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
      await api.submit(service.id, urlInput.value, outInput.value, formatDropdown.getValue());
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
    if (!el.hidden) alertModal(p.kind === "api" ? T("mb_api_title") : T("mb_error_title"), p.message, "error");
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
    /** Called when the view becomes visible again: pick up config changed elsewhere (settings). */
    refresh() {
      outInput.value = cfg()[cfgKeys.outDir] || "";
    },
  };
}
