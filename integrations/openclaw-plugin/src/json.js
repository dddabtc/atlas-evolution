import crypto from "node:crypto";

export function utcNow() {
  return new Date().toISOString();
}

function sortValue(value) {
  if (Array.isArray(value)) {
    return value.map((item) => sortValue(item));
  }
  if (value && typeof value === "object") {
    return Object.keys(value)
      .sort()
      .reduce((result, key) => {
        result[key] = sortValue(value[key]);
        return result;
      }, {});
  }
  return value;
}

export function stableStringify(value) {
  return JSON.stringify(sortValue(value));
}

export function sha256Hex(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

export function stripUndefined(value) {
  if (Array.isArray(value)) {
    return value.map((item) => stripUndefined(item));
  }
  if (value && typeof value === "object") {
    return Object.entries(value).reduce((result, [key, entry]) => {
      if (entry !== undefined) {
        result[key] = stripUndefined(entry);
      }
      return result;
    }, {});
  }
  return value;
}

export function isPlainObject(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
