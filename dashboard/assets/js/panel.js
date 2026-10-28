/* Side panel: the landing page behind an ad, and what that page offers. */

function factBox(label, value, opts) {
  const o = opts || {};
  const has = value !== null && value !== undefined && String(value).trim() !== "";
  return `<div class="fact ${o.wide ? "wide" : ""}"><div class="kicker">${esc(label)}</div><div class="v ${has ? (o.big ? "big" : "") : "none"}">${has ? esc(value) : esc(o.empty || "Not found on the page")}</div></div>`;
}

function adFacts(ad) {
  const items = [];
  const add = (v, label) => { if (v !== null && v !== undefined && v !== "") items.push(`<div><b>${esc(v)}</b><small>${esc(label)}</small></div>`); };
  add(ad.days_running !== null && ad.days_running !== undefined ? fmtInt(ad.days_running) : null, "days running");
  add(fmtDate(ad.start_date), "first seen");
  add(ad.impressions_rank ? `#${ad.impressions_rank}` : null, "impressions rank");
  add(Number(ad.copies) > 1 ? fmtInt(ad.copies) : null, "copies running");
  add(ad.reach_per_day ? fmtInt(ad.reach_per_day) : null, "EU reach a day");
  add(ad.eu_reach ? fmtNum(ad.eu_reach) : null, "EU reach");
  add(fmtShare(ad.spyfu_share), "share of ads served");
  add(ad.ctr_rank ? ad.ctr_rank : null, "CTR rank");
  add(asList(ad.placements).slice(0, 3).map(x => x.replace(/_/g, " ")).join(", ") || null, "placements");
  return items.join("");
}

function panelHtml(ad) {
  const page = pageFor(ad);
  const url = (page && page.url) || ad.landing_url;
  const href = safeHref(url);
  const shot = page && safeSrc(page.screenshot);
  const proof = page ? asList(page.proof) : [];
  const type = page ? (page.is_homepage ? "Homepage" : "Matched page") : null;
  const others = page ? asList(page.ad_ids).filter(id => id !== ad.id).length : 0;
  const ranked = ad.tier || (ad.score !== null && ad.score !== undefined);
  return `<div class="panel-inner">
    <div class="panel-top">
      <span class="kicker">Landing page</span>
      ${type ? `<span class="pill ${page.is_homepage ? "" : "y"}">${type}</span>` : ""}
      ${others ? `<span class="pill">${others + 1} ads point here</span>` : ""}
      <button class="close" data-close aria-label="Close">${ICON.close}</button>
    </div>
    <div class="panel-url">${href ? `<a href="${esc(href)}" target="_blank" rel="noopener noreferrer" style="color:inherit">${esc(url)}</a>` : esc(url || "No landing page captured for this ad")}</div>
    <div class="card browser">
      <div class="browser-bar"><i></i><i></i><i></i><span>${esc(url ? url.replace(/^https?:\/\//, "") : "")}</span></div>
      <div class="shot">${shot ? `<img src="${esc(shot)}" alt="Landing page screenshot" onerror="this.parentNode.innerHTML='<div class=&quot;none&quot;>Screenshot missing</div>'">` : `<div class="none">${page ? "No screenshot" : "Page not captured yet"}</div>`}</div>
    </div>
    ${page ? `
      <div class="page-h1">${esc(page.h1 || page.title || "No headline found")}</div>
      ${page.title && page.h1 ? `<div class="page-title">${esc(page.title)}</div>` : `<div style="height:14px"></div>`}
      <div class="facts">
        ${factBox("The offer", page.offer, { wide: true })}
        ${factBox("Price", page.price, { big: true, empty: "No price shown" })}
        ${factBox("Form fields", Number(page.form_fields) > 0 ? `${page.form_fields} field${Number(page.form_fields) === 1 ? "" : "s"}` : null, { big: true, empty: "No form on the page" })}
        <div class="fact wide"><div class="kicker">Proof on the page</div>${proof.length ? `<div class="proofs">${proof.slice(0, 8).map(p => `<span>${esc(p)}</span>`).join("")}</div>` : `<div class="v none">No proof found</div>`}</div>
      </div>` : ""}
    <h3>The ad</h3>
    <div class="ad-facts">${adFacts(ad) || `<div><b>${esc(PLATFORMS[platformOf(ad)] ? PLATFORMS[platformOf(ad)].label : ad.platform)}</b><small>platform</small></div>`}</div>
    ${ranked ? `<div class="why"><b>Tier ${esc(ad.tier || "?")}${ad.score !== null && ad.score !== undefined ? `, score ${esc(ad.score)}` : ""}${ad.grade ? `, confidence ${esc(ad.grade)}` : ""}.</b> ${esc(ad.why || "")}</div>` : ""}
  </div>`;
}

function openPanel(id, keepScroll) {
  const ad = AD_BY_ID[id];
  if (!ad) return;
  const panel = document.getElementById("panel");
  const wasOpen = document.body.classList.contains("panel-open");
  state.panelId = id;
  panel.innerHTML = panelHtml(ad);
  if (!keepScroll) panel.scrollTop = 0;
  panel.setAttribute("aria-hidden", "false");
  document.body.classList.add("panel-open");
  if (!wasOpen && state.view === "ads") setTimeout(() => carLayout(true), 0);
}

function closePanel() {
  if (!document.body.classList.contains("panel-open")) return;
  state.panelId = null;
  document.body.classList.remove("panel-open");
  document.getElementById("panel").setAttribute("aria-hidden", "true");
  if (state.view === "ads") carLayout(true);
}
