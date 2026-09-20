// Keep keyboard focus inside a dialog while it is open and give it back afterwards.
//   trapFocus(container, isTop) -> release()
// `isTop()` tells whether this dialog is the topmost one (dialogs can be stacked, only the
// top one reacts to Tab).
const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function trapFocus(container, isTop = () => true) {
  const previous = document.activeElement;

  const focusable = () => [...container.querySelectorAll(FOCUSABLE)].filter((el) => el.getClientRects().length > 0);

  function onKey(ev) {
    if (ev.key !== "Tab" || !isTop()) return;
    const list = focusable();
    if (!list.length) {
      ev.preventDefault();
      return;
    }
    const first = list[0];
    const last = list[list.length - 1];
    const active = document.activeElement;
    if (!container.contains(active) || (active === container && ev.shiftKey)) {
      ev.preventDefault();
      (ev.shiftKey ? last : first).focus();
    } else if (ev.shiftKey && active === first) {
      ev.preventDefault();
      last.focus();
    } else if (!ev.shiftKey && active === last) {
      ev.preventDefault();
      first.focus();
    }
  }

  document.addEventListener("keydown", onKey, true);
  return function release() {
    document.removeEventListener("keydown", onKey, true);
    if (previous && previous.isConnected && previous.focus) previous.focus();
  };
}
