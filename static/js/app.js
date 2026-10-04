/* ALMA SOCIAL — l'écran. Vanilla, une passe d'innerHTML par vue, esc() sur tout ce qui vient du serveur.
 *
 * Le geste qui compte : choisir des photos, toucher la marque. C'est tout.
 * Le reste (photos, résultats, agenda, réglages) sert à voir et, rarement, à arrêter.
 */
"use strict";

const $ = s => document.querySelector(s);
const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const ETAT = { moi: null, marques: [], choisis: [], filtre: "", vue: "deposer" };
/* Ce que deviendra le créneau. Une étape de campagne sans photo n'est pas un
   trou : une carte à la charte part à sa place — l'écran le dit, pour qu'on ne
   croie pas devoir trouver une photo coûte que coûte. */
function titreCreneau(s) {
  return s.pilier || (s.sujet || "").split(" — ")[0] || "Publication";
}

function etatCreneau(s) {
  if (s.source === "campagne" && (s.statut === "libre" || s.statut === "manque"))
    return "en attente d'une photo (sinon une carte à la charte)";
  return { libre: "en attente d'une photo", rempli: "prête", publie: "publiée", manque: "pas de photo",
           vide: "laissé vide", annule: "annulé" }[s.statut] || s.statut;
}

const JOURS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."];

async function api(chemin, options = {}) {
  const o = { credentials: "same-origin", ...options, headers: { "X-Alma": "1", ...(options.headers || {}) } };
  if (o.json !== undefined) { o.body = JSON.stringify(o.json); o.headers["Content-Type"] = "application/json"; o.method = o.method || "POST"; }
  const r = await fetch(chemin, o);
  if (r.status === 401) { montrerPorte(); throw new Error("Session expirée"); }
  const j = r.headers.get("content-type")?.includes("json") ? await r.json() : await r.text();
  if (!r.ok) throw new Error((j && j.erreur) || `Erreur ${r.status}`);
  return j;
}

function quand(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const auj = new Date(); const dem = new Date(); dem.setDate(auj.getDate() + 1);
  // Toujours l'heure de Paris, où que soit le téléphone : c'est celle des réseaux visés.
  const P = { timeZone: "Europe/Paris" };
  const h = d.toLocaleTimeString("fr-FR", { ...P, hour: "2-digit", minute: "2-digit" });
  const jour = x => x.toLocaleDateString("fr-FR", P);
  if (jour(d) === jour(auj)) return `aujourd'hui ${h}`;
  if (jour(d) === jour(dem)) return `demain ${h}`;
  return `${d.toLocaleDateString("fr-FR", { ...P, weekday: "short", day: "numeric", month: "short" })} ${h}`;
}

function dire(html) { $("#dialogue-corps").innerHTML = html; $("#dialogue").showModal(); }

/* ── La porte ───────────────────────────────────────────────────────── */
function montrerPorte() { $("#appli").hidden = true; $("#porte").hidden = false; $("#code").focus(); }

$("#f-porte").addEventListener("submit", async e => {
  e.preventDefault();
  $("#porte-erreur").textContent = "";
  try {
    await api("/api/connexion", { json: { code: $("#code").value } });
    $("#code").value = "";
    await demarrer();
  } catch (err) { $("#porte-erreur").textContent = err.message; }
});

async function demarrer() {
  try { ETAT.moi = await api("/api/moi"); } catch (_) { return montrerPorte(); }
  ETAT.marques = ETAT.moi.marques;
  $("#porte").hidden = true; $("#appli").hidden = false;
  bandeau(); dessinerMarques(); afficherEnvois();
  Attente.vider(suiviEnvoi).then(afficherEnvois);
  const p = new URLSearchParams(location.search);
  if (p.get("relie")) { history.replaceState(null, "", "/"); aller("reglages"); verifierComptes(p.get("relie")); }
}

function bandeau() {
  const m = ETAT.moi, b = [];
  if (m.arret_general) b.push('<span class="pastille erreur">⛔ Arrêt général</span>');
  if (m.bac_a_sable) b.push('<span class="pastille attention">🧪 Bac à sable : rien ne sort</span>');
  const pauses = ETAT.marques.filter(x => x.en_pause).length;
  if (pauses) b.push(`<span class="pastille attention">⏸ ${pauses} marque${pauses > 1 ? "s" : ""} en pause</span>`);
  $("#bandeau").innerHTML = b.join("") || `<span class="doux">${esc(m.utilisateur.nom)}</span>`;
}

