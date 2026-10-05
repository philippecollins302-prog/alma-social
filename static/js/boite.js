/* La boîte — messages, commentaires et avis de toutes les marques, l'urgence
 * puis la valeur d'abord. L'IA répond seule à ce qui est sûr ; ici n'arrive
 * que ce qui demande un humain (plainte, VIP, avis de 3 ★ ou moins), avec un
 * brouillon et le nom de qui s'en charge. Les prospects qualifiés suivent,
 * chauds en tête. Le délai réel de réponse est affiché, contre l'objectif.
 * Corriger un brouillon apprend à la marque sa voix. */
"use strict";

const CATEGORIES = { question: "Question", compliment: "Compliment", devis: "Prospect", plainte: "Plainte",
                     vip: "VIP", indesirable: "Indésirable", autre: "Autre" };
const CHAMPS_PROSPECT = { travaux: "Travaux", surface: "Surface", commune: "Commune", delai: "Délai", budget: "Budget",
  rappel: "Rappel", piece: "Pièce", sol: "Sol", pose: "Pose", copropriete: "Copropriété", besoin: "Besoin",
  groupe: "Personnes", entreprise: "Entreprise", date: "Date" };
const telLisible = t => /^\+33\d{9}$/.test(t) ? ("0" + t.slice(3)).replace(/(\d{2})(?=\d)/g, "$1 ") : t;
const TEMPERATURES = { chaud: "🔥 chaud", tiede: "🌤 tiède", froid: "❄ froid" };
const EVENEMENTS_AVIS = { pv_chantier: "Chantier livré (PV signé)", facture_payee: "Facture payée", commande_livree: "Commande livrée" };

function duree(s) {
  if (s === null || s === undefined) return "—";
  return s < 90 ? `${s} s` : s < 5400 ? `${Math.round(s / 60)} min` : `${Math.round(s / 3600)} h`;
}

function ligneDelais(d) {
  const q = d.question, v = d.devis;
  if (!q.messages && !v.messages) return "";
  const un = (x, nom, obj) => x.messages ? `${nom} : <b>${duree(x.mediane_s)}</b> <span class="doux">(objectif ${obj}${x.en_retard ? `, <span class="attention">${x.en_retard} en retard</span>` : ""})</span>` : "";
  return `<p class="petit delais">Délai réel de réponse, 7 jours — ${[un(q, "questions", "15 min"), un(v, "devis", "5 min")].filter(Boolean).join(" · ")}</p>`;
}

function carteProspect(p) {
  const rep = Object.entries(p.reponses).filter(([k]) => k !== "projet");
  return `<article class="carte prospect ${esc(p.temperature)}">
    <div class="ligne"><span>${puce(p.marque)}<b>${esc(p.nom || "sans nom")}</b></span><span class="etiquette">${esc(TEMPERATURES[p.temperature] || p.temperature)}</span></div>
    ${p.telephone ? `<a class="gros" href="tel:${esc(p.telephone)}">Appeler le ${esc(telLisible(p.telephone))}</a>` : ""}
    ${p.reponses.projet ? `<p>« ${esc(p.reponses.projet)} »</p>` : ""}
    ${rep.length ? `<p class="petit">${rep.map(([k, v]) => `${esc(CHAMPS_PROSPECT[k] || k)} : <b>${esc(v)}</b>`).join(" · ")}</p>` : ""}
    <p class="doux petit">${esc(p.raison)} · ${esc(p.source || p.porte)} · ${esc(quand(p.cree_le))}${p.publication ? `<br>Publication : ${esc(p.publication)}` : ""}</p></article>`;
}

