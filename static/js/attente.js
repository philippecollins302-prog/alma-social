/* La file d'envoi du téléphone — une photo n'est jamais perdue.
 *
 * Chaque photo choisie est d'abord rangée dans le téléphone (IndexedDB), avec
 * une référence unique. Puis on l'envoie. Pas de réseau, une coupure, l'appli
 * fermée en plein envoi : elle reste dans la file et repart au prochain
 * passage, avec la MÊME référence — le serveur reconnaît un renvoi et ne crée
 * rien deux fois. On ne l'efface du téléphone qu'une fois la réponse reçue.
 */
"use strict";

const Attente = (() => {
  const BASE = "alma-social", MAGASIN = "envois";
  let _db = null;

  function ouvrir() {
    if (_db) return Promise.resolve(_db);
    return new Promise((ok, ko) => {
      const r = indexedDB.open(BASE, 1);
      r.onupgradeneeded = () => r.result.createObjectStore(MAGASIN, { keyPath: "ref" });
      r.onsuccess = () => { _db = r.result; ok(_db); };
      r.onerror = () => ko(r.error);
    });
  }

  async function op(mode, f) {
    const db = await ouvrir();
    return new Promise((ok, ko) => {
      const t = db.transaction(MAGASIN, mode);
      const res = f(t.objectStore(MAGASIN));
      t.oncomplete = () => ok(res && "result" in res ? res.result : undefined);
      t.onerror = () => ko(t.error);
    });
  }

  function reference() {
    return (crypto.randomUUID ? crypto.randomUUID() : Date.now() + "-" + Math.random().toString(36).slice(2));
  }

  async function ajouter(marque, fichier, note = "") {
    const e = { ref: reference(), marque, note, nom: fichier.name || "photo.jpg", type: fichier.type,
                blob: fichier, etat: "attente", essais: 0, cree: Date.now(), erreur: "" };
    await op("readwrite", s => s.put(e));
    return e;
  }

  const tous = () => op("readonly", s => s.getAll());
  const retirer = ref => op("readwrite", s => s.delete(ref));
  const maj = e => op("readwrite", s => s.put(e));

  let enCours = false;
  /* Envoie tout ce qui attend, un par un. `suivi(e)` est appelé à chaque changement. */
  async function vider(suivi) {
    if (enCours) return;
    enCours = true;
    try {
      for (const e of await tous()) {
        if (e.etat === "refuse") continue;
        if (!navigator.onLine) break;
        e.etat = "envoi"; suivi && suivi(e);
        const f = new FormData();
        f.append("marque", e.marque);
        f.append("refs", e.ref);
        if (e.note) f.append("note", e.note);
        f.append("photos", e.blob, e.nom);
        try {
          const r = await fetch("/api/depot", { method: "POST", body: f, headers: { "X-Alma": "1" },
                                                credentials: "same-origin" });
          if (r.status === 401) { e.etat = "attente"; await maj(e); suivi && suivi(e, 401); break; }
          const j = await r.json().catch(() => ({}));
          const res = (j.resultats || [])[0];
          if (r.ok && res && res.ok) {
            await retirer(e.ref);
            e.etat = res.deja ? "deja" : "recue"; e.id = res.id; suivi && suivi(e);
          } else if (r.status >= 400 && r.status < 500) {
            // Refus définitif (fichier illisible, trop lourd) : on le dit, on le garde pour qu'on le voie.
            e.etat = "refuse"; e.erreur = (res && res.erreur) || j.erreur || "refusée"; await maj(e); suivi && suivi(e);
          } else {
            e.etat = "attente"; e.essais++; await maj(e); suivi && suivi(e);
          }
        } catch (_) {
          e.etat = "attente"; e.essais++; await maj(e); suivi && suivi(e);
          break;          // plus de réseau : on réessaiera au retour du réseau
        }
      }
    } finally { enCours = false; }
  }

  return { ajouter, tous, retirer, vider };
})();