/* ── 1. Déposer ─────────────────────────────────────────────────────── */
$("#fichiers").addEventListener("change", e => {
  ETAT.choisis = [...e.target.files];
  e.target.value = "";
  $("#apercus").innerHTML = ETAT.choisis.map(f => `<img alt="" src="${URL.createObjectURL(f)}">`).join("");
  $("#choisir").classList.toggle("pret", ETAT.choisis.length > 0);
  $("#choisir-texte").textContent = ETAT.choisis.length
    ? `${ETAT.choisis.length} photo${ETAT.choisis.length > 1 ? "s" : ""} prête${ETAT.choisis.length > 1 ? "s" : ""} — touchez la marque`
    : "Prendre ou choisir des photos";
  dessinerMarques();
});

function dessinerMarques() {
  const vide = ETAT.choisis.length === 0;
  $("#consigne").textContent = vide ? "Choisissez d'abord une photo, puis touchez la marque." : "Touchez la marque :";
  $("#marques").innerHTML = ETAT.marques.map(m => `
    <button class="marque" data-marque="${esc(m.id)}" style="background:${esc(m.couleur)};border-bottom:6px solid ${esc(m.accent)}" ${vide ? "disabled" : ""}>
      ${m.logo ? `<img alt="" src="${esc(m.logo)}">` : `<i class="mono">${esc(m.nom.replace(/^Groupe /, "").slice(0, 1))}</i>`}
      <span>${esc(m.nom)}</span>
      <small>${m.en_pause ? "⏸ en pause — la photo attendra en banque" : ""}</small>
    </button>`).join("");
}

$("#marques").addEventListener("click", async e => {
  const b = e.target.closest("[data-marque]");
  if (!b || !ETAT.choisis.length) return;
  const marque = b.dataset.marque;
  const fichiers = ETAT.choisis; ETAT.choisis = [];
  $("#apercus").innerHTML = ""; $("#choisir").classList.remove("pret");
  $("#choisir-texte").textContent = "Prendre ou choisir des photos";
  dessinerMarques();
  for (const f of fichiers) await Attente.ajouter(marque, f);
  await afficherEnvois();
  Attente.vider(suiviEnvoi).then(afficherEnvois);
});

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
  const nom = id => (ETAT.marques.find(m => m.id === id) || {}).nom || id;
  const lignes = [
    ...enFile.map(e => {
      const texte = e.etat === "refuse" ? `<span class="erreur">Refusée : ${esc(e.erreur)}</span>`
        : e.etat === "envoi" ? "Envoi…" : navigator.onLine ? "En attente d'envoi" : "Hors ligne : partira au retour du réseau";
      return `<div class="envoi"><img alt="" src="${URL.createObjectURL(e.blob)}"><div><b>${esc(nom(e.marque))}</b><br>${texte}</div>
        ${e.etat === "refuse" ? `<button class="secondaire" data-oublier="${esc(e.ref)}">Oublier</button>` : ""}</div>`;
    }),
    ...finis.slice(-6).reverse().map(e => `<div class="envoi"><span class="grand-emoji">✓</span><div><b>${esc(nom(e.marque))}</b><br>
      <span class="ok">${e.etat === "deja" ? "Déjà reçue" : "Reçue"}</span> <span class="doux">— la suite se fait seule</span></div></div>`),
  ];
  $("#envois").innerHTML = lignes.join("");
}

$("#envois").addEventListener("click", async e => {
  const r = e.target.dataset.oublier;
  if (r) { await Attente.retirer(r); afficherEnvois(); }
});
addEventListener("online", () => Attente.vider(suiviEnvoi).then(afficherEnvois));
setInterval(() => navigator.onLine && Attente.vider(suiviEnvoi), 30000);

/* ── Navigation ─────────────────────────────────────────────────────── */
document.querySelector(".onglets").addEventListener("click", e => {
  const b = e.target.closest("[data-vue]");
  if (b) aller(b.dataset.vue);
});

function aller(vue) {
  ETAT.vue = vue;
  document.querySelectorAll(".onglets button").forEach(b => b.classList.toggle("actif", b.dataset.vue === vue));
  document.querySelectorAll(".vue").forEach(v => v.hidden = v.id !== "v-" + vue);
  scrollTo(0, 0);
  ({ photos: vuePhotos, resultats: vueResultats, agenda: vueAgenda, reglages: vueReglages })[vue]?.();
}

