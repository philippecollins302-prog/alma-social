/* Calendrier — le mois par marque, et la proposition du 25 (la seule chose
 * qu'on « valide » : sans réponse au 1er, elle s'applique). */
"use strict";

function titreCreneau(s) { return s.pilier || (s.sujet || "").split(" — ")[0] || "Publication"; }
function etatCreneau(s) {
  if (s.source === "campagne" && (s.statut === "libre" || s.statut === "manque"))
    return "en attente d'une photo (sinon une carte à la charte)";
  return { libre: "en attente d'une photo", rempli: "prête", publie: "publiée", manque: "pas de photo",
           vide: "laissé vide", annule: "annulé" }[s.statut] || s.statut;
}

async function vueCalendrier(mois = "") {
  const ou = $("#v-calendrier");
  ou.innerHTML = `<div class="entete-vue"><h1>Calendrier</h1></div><div class="filtres" id="cal-filtres"></div><div id="cal"></div>`;
  const marqueId = filtres($("#cal-filtres"), "calendrier", () => vueCalendrier(), false);
  const cal = $("#cal");
  chargement(cal);
  try {
    const j = await api(`/api/calendrier?marque=${encodeURIComponent(marqueId)}${mois ? "&mois=" + mois : ""}`);
    const [a, m] = j.mois.split("-").map(Number);
    const prec = m === 1 ? `${a - 1}-12` : `${a}-${String(m - 1).padStart(2, "0")}`;
    const suiv = m === 12 ? `${a + 1}-01` : `${a}-${String(m + 1).padStart(2, "0")}`;
    const titre = new Date(a, m - 1, 1).toLocaleDateString("fr-FR", { month: "long", year: "numeric" });
    const ps = j.plan_suivant;
    cal.dataset.plan = JSON.stringify(ps ? ps.content : []);
    cal.dataset.marque = marqueId;
    cal.innerHTML = `
      ${ps && ps.status === "propose" ? `<section class="carte" style="border-color:var(--or)"><span class="etiquette or">Proposition du Stratège</span>
        <h3 style="margin-top:8px">Le mois prochain est prêt</h3>
        <p class="doux petit">${ps.content.length} créneau(x). Il s'appliquera le 1er, validé ou non.</p>
        <div class="actions"><button class="secondaire" data-voirplan="1">Le voir</button>
        <button class="secondaire" data-plan="${ps.id}">C'est bon</button></div></section>` : ""}
      <div class="ligne"><button class="secondaire" data-mois="${prec}">‹</button><h2 style="margin:0;text-transform:capitalize">${esc(titre)}</h2><button class="secondaire" data-mois="${suiv}">›</button></div>
      <p class="petit ${j.stock.jours_couverts < 7 ? "attention" : "doux"}">Stock : ${j.stock.banque} photo(s) en banque · ${j.stock.creneaux_vides} créneau(x) à remplir sur 3 semaines.</p>
      <section class="carte">${j.creneaux.map(s => {
        const d = new Date(s.jour + "T12:00:00");
        return `<div class="jour"><div class="date">${d.getDate()}<small>${JOURS[(d.getDay() + 6) % 7]}</small></div><div>
          ${s.etape ? `<span class="etiquette or">${esc(s.etape)}</span> ` : ""}<b>${esc(titreCreneau(s))}</b>
          <span class="doux petit">${s.heure ? "à " + esc(s.heure) : ""} · ${esc({ plan: "calendrier", depot: "dépôt", serie: "rendez-vous", campagne: "campagne", temps_fort: "temps fort" }[s.source] || s.source)}</span>
          ${s.etape && s.sujet && s.sujet !== titreCreneau(s) ? `<div class="petit">« ${esc(s.sujet)} »</div>` : ""}
          <div class="petit ${s.statut === "manque" ? "attention" : "doux"}">${esc(etatCreneau(s))}
            ${s.publications.length ? " — " + s.publications.map(p => esc(p.reseau)).join(", ") : ""}</div>
        </div></div>`;
      }).join("") || '<div class="vide"><b>Rien ce mois-ci.</b>Le plan se remplit tout seul au fil des dépôts.</div>'}</section>
      <details class="carte" id="moments" data-marque="${esc(marqueId)}"><summary>Quand publier, et avec quoi</summary><div id="moments-corps"></div></details>
      <details class="carte"><summary>Une carte sans photo</summary>
        <p class="doux petit">Un visuel à la charte : une annonce, un compte à rebours.</p>
        <input class="champ" id="c-titre" maxlength="40" placeholder="Titre (court)">
        <input class="champ" id="c-sous" maxlength="120" placeholder="Sous-titre">
        <input class="champ" id="c-detail" maxlength="80" placeholder="Détail (date, lieu…)">
        <button class="secondaire" data-carte="${esc(marqueId)}">Créer et programmer</button></details>`;
  } catch (err) { cal.innerHTML = `<p class="erreur">${esc(err.message)}</p>`; }
}

/* Les sept meilleurs créneaux par réseau, la réserve de la banque, les temps forts. */
async function chargerMoments(marqueId) {
  const ou = $("#moments-corps");
  chargement(ou);
  try {
    const j = await api(`/api/moments?marque=${encodeURIComponent(marqueId)}`);
    const JOURS_L = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"];
    const b = j.banque;
    ou.innerHTML = `
      <p class="petit doux">Chaque réseau a sa semaine. ${100 - j.exploration} % des publications partent sur ces créneaux ;
        ${j.exploration} % sur une heure moins sûre, pour apprendre ce que les chiffres ne disent pas encore.</p>
      ${j.reseaux.map(r => `<div class="moments-reseau"><b>${esc(r.nom)}</b>
        <span class="petit doux">${r.appris ? "appris sur vos publications" : "repères du secteur, en attendant vos chiffres"}</span>
        <div class="puces-heures">${r.creneaux.map(c => `<span class="puce-heure" style="--n:${c.note}">${JOURS_L[c.jour]} ${esc(c.heure)}<i>${c.note}</i></span>`).join("")}</div></div>`).join("")
        || '<p class="petit doux">Aucun réseau relié pour cette marque.</p>'}
      <h3>La réserve</h3>
      <div class="bilan">
        <div><b>${b.gagnants}</b><span>gagnant${b.gagnants > 1 ? "s" : ""} à reprendre</span></div>
        <div><b>${b.seconde_chance}</b><span>seconde${b.seconde_chance > 1 ? "s" : ""} chance${b.seconde_chance > 1 ? "s" : ""}</span></div>
        <div><b>${b.evergreen}</b><span>intemporel${b.evergreen > 1 ? "s" : ""}</span></div>
      </div>
      <p class="petit doux">Une publication qui a déçu (sous 60 % de la médiane) mais que le Critique jugeait bonne repart une fois,
        recadrée, trois semaines plus tard. Un gagnant ressort après 45 jours sur un pilier intemporel.</p>
      <h3>Temps forts à venir</h3>
      ${j.temps_forts.map(t => `<p class="petit"><b>${esc(new Date(t.jour + "T12:00:00").toLocaleDateString("fr-FR", { day: "numeric", month: "long" }))} — ${esc(t.nom)}</b><br><span class="doux">${esc(t.consigne)}</span></p>`).join("")
        || '<p class="petit doux">Aucun dans les deux mois.</p>'}
      <p class="petit doux">À dater avant d'entrer au calendrier : ${esc(j.a_confirmer.join(" · "))}.</p>`;
  } catch (err) { ou.innerHTML = `<p class="erreur">${esc(err.message)}</p>`; }
}

