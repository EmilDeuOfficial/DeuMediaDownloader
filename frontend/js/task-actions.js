// Which control buttons a queue item shows for a given task status.
//   null                         -> no buttons (finished task)
//   {toggle, cancel, disabled}   -> toggle is "pause" or "resume"; `disabled` while ffmpeg runs
const INTERRUPTIBLE = new Set(["QUEUED", "SEARCHING", "DOWNLOADING"]);
const BUSY = new Set(["CONVERTING", "EMBEDDING"]);

export function actionsFor(status) {
  if (INTERRUPTIBLE.has(status)) return { toggle: "pause", cancel: true, disabled: false };
  if (status === "PAUSED") return { toggle: "resume", cancel: true, disabled: false };
  if (BUSY.has(status)) return { toggle: "pause", cancel: true, disabled: true };
  return null;
}