function filtres(ou, choix, actuel, rappel, avecToutes = true) {
  const boutons = (avecToutes ? [{ id: "", nom: "Toutes" }] : []).concat(ETAT.marques)
    .map(m => `<button data-f="${esc(m.id)}" class="${m.id === actuel ? "actif" : ""}">${esc(m.nom)}</button>`);
  $(ou).innerHTML = boutons.join("");
  $(ou).onclick = e => { const b = e.target.closest("[data-f]"); if (b) rappel(b.dataset.f); };
}

/* ── 2. Mes photos ──────────────────────────────────────────────────── */
async function vuePhotos(filtre = ETAT.filtre) {
  ETAT.filtre = filtre;
  filtres("#filtre-photos", ETAT.marques, filtre, vuePhotos);
  const ou = $("#liste-photos");
  ou.innerHTML = '<p class="doux">Chargement…</p>';
  try {
    const j = await api("/api/photos" + (filtre ? `?marque=${encodeURIComponent(filtre)}` : ""));
    ou.innerHTML = j.photos.map(p => `
      <article class="carte photo">
        <img alt="" loading="lazy" src="${esc(p.vignette)}">
        <div>
          <div class="ligne"><b>${esc(nomMarque(p.marque))}</b><span class="doux petit">${esc(quand(p.depose_le))}</span></div>
          <div class="${p.statut === "refuse" || p.statut === "quarantaine" ? "attention" : ""}">${esc(p.etat)}</div>
          ${p.simule ? '<div class="doux petit">Lecture simulée : la clé du modèle n\'est pas posée.</div>' : ""}
          <ul class="pubs">${p.publications.map(x => `<li>
            <span class="etat-${esc(x.statut)}">${esc(x.reseau)} — ${esc(x.etat)}</span>
            <span class="doux"> ${esc(quand(x.quand))}</span>
            ${x.lien ? ` · <a href="${esc(x.lien)}" target="_blank" rel="noopener">voir</a>` : ""}
            ${x.apercu ? ` · <a href="#" data-apercu="${x.id}">aperçu</a>` : ""}
            ${x.erreur ? `<div class="doux petit">${esc(x.erreur)}</div>` : ""}</li>`).join("")}</ul>
          ${p.statut !== "retire" ? `<div class="actions">
            <button class="danger" data-retirer="${p.id}">Retirer partout</button>
            ${p.sorte === "photo" ? `<button class="secondaire" data-flouter="${p.id}">${p.floutee ? "Floutée ✓" : "Flouter visages et plaques"}</button>` : ""}
          </div>` : ""}
        </div>
      </article>`).join("") || '<p class="doux">Aucune photo pour l\'instant.</p>';
    ou.dataset.photos = JSON.stringify(j.photos.flatMap(p => p.publications.map(x => [x.id, x.reseau, x.texte])));
  } catch (err) { ou.innerHTML = `<p class="erreur">${esc(err.message)}</p>`; }
}

const nomMarque = id => (ETAT.marques.find(m => m.id === id) || {}).nom || id;

$("#liste-photos").addEventListener("click", async e => {
  const t = e.target;
  if (t.dataset.apercu) {
    e.preventDefault();
    const infos = JSON.parse($("#liste-photos").dataset.photos || "[]").find(x => String(x[0]) === t.dataset.apercu) || [];
    return dire(`<h3>${esc(infos[1] || "")}</h3><img alt="" src="/apercu/${esc(t.dataset.apercu)}"><pre class="texte">${esc(infos[2] || "")}</pre>`);
  }
  if (t.dataset.retirer) {
    if (!confirm("Retirer cette photo partout ? Ce qui est programmé est annulé ; ce qui est sorti est retiré là où le réseau le permet.")) return;
    try {
      const r = await api(`/api/photo/${t.dataset.retirer}/retirer`, { json: {} });
      const main = r.a_la_main.map(x => `<li>${esc(x.reseau)} : ${x.lien ? `<a href="${esc(x.lien)}" target="_blank" rel="noopener">ouvrir et supprimer à la main</a>` : "à supprimer à la main dans l'appli"}</li>`).join("");
      dire(`<h3>Retirée</h3><p>Annulées : ${esc(r.annules.join(", ") || "aucune")}<br>Retirées : ${esc(r.retires.join(", ") || "aucune")}</p>
        ${main ? `<p class="attention">Ces réseaux ne permettent pas le retrait automatique :</p><ul>${main}</ul>` : ""}
        ${r.erreurs.length ? `<p class="erreur">${esc(r.erreurs.join(" ; "))}</p>` : ""}`);
      vuePhotos();
    } catch (err) { dire(`<p class="erreur">${esc(err.message)}</p>`); }
  }
  if (t.dataset.flouter) {
    try {
      const r = await api(`/api/photo/${t.dataset.flouter}/flouter`, { json: {} });
      dire(r.boites ? `<p>${r.boites} zone(s) floutée(s). ${r.reprogrammes} publication(s) à venir repartiront floutées.</p>
        ${r.deja_sortis ? `<p class="attention">${r.deja_sortis} publication(s) étaient déjà sorties : « Retirer partout » si besoin.</p>` : ""}`
        : "<p>Aucun visage ni plaque repéré sur cette photo.</p>");
      vuePhotos();
    } catch (err) { dire(`<p class="erreur">${esc(err.message)}</p>`); }
  }
});

