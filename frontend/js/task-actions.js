// Which control buttons a queue item shows for a given task status.
//   null -> no buttons (finished task)
//   {toggle, cancel, disabled, cancelDisabled}
//     toggle is "pause", "resume" or null (a task that cannot be paused, like a recording);
//     `disabled` greys out the toggle while ffmpeg runs; `cancelDisabled` greys out cancel.
//     A conversion can be cancelled (it can take minutes), writing the tags cannot.
const INTERRUPTIBLE = new Set(["QUEUED", "SEARCHING", "DOWNLOADING", "RECORDING"]);

export function actionsFor(status, canPause = true) {
  const toggle = canPause ? "pause" : null;
  if (INTERRUPTIBLE.has(status)) return { toggle, cancel: true, disabled: false, cancelDisabled: false };
  if (status === "PAUSED") return { toggle: "resume", cancel: true, disabled: false, cancelDisabled: false };
  if (status === "CONVERTING") return { toggle, cancel: true, disabled: true, cancelDisabled: false };
  if (status === "EMBEDDING") return { toggle, cancel: true, disabled: true, cancelDisabled: true };
  return null;
}

// Statuses whose label shows the progress in percent.
const SHOWS_PERCENT = new Set(["DOWNLOADING", "CONVERTING", "RECORDING"]);

/** Status text of a queue item: the label, plus the progress while something runs. */
export function statusText(label, status, progress) {
  if (!SHOWS_PERCENT.has(status) || typeof progress !== "number") return label;
  const pct = Math.floor(Math.min(1, Math.max(0, progress)) * 100);
  return `${label} ${pct} %`;
}
