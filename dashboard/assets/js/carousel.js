/* Ads view: count, filters, the swipeable carousel and the wall. */

function countTitle(list) {
  const n = list.length;
  const what = state.platform === "all" ? (n === 1 ? "ad" : "ads") : (n === 1 ? PLATFORMS[state.platform].plural.replace(/ads$/, "ad") : PLATFORMS[state.platform].plural);
  return `<span class="hl">${n}</span> ${esc(what)}`;
}

function countSub(list) {
  if (state.comp !== "all") return `from ${esc(COMP_NAME[state.comp] || state.comp)}`;
  const comps = new Set(list.map(compKey)).size;
  const plats = new Set(list.map(platformOf)).size;
  return `from ${comps} competitor${comps === 1 ? "" : "s"}${state.platform === "all" ? ` across ${plats} platform${plats === 1 ? "" : "s"}` : ""}`;
}

function platformChips() {
  const byComp = ADS.filter(a => state.comp === "all" || compKey(a) === state.comp);
  const counts = {};
  byComp.forEach(a => { const p = platformOf(a); counts[p] = (counts[p] || 0) + 1; });
  const chips = [`<button class="chip ${state.platform === "all" ? "on" : ""}" data-plat="all">All <span class="n">${byComp.length}</span></button>`];
  PLATFORM_ORDER.filter(p => counts[p]).forEach(p => {
    chips.push(`<button class="chip ${state.platform === p ? "on" : ""}" data-plat="${p}">${ICON[p]}${esc(PLATFORMS[p].label)} <span class="n">${counts[p]}</span></button>`);
  });
  return chips.join("");
}

function compChips() {
  const byPlat = ADS.filter(a => state.platform === "all" || platformOf(a) === state.platform);
  const counts = {};
  byPlat.forEach(a => { const k = compKey(a); counts[k] = (counts[k] || 0) + 1; });
  const shown = COMPETITORS.filter(c => counts[c.key]).slice(0, 12);
  return [`<button class="chip ${state.comp === "all" ? "on" : ""}" data-comp="all">All</button>`]
    .concat(shown.map(c => `<button class="chip ${state.comp === c.key ? "on" : ""}" data-comp="${esc(c.key)}">${esc(c.name)} <span class="n">${counts[c.key]}</span></button>`))
    .join("");
}

function slideMeta(ad) {
  const bits = [`<b>${esc(ad.advertiser || COMP_NAME[compKey(ad)] || "")}</b>`];
  if (ad.days_running !== null && ad.days_running !== undefined) bits.push(`<span class="muted">Running ${fmtInt(ad.days_running)} day${ad.days_running === 1 ? "" : "s"}</span>`);
  else if (ad.start_date) bits.push(`<span class="muted">Since ${esc(fmtDate(ad.start_date))}</span>`);
  if (ad.score !== null && ad.score !== undefined) bits.push(`<span class="muted">Score ${esc(ad.score)}</span>`);
  return bits.join('<i class="dot"></i>') + `<button class="btn" data-open="${esc(ad.id)}">Landing page ${ICON.arrowR}</button>`;
}

function renderAdsView() {
  const list = filteredAds();
  if (state.idx >= list.length) state.idx = Math.max(0, list.length - 1);
  const body = !list.length
    ? `<div class="empty"><h1>Nothing here.</h1><p>No ads match these filters.</p></div>`
    : state.mode === "wall" ? wallHtml(list) : stageHtml(list);
  document.getElementById("app").innerHTML = `
    <section class="view view-ads">
      <div class="toolbar">
        <div class="count"><h1>${countTitle(list)}</h1><p>${countSub(list)}</p></div>
        <div class="seg"><button class="${state.mode === "carousel" ? "on" : ""}" data-mode="carousel">Swipe</button><button class="${state.mode === "wall" ? "on" : ""}" data-mode="wall">Wall</button></div>
      </div>
      <div class="filterbar">
        <span class="chip-label">Platform</span>${platformChips()}
        <span class="vsep"></span>
        <span class="chip-label">Competitor</span>${compChips()}
      </div>
      ${body}
    </section>`;
  CURRENT_FIT = () => carLayout(false);
  bindAdsView();
  if (list.length) carLayout(false);
}

function stageHtml(list) {
  return `<div class="stage" id="stage">
      <button class="arrow prev" id="prev" aria-label="Previous ad">${ICON.left}</button>
      <div class="track" id="track">${list.map((ad, i) => `
        <div class="slide" data-i="${i}" data-id="${esc(ad.id)}">
          ${fitBox(renderAd(ad), tierBadge(ad.tier))}
          <div class="slide-meta">${slideMeta(ad)}</div>
        </div>`).join("")}</div>
      <button class="arrow next" id="next" aria-label="Next ad">${ICON.right}</button>
    </div>
    <div class="controls"><span class="pos" id="pos"></span><span class="hint">Arrow keys or swipe. Click an ad to see the page behind it.</span></div>`;
}