/* ── 3. Résultats ───────────────────────────────────────────────────── */
async function vueResultats() {
  $("#tableau").innerHTML = '<p class="doux">Chargement…</p>';
  try {
    const [t, al, av, bo] = await Promise.all([api("/api/tableau"), api("/api/alertes"), api("/api/avis"), api("/api/boite")]);
    const avisDur = av.avis.filter(a => a.status === "alerte");
    const messages = bo.messages.filter(m => m.status === "alerte");
    const recentes = al.alertes.filter(a => !a.read_at).slice(0, 5);
    $("#a-traiter").innerHTML = (avisDur.length || messages.length || recentes.length) ? `<section class="carte">
      <h2>À traiter</h2>
      ${avisDur.map(a => `<div class="carte"><b>${esc(nomMarque(a.brand_id))} — ${"★".repeat(a.rating)}${"☆".repeat(5 - a.rating)}</b>
        <p>${esc(a.text)}</p><p class="doux petit">Brouillon de réponse :</p>
        <textarea class="champ" rows="4" id="avis-${a.id}">${esc(a.draft)}</textarea>
        <button class="gros" data-avis="${a.id}">Envoyer cette réponse</button></div>`).join("")}
      ${messages.map(m => `<div class="carte"><b>${esc(nomMarque(m.brand_id))} — ${esc(m.category)}</b> <span class="doux">${esc(m.author)}</span>
        <p>${esc(m.text)}</p><textarea class="champ" rows="3" id="msg-${m.id}" placeholder="Votre réponse"></textarea>
        <button class="secondaire" data-message="${m.id}">Répondre</button></div>`).join("")}
      ${recentes.map(a => `<p class="${a.level === "info" ? "" : "attention"}"><b>${esc(a.subject)}</b><br>
        <span class="petit doux">${esc((a.body || "").split("\n")[0])}</span></p>`).join("")}
    </section>` : "";
    $("#tableau").innerHTML = (t.bac_a_sable ? '<p class="attention">🧪 Bac à sable : les publications sont simulées et comptées à part.</p>' : "")
      + t.marques.map(x => {
        const c = x.chiffre, food = x.marque.secteur === "food";
        const vues = x.audience.reduce((s, a) => s + a.vues, 0);
        return `<section class="carte">
          <div class="ligne"><h2>${esc(x.marque.nom)}</h2>${x.en_pause ? '<span class="attention">⏸ en pause</span>' : ""}</div>
          <div class="ligne"><div><div class="chiffre">${c.clients}</div><div class="doux">client${c.clients > 1 ? "s" : ""} en ${t.jours} jours</div></div>
            <div class="petit doux" style="text-align:right">${c.par_type.devis} devis · ${c.par_type.commande} commandes · ${c.par_type.appel} appels<br>
            ${c.clics} clics${food ? ` · ${c.clics_commande} vers les apps` : ""}</div></div>
          ${c.top.length ? `<ol class="petit">${c.top.map(p => `<li><b>${p.clients}</b> — ${esc(p.texte.split("\n")[0])}</li>`).join("")}</ol>` : '<p class="doux petit">Aucune demande rattachée à une publication pour l\'instant.</p>'}
          <p class="petit">Cette semaine : <b>${x.semaine}</b> publication(s) — cadence ${x.cadence[0]} à ${x.cadence[1]}.
            ${vues ? `Audience : ${vues} vues.` : ""}</p>
          <p class="petit ${x.stock.jours_couverts < 7 ? "attention" : "doux"}">Stock : ${x.stock.banque} photo(s) en banque, de quoi tenir ${x.stock.jours_couverts} jour(s).</p>
          ${x.piliers_oublies.length ? `<p class="petit attention">Rien depuis 3 semaines : ${esc(x.piliers_oublies.join(", "))}.</p>` : ""}
          <p class="petit doux">${esc(x.veille.phrase)}${x.veille.avis.avis ? ` · Google : ${x.veille.avis.moyenne} ★ (${x.veille.avis.avis})` : ""}</p>
          <details><summary>Noter un client (« il nous a vus sur… »)</summary>
            <select class="champ" id="lt-${esc(x.marque.id)}"><option value="${food ? "commande" : "devis"}">${food ? "Commande" : "Demande de devis"}</option><option value="appel">Appel</option>${food ? "" : '<option value="commande">Commande signée</option>'}</select>
            <input class="champ" id="ls-${esc(x.marque.id)}" placeholder="Vu où ? (Instagram, Google…)">
            <button class="secondaire" data-lead="${esc(x.marque.id)}">Enregistrer</button></details>
        </section>`;
      }).join("");
  } catch (err) { $("#tableau").innerHTML = `<p class="erreur">${esc(err.message)}</p>`; }
}

