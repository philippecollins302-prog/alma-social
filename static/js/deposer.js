/* Déposer — le seul geste : la photo, une phrase si on veut, la marque.
 *
 * La photo est d'abord rangée dans le téléphone (attente.js), puis envoyée :
 * un sous-sol sans réseau ne perd rien. Après le tap sur la marque, plus
 * aucune action : la suite se fait seule, et « Derniers dépôts » raconte ce
 * qu'elle devient.
 */
"use strict";

const CONSEILS = {
  food: "Vue de dessus ou à 45°, lumière du jour, le bowl entier dans le cadre.",
  btp: "Plan large puis détail, même angle qu'avant les travaux si possible.",
  b2b: "Des gens réels, un lieu réel, la lumière derrière vous.",
};

function deposerInit() {
  $("#fichiers").addEventListener("change", e => {
    ETAT.choisis = [...e.target.files];
    e.target.value = "";
    $("#apercus").innerHTML = ETAT.choisis.map(f => `<img alt="" src="${URL.createObjectURL(f)}">`).join("");
    $("#choisir").classList.toggle("pret", ETAT.choisis.length > 0);
    $("#dictee").hidden = !ETAT.choisis.length;
    const n = ETAT.choisis.length;
    $("#choisir-texte").textContent = n ? `${n} photo${n > 1 ? "s" : ""} prête${n > 1 ? "s" : ""}` : "Prendre ou choisir des photos";
    dessinerMarques();
  });
  dicter($("#micro"), $("#note"));
  $("#marques").addEventListener("click", async e => {
    const b = e.target.closest("[data-marque]");
    if (!b || !ETAT.choisis.length) return;
    const m = b.dataset.marque, fichiers = ETAT.choisis, note = $("#note").value.trim();
    ETAT.choisis = []; $("#note").value = ""; $("#dictee").hidden = true;
    $("#apercus").innerHTML = ""; $("#choisir").classList.remove("pret");
    $("#choisir-texte").textContent = "Prendre ou choisir des photos";
    dessinerMarques();
    for (const f of fichiers) await Attente.ajouter(m, f, note);
    await afficherEnvois();
    Attente.vider(suiviEnvoi).then(() => { afficherEnvois(); derniersDepots(); });
  });
  $("#envois").addEventListener("click", async e => {
    const r = e.target.dataset.oublier;
    if (r) { await Attente.retirer(r); afficherEnvois(); }
  });
  $("#derniers").addEventListener("click", actionPhoto);
  addEventListener("online", () => Attente.vider(suiviEnvoi).then(afficherEnvois));
  setInterval(() => navigator.onLine && Attente.vider(suiviEnvoi), 30000);
  Attente.vider(suiviEnvoi).then(afficherEnvois);
}

function dessinerMarques() {
  const vide = ETAT.choisis.length === 0;
  $("#consigne").textContent = vide ? "Choisissez une photo, puis touchez la marque" : "Touchez la marque — c'est tout";
  $("#marques").innerHTML = ETAT.marques.map(m => `
    <button class="marque" data-marque="${esc(m.id)}" ${vide ? "disabled" : ""}
      style="background:${esc(m.couleur)};border-bottom:5px solid ${esc(m.accent)}">
      ${m.logo ? `<img class="logo" alt="" src="${esc(m.logo)}">` : `<i class="mono">${esc(m.nom.replace(/^Groupe /, "").slice(0, 1))}</i>`}
      <b>${esc(m.nom.split(" — ")[0])}</b>${m.nom.includes(" — ") ? `<small>${esc(m.nom.split(" — ")[1])}</small>` : ""}
      <small>${m.en_pause ? "⏸ en pause — la photo attendra" : esc(m.reseaux.filter(r => r.etat === "actif").length ? `${m.reseaux.filter(r => r.etat === "actif").length} réseaux reliés` : "")}</small>
    </button>`).join("");
  const secteurs = new Set(ETAT.marques.map(m => m.secteur));
  $("#conseil").textContent = secteurs.size === 1 ? (CONSEILS[[...secteurs][0]] || CONSEILS.btp)
    : "Lumière du jour, le sujet au centre, téléphone stable.";
}

const SUIVIS = {};
function suiviEnvoi(e, code) {
  SUIVIS[e.ref] = e;
  if (code === 401) montrerPorte();
  afficherEnvois();
}

async function afficherEnvois() {
  const enFile = await Attente.tous().catch(() => []);
  const refs = new Set(enFile.map(e => e.ref));
  const finis = Object.values(SUIVIS).filter(e => !refs.has(e.ref) && (e.etat === "recue" || e.etat === "deja"));
  $("#envois").innerHTML = [
    ...enFile.map(e => {
      const t = e.etat === "refuse" ? `<span class="erreur">Refusée : ${esc(e.erreur)}</span>`
        : e.etat === "envoi" ? "Envoi…" : navigator.onLine ? "En attente d'envoi" : "Hors ligne : partira au retour du réseau";
      return `<div class="envoi"><img alt="" src="${URL.createObjectURL(e.blob)}"><div>${puce(e.marque)}<b>${esc(nomMarque(e.marque))}</b><br>${t}</div>
        ${e.etat === "refuse" ? `<button class="secondaire" data-oublier="${esc(e.ref)}">Oublier</button>` : ""}</div>`;
    }),
    ...finis.slice(-4).reverse().map(e => `<div class="envoi"><span class="chiffre or" style="font-size:30px">✓</span><div>${puce(e.marque)}<b>${esc(nomMarque(e.marque))}</b><br>
      <span class="ok">${e.etat === "deja" ? "Déjà reçue" : "Reçue"}</span> <span class="doux">— la suite se fait seule</span></div></div>`),
  ].join("");
}

