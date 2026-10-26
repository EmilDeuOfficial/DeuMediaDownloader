import { h } from "../dom.js";
import { api, on } from "../bridge.js";
import { T } from "../i18n.js";
import { app } from "../state.js";
import { icon } from "../icons.js";
import { updates } from "../updates.js";
import { parseNotes, formatSize } from "../update-state.js";
import { trapFocus } from "../focus-trap.js";
import { animateOut } from "../motion.js";

// Update dialog: release notes of the new version and a button that downloads the setup and
// installs it. One dialog at a time; opening it again while it is open does nothing.
let openDialog = false;

function notesBox(notes) {
  const blocks = parseNotes(notes);
  if (!blocks.length) return h("div", { class: "upd-notes upd-empty" }, T("upd_no_notes"));
  return h(
    "div",
    { class: "upd-notes", tabIndex: 0 },
    blocks.map((block) =>
      h(
        "div",
        { class: `upd-${block.type}` },
        block.segments.map((seg) => (seg.bold ? h("strong", {}, seg.text) : seg.text)),
      ),
    ),
  );
}

export function openUpdate() {
  if (openDialog) return;
  openDialog = true;

  // step: what the dialog is doing right now
  //   "idle" (shows the check result) | "download" | "start" | "error"
  let step = "idle";
  let busy = false; // the download is running: the dialog cannot be closed
  let cancelling = false;
  let failedStep = "check"; // which action the "Try again" button repeats
  let errorText = "";
  let progress = 0;
  let stopProgress = () => {};

  const head = h("div", { class: "modal-head info" });
  const body = h("div", { class: "modal-body upd-body" });
  const actions = h("div", { class: "modal-actions" });
  const closeBtn = h("button", { class: "tb-btn danger", type: "button", "aria-label": T("tip_close"), title: T("tip_close"), onClick: () => close() }, icon("close"));
  const dialog = h("div", { class: "modal update-modal", role: "dialog", "aria-modal": "true" }, head, body, actions);
  // The accent colour follows the downloader that is open (the launcher uses the default).
  const service = document.querySelector(".tool-view:not([hidden])")?.dataset.service;
  const overlay = h("div", { class: "modal-overlay", dataset: service ? { service } : {} }, dialog);

  const button = (label, kind, onClick) => h("button", { class: `btn ${kind}`, type: "button", onClick }, label);

  function setHead(titleKey, kind = "info") {
    head.className = `modal-head ${kind}`;
    head.replaceChildren(
      icon(kind === "error" ? "warning" : "download"),
      h("span", {}, T(titleKey)),
      h("span", { class: "tb-spacer" }),
      ...(busy ? [] : [closeBtn]),
    );
  }

  const progressBar = h("div", { class: "upd-bar-fill" });
  const percent = h("span", { class: "upd-percent" }, "0%");
  function paintProgress() {
    const value = `${Math.round(progress * 100)}%`;
    progressBar.style.width = value;
    percent.textContent = value;
  }

  function paint() {
    const { phase, info, error } = updates.store.get();
    dialog.dataset.step = step;
    actions.replaceChildren();

    if (step === "download" || step === "start") {
      setHead("upd_head_available");
      body.replaceChildren(
        h("div", { class: "upd-status" }, step === "start" ? T("upd_starting") : T("upd_downloading"), step === "download" ? percent : null),
        h("div", { class: "upd-bar" }, progressBar),
      );
      paintProgress();
      if (step === "download") actions.append(button(T("cancel_btn"), "neutral", cancelDownload));
      return;
    }

    if (step === "error" || phase === "error") {
      setHead("upd_head_error", "error");
      body.replaceChildren(h("div", {}, step === "error" ? errorText : error));
      actions.append(button(T("upd_btn_retry"), "accent", retry), button(T("btn_ok"), "neutral", () => close()));
      return;
    }

    if (phase === "idle" || phase === "checking") {
      setHead("upd_head_checking");
      body.replaceChildren(
        h("div", { class: "upd-status" }, T("upd_head_checking")),
        h("div", { class: "upd-bar indeterminate" }, h("div", { class: "upd-bar-fill" })),
      );
      return;
    }

    if (phase === "available") {
      setHead("upd_head_available");
      const size = formatSize(info.size, app.get().lang);
      body.replaceChildren(
        h("div", { class: "upd-line" }, T("upd_available_line", info.version, info.current)),
        h("div", { class: "upd-sub" }, T("upd_notes_title")),
        notesBox(info.notes),
        size ? h("div", { class: "upd-size" }, T("upd_size", size)) : null,
      );
      actions.append(
        button(T("upd_btn_release"), "neutral", () => api.open_url(info.page).catch(() => {})),
        h("span", { class: "tb-spacer" }),
        button(T("upd_btn_install"), "accent", install),
      );
      return;
    }

    // phase === "current"
    setHead("upd_head_current");
    body.replaceChildren(h("div", { class: "upd-line" }, T("upd_current_line", info.current)));
    actions.append(button(T("upd_btn_check"), "neutral", recheck), button(T("btn_ok"), "accent", () => close()));
  }

  function recheck() {
    step = "idle";
    failedStep = "check";
    updates.check();
  }

  function retry() {
    errorText = "";
    if (failedStep === "install") install();
    else recheck();
  }

  async function install() {
    failedStep = "install";
    step = "download";
    busy = true;
    cancelling = false;
    progress = 0;
    paint();
    stopProgress = on("update_progress", ({ progress: value }) => {
      progress = value;
      if (value >= 1 && step === "download") {
        // The file is verified; what follows is the Windows prompt for the setup.
        step = "start";
        paint();
      } else if (step === "download") {
        paintProgress();
      }
    });
    try {
      await api.install_app_update();
      // The setup is running and the app is about to close (not reached in the real app).
      step = "start";
    } catch (err) {
      if (cancelling) {
        step = "idle";
      } else {
        step = "error";
        errorText = err.message;
      }
    } finally {
      stopProgress();
      busy = false;
      paint();
    }
  }

  function cancelDownload() {
    cancelling = true;
    api.cancel_app_update().catch(() => {});
  }

  function onKey(ev) {
    if (ev.key !== "Escape") return;
    const all = document.querySelectorAll(".modal-overlay:not(.leaving)");
    if (all[all.length - 1] !== overlay) return;
    ev.stopPropagation();
    close();
  }

  let releaseFocus = () => {};
  function close() {
    if (busy) return;
    openDialog = false;
    unsubscribe();
    stopProgress();
    document.removeEventListener("keydown", onKey, true);
    releaseFocus();
    animateOut(overlay);
  }

  // The result of a check that is still running arrives while the dialog is open.
  const unsubscribe = updates.store.subscribe(() => {
    if (step === "idle" || step === "error") paint();
  });

  document.addEventListener("keydown", onKey, true);
  document.body.append(overlay);
  releaseFocus = trapFocus(overlay, () => {
    const all = document.querySelectorAll(".modal-overlay:not(.leaving)");
    return all[all.length - 1] === overlay;
  });

  // The check at app start already knows an update: show it. Otherwise look now.
  if (updates.store.get().phase !== "available") updates.check();
  paint();
  dialog.tabIndex = -1;
  dialog.focus();
}
