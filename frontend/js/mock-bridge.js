// Browser-only stand-in for the Python Api (used with ?mock=1).
// Mirrors the {ok, data} contract and emits the same events as services.py.

const LABELS = {
  QUEUED: "Queued",
  SEARCHING: "Searching\u2026",
  DOWNLOADING: "Downloading\u2026",
  CONVERTING: "Converting\u2026",
  EMBEDDING: "Embedding\u2026",
  DONE: "Done",
  ERROR: "Error",
};

const SAMPLE_NAMES = {
  spotify: ["Daft Punk - Get Lucky", "Queen - Bohemian Rhapsody", "Radiohead - Karma Police (Remastered edition with a very long title)"],
  youtube: ["Lo-fi beats to relax and study to", "Rick Astley - Never Gonna Give You Up", "A very long video title that needs to be cut off at some point because it is too long"],
  tiktok: ["cooluser - dance challenge #fyp", "chef - 60 second pasta", "cat - zoomies"],
};

let config = {};
let bootstrapData = null;
const tasks = { spotify: [], youtube: [], tiktok: [] };
let counter = 0;

const emit = (name, payload) => window.__bridge.emit(name, payload);
const ok = (data = null) => ({ ok: true, data });
const fail = (error, extra = {}) => ({ ok: false, error, ...extra });

function view(task) {
  const label =
    task.status === "ERROR" && task.error
      ? `Error: ${task.error.slice(0, 60)}${task.error.length > 60 ? "\u2026" : ""}`
      : LABELS[task.status];
  return { ...task, label };
}

function simulate(task, failing) {
  const steps = task.service === "spotify" ? ["SEARCHING", "DOWNLOADING", "CONVERTING", "EMBEDDING"] : ["DOWNLOADING", "CONVERTING"];
  let i = 0;
  const setStatus = (status) => {
    task.status = status;
    emit("task_status", view(task));
    emit("log", { service: task.service, msg: `${LABELS[status]}: ${task.name}` });
  };
  const tick = () => {
    if (i < steps.length) {
      setStatus(steps[i]);
      if (steps[i] === "DOWNLOADING") {
        let p = 0;
        const t = setInterval(() => {
          p = Math.min(1, p + 0.08 + Math.random() * 0.08);
          task.progress = p;
          emit("task_progress", { service: task.service, id: task.id, progress: p });
          if (p >= 1) {
            clearInterval(t);
            i++;
            setTimeout(tick, 250);
          }
        }, 120);
        return;
      }
      i++;
      setTimeout(tick, 500);
      return;
    }
    if (failing) {
      task.error = "HTTP Error 403: Forbidden (mock error to check how long messages are shortened)";
      task.progress = 0;
      task.status = "ERROR";
      emit("task_status", view(task));
      emit("log", { service: task.service, msg: `Error: ${task.name} - ${task.error}` });
    } else {
      task.progress = 1;
      task.status = "DONE";
      emit("task_status", view(task));
      emit("log", { service: task.service, msg: `Done:  ${task.name}` });
    }
  };
  setTimeout(tick, 400);
}

export const mockApi = {
  async bootstrap() {
    if (!bootstrapData) {
      const res = await fetch("mock/bootstrap.json");
      bootstrapData = await res.json();
      config = { ...bootstrapData.config };
    }
    return ok({ ...bootstrapData, config: { ...config }, tasks: Object.fromEntries(Object.entries(tasks).map(([k, v]) => [k, v.map(view)])) });
  },
  async save_config(partial) {
    config = { ...config, ...partial };
    return ok({ ...config });
  },
  async save_settings(service, partial) {
    config = { ...config, ...partial };
    setTimeout(() => emit("log", { service, msg: "(mock) settings applied" }), 100);
    return ok({ ...config });
  },
  async submit(service, url, outDir, fmt) {
    const strings = bootstrapData.strings;
    if (!(url || "").trim()) return fail(strings[`mb_no_url_${service}`], { title: strings.mb_no_url_title });
    if (!(outDir || "").trim()) return fail(strings.mb_no_outdir, { title: strings.mb_no_outdir_title });
    if (/fail/i.test(url)) {
      setTimeout(() => {
        emit("log", { service, msg: strings.err_resolving.replace("{}", "mock resolve failure") });
        emit("resolve_error", { service, message: "mock resolve failure", kind: "error" });
      }, 400);
      return ok();
    }
    setTimeout(() => {
      emit("log", { service, msg: "(mock) fetching info" });
      const names = SAMPLE_NAMES[service];
      emit("log", { service, msg: strings[service === "spotify" ? "queued_n_tracks" : "queued_n_videos"].replace("{}", names.length).replace("{}", fmt) });
      names.forEach((name, idx) => {
        const task = { id: `mock-${++counter}`, service, name: name.length > 60 ? name.slice(0, 57) + "\u2026" : name, status: "QUEUED", progress: 0, error: "" };
        tasks[service].push(task);
        emit("task_added", view(task));
        emit("log", { service, msg: strings.log_queued.replace("{}", name) });
        simulate(task, idx === 2 && /err/i.test(url));
      });
      emit("resolve_done", { service });
    }, 600);
    return ok();
  },
  async clear_done(service) {
    const removed = tasks[service].filter((t) => t.status === "DONE" || t.status === "ERROR").map((t) => t.id);
    tasks[service] = tasks[service].filter((t) => !removed.includes(t.id));
    return ok(removed);
  },
  async pick_folder(initial) {
    return ok(initial ? initial + "/picked" : "C:/Users/Demo/Music/Picked");
  },
  async pick_file() {
    return ok("C:/Users/Demo/cookies.txt");
  },
  async open_folder() { return ok(); },
  async open_url(url) { window.open(url, "_blank", "noopener"); return ok(); },
  async minimize() { return ok(); },
  async toggle_maximize() { return ok(); },
  async close() { return ok(); },
  async set_view() { return ok(); },
  async save_geometry() { return ok(); },
  async clear_data() { return ok(); },
  async uninstall_ffmpeg() { return ok(); },
  async uninstall_app() { return ok(); },
};
