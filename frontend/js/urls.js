// Split plain text into text and http(s) URL parts. Punctuation that ends a sentence
// ("... see https://x.y/z.") is not part of the URL.
const URL_RE = /(https?:\/\/[^\s]+)/g;
const TRAILING = /[.,;:!?)\]]+$/;

export function splitUrls(text) {
  const parts = [];
  String(text)
    .split(URL_RE)
    .forEach((piece, i) => {
      if (i % 2 === 0) {
        if (piece) parts.push({ type: "text", value: piece });
        return;
      }
      const url = piece.replace(TRAILING, "");
      parts.push({ type: "url", value: url });
      if (url.length < piece.length) parts.push({ type: "text", value: piece.slice(url.length) });
    });
  return parts;
}
