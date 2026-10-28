/* App state, header tabs, routing and keyboard. Loaded last. */
const DATA = (() => {
  try { return JSON.parse(document.getElementById("payload").textContent); }
  catch (e) { console.error("Dashboard data could not be read", e); return { ads: [] }; }
})();
const ADS = Array.isArray(DATA.ads) ? DATA.ads : [];
const PAGES = Array.isArray(DATA.pages) ? DATA.pages : [];
const AD_BY_ID = Object.fromEntries(ADS.map(a => [a.id, a]));

const VIEWS = [
  { id: "ads", n: 1, label: "Ads", on: () => ADS.length > 0 },
  { id: "winners", n: 2, label: "Winners", on: () => !!DATA.ranked },
  { id: "you", n: 3, label: "Your business", on: () => !!(DATA.proof && DATA.proof.length) },
  { id: "versus", n: 4, label: "Ours vs theirs", on: () => !!(DATA.drafts && DATA.drafts.length) },
  { id: "published", n: 5, label: "Published", on: () => !!DATA.published },
];

const state = { view: "ads", platform: "all", comp: "all", mode: "carousel", idx: 0, winPlatform: "all", panelId: null };

function compKey(ad) { return String(ad.domain || ad.advertiser || "unknown").toLowerCase().replace(/^www\./, ""); }

const COMPETITORS = (() => {
  const named = {};
  (DATA.competitors || []).forEach(c => { if (c && c.domain) named[String(c.domain).toLowerCase()] = c.name; });
  const groups = {};
  ADS.forEach(a => {
    const k = compKey(a);
    groups[k] = groups[k] || { key: k, count: 0, names: {} };
    groups[k].count++;
    if (a.advertiser) groups[k].names[a.advertiser] = (groups[k].names[a.advertiser] || 0) + 1;
  });
  return Object.values(groups).map(g => {
    const top = Object.entries(g.names).sort((a, b) => b[1] - a[1])[0];
    return { key: g.key, count: g.count, name: named[g.key] || (top ? top[0] : g.key) };
  }).sort((a, b) => b.count - a.count);
})();
const COMP_NAME = Object.fromEntries(COMPETITORS.map(c => [c.key, c.name]));

function platformOf(ad) {
  const p = String(ad.platform || "").toLowerCase();
  return (p === "facebook" || p === "instagram") ? "meta" : p;
}

/* Carousel order: ads with something to show first, winners first once ranked,
   and on "All" the platforms take turns so a few swipes show every platform. */
function hasContent(a) {
  const m = a.media || {};
  return !!(asList(a.headline).length || a.body || m.image || m.thumbnail || (Array.isArray(a.cards) && a.cards.length));
}
const ORDERED = ADS.map((a, i) => ({ a, i })).sort((x, y) =>
  (hasContent(y.a) - hasContent(x.a)) ||
  ((Number(y.a.score) || -1) - (Number(x.a.score) || -1)) ||
  (x.i - y.i)).map(x => x.a);

function filteredAds() {
  const list = ORDERED.filter(a => (state.platform === "all" || platformOf(a) === state.platform) && (state.comp === "all" || compKey(a) === state.comp));
  if (state.platform !== "all") return list;
  const groups = PLATFORM_ORDER.map(p => list.filter(a => platformOf(a) === p)).filter(g => g.length);
  const out = [];
  for (let i = 0; out.length < list.length; i++) groups.forEach(g => { if (g[i]) out.push(g[i]); });
  return out;
}

function pageFor(ad) {
  if (!ad) return null;
  const i = ad._page;
  return (typeof i === "number" && PAGES[i]) ? PAGES[i] : null;
}

function renderTop() {
  const tabs = VIEWS.filter(v => v.on());
  const comps = (DATA.competitors && DATA.competitors.length ? DATA.competitors.map(c => c.domain) : COMPETITORS.slice(0, 3).map(c => c.key));
  document.getElementById("top").innerHTML = `
    <div class="brand">
      <div class="mark">${ICON.mark}</div>
      <div><div class="brand-name">Competitor Ads</div><div class="brand-sub">${esc(comps.join("  ·  "))}</div></div>
    </div>
    <nav class="tabs">${tabs.map(v => `<button class="tab ${state.view === v.id ? "on" : ""}" data-view="${v.id}"><span class="tab-n">${v.n}</span>${esc(v.label)}</button>`).join("")}</nav>
    ${DATA.mode === "sample" ? `<div class="sample-pill" title="data/ads.json is missing, showing data/sample/">Sample data</div>` : ""}`;
}

function render() {
  CURRENT_FIT = null;
  renderTop();
  const app = document.getElementById("app");
  if (!ADS.length && !DATA.published) {
    app.innerHTML = `<section class="view empty"><h1>No ads yet.</h1><p>Run <code>/pull-ads</code> and this page fills itself.</p></section>`;
    return;
  }
  ({ ads: renderAdsView, winners: renderWinners, you: renderYou, versus: renderVersus, published: renderPublished }[state.view] || renderAdsView)();
}

function setView(v) {
  const ok = VIEWS.find(x => x.id === v && x.on());
  state.view = ok ? v : defaultView();
  if (location.hash.slice(1) !== state.view) history.replaceState(null, "", "#" + state.view);
  render();
}

function defaultView() {
  const on = VIEWS.filter(v => v.on());
  return on.length ? on[on.length - 1].id : "ads";
}

document.addEventListener("click", e => {
  const t = e.target.closest("[data-view]");
  if (t) { setView(t.dataset.view); return; }
  const open = e.target.closest("[data-open]");
  if (open && !e.target.closest(".stage")) { openPanel(open.dataset.open); return; }
  if (e.target.closest("[data-close]")) closePanel();
});

document.addEventListener("keydown", e => {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.key === "Escape") { closePanel(); return; }
  if (state.view !== "ads" || state.mode !== "carousel") return;
  if (e.key === "ArrowRight") { e.preventDefault(); carGo(state.idx + 1); }
  else if (e.key === "ArrowLeft") { e.preventDefault(); carGo(state.idx - 1); }
  else if (e.key === "Enter") { const ad = filteredAds()[state.idx]; if (ad) openPanel(ad.id); }
});

window.addEventListener("hashchange", () => { closePanel(); setView(location.hash.slice(1)); });

/* Images without a fixed size change an ad's height when they load: refit the current view. */
let CURRENT_FIT = null, fitTimer;
document.getElementById("app").addEventListener("load", e => {
  if (e.target.tagName !== "IMG" || !CURRENT_FIT) return;
  clearTimeout(fitTimer);
  fitTimer = setTimeout(() => CURRENT_FIT && CURRENT_FIT(), 90);
}, true);

let resizeTimer;
window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { if (state.view === "ads") carLayout(false); else render(); }, 120); });

setView(location.hash.slice(1) || defaultView());
if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => { if (state.view === "ads") carLayout(false); else render(); });
