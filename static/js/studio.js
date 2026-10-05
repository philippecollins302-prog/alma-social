/* Studio — ce que l'application fabrique avec vos photos, et la répétition
 * générale d'une campagne. Une rafale de photos SAZÚ devient seule un Reel et
 * un carrousel ; ici on les regarde, et on peut en demander d'autres
 * (avant/après d'un chantier, carrousel d'une réalisation). La répétition
 * montre chaque étape d'une campagne telle qu'elle partira — visuel, texte
 * réseau par réseau, heure — sans rien publier. */
"use strict";

const NOMS_MONTAGE = { reel: "Reel", carrousel: "Carrousel", avant_apres: "Avant / après", rideau: "Rideau avant/après" };
const NOMS_RESEAU = { instagram: "Instagram", facebook: "Facebook", tiktok: "TikTok", gbp: "Google", linkedin: "LinkedIn",
  youtube: "YouTube", pinterest: "Pinterest", threads: "Threads", linkedin_perso: "LinkedIn perso" };

async function vueStudio() {
  const ou = $("#v-studio");
  ou.innerHTML = `<div class="entete-vue"><h1>Studio</h1></div><div class="filtres" id="st-filtres"></div>
    <div id="st-repetitions"></div><h2 class="section">Montages</h2>
    <button class="secondaire large" data-fabriquer="1">＋ Fabriquer un montage</button><div id="st-travaux"></div>`;
  const f = filtres($("#st-filtres"), "studio", () => vueStudio());
  chargement($("#st-travaux"));
  try {
    const [t, c] = await Promise.all([api("/api/studio" + (f ? `?marque=${encodeURIComponent(f)}` : "")), api("/api/campagnes")]);
    const camps = c.campagnes.filter(x => x.status === "active" && (!f || (x.brand_ids || []).includes(f)));
    $("#st-repetitions").innerHTML = camps.map(x => `
      <section class="carte repetition" data-campagne="${x.id}">
        <div class="ligne"><span class="etiquette or">Campagne</span><span class="doux petit">${esc(x.start)} → ${esc(x.end)}</span></div>
        <h2 style="margin-top:8px">${esc(x.name)}</h2>
        <p class="petit doux">La répétition rejoue chaque étape comme l'horloge le fera : mêmes textes, mêmes garde-fous,
          logo à l'heure dite. Rien n'est publié.</p>
        <div class="actions"><button class="secondaire" data-repeter="${x.id}">Rejouer la répétition</button></div>
        <div class="etapes" id="rep-${x.id}"></div>
      </section>`).join("");
    camps.forEach(x => chargerRepetition(x.id, false));
    $("#st-travaux").innerHTML = t.travaux.map(travail).join("")
      || '<div class="vide"><b>Aucun montage encore.</b>Déposez trois photos SAZÚ d\'un coup : le studio en fait un Reel et un carrousel.</div>';
  } catch (err) { $("#st-travaux").innerHTML = `<p class="erreur">${esc(err.message)}</p>`; }
}

function travail(j) {
  const f = j.fichiers || [];
  const media = j.type === "reel" || j.type === "rideau"
    ? f.map(x => `<video controls playsinline preload="none" poster="${esc(x.url.replace(/\.mp4$/, ".jpg"))}" src="${esc(x.url)}"></video>`).join("")
    : `<div class="bande">${f.map(x => `<img alt="" loading="lazy" src="${esc(x.url)}">`).join("")}</div>`;
  const params = (j.sortie || {}).params || {};
  return `<article class="carte montage">
      <div class="ligne"><span>${puce(j.brand_id)}<b>${esc(NOMS_MONTAGE[j.type] || j.type)}</b>
        <span class="doux petit">· ${(j.asset_ids || []).length} photo${(j.asset_ids || []).length > 1 ? "s" : ""}${params.auto ? " · automatique" : ""}</span></span>
        <span class="petit ${j.statut === "fait" ? "ok" : j.statut === "echec" ? "erreur" : "doux"}">${esc({ fait: "prêt", echec: "échec", attente: "en cours" }[j.statut] || j.statut)}</span></div>
      ${j.statut === "echec" ? `<p class="petit erreur">${esc(j.erreur)}</p>` : media}
      ${params.accroche || params.titre ? `<p class="petit">« ${esc(params.accroche || params.titre)} »</p>` : ""}
      <details><summary class="petit doux">Ce qui a été fait (${(j.traitements || []).length})</summary>
        <ul class="petit">${(j.traitements || []).map(x => `<li>${esc(x)}</li>`).join("")}</ul></details>
    </article>`;
}

