/* ALMA SOCIAL — le socle de l'écran : outils, porte, navigation.
 *
 * Vanilla, une passe d'innerHTML par vue, esc() sur TOUT ce qui vient du
 * serveur. Les quartiers (deposer.js, aujourdhui.js…) se chargent dans
 * l'ordre de la page et enregistrent leur vue dans VUES ; demarrage.js lance
 * le tout en dernier.
 */
"use strict";

const $ = s => document.querySelector(s);
const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const ETAT = { moi: null, marques: [], choisis: [], vue: "deposer", filtres: {} };
const VUES = {};
const JOURS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."];
const P = { timeZone: "Europe/Paris" };

async function api(chemin, options = {}) {
  const o = { credentials: "same-origin", ...options, headers: { "X-Alma": "1", ...(options.headers || {}) } };
  if (o.json !== undefined) { o.body = JSON.stringify(o.json); o.headers["Content-Type"] = "application/json"; o.method = o.method || "POST"; }
  const r = await fetch(chemin, o);
  if (r.status === 401) { montrerPorte(); throw new Error("Session expirée"); }
  const j = r.headers.get("content-type")?.includes("json") ? await r.json() : await r.text();
  if (!r.ok) throw new Error((j && j.erreur) || `Erreur ${r.status}`);
  return j;
}

/* Toujours l'heure de Paris, où que soit le téléphone : c'est celle des réseaux visés. */
function quand(iso) {
  if (!iso) return "";
  const d = new Date(iso), auj = new Date(), dem = new Date(); dem.setDate(auj.getDate() + 1);
  const h = d.toLocaleTimeString("fr-FR", { ...P, hour: "2-digit", minute: "2-digit" });
  const jour = x => x.toLocaleDateString("fr-FR", P);
  if (jour(d) === jour(auj)) return `aujourd'hui ${h}`;
  if (jour(d) === jour(dem)) return `demain ${h}`;
  return `${d.toLocaleDateString("fr-FR", { ...P, weekday: "short", day: "numeric", month: "short" })} ${h}`;
}
const heure = iso => iso ? new Date(iso).toLocaleTimeString("fr-FR", { ...P, hour: "2-digit", minute: "2-digit" }) : "";
const euros = (n, d = 2) => (n ?? 0).toLocaleString("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d });

function dire(html) { $("#dialogue-corps").innerHTML = html; $("#dialogue").showModal(); }
function erreur(err) { dire(`<p class="erreur">${esc(err.message || err)}</p>`); }
const chargement = ou => { ou.innerHTML = '<p class="doux">Un instant…</p>'; };
const marque = id => ETAT.marques.find(m => m.id === id) || { id, nom: id, couleur: "#555", accent: "#999" };
const nomMarque = id => marque(id).nom;
const puce = id => `<span class="trait-marque" style="background:${esc(marque(id).couleur)}"></span>`;
const pdg = () => ETAT.moi?.utilisateur?.role === "pdg";

function noteCritique(n, juge) {
  if (n == null) return "";
  const titre = juge === "grille-locale" ? "Note de la grille locale (forme seulement)" : `Note du Critique (${juge || "modèle"})`;
  return `<span class="note ${n < 80 ? "moyen" : ""}" title="${esc(titre)}">✦ ${esc(n)}</span>`;
}

/* ── La porte ── */
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

async function rafraichirMoi() {
  ETAT.moi = await api("/api/moi");
  ETAT.marques = ETAT.moi.marques;
  bandeau();
}

function bandeau() {
  const m = ETAT.moi, b = [];
  if (m.arret_general) b.push('<span class="pastille erreur">⛔ Arrêt général</span>');
  if (m.bac_a_sable) b.push('<span class="pastille attention">🧪 Bac à sable</span>');
  const pauses = ETAT.marques.filter(x => x.en_pause).length;
  if (pauses) b.push(`<span class="pastille attention">⏸ ${pauses} en pause</span>`);
  $("#bandeau").innerHTML = b.join("");
}

/* ── La navigation ── */
function aller(vue, ...args) {
  if (vue === "plus") return $("#tiroir").showModal();
  $("#tiroir").open && $("#tiroir").close();
  ETAT.vue = vue;
  document.querySelectorAll(".onglets button").forEach(b => b.classList.toggle("actif", b.dataset.vue === vue
    || (b.dataset.vue === "plus" && ["calendrier", "demander", "marques", "sante", "reglages"].includes(vue))));
  document.querySelectorAll(".vue").forEach(v => v.hidden = v.id !== "v-" + vue);
  scrollTo(0, 0);
  try { history.replaceState(null, "", vue === "deposer" ? "/" : "/#" + vue); } catch (_) { /* rien */ }
  VUES[vue]?.(...args);
}

document.addEventListener("click", e => {
  const b = e.target.closest("[data-vue],[data-aller]");
  if (b && (b.closest(".onglets") || b.closest("#tiroir") || b.closest(".haut") || b.dataset.aller)) {
    e.preventDefault();
    aller(b.dataset.vue || b.dataset.aller);
  }
});

/* Un rang de pastilles de marque, mémorisé par vue. */
function filtres(ou, cle, rappel, avecToutes = true) {
  const actuel = ETAT.filtres[cle] ?? (avecToutes ? "" : ETAT.marques[0]?.id);
  const boutons = (avecToutes ? [{ id: "", nom: "Toutes" }] : []).concat(ETAT.marques)
    .map(m => `<button data-f="${esc(m.id)}" class="${m.id === actuel ? "actif" : ""}">${esc(m.nom.split(" — ")[0])}</button>`);
  ou.innerHTML = boutons.join("");
  ou.onclick = e => { const b = e.target.closest("[data-f]"); if (b) { ETAT.filtres[cle] = b.dataset.f; rappel(b.dataset.f); } };
  return actuel;
}

/* La dictée : le micro du téléphone, en français, si le navigateur sait faire. */
function dicter(bouton, champ, fini) {
  const R = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!R) { bouton.hidden = true; return; }
  bouton.addEventListener("click", () => {
    const r = new R();
    r.lang = "fr-FR"; r.interimResults = true;
    bouton.classList.add("ecoute");
    r.onresult = ev => { champ.value = [...ev.results].map(x => x[0].transcript).join(" "); };
    r.onend = () => { bouton.classList.remove("ecoute"); fini && champ.value && fini(champ.value); };
    r.start();
  });
}
