import { api, startEvents } from "./bridge.js";
import { setStrings } from "./i18n.js";
import { app } from "./state.js";
import { SERVICES, SERVICE_ORDER } from "./services.js";
import { createLauncher } from "./views/launcher.js";
import { createToolView } from "./views/tool-view.js";
import { installResizeHandles, setResizable } from "./components/resize-handles.js";
import { openSettings } from "./components/settings-modal.js";

// No browser context menu (Reload, Inspect, ...) except where copy/paste is useful.
document.addEventListener("contextmenu", (ev) => {
  if (!ev.target.closest("input, textarea, .log-box, .modal-body")) ev.preventDefault();
});

// This is an app window, not a web page: no reload or browser zoom by keyboard.
document.addEventListener(
  "keydown",
  (ev) => {
    const key = ev.key.toLowerCase();
    if (key === "f5" || (ev.ctrlKey && ["r", "+", "-", "=", "0"].includes(key))) ev.preventDefault();
  },
  true,
);

const root = document.getElementById("app");
const views = {};
let current = null;

async function navigate(name) {
  try {
    await api.set_view(name);
  } catch (err) {
    console.error("set_view failed", err);
  }
  current = name;
  for (const [id, view] of Object.entries(views)) view.el.hidden = id !== name;
  setResizable(name !== "launcher");
  // Api.set_view restores a maximized window, so no view may keep showing "restore".
  for (const view of Object.values(views)) view.setMaximized?.(false);
  views[name].refresh?.();
  views[name].focus?.();
}

async function boot() {
  const data = await api.bootstrap();
  setStrings(data.strings);
  app.set({
    appName: data.app_name,
    version: data.version,
    ffmpegOk: data.ffmpeg_ok,
    config: data.config,
    options: data.options,
  });

  views.launcher = createLauncher({
    appTitle: data.strings.launcher_title || data.app_name,
    onChoose: (id) => navigate(id),
    onMinimize: () => api.minimize().catch(() => {}),
    onClose: () => api.close().catch(() => {}),
  });

  for (const id of SERVICE_ORDER) {
    const view = createToolView(SERVICES[id], {
      onBack: () => navigate("launcher"),
      onSettings: openSettings,
    });
    view.restoreTasks(data.tasks && data.tasks[id]);
    views[id] = view;
  }

  for (const view of Object.values(views)) {
    view.el.hidden = true;
    root.append(view.el);
  }
  installResizeHandles();
  startEvents();
  await navigate("launcher");
}

boot().catch((err) => {
  console.error("boot failed", err);
  root.textContent = `Failed to start: ${err.message}`;
});