$("#v-calendrier").addEventListener("toggle", e => {
  if (e.target.id === "moments" && e.target.open && !$("#moments-corps").childElementCount) chargerMoments(e.target.dataset.marque);
}, true);

$("#v-calendrier").addEventListener("click", async e => {
  const t = e.target.closest("button"), cal = $("#cal");
  if (!t || !cal) return;
  try {
    if (t.dataset.mois) vueCalendrier(t.dataset.mois);
    if (t.dataset.plan) { await api(`/api/plan/${t.dataset.plan}/valider`, { json: {} }); vueCalendrier(); }
    if (t.dataset.voirplan) {
      const p = JSON.parse(cal.dataset.plan || "[]");
      dire(`<h3>Le mois prochain</h3>${p.map(x => `<p><b>${esc(x.jour_lisible)}</b> — ${esc(x.sujet.split(" — ")[0])} <span class="doux petit">${esc(x.heure)} · ${esc(x.reseaux.join(", "))}</span>${x.pourquoi ? `<br><span class="petit doux">${esc(x.pourquoi)}</span>` : ""}</p>`).join("")}`);
    }
    if (t.dataset.carte) {
      const r = await api("/api/carte", { json: { marque: t.dataset.carte, titre: $("#c-titre").value, sous_titre: $("#c-sous").value, detail: $("#c-detail").value } });
      dire(r.place ? "<p>Carte créée et programmée.</p>" : "<p>Carte créée : elle attend en banque le prochain créneau libre.</p>");
      vueCalendrier();
    }
  } catch (err) { erreur(err); }
});

VUES.calendrier = vueCalendrier;
