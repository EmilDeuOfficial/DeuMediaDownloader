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
let maximized = false;

const emit = (name, payload) => window.__bridge.emit(name, payload);
const ok = (data = null) => ({ ok: true, data });
const fail = (error, extra = {}) => ({ ok: false, error, ...extra });

// Same idea as errors.short_error() in Python: a few words for the queue, full text stays elsewhere.
function mockShortError(error) {
  const strings = (bootstrapData && bootstrapData.strings) || {};
  const http = /HTTP Error (\d{3})/i.exec(error);
  if (http) return (strings.err_short_http || "HTTP error {}").replace("{}", http[1]);
  return error.length > 45 ? error.slice(0, 45) + "\u2026" : error;
}

function statusText(status) {
  const strings = bootstrapData && bootstrapData.strings;
  return (strings && strings["status_" + status.toLowerCase()]) || LABELS[status] || status;
}

// File extension of a format name like "OGG Vorbis (192 kbps)" (the real one comes from Python).
function mockExt(fmt) {
  const base = String(fmt || "").split(" ")[0].toLowerCase();
  return base === "aac" ? "m4a" : base;
}

function view(task) {
  const label =
    task.status === "ERROR" && task.error
      ? `${statusText("ERROR")}: ${mockShortError(task.error)}`
      : statusText(task.status);
  const { stop, resume, step, ...plain } = task;
  return { ...plain, label };
}

// Fake download: SEARCHING/DOWNLOADING/CONVERTING/... with pause and cancel honoured
// between steps and while the progress bar moves (like the real worker).
function simulate(task, failing) {
  const steps = task.service === "spotify" ? ["SEARCHING", "DOWNLOADING", "CONVERTING", "EMBEDDING"] : ["DOWNLOADING", "CONVERTING"];
  task.step = 0;

  const setStatus = (status) => {
    task.status = status;
    emit("task_status", view(task));
    emit("log", { service: task.service, msg: `${statusText(status)}: ${task.name}` });
  };
  const halted = () => {
    if (task.stop === "cancel") {
      task.progress = 0;
      setStatus("CANCELLED");
      return true;
    }
    if (task.stop === "pause") {
      setStatus("PAUSED");
      return true;
    }
    return false;
  };
  const tick = () => {
    if (task.stop && halted()) return;
    if (task.step < steps.length) {
      const status = steps[task.step];
      setStatus(status);
      if (status === "DOWNLOADING") {
        let p = task.progress || 0;
        const timer = setInterval(() => {
          if (task.stop) {
            clearInterval(timer);
            halted();
            return;
          }
          p = Math.min(1, p + 0.03 + Math.random() * 0.03);
          task.progress = p;
          emit("task_progress", { service: task.service, id: task.id, progress: p });
          if (p >= 1) {
            clearInterval(timer);
            task.step++;
            setTimeout(tick, 250);
          }
        }, 120);
        return;
      }
      task.step++;
      setTimeout(tick, 900);
      return;
    }
    if (failing) {
      task.error = "HTTP Error 403: Forbidden (mock error to check how long messages are shortened)";
      task.progress = 0;
      task.status = "ERROR";
      emit("task_status", view(task));
      emit("log", { service: task.service, msg: `${statusText("ERROR")}: ${task.name} - ${task.error}` });
    } else {
      task.progress = 1;
      task.status = "DONE";
      emit("task_status", view(task));
      emit("log", { service: task.service, msg: `${statusText("DONE")}: ${task.name}` });
    }
  };
  task.resume = () => {
    task.stop = null;
    setStatus("QUEUED");
    setTimeout(tick, 300);
  };
  setTimeout(tick, 400);
}

const findTask = (service, id) => (tasks[service] || []).find((t) => t.id === id);

export const mockApi = {
  async bootstrap() {
    if (!bootstrapData) {
      const lang = new URLSearchParams(location.search).get("lang");
      const res = await fetch(lang === "de" ? "mock/bootstrap.de.json" : "mock/bootstrap.json");
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
        const task = { id: `mock-${++counter}`, service, name: name.length > 60 ? name.slice(0, 57) + "\u2026" : name, format: fmt, ext: mockExt(fmt), status: "QUEUED", progress: 0, error: "" };
        tasks[service].push(task);
        emit("task_added", view(task));
        emit("log", { service, msg: strings.log_queued.replace("{}", name) });
        simulate(task, idx === 2 && /err/i.test(url));
      });
      emit("resolve_done", { service });
    }, 600);
    return ok();
  },
  async pause_task(service, id) {
    const t = findTask(service, id);
    if (!t || !["QUEUED", "SEARCHING", "DOWNLOADING"].includes(t.status)) return ok(false);
    t.stop = "pause";
    if (t.status === "QUEUED") {
      t.status = "PAUSED";
      emit("task_status", view(t));
    }
    return ok(true);
  },
  async resume_task(service, id) {
    const t = findTask(service, id);
    if (!t || t.status !== "PAUSED") return ok(false);
    t.resume();
    return ok(true);
  },
  async cancel_task(service, id) {
    const t = findTask(service, id);
    if (!t || !["QUEUED", "SEARCHING", "DOWNLOADING", "PAUSED"].includes(t.status)) return ok(false);
    t.stop = "cancel";
    if (t.status === "QUEUED" || t.status === "PAUSED") {
      t.progress = 0;
      t.status = "CANCELLED";
      emit("task_status", view(t));
    }
    return ok(true);
  },
  async clear_done(service) {
    const removed = tasks[service].filter((t) => ["DONE", "ERROR", "CANCELLED"].includes(t.status)).map((t) => t.id);
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
  async toggle_maximize() { maximized = !maximized; return ok(maximized); },
  async close() { return ok(); },
  async set_view() { maximized = false; return ok(); },
  async save_geometry() { return ok(); },
  async clear_data() { return ok(); },
  async uninstall_ffmpeg() { return ok(); },
  async uninstall_app() { return ok(); },
};
