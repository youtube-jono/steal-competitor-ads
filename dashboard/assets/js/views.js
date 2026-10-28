/* Stage views: winners (rank), your business (learn), ours vs theirs (write), published. */

function hasNum(v) { return v !== null && v !== undefined && v !== "" && !isNaN(Number(v)); }

function clue(label, value) {
  return value === null || value === undefined || value === "" ? "" : `<div class="clue"><b>${esc(value)}</b><small>${esc(label)}</small></div>`;
}

function winnerCard(ad) {
  const p = platformOf(ad);
  const score = hasNum(ad.score) ? Math.round(Number(ad.score)) : null;
  const grade = ad.grade && GRADE_TEXT[ad.grade] ? `<div class="clue grade"><b>${esc(ad.grade)}</b><small>confidence, ${esc(GRADE_TEXT[ad.grade])}</small></div>` : "";
  return `<div class="card win" data-open="${esc(ad.id)}">
    <div class="win-rank"><b>#${esc(ad.rank || "?")}</b><small>on ${esc(PLATFORMS[p] ? PLATFORMS[p].label : p)}</small></div>
    <div class="win-thumb">${fitBox(renderAd(ad))}</div>
    <div class="win-body">
      <div class="win-top">${tierBadge(ad.tier).replace('class="tier', 'class="tier tier-inline')}<div class="win-adv">${esc(ad.advertiser || "")}</div></div>
      <div class="win-hl">${esc(joinText(ad.headline, " | ") || ad.body || "")}</div>
      <div class="score"><b>${score === null ? "n/a" : score}</b><div class="bar"><i style="width:${score === null ? 0 : Math.max(2, Math.min(100, score))}%"></i></div><small>/ 100</small></div>
      <div class="clues">
        ${clue("days running", hasNum(ad.days_running) ? fmtInt(ad.days_running) : null)}
        ${clue("impressions rank", ad.impressions_rank ? `#${ad.impressions_rank}` : null)}
        ${clue("copies", hasNum(ad.copies) && Number(ad.copies) > 1 ? fmtInt(ad.copies) : null)}
        ${clue("reach a day", hasNum(ad.reach_per_day) ? fmtInt(ad.reach_per_day) : null)}
        ${clue("share served", fmtShare(ad.spyfu_share))}
        ${clue("CTR rank", ad.ctr_rank || null)}
        ${grade}
      </div>
      ${ad.why ? `<div class="win-why">${esc(ad.why)}</div>` : ""}
    </div>
  </div>`;
}

function renderWinners() {
  const ranked = ADS.filter(a => a.tier || hasNum(a.score));
  const list = ranked.filter(a => state.winPlatform === "all" || platformOf(a) === state.winPlatform)
    .sort((a, b) => (hasNum(b.score) ? Number(b.score) : -1) - (hasNum(a.score) ? Number(a.score) : -1) || (b.days_running || 0) - (a.days_running || 0));
  const tiers = { A: 0, B: 0, C: 0 };
  ranked.forEach(a => { if (tiers[a.tier] !== undefined) tiers[a.tier]++; });
  const counts = {};
  ranked.forEach(a => { const p = platformOf(a); counts[p] = (counts[p] || 0) + 1; });
  document.getElementById("app").innerHTML = `<section class="view">
    <div class="view-head">
      <div><h1>The <span class="hl">winners</span></h1><p>Every ad scored on delivery clues. Days running only breaks ties.</p></div>
      <div class="legend">${["A", "B", "C"].map(t => `<div class="tier ${t}">${t}</div><span>${tiers[t]}</span>`).join("")}</div>
    </div>
    <div class="chip-row" style="justify-content:flex-start;margin-bottom:26px">
      <button class="chip ${state.winPlatform === "all" ? "on" : ""}" data-wplat="all">All <span class="n">${ranked.length}</span></button>
      ${PLATFORM_ORDER.filter(p => counts[p]).map(p => `<button class="chip ${state.winPlatform === p ? "on" : ""}" data-wplat="${p}">${ICON[p]}${esc(PLATFORMS[p].label)} <span class="n">${counts[p]}</span></button>`).join("")}
    </div>
    <div class="win-grid" id="wins">${list.map(winnerCard).join("")}</div>
  </section>`;
  document.querySelectorAll("[data-wplat]").forEach(b => b.onclick = () => { state.winPlatform = b.dataset.wplat; renderWinners(); });
  CURRENT_FIT = () => fitAll(document.getElementById("wins"), 272, 256, 1);
  CURRENT_FIT();
}

function proofCard(item, first) {
  const claim = stripMd(item.claim);
  const lead = claim.match(/^([$€£]?\d[\d.,]*[KkMm]?\+?%?|#\d+)\s+(.*)$/);
  const any = !lead && claim.match(/([$€£]\d[\d.,]*[KkMm]?\+?|\b(?:19|20)\d{2}\b|\b\d{1,3}(?:,\d{3})+\+?|\b\d+[KkMm]\+?)/);
  const tidy = t => t.replace(/[.,]+$/, "");
  const body = lead ? `<div class="big">${esc(tidy(lead[1]))}</div><div class="claim">${esc(lead[2])}</div>`
    : any ? `<div class="big">${esc(tidy(any[1]))}</div><div class="claim">${esc(claim)}</div>`
    : `<div class="claim solo">${esc(claim)}</div>`;
  return `<div class="card proof ${first ? "first" : ""}">${body}${item.source ? `<div class="src">${esc(stripMd(item.source))}</div>` : ""}</div>`;
}

function renderYou() {
  const biz = DATA.business || {};
  const sections = (DATA.proof || []).filter(s => s && Array.isArray(s.items) && s.items.length);
  const total = sections.reduce((n, s) => n + s.items.length, 0);
  const sum = (biz.summary || []).map(stripMd);
  const cap = t => t ? t[0].toUpperCase() + t.slice(1) : "";
  document.getElementById("app").innerHTML = `<section class="view">
    <div class="view-head"><div><div class="kicker" style="margin-bottom:10px">Your business${biz.domain ? `  ·  ${esc(biz.domain)}` : ""}</div><h1>${esc(biz.name || "You")}</h1></div>
      <div class="legend"><span>${total} thing${total === 1 ? "" : "s"} you can prove</span></div></div>
    ${sum.length ? `<div class="card you-sum"><p class="tag">${esc(sum[0])}</p>${sum[1] ? `<p>${esc(sum[1])}</p>` : ""}</div>` : ""}
    ${sections.map((s, si) => `
      ${s.title ? `<h2 class="proof-head">${esc(cap(s.title))}</h2>` : ""}
      <div class="proof-grid">${s.items.map((it, i) => proofCard(it, si === 0 && i === 0)).join("")}</div>`).join("")}
    <div style="height:70px"></div>
  </section>`;
}

function voteDots(bt) {
  const runs = Math.max(1, Math.min(9, Number(bt && bt.runs) || 5));
  const wins = Math.max(0, Math.min(runs, Number(bt && bt.wins) || 0));
  return `<span class="vote">${Array.from({ length: runs }, (_, i) => `<i class="${i < wins ? "w" : ""}"></i>`).join("")}</span>`;
}

function vsRow(d) {
  const biz = DATA.business || {};
  const bt = d.buyer_test || {};
  const theirs = asList(d.beats).map(id => AD_BY_ID[id]).filter(Boolean).slice(0, 3);
  return `<div class="card vs">
    <div class="vs-side vs-ours">
      <div class="kicker">Ours <span class="angle">${esc(d.angle || "")}</span></div>
      ${fitBox(renderDraft(d, biz), tierBadge("S"))}
      <div class="gates">
        <div class="gate"><span class="ok">${ICON.check}</span>Rules pass</div>
        <div class="gate">Buyer test ${voteDots(bt)} ${esc(bt.wins ?? "?")}/${esc(bt.runs ?? 5)}</div>
      </div>
    </div>
    <div class="vs-mid">VS</div>
    <div class="vs-side">
      <div class="kicker">Their A tier it beat</div>
      <div class="theirs-row">${theirs.length ? theirs.map(a => `
        <div class="their" data-open="${esc(a.id)}" style="cursor:pointer">
          <div class="their-box">${tierBadge(a.tier || "A", true)}${fitBox(renderAd(a))}</div>
          <div class="their-cap">${esc(a.advertiser || "")}<small>${esc(PLATFORMS[platformOf(a)] ? PLATFORMS[platformOf(a)].label : "")}${a.score !== undefined && a.score !== null ? `, score ${esc(a.score)}` : ""}</small></div>
        </div>`).join("") : `<div class="angle">Their A-tier ads are not in this pull.</div>`}</div>
    </div>
  </div>`;
}

function sentBackRow(d) {
  const bt = d.buyer_test || {};
  const rulesOk = d.gate_rules === "pass";
  return `<div class="sb-row">
    <div><b>${esc(joinText(d.headline, " | "))}</b><span class="angle">${esc(d.angle || "")}</span></div>
    <div class="sb-why">
      <span class="pill ${rulesOk ? "" : "k"}">${rulesOk ? "Rules pass" : `Rules: ${esc(String(d.gate_rules || "fail").slice(0, 70))}`}</span>
      ${rulesOk ? `<span class="pill k">Buyer test ${esc(bt.wins ?? "?")}/${esc(bt.runs ?? 5)}</span>` : ""}
    </div>
  </div>`;
}

function renderVersus() {
  const drafts = DATA.drafts || [];
  const s = drafts.filter(d => d.tier === "S");
  const back = drafts.filter(d => d.tier !== "S");
  document.getElementById("app").innerHTML = `<section class="view">
    <div class="view-head"><div><h1>Ours vs <span class="hl">theirs</span></h1>
      <p>${drafts.length} drafts. ${s.length} made S tier: passed the rules, then beat their A tier in a blind buyer test.</p></div>
      <div class="legend"><div class="tier S">S</div><span>${s.length}</span></div></div>
    <div class="vs-list" id="vs">${s.map(vsRow).join("")}</div>
    ${back.length ? `<div class="card sent-back"><h2>Sent back (${back.length})</h2>${back.map(sentBackRow).join("")}</div>` : ""}
  </section>`;
  const vs = document.getElementById("vs");
  CURRENT_FIT = () => {
    vs.querySelectorAll(".vs-ours").forEach(el => fitAll(el, el.clientWidth - 20, 320, 1.15));
    vs.querySelectorAll(".their-box").forEach(el => fitAll(el, el.clientWidth - 24, 226, 1));
  };
  CURRENT_FIT();
}

function fmtCustomer(id) {
  const d = String(id || "").replace(/\D/g, "");
  return d.length === 10 ? `${d.slice(0, 3)}-${d.slice(3, 6)}-${d.slice(6)}` : String(id || "");
}

function fmtWhen(iso) {
  if (!iso) return null;
  const t = new Date(iso);
  if (isNaN(t)) return String(iso);
  return `${t.getDate()} ${MONTHS[t.getMonth()]} ${t.getFullYear()}, ${String(t.getHours()).padStart(2, "0")}:${String(t.getMinutes()).padStart(2, "0")}`;
}

function publishedPreview(p) {
  const heads = asList(p.headlines), descs = asList(p.descriptions);
  if (!heads.length) return null;
  const biz = DATA.business || {};
  const host = hostOf(p.final_url) || biz.domain || "";
  const path = asList(p.path).join("/");
  return renderAd({ platform: "google", advertiser: p.account_name || biz.name || "You", domain: host,
    display_url: host + (path ? "/" + path : ""), headline: heads.slice(0, 3), description: descs.slice(0, 2), media: {} });
}

function renderPublished() {
  const p = DATA.published || {};
  const ids = asList(p.ad_ids);
  const s = (DATA.drafts || []).filter(d => d.tier === "S");
  const status = String(p.status || "PAUSED").toUpperCase();
  const preview = publishedPreview(p);
  const keywords = asList(p.keywords);
  const fourth = hasNum(p.daily_budget)
    ? `<div><small>Daily budget</small><b>$${esc(Number(p.daily_budget).toFixed(2))}</b></div>`
    : `<div><small>Ads</small><b>${ids.length}</b></div>`;
  document.getElementById("app").innerHTML = `<section class="view">
    <div class="view-head"><div><h1>Live in <span class="hl">Google Ads</span></h1><p>One Search campaign, created paused. Nothing spends until you switch it on.</p></div></div>
    <div class="card pub">
      <div class="pub-top"><span style="width:34px;height:34px;display:block">${ICON.google}</span><span class="kicker">Search campaign${p.account_name ? `  ·  ${esc(p.account_name)}` : ""}</span>
        <span class="paused">${status === "PAUSED" ? ICON.pause : ""}${esc(status)}</span></div>
      <div class="pub-name">${esc(p.campaign_name || "Campaign")}</div>
      <div class="ids">
        <div><small>Customer ID</small><b>${esc(fmtCustomer(p.customer_id) || "n/a")}</b></div>
        <div><small>Campaign ID</small><b>${esc(p.campaign_id || (p.validate_only ? "after the real push" : "n/a"))}</b></div>
        <div><small>Ad group ID</small><b>${esc(p.ad_group_id || (p.validate_only ? "after the real push" : "n/a"))}</b></div>
        ${fourth}
      </div>
      ${keywords.length ? `<div class="kw">${keywords.slice(0, 12).map(k => `<span>${esc(k)}</span>`).join("")}</div>` : ""}
      ${ids.length ? `<div class="pub-note">Ad IDs: ${ids.map(esc).join(", ")}</div>` : ""}
      ${p.validate_only ? `<div class="pub-note warn">Validate only: Google checked every ad and nothing was created yet.</div>` : ""}
      ${p.at ? `<div class="pub-note">Pushed ${esc(fmtWhen(p.at))}</div>` : ""}
    </div>
    ${preview ? `<h2 class="proof-head">What went in: ${asList(p.headlines).length} headlines, ${asList(p.descriptions).length} descriptions</h2>
      <div class="went-in" id="went"><div class="wrap">${fitBox(preview, tierBadge("S", true))}</div>
        <div class="card rsa-list"><ol>${asList(p.headlines).map(h => `<li>${esc(h)}</li>`).join("")}</ol></div></div>`
    : s.length ? `<h2 class="proof-head">What went in</h2>
      <div class="went-in" id="went">${s.map(d => `<div class="wrap">${fitBox(renderDraft(d, DATA.business || {}), tierBadge("S", true))}</div>`).join("")}</div>` : ""}
  </section>`;
  const w = document.getElementById("went");
  CURRENT_FIT = () => { if (w) w.querySelectorAll(".wrap").forEach(el => fitAll(el, el.clientWidth - 20, 400, 1.1)); };
  CURRENT_FIT();
}
