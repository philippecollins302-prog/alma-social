/* Aujourd'hui — la planche de ce qui sort aujourd'hui et demain : le visuel,
 * le texte exact, l'heure, la note du Critique. On regarde ; on n'approuve
 * rien (sauf une marque passée en « copilote », réglage désactivé par défaut). */
"use strict";

async function vueAujourdhui() {
  const ou = $("#v-aujourdhui");
  ou.innerHTML = `<div class="entete-vue"><h1>Aujourd'hui</h1><span class="doux petit" id="auj-compte"></span></div>
    <div class="filtres" id="auj-filtres"></div><div id="auj-liste"></div>`;
  const f = filtres($("#auj-filtres"), "aujourdhui", () => vueAujourdhui());
  const liste = $("#auj-liste");
  chargement(liste);
  try {
    const j = await api("/api/aujourdhui" + (f ? `?marque=${encodeURIComponent(f)}` : ""));
    const jour = iso => new Date(iso).toLocaleDateString("fr-FR", P);
    const auj = new Date().toLocaleDateString("fr-FR", P);
    const groupes = { auj: [], dem: [] };
    j.publications.forEach(p => groupes[jour(p.heure) === auj ? "auj" : "dem"].push(p));
    $("#auj-compte").textContent = `${j.publications.length} publication${j.publications.length > 1 ? "s" : ""}`;
    liste.dataset.photos = JSON.stringify(j.publications.map(p => [p.id, p.nom_reseau, p.texte]));
    const carte = p => `
      <article class="sortie">
        ${p.vignette ? `<img alt="" loading="lazy" src="${esc(p.vignette)}">` : '<img alt="">'}
        <div>
          <div class="ligne"><span class="heure">${esc(heure(p.heure))}</span>${noteCritique(p.note, p.juge)}</div>
          <div class="petit">${puce(p.marque)}<b>${esc(nomMarque(p.marque))}</b> · ${esc(p.nom_reseau)}
            <span class="etat-${esc(p.statut)}">· ${esc({ programme: "programmée", publie: "publiée", simule: "simulée", a_valider: "aperçu copilote", echec: "échec", suspendu: "suspendue", envoi: "envoi…", preparation: "préparation", refuse: "écartée" }[p.statut] || p.statut)}</span></div>
          <div class="texte">${esc(p.texte)}</div>
          <div class="actions">
            <a href="#" class="secondaire" data-apercu="${p.id}">Voir en entier</a>
            ${p.lien ? `<a class="secondaire" href="${esc(p.lien)}" target="_blank" rel="noopener">Sur le réseau</a>` : ""}
            ${p.statut === "a_valider" ? `<button class="secondaire" data-valider="${p.id}">Laisser partir</button>` : ""}
          </div>
        </div>
      </article>`;
    liste.innerHTML = (j.bac_a_sable ? '<p class="attention petit">🧪 Bac à sable : tout ce qui suit est simulé, rien ne sort pour de vrai.</p>' : "")
      + `<div class="jour-titre">Aujourd'hui</div>` + (groupes.auj.map(carte).join("") || '<div class="vide"><b>Rien aujourd\'hui.</b>Une photo déposée maintenant peut encore sortir ce soir.</div>')
      + `<div class="jour-titre">Demain</div>` + (groupes.dem.map(carte).join("") || '<p class="doux petit">Rien de prévu demain pour l\'instant.</p>');
  } catch (err) { liste.innerHTML = `<p class="erreur">${esc(err.message)}</p>`; }
}

$("#v-aujourdhui").addEventListener("click", async e => {
  const t = e.target;
  if (t.dataset.apercu) {
    e.preventDefault();
    const infos = JSON.parse($("#auj-liste").dataset.photos || "[]").find(x => String(x[0]) === t.dataset.apercu) || [];
    return dire(`<h3>${esc(infos[1] || "")}</h3><img alt="" src="/apercu/${esc(t.dataset.apercu)}"><pre class="texte">${esc(infos[2] || "")}</pre>`);
  }
  if (t.dataset.valider) {
    try { await api(`/api/valider/${t.dataset.valider}`, { json: {} }); vueAujourdhui(); } catch (err) { erreur(err); }
  }
});

VUES.aujourdhui = vueAujourdhui;