async function derniersDepots() {
  const ou = $("#derniers");
  try {
    const j = await api("/api/photos?limite=8");
    ou.dataset.photos = JSON.stringify(j.photos.flatMap(p => p.publications.map(x => [x.id, x.reseau, x.texte, x.format])));
    ou.innerHTML = j.photos.map(p => `
      <article class="carte photo">
        <img alt="" loading="lazy" src="${esc(p.vignette)}">
        <div>
          <div class="ligne"><span>${puce(p.marque)}<b>${esc(nomMarque(p.marque))}</b></span><span class="doux petit">${esc(quand(p.depose_le))}</span></div>
          ${p.sujet ? `<div class="petit">${esc(p.sujet)}</div>` : ""}
          <div class="petit ${p.statut === "refuse" || p.statut === "quarantaine" ? "attention" : "doux"}">${esc(p.etat)}</div>
          <ul class="pubs">${p.publications.map(x => `<li>
            <span class="etat-${esc(x.statut)}">${esc(x.reseau)} — ${esc(x.etat)}</span>
            <span class="doux"> ${esc(quand(x.quand))}</span>
            ${x.lien ? ` · <a href="${esc(x.lien)}" target="_blank" rel="noopener">voir</a>` : ""}
            ${x.apercu ? ` · <a href="#" data-apercu="${x.id}">aperçu</a>` : ""}
            ${x.erreur ? `<div class="doux petit">${esc(x.erreur)}</div>` : ""}</li>`).join("")}</ul>
          ${p.statut !== "retire" ? `<div class="actions">
            <button class="secondaire" data-retirer="${p.id}">Retirer partout</button>
            ${p.sorte === "photo" ? `<button class="secondaire" data-flouter="${p.id}">${p.floutee ? "Floutée ✓" : "Flouter visages"}</button>` : ""}
          </div>` : ""}
        </div>
      </article>`).join("") || '<div class="vide"><b>Rien encore.</b>La première photo déposée apparaîtra ici, avec ce qu\'elle devient.</div>';
  } catch (err) { ou.innerHTML = `<p class="erreur">${esc(err.message)}</p>`; }
}

/* Aperçu, retrait, floutage : partagés avec Aujourd'hui. */
async function actionPhoto(e) {
  const t = e.target;
  if (t.dataset.apercu) {
    e.preventDefault();
    const infos = JSON.parse(t.closest("[data-photos]")?.dataset.photos || "[]").find(x => String(x[0]) === t.dataset.apercu) || [];
    return montrerApercu(t.dataset.apercu, infos[1], infos[2], infos[3]);
  }
  try {
    if (t.dataset.retirer) {
      if (!confirm("Retirer cette photo partout ? Ce qui est programmé est annulé ; ce qui est sorti est retiré là où le réseau le permet.")) return;
      const r = await api(`/api/photo/${t.dataset.retirer}/retirer`, { json: {} });
      const main = r.a_la_main.map(x => `<li>${esc(x.reseau)} : ${x.lien ? `<a href="${esc(x.lien)}" target="_blank" rel="noopener">ouvrir et supprimer à la main</a>` : "à supprimer à la main dans l'appli"}</li>`).join("");
      dire(`<h3>Retirée</h3><p>Annulées : ${esc(r.annules.join(", ") || "aucune")}<br>Retirées : ${esc(r.retires.join(", ") || "aucune")}</p>
        ${main ? `<p class="attention">Ces réseaux ne permettent pas le retrait automatique :</p><ul>${main}</ul>` : ""}
        ${r.erreurs.length ? `<p class="erreur">${esc(r.erreurs.join(" ; "))}</p>` : ""}`);
      derniersDepots();
    }
    if (t.dataset.flouter) {
      const r = await api(`/api/photo/${t.dataset.flouter}/flouter`, { json: {} });
      dire(r.boites ? `<p>${r.boites} zone(s) floutée(s). ${r.reprogrammes} publication(s) à venir repartiront floutées.</p>
        ${r.deja_sortis ? `<p class="attention">${r.deja_sortis} publication(s) étaient déjà sorties : « Retirer partout » si besoin.</p>` : ""}`
        : "<p>Aucun visage ni plaque repéré sur cette photo.</p>");
      derniersDepots();
    }
  } catch (err) { erreur(err); }
}

VUES.deposer_init = deposerInit;
VUES.deposer = () => { dessinerMarques(); afficherEnvois(); derniersDepots(); };
