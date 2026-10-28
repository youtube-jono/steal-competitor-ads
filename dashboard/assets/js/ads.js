/* Real-looking ads, one renderer per platform. Each returns an HTML string. */

function mediaPlaceholder(ad, dark, video) {
  const h = hue(ad.advertiser || ad.domain);
  const bg = dark
    ? `linear-gradient(150deg, hsl(${h},35%,22%), hsl(${(h + 40) % 360},30%,10%))`
    : `linear-gradient(150deg, hsl(${h},60%,90%), hsl(${(h + 40) % 360},55%,80%))`;
  const text = joinText(ad.headline, " | ") || ad.advertiser || "";
  const size = text.length > 80 ? 22 : text.length > 40 ? 28 : 34;
  return `<div class="media-ph${video ? " vid" : ""}" style="background:${bg};color:${dark ? "#fff" : "#1c1c1c"};font-size:${size}px">${esc(text)}<small>${esc(ad.domain || ad.display_url || "")}</small></div>`;
}

function displayUrl(ad) {
  const clean = v => String(v || "").replace(/^https?:\/\//, "").replace(/\/$/, "");
  const metaHost = v => BLOCKED_HOSTS.some(b => clean(v).split("/")[0].replace(/^www\./, "").endsWith(b));
  const raw = [ad.display_url, ad.domain, hostOf(ad.landing_url)].find(v => v && !metaHost(v));
  return clean(raw);
}

function googleUrlLine(ad) {
  const d = displayUrl(ad);
  if (!d) return "";
  const parts = d.split("/").filter(Boolean);
  const host = parts.shift();
  const full = /^www\./.test(host) ? host : `www.${host}`;
  return `https://${esc(full)}${parts.map(p => ` <span>&rsaquo;</span> ${esc(p)}`).join("")}`;
}

function googleHead(ad) {
  const name = ad.advertiser || ad.domain || "Sponsored";
  const host = (ad.domain || hostOf(ad.landing_url) || displayUrl(ad).split("/")[0] || "").replace(/^www\./, "");
  const fav = host ? img(`https://www.google.com/s2/favicons?domain=${encodeURIComponent(host)}&sz=64`, "", "") : "";
  return `<div class="g-sponsored">Sponsored</div>
    <div class="g-head">
      <div class="g-fav">${esc(initials(name)[0])}${fav}</div>
      <div class="g-site"><div class="g-name">${esc(name)}</div><div class="g-url">${googleUrlLine(ad)}</div></div>
      <div class="g-dots">${ICON.dotsV}</div>
    </div>`;
}

function googleSearch(ad, headlines) {
  const descs = asList(ad.description).concat(asList(ad.body));
  const links = asList(Array.isArray(ad.sitelinks) ? ad.sitelinks.map(s => (s && typeof s === "object") ? (s.text || s.title) : s) : ad.sitelinks);
  const callouts = asList(ad.callouts);
  return `<div class="ad g-ad">
    ${googleHead(ad)}
    <div class="g-title">${esc(headlines.slice(0, 3).join(" | "))}</div>
    <div class="g-desc clamp2">${esc(descs.slice(0, 2).join(" "))}</div>
    ${links.length ? `<div class="g-links">${links.slice(0, 4).map(esc).join('<span class="sep">&middot;</span>')}</div>` : ""}
    ${callouts.length ? `<div class="g-callouts">${callouts.slice(0, 4).map(esc).join('<span class="sep">&middot;</span>')}</div>` : ""}
  </div>`;
}

function googleVideo(ad) {
  const m = ad.media || {};
  const src = m.thumbnail || m.image;
  const name = ad.advertiser || ad.domain || "Sponsored";
  return `<div class="ad g-ad g-video">
    <div class="g-vid">${src ? "" : mediaPlaceholder({ ...ad, headline: ad.headline || "Video ad" }, true, true)}${img(src, "", "")}<div class="play" style="background:#ff0033;border:0;border-radius:18px;width:68px;height:48px">${ICON.play}</div><span class="g-vid-ad">Sponsored</span></div>
    <div class="g-vid-meta">${avatar(name, ad.avatar)}<div><div class="g-vid-title">${esc(joinText(ad.headline, " | ") || "Video ad on YouTube")}</div><div class="g-vid-sub">Sponsored &middot; ${esc(name)}</div></div></div>
  </div>`;
}

/* No text captured: the Transparency Center image IS the ad, so show it on its own. */
function googleDisplay(ad) {
  const m = ad.media || {};
  const src = m.image || m.thumbnail;
  if (src && ad.format === "text") {
    return `<div class="ad g-ad g-shot"><div class="g-creative">${img(src, "", "Google ad")}</div></div>`;
  }
  return `<div class="ad g-ad g-display">
    ${googleHead(ad)}
    <div class="g-creative">${src ? img(src, "", "Ad creative") : mediaPlaceholder(ad)}</div>
  </div>`;
}

function renderGoogle(ad) {
  const headlines = asList(ad.headline);
  if (headlines.length) return googleSearch(ad, headlines);
  if (ad.format === "video") return googleVideo(ad);
  return googleDisplay(ad);
}

function metaMedia(ad) {
  const m = ad.media || {};
  const isVideo = ad.format === "video" || (m.video && !m.image);
  const src = isVideo ? (m.thumbnail || m.image) : (m.image || m.thumbnail);
  return `<div class="fb-media">${mediaPlaceholder(ad, false, isVideo)}${img(src, "", "")}${isVideo ? `<div class="play">${ICON.play}</div>` : ""}</div>`;
}

function metaCarousel(ad) {
  const cards = (Array.isArray(ad.cards) ? ad.cards : []).filter(c => c && typeof c === "object").slice(0, 5);
  return `<div class="fb-carousel">${cards.map(c => `
    <div class="fb-card">
      <div class="img">${mediaPlaceholder({ ...ad, headline: c.title })}${img(c.image, "", "")}</div>
      <div class="fb-card-b"><div class="t clamp2">${esc(c.title || ad.headline || "")}</div>${(c.cta || ad.cta) ? `<div class="fb-cta">${esc(c.cta || ad.cta)}</div>` : ""}</div>
    </div>`).join("")}</div>`;
}

function renderFacebook(ad) {
  const name = ad.advertiser || "Sponsored";
  const text = ad.body || "";
  const isCarousel = ad.format === "carousel" && Array.isArray(ad.cards) && ad.cards.length > 1;
  const hl = joinText(ad.headline, " | ");
  const linkBar = (hl || ad.cta || displayUrl(ad)) ? `
    <div class="fb-link">
      <div class="fb-link-l">
        <div class="fb-domain">${esc(displayUrl(ad))}</div>
        ${hl ? `<div class="fb-hl clamp2">${esc(hl)}</div>` : ""}
        ${ad.description ? `<div class="fb-ld">${esc(joinText(ad.description, " "))}</div>` : ""}
      </div>
      ${ad.cta ? `<div class="fb-cta">${esc(ad.cta)}</div>` : ""}
    </div>` : "";
  return `<div class="ad fb">
    <div class="fb-head">
      ${avatar(name, ad.avatar)}
      <div class="fb-who"><div class="fb-name">${esc(name)}</div><div class="fb-sub">Sponsored &middot; ${ICON.globe}</div></div>
      <div class="fb-icons">${ICON.dotsH}${ICON.x}</div>
    </div>
    ${text ? `<div class="fb-text"><div class="clamp3">${esc(text)}</div></div>` : `<div style="height:12px"></div>`}
    ${isCarousel ? metaCarousel(ad) : metaMedia(ad) + linkBar}
    <div class="fb-actions"><span>${ICON.like}Like</span><span>${ICON.comment}Comment</span><span>${ICON.share}Share</span></div>
  </div>`;
}

function renderInstagram(ad) {
  const name = ad.advertiser || "sponsored";
  const handle = String(name).toLowerCase().replace(/[^a-z0-9._]/g, "");
  return `<div class="ad ig">
    <div class="ig-head">
      <div class="ig-ring">${avatar(name, ad.avatar)}</div>
      <div style="flex:1;min-width:0"><div class="ig-name">${esc(handle)}</div><div class="ig-sub">Sponsored</div></div>
      <div style="color:#000">${ICON.dotsH}</div>
    </div>
    ${metaMedia(ad).replace("fb-media", "fb-media ig-media")}
    <div class="ig-cta"><span>${esc(ad.cta || "Learn more")}</span>${ICON.chevR}</div>
    <div class="ig-actions">${ICON.igHeart}${ICON.igComment}${ICON.igSend}</div>
    <div class="ig-text clamp3"><b>${esc(handle)}</b>${esc(ad.body || joinText(ad.headline, " "))}</div>
  </div>`;
}

function renderMeta(ad) {
  const p = asList(ad.placements).map(s => s.toLowerCase());
  if (p.length && p.includes("instagram") && !p.includes("facebook")) return renderInstagram(ad);
  return renderFacebook(ad);
}

function renderTikTok(ad) {
  const m = ad.media || {};
  const name = ad.advertiser || "sponsored";
  const handle = String(name).replace(/\s+/g, "").replace(/[^A-Za-z0-9._]/g, "");
  const caption = ad.body || joinText(ad.headline, " ");
  const src = m.thumbnail || m.image;
  const likes = fmtNum(ad.likes);
  return `<div class="ad tt">
    <div class="tt-media">${src ? "" : `<div class="tt-ph" style="background:linear-gradient(160deg,hsl(${hue(name)},45%,28%),#050505)">${esc(String(ad.headline || caption).slice(0, 90))}</div>`}${img(src, "", "")}</div>
    <div class="tt-shade"></div>
    <div class="tt-top"><span>Following</span><span class="on">For You</span></div>
    <div class="tt-search">${ICON.search}</div>
    <div class="play" style="background:rgba(0,0,0,.25);border:0">${ICON.play}</div>
    <div class="tt-rail">
      <div class="tt-av">${avatar(name, ad.avatar)}<div class="tt-plus">${ICON.plus}</div></div>
      <div>${ICON.heart}<span>${esc(likes || "")}</span></div>
      <div>${ICON.bubble}<span></span></div>
      <div>${ICON.bookmark}<span></span></div>
      <div>${ICON.ttshare}<span>Share</span></div>
      <div class="tt-disc"></div>
    </div>
    <div class="tt-bottom">
      <div class="tt-handle">${esc(handle || name)}</div>
      <div class="tt-caption clamp3">${esc(caption)}</div>
      <div class="tt-sponsored">Sponsored</div>
      <div class="tt-music">${ICON.note}<span>${esc(ad.music || "Promoted Music")}</span></div>
      <div class="tt-cta"><span>${esc(ad.cta || "Learn more")}</span>${ICON.chevR}</div>
    </div>
  </div>`;
}

function renderLinkedIn(ad) {
  const m = ad.media || {};
  const name = ad.advertiser || "Sponsored";
  const isVideo = ad.format === "video";
  const src = isVideo ? (m.thumbnail || m.image) : (m.image || m.thumbnail);
  const hl = joinText(ad.headline, " | ");
  return `<div class="ad li">
    <div class="li-head">
      ${avatar(name, ad.avatar, "li-logo")}
      <div class="li-who"><div class="li-name">${esc(name)}</div><div class="li-sub">Promoted</div></div>
      <div class="li-dots">${ICON.dotsH}</div>
    </div>
    <div class="li-text"><div class="clamp3">${esc(ad.body || "")}</div></div>
    <div class="li-media ${isVideo ? "" : "square"}">${src ? "" : mediaPlaceholder(ad, true, isVideo)}${img(src, "", "")}${isVideo ? `<div class="play">${ICON.play}</div>` : ""}</div>
    <div class="li-bar">
      <div class="li-bar-l">${hl ? `<div class="li-hl clamp2">${esc(hl)}</div>` : ""}<div class="li-domain">${esc(displayUrl(ad))}</div></div>
      <div class="li-cta">${esc(ad.cta || "Learn more")}</div>
    </div>
    <div class="li-actions"><span>${ICON.like}Like</span><span>${ICON.comment}Comment</span><span>${ICON.repost}Repost</span><span>${ICON.send}Send</span></div>
  </div>`;
}

function renderAd(ad) {
  switch ((ad.platform || "").toLowerCase()) {
    case "google": return renderGoogle(ad);
    case "meta": case "facebook": case "instagram": return renderMeta(ad);
    case "tiktok": return renderTikTok(ad);
    case "linkedin": return renderLinkedIn(ad);
    default: return renderGoogle(ad);
  }
}

/* Our draft, drawn on its own platform with our name and domain. */
function renderDraft(d, biz) {
  const ad = {
    platform: d.platform || "google",
    advertiser: biz.name || "You",
    domain: biz.domain || null,
    display_url: biz.domain || null,
    headline: d.headline,
    description: d.description,
    body: d.platform === "google" ? null : joinText(d.description, " "),
    cta: d.cta || null,
    format: "image",
    media: {},
  };
  return renderAd(ad);
}

/* A fit box: the ad keeps its natural size and is scaled to fit. */
function fitBox(adHtml, badge) {
  return `<div class="fit">${badge || ""}${adHtml}</div>`;
}

function tierBadge(t, small) {
  if (!t || !/^[ABCS]$/.test(String(t))) return "";
  return `<div class="tier ${esc(t)}${small ? " sm" : ""}">${esc(t)}</div>`;
}

function fitAll(root, maxW, maxH, maxScale) {
  root.querySelectorAll(".fit").forEach(f => {
    const ad = f.querySelector(".ad");
    if (!ad) return;
    ad.style.transform = "none";
    const w = ad.offsetWidth, h = ad.offsetHeight;
    if (!w || !h) return;
    const s = Math.min(maxScale || 1, maxW / w, maxH / h);
    ad.style.transform = `scale(${s})`;
    f.style.width = `${Math.round(w * s)}px`;
    f.style.height = `${Math.round(h * s)}px`;
  });
}
