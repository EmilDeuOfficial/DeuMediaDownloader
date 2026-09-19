// Minimal observable state container.
export function createStore(initial = {}) {
  let state = { ...initial };
  const subscribers = new Set();
  return {
    get: () => state,
    set(patch) {
      state = { ...state, ...patch };
      for (const fn of subscribers) fn(state);
    },
    subscribe(fn) {
      subscribers.add(fn);
      return () => subscribers.delete(fn);
    },
  };
}
