import { h } from "../dom.js";
import { T } from "../i18n.js";
import { SERVICES, SERVICE_ORDER } from "../services.js";
import { createLauncherBar } from "../components/titlebar.js";

// Start screen: three cards, one per service (720x360, not resizable).
export function createLauncher({ appTitle, onChoose, onClose }) {
  const cards = SERVICE_ORDER.map((id) => {
    const svc = SERVICES[id];
    const l = svc.launcher;
    return h(
      "div",
      { class: "launcher-card", dataset: { service: id } },
      h("span", { class: `brand-icon brand-${id}`, style: { width: "44px", height: "44px" } }),
      h("div", { class: "lc-title" }, svc.title),
      h("div", { class: "lc-desc" }, T(l.descKey)),
      h(
        "button",
        {
          class: "btn lc-open",
          type: "button",
          style: { "--btn": l.btn, "--btn-hover": l.btnHover },
          onClick: () => onChoose(id),
        },
        T(l.openKey),
      ),
    );
  });

  const el = h(
    "div",
    { class: "view launcher-view" },
    createLauncherBar({ title: appTitle, onClose }),
    h(
      "div",
      { class: "launcher-body" },
      h("div", { class: "launcher-heading" }, T("choose_downloader")),
      h("div", { class: "launcher-cards" }, cards),
    ),
  );
  return { el };
}
