import { h } from "../dom.js";
import { icon } from "../icons.js";
import { T } from "../i18n.js";
import { SERVICES } from "../services.js";

let current = null;

/** Close the notice that is showing, if any. */
export function hideLinkBanner() {
  if (!current) return;
  current.remove();
  current = null;
}

/**
 * Small notice at the bottom of the window: "<site> link found in the clipboard" with a button
 * that takes the link. Only one is shown; a newer one replaces it.
 */
export function showLinkBanner({ url, service, onUse }) {
  hideLinkBanner();
  const title = SERVICES[service]?.title || service;
  const banner = h(
    "div",
    { class: "link-banner", role: "status", dataset: { service } },
    h("span", { class: `brand-icon brand-${service}`, style: { width: "20px", height: "20px" } }),
    h("div", { class: "lb-text" }, h("div", { class: "lb-title" }, T("link_found_clip", title)), h("div", { class: "lb-url", title: url }, url)),
    h(
      "button",
      {
        class: "btn accent small",
        type: "button",
        onClick: () => {
          hideLinkBanner();
          onUse();
        },
      },
      T("link_use"),
    ),
    h("button", { class: "tb-btn lb-close", type: "button", title: T("link_dismiss"), "aria-label": T("link_dismiss"), onClick: hideLinkBanner }, icon("close")),
  );
  current = banner;
  document.body.append(banner);
}
