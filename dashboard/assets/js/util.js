/* Shared helpers. Every piece of ad data is untrusted: escape it, check every URL. */
const BLOCKED_HOSTS = ["facebook.com", "fb.me", "fb.com", "instagram.com"];

function esc(v) {
  if (v === null || v === undefined) return "";
  return String(v).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function hostOf(u) {
  try { return new URL(u).hostname.replace(/^www\./, ""); } catch (e) { return ""; }
}

/* Image sources: http(s) or a relative path. Never javascript:, data: or file:. */
function safeSrc(u) {
  if (!u || typeof u !== "string") return null;
  const s = u.trim();
  if (/^https?:\/\//i.test(s)) return s;
  if (/^[a-z][a-z0-9+.-]*:/i.test(s)) return null;
  return s;
}

/* Clickable links: http(s) only, and never a Meta page. */
function safeHref(u) {
  if (!u || typeof u !== "string" || !/^https?:\/\//i.test(u.trim())) return null;
  const h = hostOf(u);
  if (BLOCKED_HOSTS.some(b => h === b || h.endsWith("." + b))) return null;
  return u.trim();
}

function img(src, cls, alt) {
  const u = safeSrc(src);
  if (!u) return "";
  return `<img class="${cls || ""}" src="${esc(u)}" alt="${esc(alt || "")}" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="this.classList.add('broken')">`;
}

function hue(str) {
  let h = 0;
  for (const c of String(str || "x")) h = (h * 31 + c.charCodeAt(0)) % 360;
  return h;
}

function initials(name) {
  const w = String(name || "?").replace(/[^A-Za-z0-9 ]/g, " ").trim().split(/\s+/);
  return ((w[0] || "?")[0] + (w[1] ? w[1][0] : "")).toUpperCase();
}

function avatar(name, src, cls) {
  const h = hue(name);
  return `<div class="${cls || "av"}" style="background:hsl(${h},55%,42%)">${esc(initials(name))}${img(src, "", "")}</div>`;
}

function fmtNum(n) {
  if (n === null || n === undefined || n === "" || isNaN(Number(n))) return null;
  const v = Number(n);
  if (Math.abs(v) >= 1e6) return (v / 1e6).toFixed(v >= 1e7 ? 0 : 1).replace(/\.0$/, "") + "M";
  if (Math.abs(v) >= 1e4) return (v / 1e3).toFixed(v >= 1e5 ? 0 : 1).replace(/\.0$/, "") + "K";
  return Math.round(v).toLocaleString("en-US");
}

function fmtInt(n) {
  if (n === null || n === undefined || isNaN(Number(n))) return null;
  return Math.round(Number(n)).toLocaleString("en-US");
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function fmtDate(iso) {
  if (!iso) return null;
  const m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return null;
  return `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}`;
}

function asList(v) {
  if (Array.isArray(v)) return v.filter(x => x !== null && x !== undefined && String(x).trim() !== "").map(String);
  if (v === null || v === undefined || String(v).trim() === "") return [];
  return [String(v)];
}

function joinText(v, sep) { return asList(v).join(sep); }

function stripMd(s) { return String(s || "").replace(/\*\*|__|`/g, "").replace(/\[([^\]]+)\]\([^)]+\)/g, "$1").trim(); }

const PLATFORMS = {
  google: { label: "Google", plural: "Google ads" },
  meta: { label: "Facebook & Instagram", plural: "Facebook & Instagram ads" },
  tiktok: { label: "TikTok", plural: "TikTok ads" },
  linkedin: { label: "LinkedIn", plural: "LinkedIn ads" },
};
const PLATFORM_ORDER = ["google", "meta", "tiktok", "linkedin"];
const GRADE_TEXT = { A: "delivery data", B: "rank only", C: "dates only" };

/* SpyFu share arrives as a fraction (0.31) or a percent (31): show "31%". */
function fmtShare(v) {
  if (v === null || v === undefined || v === "" || isNaN(Number(v))) return null;
  const n = Number(v) <= 1 ? Number(v) * 100 : Number(v);
  return `${n >= 10 ? Math.round(n) : n.toFixed(1).replace(/\.0$/, "")}%`;
}