$("#v-resultats").addEventListener("click", async e => {
  const t = e.target;
  try {
    if (t.dataset.avis) { await api(`/api/avis/${t.dataset.avis}/repondre`, { json: { texte: $("#avis-" + t.dataset.avis).value } }); vueResultats(); }
    if (t.dataset.message) { await api(`/api/boite/${t.dataset.message}/repondre`, { json: { texte: $("#msg-" + t.dataset.message).value } }); vueResultats(); }
    if (t.dataset.lead) {
      const id = t.dataset.lead;
      await api("/api/leads", { json: { marque: id, type: $("#lt-" + id).value, canal: "manuel", source: $("#ls-" + id).value } });
      dire("<p>Client enregistré. Merci : c'est ce chiffre qui guide le reste.</p>"); vueResultats();
    }
  } catch (err) { dire(`<p class="erreur">${esc(err.message)}</p>`); }
});

/* ── 4. Agenda ──────────────────────────────────────────────────────── */
async function vueAgenda(marque = ETAT.agenda || ETAT.marques[0]?.id, mois = "") {
  ETAT.agenda = marque;
  filtres("#filtre-agenda", ETAT.marques, marque, m => vueAgenda(m), false);
  const ou = $("#agenda");
  ou.innerHTML = '<p class="doux">Chargement…</p>';
  try {
    const j = await api(`/api/calendrier?marque=${encodeURIComponent(marque)}${mois ? "&mois=" + mois : ""}`);
    const [a, m] = j.mois.split("-").map(Number);
    const prec = m === 1 ? `${a - 1}-12` : `${a}-${String(m - 1).padStart(2, "0")}`;
    const suiv = m === 12 ? `${a + 1}-01` : `${a}-${String(m + 1).padStart(2, "0")}`;
    const titre = new Date(a, m - 1, 1).toLocaleDateString("fr-FR", { month: "long", year: "numeric" });
    const ps = j.plan_suivant;
    ou.innerHTML = `
      ${ps && ps.status === "propose" ? `<section class="carte"><b>Le calendrier du mois prochain est prêt.</b>
        <p class="doux petit">Il s'appliquera le 1er, validé ou non. ${ps.content.length} créneau(x).</p>
        <button class="secondaire" data-plan="${ps.id}">Je l'ai vu, c'est bon</button>
        <button class="secondaire" data-voirplan="1">Le voir</button></section>` : ""}
      <div class="ligne"><button class="secondaire" data-mois="${prec}">‹</button><h2>${esc(titre)}</h2><button class="secondaire" data-mois="${suiv}">›</button></div>
      <p class="petit ${j.stock.jours_couverts < 7 ? "attention" : "doux"}">Stock : ${j.stock.banque} photo(s) en banque · ${j.stock.creneaux_vides} créneau(x) à remplir sur 3 semaines.</p>
      <section class="carte">${j.creneaux.map(s => {
        const d = new Date(s.jour + "T12:00:00");
        return `<div class="jour"><div class="date">${d.getDate()}<small>${JOURS[(d.getDay() + 6) % 7]}</small></div><div>
          ${s.etape ? `<span class="etiquette">${esc(s.etape)}</span> ` : ""}<b>${esc(titreCreneau(s))}</b>
          <span class="doux petit">${s.heure ? "à " + esc(s.heure) : ""} · ${esc({ plan: "calendrier", depot: "dépôt", serie: "rendez-vous", campagne: "campagne" }[s.source] || s.source)}</span>
          ${s.etape && s.sujet && s.sujet !== titreCreneau(s) ? `<div class="petit">« ${esc(s.sujet)} »</div>` : ""}
          <div class="petit ${s.statut === "manque" ? "attention" : "doux"}">${esc(etatCreneau(s))}
            ${s.publications.length ? " — " + s.publications.map(p => esc(p.reseau)).join(", ") : ""}</div>
        </div></div>`;
      }).join("") || '<p class="doux">Rien de prévu ce mois-ci.</p>'}</section>
      <section class="carte"><h3>Une carte sans photo</h3>
        <p class="doux petit">Un visuel aux couleurs de la marque : une annonce, un compte à rebours.</p>
        <input class="champ" id="c-titre" maxlength="40" placeholder="Titre (court)">
        <input class="champ" id="c-sous" maxlength="120" placeholder="Sous-titre">
        <input class="champ" id="c-detail" maxlength="80" placeholder="Détail (date, lieu…)">
        <button class="secondaire" data-carte="${esc(marque)}">Créer et programmer</button></section>`;
    ou.dataset.plan = JSON.stringify(ps ? ps.content : []);
    ou.dataset.marque = marque;
  } catch (err) { ou.innerHTML = `<p class="erreur">${esc(err.message)}</p>`; }
}

