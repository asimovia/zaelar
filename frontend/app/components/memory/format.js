// memory/format.js — numbers, sizes and dates in the instance language (V2-808, V2-814). No word lists: Intl does it.
import * as store from "../../core/store.js?v=2";
import { t } from "../../core/i18n.js?v=1";

const lang = () => store.lang() || "en";

export const num = (n) => new Intl.NumberFormat(lang()).format(Number(n) || 0);

export function bytes(b) {
  b = Number(b) || 0;
  const units = ["byte", "kilobyte", "megabyte", "gigabyte", "terabyte"];
  let i = 0;
  while (b >= 1024 && i < units.length - 1) { b /= 1024; i++; }
  return new Intl.NumberFormat(lang(), { style: "unit", unit: units[i], unitDisplay: "short",
                                         maximumFractionDigits: b < 10 && i > 1 ? 1 : 0 }).format(b);
}

export function ago(sec) {
  if (!sec) return "—";
  const d = Math.round(Number(sec) - Date.now() / 1000);
  const rtf = new Intl.RelativeTimeFormat(lang(), { numeric: "auto" });
  const a = Math.abs(d);
  if (a < 60) return t("memory.just_now");
  if (a < 3600) return rtf.format(Math.round(d / 60), "minute");
  if (a < 86400) return rtf.format(Math.round(d / 3600), "hour");
  if (a < 86400 * 30) return rtf.format(Math.round(d / 86400), "day");
  return date(sec);
}

export const date = (sec) => (sec ? new Intl.DateTimeFormat(lang(), { day: "numeric", month: "short" })
  .format(new Date(Number(sec) * 1000)) : "");

export const dateTime = (sec) => (sec ? new Intl.DateTimeFormat(lang(), {
  day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(Number(sec) * 1000)) : "");

// A translated label for a code, or "" when the bundle has none — a code is never painted at the operator.
export function label(prefix, code) {
  if (!code) return "";
  const key = `${prefix}${code}`;
  const s = t(key);
  return s === key ? "" : s;
}