async function chargerRepetition(cid, rejouer) {
  const ou = $(`#rep-${cid}`);
  if (!ou) return;
  if (rejouer) ou.innerHTML = '<p class="doux">La répétition tourne : chaque étape est écrite, relue par le garde-fou et le Critique…</p>';
  try {
    const r = rejouer ? await api(`/api/campagnes/${cid}/repetition`, { json: {} }) : await api(`/api/campagnes/${cid}/repetition`);
    if (!r.etapes || !r.etapes.length) {
      ou.innerHTML = rejouer ? '<p class="doux petit">Aucune étape à venir dans cette campagne.</p>' : '<p class="doux petit">Pas encore répétée.</p>';
      return;
    }
    const s = r.resume || {};
    const jour = iso => new Date(iso + "T12:00:00").toLocaleDateString("fr-FR", { weekday: "short", day: "numeric", month: "short" });
    ou.innerHTML = `
      <div class="bilan">
        <div><b>${s.pretes}/${s.etapes}</b><span>étapes prêtes</span></div>
        <div><b>${s.publications}</b><span>publications</span></div>
        <div><b>${s.cartes}</b><span>cartes à la charte</span></div>
      </div>
      <p class="petit doux">Répétée ${esc(quand(r.created_at))}${s.premiere_etape_avec_logo ? ` · logo révélé à l'étape ${esc(s.premiere_etape_avec_logo)}` : ""}.
        ${s.cartes ? "Une étape sans photo du bon sujet part en carte à la charte ; déposez une photo pour la remplacer." : ""}</p>
      ${r.etapes.map(e => `
        <article class="etape ${e.verdict === "pret" ? "" : "a-revoir"}">
          <img alt="" src="${esc(e.visuel.url)}">
          <div>
            <div class="ligne"><span class="etiquette ${e.verdict === "pret" ? "" : "attention"}">${esc(e.etiquette)}</span>
              <span class="heure">${esc(jour(e.jour))} · ${esc(e.heure)}</span></div>
            <div class="petit doux">${e.visuel.source === "carte" ? "Carte à la charte" : "Photo"} · ${e.logo ? "logo visible" : "logo caché"}
              · ${e.reseaux.map(x => esc(NOMS_RESEAU[x] || x)).join(", ")}</div>
            ${e.raisons.length ? `<p class="petit attention">${e.raisons.map(esc).join("<br>")}</p>` : ""}
            <div class="onglets-texte">${Object.keys(e.textes).map((pf, i) => `<button class="${i ? "" : "actif"}" data-pf="${esc(pf)}">${esc(NOMS_RESEAU[pf] || pf)}</button>`).join("")}</div>
            ${Object.entries(e.textes).map(([pf, t], i) => `<div class="texte-reseau" data-texte="${esc(pf)}" ${i ? "hidden" : ""}>
              <div class="ligne petit"><span class="doux">${esc(t.modele || "")}</span>${noteCritique(t.note, t.juge)}</div>
              <pre class="texte">${esc(t.texte || "—")}</pre></div>`).join("")}
          </div>
        </article>`).join("")}`;
  } catch (err) { ou.innerHTML = `<p class="erreur">${esc(err.message)}</p>`; }
}

async function fabriquerMontage() {
  const f = ETAT.filtres.studio || ETAT.marques[0]?.id;
  const j = await api(`/api/photos?marque=${encodeURIComponent(f)}&limite=24`);
  const photos = j.photos.filter(p => p.sorte === "photo" && !["refuse", "quarantaine", "retire"].includes(p.statut));
  if (!photos.length) return dire('<p>Aucune photo utilisable pour cette marque.</p>');
  dire(`<h3>Un montage pour ${esc(nomMarque(f))}</h3>
    <p class="petit doux">Touchez les photos dans l'ordre du montage.</p>
    <div class="choix-photos">${photos.map(p => `<label><input type="checkbox" value="${p.id}"><img alt="" src="${esc(p.vignette)}"><i></i></label>`).join("")}</div>
    <select id="mt-type" class="champ">
      <option value="carrousel">Carrousel (couverture, vues numérotées, appel à l'action)</option>
      <option value="reel">Reel (mouvements, sous-titres, fin sur l'appel)</option>
      <option value="avant_apres">Avant / après en image (2 photos : avant puis après)</option>
      <option value="rideau">Avant / après en vidéo (2 photos)</option>
    </select>
    <input id="mt-accroche" class="champ" maxlength="80" placeholder="L'accroche, écrite sur la première image">
    <button class="large" id="mt-go">Fabriquer</button>`);
  const ordre = [];
  $("#dialogue-corps").addEventListener("change", e => {
    if (e.target.type !== "checkbox") return;
    const v = Number(e.target.value), i = ordre.indexOf(v);
    if (e.target.checked && i < 0) ordre.push(v); else if (!e.target.checked && i >= 0) ordre.splice(i, 1);
    document.querySelectorAll(".choix-photos input").forEach(x => { x.nextElementSibling.nextElementSibling.textContent = ordre.indexOf(Number(x.value)) + 1 || ""; });
  });
  $("#mt-go").onclick = async () => {
    const b = $("#mt-go"); b.disabled = true; b.textContent = "Le studio travaille…";
    const type = $("#mt-type").value, acc = $("#mt-accroche").value.trim();
    try {
      await api("/api/studio", { json: { marque: f, type, photos: ordre, accroche: acc, titre: acc } });
      $("#dialogue").close(); vueStudio();
    } catch (err) { b.disabled = false; b.textContent = "Fabriquer"; erreur(err); }
  };
}

$("#v-studio").addEventListener("click", async e => {
  const t = e.target;
  if (t.dataset.repeter) { t.disabled = true; await chargerRepetition(t.dataset.repeter, true); t.disabled = false; }
  if (t.dataset.fabriquer) fabriquerMontage().catch(erreur);
  if (t.matches(".etape .texte")) t.classList.toggle("ouvert");
  if (t.dataset.pf) {
    const etape = t.closest(".etape");
    etape.querySelectorAll("[data-pf]").forEach(x => x.classList.toggle("actif", x === t));
    etape.querySelectorAll("[data-texte]").forEach(x => { x.hidden = x.dataset.texte !== t.dataset.pf; });
  }
});

VUES.studio = vueStudio;
