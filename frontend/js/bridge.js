// Connection to the Python side.
//   api.<method>(...args)  -> Promise of the "data" part; rejects with Error(message) on ok:false
//   on(eventName, handler) -> unsubscribe function; Python calls window.__bridge.emit(name, payload)
// With ?mock=1 the api is served by mock-bridge.js so the UI can run in a plain browser.

const listeners = new Map();
let buffering = true;
const buffered = [];

function dispatch(name, payload) {
  for (const fn of listeners.get(name) || []) {
    try {
      fn(payload);
    } catch (err) {
      console.error(`event handler for "${name}" failed`, err);
    }
  }
}

// Python may emit before the views exist (e.g. the Spotify init log right after
// bootstrap); those events are held back until startEvents() is called.
window.__bridge = {
  emit(name, payload) {
    if (buffering) buffered.push([name, payload]);
    else dispatch(name, payload);
  },
};

export function startEvents() {
  buffering = false;
  for (const [name, payload] of buffered.splice(0)) dispatch(name, payload);
}

export function on(name, handler) {
  if (!listeners.has(name)) listeners.set(name, new Set());
  listeners.get(name).add(handler);
  return () => listeners.get(name).delete(handler);
}

export const isMock = new URLSearchParams(location.search).has("mock");

let implPromise = null;

function loadImpl() {
  if (implPromise) return implPromise;
  if (isMock) {
    implPromise = import("./mock-bridge.js").then((m) => m.mockApi);
  } else if (window.pywebview && window.pywebview.api) {
    implPromise = Promise.resolve(window.pywebview.api);
  } else {
    implPromise = new Promise((resolve) => {
      window.addEventListener("pywebviewready", () => resolve(window.pywebview.api), { once: true });
    });
  }
  return implPromise;
}

export const api = new Proxy(
  {},
  {
    get: (_, method) => async (...args) => {
      const impl = await loadImpl();
      const res = await impl[method](...args);
      if (!res || res.ok !== true) {
        const err = new Error((res && res.error) || "Unknown error");
        err.title = res && res.title;
        err.kind = res && res.kind;
        throw err;
      }
      return res.data;
    },
  },
);
