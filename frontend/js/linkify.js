import { h } from "./dom.js";
import { api } from "./bridge.js";
import { splitUrls } from "./urls.js";

// Plain text -> DOM nodes. http(s) URLs become links that the backend opens in the
// default browser; everything else is inserted as text (never as HTML).
export function linkify(text) {
  return splitUrls(text).map((part) => {
    if (part.type === "text") return part.value;
    return h(
      "a",
      {
        class: "ext-link",
        href: part.value,
        onClick: (ev) => {
          ev.preventDefault();
          api.open_url(part.value).catch(() => {});
        },
      },
      part.value,
    );
  });
}
