/* Le dernier chargé : tous les quartiers ont posé leur vue, on peut ouvrir. */
"use strict";

async function demarrer() {
  try { await rafraichirMoi(); } catch (_) { return montrerPorte(); }
  $("#porte").hidden = true; $("#appli").hidden = false;
  VUES.deposer_init?.();
  const p = new URLSearchParams(location.search);
  if (p.get("relie")) { history.replaceState(null, "", "/"); aller("reglages"); return verifierComptes(p.get("relie")); }
  const ancre = location.hash.slice(1);
  aller(VUES[ancre] ? ancre : "deposer");
  pastilleBoite();
}

async function pastilleBoite() {
  try {
    const j = await api("/api/boite");
    const n = j.messages.filter(m => m.status === "alerte").length;
    $("#pastille-boite").hidden = !n; $("#pastille-boite").textContent = n;
  } catch (_) { /* la pastille n'est qu'un signe */ }
}

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
demarrer();
