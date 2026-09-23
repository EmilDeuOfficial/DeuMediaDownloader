// Small helpers for the CSS animations in css/motion.css.

/** Restart the animation behind `cls` on `el` (a class that is already set would not play again). */
export function replay(el, cls) {
  el.classList.remove(cls);
  void el.offsetWidth; // force a style flush so the animation starts over
  el.classList.add(cls);
}

/**
 * Play the "leaving" animation of `el`, then remove it. Resolves when it is gone.
 * Falls back to a timer when no animation runs (for example with "reduce motion").
 */
export function animateOut(el, cls = "leaving", fallbackMs = 450) {
  return new Promise((resolve) => {
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      el.remove();
      resolve();
    };
    el.addEventListener("animationend", (ev) => { if (ev.target === el) finish(); });
    el.classList.add(cls);
    setTimeout(finish, fallbackMs);
  });
}
