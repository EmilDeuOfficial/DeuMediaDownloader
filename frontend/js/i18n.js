// String table comes from Python (bootstrap). "{}" placeholders are filled in order,
// matching str.format on the Python side. Unknown keys return the key itself.
let strings = {};

export function setStrings(dict) {
  strings = dict || {};
}

export function T(key, ...args) {
  let text = Object.prototype.hasOwnProperty.call(strings, key) ? strings[key] : key;
  if (args.length) {
    let i = 0;
    text = text.replace(/\{\}/g, () => (i < args.length ? String(args[i++]) : "{}"));
  }
  return text;
}