$("#agenda").addEventListener("click", async e => {
  const t = e.target, ou = $("#agenda");
  try {
    if (t.dataset.mois) vueAgenda(ou.dataset.marque, t.dataset.mois);
    if (t.dataset.plan) { await api(`/api/plan/${t.dataset.plan}/valider`, { json: {} }); vueAgenda(ou.dataset.marque); }
    if (t.dataset.voirplan) {
      const p = JSON.parse(ou.dataset.plan || "[]");
      dire(`<h3>Le mois prochain</h3>${p.map(x => `<p><b>${esc(x.jour_lisible)}</b> — ${esc(x.sujet.split(" — ")[0])} <span class="doux petit">${esc(x.heure)} · ${esc(x.reseaux.join(", "))}</span></p>`).join("")}`);
    }
    if (t.dataset.carte) {
      const r = await api("/api/carte", { json: { marque: t.dataset.carte, titre: $("#c-titre").value, sous_titre: $("#c-sous").value, detail: $("#c-detail").value } });
      dire(r.place ? "<p>Carte créée et programmée.</p>" : "<p>Carte créée : elle attend en banque le prochain créneau libre.</p>");
      vueAgenda(ou.dataset.marque);
    }
  } catch (err) { dire(`<p class="erreur">${esc(err.message)}</p>`); }
});