async function vueBoite() {
  const ou = $("#v-boite");
  ou.innerHTML = `<div class="entete-vue"><h1>Boîte</h1><span class="doux petit" id="boite-compte"></span></div>
    <div class="filtres" id="boite-filtres"></div><div id="boite"></div>`;
  const f = filtres($("#boite-filtres"), "boite", () => vueBoite());
  const b = $("#boite");
  chargement(b);
  try {
    const q = f ? `?marque=${encodeURIComponent(f)}` : "";
    const [bo, av] = await Promise.all([api("/api/boite" + q), api("/api/avis" + q)]);
    const urgents = bo.messages.filter(m => m.status === "alerte");
    const avisDurs = av.avis.filter(a => a.status === "alerte" || a.status === "a_repondre");
    const autres = bo.messages.filter(m => !["alerte", "traite"].includes(m.status)).slice(0, 40);
    $("#boite-compte").textContent = `${urgents.length + avisDurs.length} à traiter`;
    b.innerHTML = `
      ${bo.crises.map(id => `<p class="crise">🚨 <b>${esc(nomMarque(id))}</b> est en mode crise : aucune réponse ne part seule. Réglages → Lever la crise.</p>`).join("")}
      ${ligneDelais(bo.delais)}
      ${urgents.length + avisDurs.length ? '<h2 class="section">À traiter par vous</h2>' : '<div class="vide"><b>Rien à traiter.</b>L\'IA a répondu à tout ce qui était sûr. Ce qui demande un humain arrivera ici.</div>'}
      ${avisDurs.map(a => `<article class="carte">
        <div class="ligne"><span>${puce(a.brand_id)}<b>${esc(nomMarque(a.brand_id))}</b> · Google</span>
          <span class="attention">${"★".repeat(a.rating)}${"☆".repeat(5 - a.rating)}</span></div>
        <p>${esc(a.text)}</p><p class="doux petit">— ${esc(a.author)} · ${esc(quand(a.received_at))}</p>
        <textarea class="champ" rows="4" id="avis-${a.id}">${esc(a.draft)}</textarea>
        <button class="gros" data-avis="${a.id}">Envoyer cette réponse</button></article>`).join("")}
      ${urgents.map(m => `<article class="carte">
        <div class="ligne"><span>${puce(m.brand_id)}<b>${esc(nomMarque(m.brand_id))}</b> · ${esc(m.platform)}</span>
          <span class="etiquette ${m.category === "devis" ? "or" : ""}">${esc(CATEGORIES[m.category] || m.category)}</span></div>
        <p>${esc(m.text)}</p><p class="doux petit">— ${esc(m.author)} · ${esc(quand(m.received_at))}${m.assigned_to ? ` · pour <b>${esc(m.assigned_to)}</b>` : ""}</p>
        <textarea class="champ" rows="3" id="msg-${m.id}" placeholder="Votre réponse">${esc(m.reply)}</textarea>
        <div class="actions"><button class="gros" data-message="${m.id}">Répondre</button>
          <button class="secondaire" data-traite="${m.id}">Réglé autrement</button></div></article>`).join("")}
      ${bo.prospects.length ? `<h2 class="section">Prospects qualifiés</h2>${bo.prospects.map(carteProspect).join("")}
        <a class="secondaire" href="/api/prospects.csv${q}" download>Exporter (CSV)</a>` : ""}
      ${autres.length ? `<h2 class="section">Traités par l'IA</h2>${autres.map(m => `<div class="carte petit">
        <div class="ligne"><span>${puce(m.brand_id)}<b>${esc(m.author)}</b> · ${esc(m.platform)}</span><span class="doux">${esc(quand(m.received_at))}</span></div>
        <p style="margin:6px 0">${esc(m.text)}</p>
        ${m.reply ? `<p class="doux" style="margin:0">↳ ${esc(m.reply)} <span class="etiquette">${m.replied_by === "ia" ? "IA" : "vous"}</span>${m.first_reply_s !== null ? ` <span class="doux">en ${duree(m.first_reply_s)}</span>` : ""}</p>` : ""}</div>`).join("")}` : ""}
      <details class="carte" data-demande-avis><summary><b>Demander un avis</b> — chantier livré, facture payée, commande livrée</summary>
        <p class="doux petit">À tous les clients, sans tri et sans contrepartie : c'est la règle de Google et celle de la loi. Un e-mail tout de suite (à une heure décente), deux relances à J+3 et J+5, rien si le client a déjà cliqué.</p>
        <select class="champ" id="da-marque">${ETAT.marques.map(m => `<option value="${esc(m.id)}" ${m.id === f ? "selected" : ""}>${esc(m.nom)}</option>`).join("")}</select>
        <select class="champ" id="da-evenement">${Object.entries(EVENEMENTS_AVIS).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select>
        <input class="champ" id="da-nom" placeholder="Nom du client" autocomplete="off">
        <input class="champ" id="da-email" type="email" placeholder="E-mail" autocomplete="off">
        <input class="champ" id="da-tel" type="tel" placeholder="Téléphone (si pas d'e-mail)" autocomplete="off">
        <button class="gros" data-demander-avis="1">Envoyer la demande</button></details>
      <details class="carte" data-reputation><summary><b>Réputation</b> — avis, Google Maps, fiche</summary><div id="reputation"></div></details>`;
  } catch (err) { b.innerHTML = `<p class="erreur">${esc(err.message)}</p>`; }
}

async function chargerReputation() {
  const ou = $("#reputation");
  const id = ETAT.filtres.boite || ETAT.marques[0]?.id;
  if (!ou || !id) return;
  chargement(ou);
  try {
    const r = await api(`/api/reputation?marque=${encodeURIComponent(id)}`);
    const l = r.lecture, mp = r.maps;
    ou.innerHTML = `<h3>${esc(nomMarque(id))}</h3>
      <p>${esc(l.phrase)}</p>
      ${l.idees.length ? `<p class="petit">Idées de contenus qui répondent aux avis :</p><ul class="petit">${l.idees.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
      <p class="petit">Demandes d'avis (30 j) : ${r.bilan.parties} parties, ${r.bilan.ouvertes} ouvertes${r.bilan.taux !== null ? ` (${Math.round(100 * r.bilan.taux)} %)` : ""}.
        ${r.lien_avis ? "" : '<span class="attention">Identifiant de la fiche Google manquant : les demandes partent, mais le lien mène à une page d\'attente.</span>'}</p>
      ${r.demandes.length ? `<ul class="pubs petit">${r.demandes.slice(0, 8).map(d => `<li class="ligne"><span>${esc(d.client || "client")} · ${esc(d.evenement)}</span>
        <span class="${d.statut === "clique" ? "ok" : d.statut === "echec" ? "attention" : "doux"}">${esc({ a_envoyer: "à envoyer", envoye: `envoyée ×${d.envois}`, clique: "ouverte", stop: "arrêtée", echec: d.erreur || "échec" }[d.statut] || d.statut)}</span></li>`).join("")}</ul>` : ""}
      <p class="petit">QR code et puce NFC des avis : <code>${esc(r.lien_avis_qr)}</code> — à créer dans Résultats → Terrain, avec cette adresse comme cible.</p>
      <h3>Google Maps</h3>
      <p>${esc(mp.phrase)}</p>
      ${r.cle_places ? "" : '<p class="doux petit">Relevé automatique coupé : il faut une clé Google Places (une dépense, la décision de Philippe). Un relevé à la main reste possible :</p>'}
      <div class="actions"><select class="champ" id="mp-requete">${r.requetes.map(x => `<option>${esc(x)}</option>`).join("")}</select>
        <input class="champ" id="mp-position" inputmode="numeric" placeholder="Position (vide : absent)" style="max-width:12em">
        <button class="secondaire" data-maps-releve="${esc(id)}">Noter</button></div>
      <h3>La fiche</h3>
      ${r.audit.length ? `<ul class="petit">${r.audit.map(a => `<li class="${a.gravite === "bloquant" || a.gravite === "important" ? "attention" : ""}">${esc(a.phrase)}</li>`).join("")}</ul>` : '<p class="ok petit">Rien à reprendre sur la fiche.</p>'}
      <div class="actions"><input class="champ" id="mp-place" placeholder="Identifiant de la fiche Google (place ID)" value="${esc(r.place_id)}">
        <button class="secondaire" data-place="${esc(id)}">Enregistrer</button></div>
      ${r.concurrents.length ? `<h3>Avis des concurrents</h3><p class="doux petit">Collez des avis lus chez eux (un par ligne) : on n'aspire rien, les conditions de Google l'interdisent.</p>
        <select class="champ" id="ac-qui">${r.concurrents.map(c => `<option value="${c.id}">${esc(c.nom)}</option>`).join("")}</select>
        <select class="champ" id="ac-note">${[5, 4, 3, 2, 1].map(n => `<option value="${n}">${n} ★</option>`).join("")}</select>
        <textarea class="champ" id="ac-textes" rows="3" placeholder="Un avis par ligne"></textarea>
        <button class="secondaire" data-avis-concurrent="1">Ajouter</button>` : ""}`;
  } catch (err) { ou.innerHTML = `<p class="erreur">${esc(err.message)}</p>`; }
}

$("#v-boite").addEventListener("toggle", e => {
  if (e.target.matches("details[data-reputation]") && e.target.open) chargerReputation();
}, true);

$("#v-boite").addEventListener("click", async e => {
  const t = e.target.closest("button");
  if (!t) return;
  const d = t.dataset;
  try {
    if (d.avis) { await api(`/api/avis/${d.avis}/repondre`, { json: { texte: $("#avis-" + d.avis).value } }); vueBoite(); pastilleBoite(); }
    if (d.message) { await api(`/api/boite/${d.message}/repondre`, { json: { texte: $("#msg-" + d.message).value } }); vueBoite(); pastilleBoite(); }
    if (d.traite) { await api(`/api/boite/${d.traite}/traite`, { json: {} }); vueBoite(); pastilleBoite(); }
    if (d.demanderAvis) {
      const r = await api("/api/demandes-avis", { json: { marque: $("#da-marque").value, evenement: $("#da-evenement").value,
        nom: $("#da-nom").value, email: $("#da-email").value, telephone: $("#da-tel").value } });
      dire(r.deja ? "<p>Cette demande existait déjà.</p>" : `<p class="ok">Demande enregistrée : elle part ${r.canal === "email" ? "par e-mail" : "par SMS dès qu'un fournisseur sera branché"}, puis deux relances.</p>`);
      ["#da-nom", "#da-email", "#da-tel"].forEach(s => { $(s).value = ""; });
    }
    if (d.mapsReleve) {
      await api("/api/maps/releve", { json: { marque: d.mapsReleve, requete: $("#mp-requete").value, position: $("#mp-position").value.trim() } });
      chargerReputation();
    }
    if (d.place) { await api(`/api/marque/${d.place}/google`, { json: { place_id: $("#mp-place").value.trim() } }); chargerReputation(); }
    if (d.avisConcurrent) {
      const r = await api(`/api/concurrents/${$("#ac-qui").value}/avis`, { json: { note: Number($("#ac-note").value), textes: $("#ac-textes").value.split("\n") } });
      dire(`<p>${r.ajoutes} avis ajouté(s).</p>`);
      chargerReputation();
    }
  } catch (err) { erreur(err); }
});

VUES.boite = vueBoite;