function wallHtml(list) {
  return `<div class="wall" id="wall"><div class="wall-cols">${list.map(ad => `
    <div class="wall-item" data-open="${esc(ad.id)}">
      ${fitBox(renderAd(ad), tierBadge(ad.tier, true))}
      <div class="wall-cap">${esc(ad.advertiser || "")}${ad.days_running ? ` &middot; ${fmtInt(ad.days_running)} days` : ""}</div>
    </div>`).join("")}</div></div>`;
}

function bindAdsView() {
  const app = document.getElementById("app");
  app.querySelectorAll("[data-plat]").forEach(b => b.onclick = () => { state.platform = b.dataset.plat; state.idx = 0; closePanel(); renderAdsView(); });
  app.querySelectorAll("[data-comp]").forEach(b => b.onclick = () => { state.comp = b.dataset.comp; state.idx = 0; closePanel(); renderAdsView(); });
  app.querySelectorAll("[data-mode]").forEach(b => b.onclick = () => { state.mode = b.dataset.mode; closePanel(); renderAdsView(); });
  const stage = document.getElementById("stage");
  if (stage) bindStage(stage);
}

function carLayout(animate) {
  const stage = document.getElementById("stage");
  const wall = document.getElementById("wall");
  if (wall) { fitAll(wall, 290, 2000, 1); return; }
  if (!stage) return;
  const track = document.getElementById("track");
  const maxH = Math.max(240, stage.clientHeight - 140);
  const maxW = Math.min(980, (stage.clientWidth - panelWidth()) * 0.62);
  fitAll(track, maxW, maxH, 1.45);
  carPosition(animate);
}

function panelWidth() {
  return document.body.classList.contains("panel-open") ? document.getElementById("panel").offsetWidth : 0;
}

function carPosition(animate) {
  const track = document.getElementById("track");
  const stage = document.getElementById("stage");
  if (!track || !stage) return;
  const slides = track.children;
  const s = slides[state.idx];
  if (!s) return;
  if (animate === false) track.classList.add("dragging");
  const x = (stage.clientWidth - panelWidth()) / 2 - (s.offsetLeft + s.offsetWidth / 2);
  track.dataset.x = x;
  track.style.transform = `translateX(${x}px)`;
  [...slides].forEach((el, i) => el.classList.toggle("on", i === state.idx));
  if (animate === false) { void track.offsetWidth; track.classList.remove("dragging"); }
  const n = slides.length;
  document.getElementById("pos").textContent = `${state.idx + 1} / ${n}`;
  document.getElementById("prev").disabled = state.idx === 0;
  document.getElementById("next").disabled = state.idx >= n - 1;
}

function carGo(i) {
  const n = filteredAds().length;
  if (!n) return;
  state.idx = Math.max(0, Math.min(n - 1, i));
  carPosition(true);
  if (state.panelId) openPanel(filteredAds()[state.idx].id, true);
}

function bindStage(stage) {
  const track = document.getElementById("track");
  document.getElementById("prev").onclick = e => { e.stopPropagation(); carGo(state.idx - 1); };
  document.getElementById("next").onclick = e => { e.stopPropagation(); carGo(state.idx + 1); };
  stage.addEventListener("pointerdown", e => {
    if (e.button !== 0 || e.target.closest(".arrow")) return;
    CAR_DRAG = { x0: e.clientX, base: Number(track.dataset.x || 0), moved: false, target: e.target };
    track.classList.add("dragging");
  });
  let wheelAcc = 0, wheelLock = 0;
  stage.addEventListener("wheel", e => {
    if (Math.abs(e.deltaX) <= Math.abs(e.deltaY)) return;
    e.preventDefault();
    if (Date.now() < wheelLock) return;
    wheelAcc += e.deltaX;
    if (Math.abs(wheelAcc) > 50) { carGo(state.idx + (wheelAcc > 0 ? 1 : -1)); wheelAcc = 0; wheelLock = Date.now() + 380; }
  }, { passive: false });
}

/* Drag listeners live on window once, so re-rendering never stacks them. */
let CAR_DRAG = null;
window.addEventListener("pointermove", e => {
  const track = document.getElementById("track");
  if (!CAR_DRAG || !track) return;
  const dx = e.clientX - CAR_DRAG.x0;
  if (Math.abs(dx) > 6) CAR_DRAG.moved = true;
  if (CAR_DRAG.moved) track.style.transform = `translateX(${CAR_DRAG.base + dx}px)`;
});
window.addEventListener("pointerup", e => {
  const track = document.getElementById("track");
  if (!CAR_DRAG || !track) { CAR_DRAG = null; return; }
  const d = CAR_DRAG; CAR_DRAG = null;
  track.classList.remove("dragging");
  const dx = e.clientX - d.x0;
  if (d.moved) {
    if (dx < -60) carGo(state.idx + Math.max(1, Math.round(-dx / 500)));
    else if (dx > 60) carGo(state.idx - Math.max(1, Math.round(dx / 500)));
    else carPosition(true);
    return;
  }
  const slide = d.target.closest(".slide");
  if (!slide) return;
  const i = Number(slide.dataset.i);
  const wasActive = i === state.idx;
  if (!wasActive) carGo(i);
  if (wasActive || d.target.closest("[data-open]") || state.panelId) openPanel(slide.dataset.id);
});