/* ── 5. Réglages ────────────────────────────────────────────────────── */
async function vueReglages() {
  const ou = $("#reglages");
  const moi = ETAT.moi = await api("/api/moi");
  ETAT.marques = moi.marques; bandeau();
  const pdg = moi.utilisateur.role === "pdg";
  let sante = null;
  try { sante = await api("/api/sante"); } catch (_) { /* la santé n'empêche pas les réglages */ }
  ou.innerHTML = `
    ${pdg ? `<section class="carte">
      <button class="stop ${moi.arret_general ? "leve" : ""}" data-arret="${moi.arret_general ? 0 : 1}">
        ${moi.arret_general ? "▶ Lever l'arrêt général" : "⛔ ARRÊT GÉNÉRAL — plus rien ne part"}</button>
      <p class="doux petit">${moi.arret_general ? "Rien ne part en ce moment, nulle part." : "Un geste, et plus aucune publication ne sort sur aucun réseau."}</p>
      <div class="ligne"><span>${moi.bac_a_sable ? "🧪 Bac à sable <b>ouvert</b> : tout est simulé." : "✅ Les publications sortent pour de vrai."}</span>
        <button class="secondaire" data-bac="${moi.bac_a_sable ? 0 : 1}">${moi.bac_a_sable ? "Ouvrir les vannes" : "Revenir au bac à sable"}</button></div>
    </section>` : ""}
    ${ETAT.marques.map(m => `<section class="carte">
      <div class="ligne"><h3>${esc(m.nom)}</h3>
        ${m.en_pause ? `<button class="secondaire" data-reprendre="${esc(m.id)}">▶ Reprendre</button>`
                     : `<button class="secondaire" data-pause="${esc(m.id)}">⏸ Pause 48 h</button>`}</div>
      ${m.en_pause ? `<p class="attention petit">En pause${m.pause_raison ? " (" + esc(m.pause_raison) + ")" : ""}. Rien ne repart sans « Reprendre ».</p>` : ""}
      <ul class="pubs">${m.reseaux.map(r => `<li class="ligne"><span>${esc(r.nom)} ${r.poignee ? `<span class="doux">${esc(r.poignee)}</span>` : ""}</span>
        <span class="${r.etat === "actif" ? "ok" : r.etat === "a_relier" ? "doux" : "attention"}">${esc({ actif: "relié", a_relier: "à relier", pause: "en pause", erreur: "à reconnecter" }[r.etat] || r.etat)}</span></li>`).join("")}</ul>
      <div class="actions"><button class="secondaire" data-relier="${esc(m.id)}">Relier les réseaux</button>
        <button class="secondaire" data-verifier="${esc(m.id)}">Vérifier</button>
        <button class="secondaire" data-comptes="${esc(m.id)}">Détails</button></div>
      ${m.a_completer.length ? `<details><summary class="petit">À compléter (${m.a_completer.length})</summary><ul class="petit">${m.a_completer.map(x => `<li>${esc(x)}</li>`).join("")}</ul></details>` : ""}
    </section>`).join("")}
    ${sante ? `<section class="carte"><h3>Santé</h3>
      <p class="petit">Horloge : ${sante.horloge.vivante ? '<span class="ok">tourne</span>' : '<span class="erreur">arrêtée</span>'}
        · ${sante.publies_24h} publication(s) en 24 h</p>
      ${Object.entries(sante.cles).map(([k, v]) => `<span class="etiquette" style="margin:2px">${v ? "✓" : "✗"} ${esc({ anthropic: "Claude", upload_post: "Upload-Post", webhook: "webhook", chiffrement: "chiffrement", nettoyage: "nettoyage", courrier: "courrier" }[k] || k)}</span>`).join("")}
      ${pdg && sante.cles.upload_post && !sante.cles.webhook ? `<p class="petit doux">Sans notifications, une publication longue est confirmée en interrogeant Upload-Post toutes les deux minutes ; un compte déconnecté se voit au prochain envoi.</p>
        <div class="actions"><button class="secondaire" data-webhook="1">Brancher les notifications d'Upload-Post</button></div>` : ""}
      ${sante.derniers_echecs.length ? `<p class="attention petit">Derniers échecs :</p><ul class="petit">${sante.derniers_echecs.map(x => `<li>${esc(nomMarque(x.brand_id))} · ${esc(x.platform)} : ${esc(x.error)}</li>`).join("")}</ul>` : '<p class="ok petit">Aucun échec récent.</p>'}
      ${sante.jetons_qui_expirent.length ? `<p class="attention petit">Jetons qui expirent : ${sante.jetons_qui_expirent.map(x => esc(x.marque + " " + x.reseau)).join(", ")}</p>` : ""}
      ${sante.file ? `<p class="doux petit">File : ${esc(JSON.stringify(sante.file.compte))}</p>` : ""}
    </section>` : ""}
    <section class="carte"><h3>Journal</h3>
      <p class="doux petit">Tout ce qui est sorti en votre nom : le texte exact, l'image, le réseau, l'heure. Non modifiable.</p>
      <div class="actions"><a class="secondaire" href="/api/journal?format=csv" download>Exporter (CSV)</a>
      ${pdg ? '<button class="secondaire" data-chaine="1">Vérifier l\'intégrité</button>' : ""}
      <a class="secondaire" href="/api/rapport" target="_blank">Aperçu du récapitulatif du lundi</a></div></section>
    <section class="carte"><button class="secondaire" data-sortir="1">Se déconnecter</button>
      <p class="doux petit">ALMA SOCIAL ${esc(moi.version)}</p></section>`;
}

async function verifierComptes(id) {
  try {
    const r = await api(`/api/comptes/verifier/${id}`, { json: {} });
    dire(`<h3>Réseaux de ${esc(nomMarque(id))}</h3>${Object.entries(r.relies).map(([k, v]) => `<p>${esc(k)} : <b>${esc({ actif: "relié", a_relier: "pas encore relié", erreur: "à reconnecter", pause: "en pause" }[v] || v)}</b></p>`).join("")}`);
    vueReglages();
  } catch (err) { dire(`<p class="erreur">${esc(err.message)}</p>`); }
}

