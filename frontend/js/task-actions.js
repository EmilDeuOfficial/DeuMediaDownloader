// Which control buttons a queue item shows for a given task status.
//   null                         -> no buttons (finished task)
//   {toggle, cancel, disabled}   -> toggle is "pause", "resume" or null (a task that cannot be
//                                   paused, like a recording); `disabled` while ffmpeg runs
const INTERRUPTIBLE = new Set(["QUEUED", "SEARCHING", "DOWNLOADING", "RECORDING"]);
const BUSY = new Set(["CONVERTING", "EMBEDDING"]);

export function actionsFor(status, canPause = true) {
  const toggle = canPause ? "pause" : null;
  if (INTERRUPTIBLE.has(status)) return { toggle, cancel: true, disabled: false };
  if (status === "PAUSED") return { toggle: "resume", cancel: true, disabled: false };
  if (BUSY.has(status)) return { toggle, cancel: true, disabled: true };
  return null;
}
