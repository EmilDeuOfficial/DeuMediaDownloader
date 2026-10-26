import { api } from "./bridge.js";
import { createUpdates } from "./update-state.js";

// The one update state of the running app (see update-state.js).
export const updates = createUpdates(api);