$("#reglages").addEventListener("click", async e => {
  const t = e.target.closest("button");
  if (!t) return;
  const d = t.dataset;
  try {
    if (d.arret) {
      if (d.arret === "1" && !confirm("Arrêter TOUTES les publications, sur tous les réseaux, pour toutes les marques ?")) return;
      const r = await api("/api/arret", { json: { actif: d.arret === "1" } });
      if (!r.arret_general && r.repris) dire(`<p>${r.repris} publication(s) suspendue(s) repartent, étalées dans le temps.</p>`);
    }
    if (d.bac) {
      if (d.bac === "0" && !confirm("Ouvrir les vannes : les publications sortiront pour de vrai sur les comptes reliés. Continuer ?")) return;
      await api("/api/bac-a-sable", { json: { ouvert: d.bac === "1" } });
    }
    if (d.pause) await api(`/api/marque/${d.pause}/pause`, { json: {} });
    if (d.reprendre) await api(`/api/marque/${d.reprendre}/reprendre`, { json: {} });
    if (d.relier) { const r = await api(`/api/comptes/relier/${d.relier}`, { json: {} }); location.href = r.url; return; }
    if (d.verifier) return verifierComptes(d.verifier);
    if (d.webhook) { const r = await api("/api/webhook/brancher", { json: {} }); aller("reglages"); return dire(`<p class="ok">Notifications branchées sur ${esc(r.adresse)}.</p>`); }
    if (d.comptes) {
      const r = await api(`/api/comptes?marque=${encodeURIComponent(d.comptes)}`);
      return dire(`<h3>Comptes de ${esc(nomMarque(d.comptes))}</h3>${r.cle_presente ? "" : '<p class="attention">La clé Upload-Post n\'est pas encore posée dans l\'environnement.</p>'}
        ${r.comptes.map(c => `<div class="carte"><b>${esc(c.reseau)}</b> — ${esc(c.etat)} ${c.poignee ? esc(c.poignee) : ""}
          ${c.derniere_erreur ? `<p class="petit attention">${esc(c.derniere_erreur)}</p>` : ""}
          ${["facebook", "linkedin", "pinterest", "gbp"].includes(c.cle) ? `<input class="champ" data-option="${c.id}" data-cle="${{ facebook: "facebook_page_id", linkedin: "linkedin_page_id", pinterest: "pinterest_board_id", gbp: "gbp_location_id" }[c.cle]}"
             placeholder="${{ facebook: "Identifiant de la page Facebook", linkedin: "Identifiant de la page LinkedIn", pinterest: "Identifiant du tableau Pinterest", gbp: "Identifiant de l'établissement Google" }[c.cle]}"
             value="${esc(Object.values(c.options)[0] || "")}"><button class="secondaire" data-enregistrer="${c.id}">Enregistrer</button>` : ""}
          ${["pause", "erreur"].includes(c.etat) ? `<button class="secondaire" data-relancer="${c.id}">Relancer ce réseau</button>` : ""}</div>`).join("")}`);
    }
    if (d.chaine) { const r = await api("/api/journal/verifier"); return dire(r.intact ? `<p class="ok">Journal intact : ${r.lignes} lignes, aucune retouchée.</p>` : `<p class="erreur">Chaîne rompue à la ligne ${r.rompu_a}.</p>`); }
    if (d.sortir) { await api("/api/deconnexion", { json: {} }); return montrerPorte(); }
    vueReglages();
  } catch (err) { dire(`<p class="erreur">${esc(err.message)}</p>`); }
});

$("#dialogue").addEventListener("click", async e => {
  const t = e.target.closest("button");
  if (!t) return;
  try {
    if (t.dataset.enregistrer) {
      const champ = document.querySelector(`[data-option="${t.dataset.enregistrer}"]`);
      await api(`/api/comptes/${t.dataset.enregistrer}`, { json: { options: { [champ.dataset.cle]: champ.value.trim() } } });
      t.textContent = "Enregistré ✓";
    }
    if (t.dataset.relancer) { await api(`/api/comptes/${t.dataset.relancer}`, { json: { relancer: true } }); t.textContent = "Relancé ✓"; }
  } catch (err) { t.insertAdjacentHTML("afterend", `<p class="erreur">${esc(err.message)}</p>`); }
});

/* ── Hors ligne ─────────────────────────────────────────────────────── */
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
demarrer();
