import { h } from "../dom.js";
import { api } from "../bridge.js";

// The window is frameless, so it has no native resize border. Eight invisible handles
// drive api.resize_to(); Python clamps to the minimum size and keeps the opposite edge
// fixed (fix "E" = east edge stays, "S" = south edge stays).
export function installResizeHandles() {
  for (const edge of ["n", "s", "e", "w", "nw", "ne", "sw", "se"]) {
    const handle = h("div", { class: `rz ${edge}`, dataset: { edge } });
    document.body.append(handle);

    handle.addEventListener("pointerdown", async (ev) => {
      ev.preventDefault();
      handle.setPointerCapture(ev.pointerId);
      const startX = ev.screenX;
      const startY = ev.screenY;
      let rect;
      try {
        rect = await api.get_rect();
      } catch {
        return;
      }

      let pending = null;
      let busy = false;
      const flush = async () => {
        if (busy || !pending) return;
        busy = true;
        const args = pending;
        pending = null;
        try {
          await api.resize_to(...args);
        } catch (err) {
          console.error("resize failed", err);
        }
        busy = false;
        flush();
      };

      const onMove = (e) => {
        const dx = e.screenX - startX;
        const dy = e.screenY - startY;
        let w = rect.w;
        let hgt = rect.h;
        let fix = "";
        if (edge.includes("e")) w = rect.w + dx;
        if (edge.includes("w")) {
          w = rect.w - dx;
          fix += "E";
        }
        if (edge.includes("s")) hgt = rect.h + dy;
        if (edge.includes("n")) {
          hgt = rect.h - dy;
          fix += "S";
        }
        pending = [Math.round(w), Math.round(hgt), fix];
        flush();
      };
      const onUp = () => {
        handle.removeEventListener("pointermove", onMove);
        handle.removeEventListener("pointerup", onUp);
        handle.removeEventListener("pointercancel", onUp);
      };
      handle.addEventListener("pointermove", onMove);
      handle.addEventListener("pointerup", onUp);
      handle.addEventListener("pointercancel", onUp);
    });
  }
}

export function setResizable(enabled) {
  document.body.classList.toggle("no-resize", !enabled);
}
