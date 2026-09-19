import { createStore } from "./store.js";
import { api } from "./bridge.js";

// Shared, read-mostly application state filled from api.bootstrap().
export const app = createStore({
  appName: "DeuMediaDownloader",
  version: "",
  ffmpegOk: true,
  config: {},
  options: {},
});

// Update the local config copy right away and persist it in the background.
export function saveConfig(partial) {
  const { config } = app.get();
  app.set({ config: { ...config, ...partial } });
  api.save_config(partial).catch((err) => console.error("save_config failed", err));
}
