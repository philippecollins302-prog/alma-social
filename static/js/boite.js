/* La boîte — messages, commentaires et avis de toutes les marques, l'urgence
 * d'abord. L'IA répond seule à ce qui est sûr ; ici n'arrive que ce qui
 * demande un humain (plainte, VIP, avis de 3 ★ ou moins), avec un brouillon.
 * Corriger un brouillon apprend à la marque sa voix. */
"use strict";

const CATEGORIES = { question: "Question", compliment: "Compliment", devis: "Prospect", plainte: "Plainte",
                     vip: "VIP", indesirable: "Indésirable", autre: "Autre" };

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
    const autres = bo.messages.filter(m => m.status !== "alerte").slice(0, 40);
    $("#boite-compte").textContent = `${urgents.length + avisDurs.length} à traiter`;
    b.innerHTML = `
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
        <p>${esc(m.text)}</p><p class="doux petit">— ${esc(m.author)} · ${esc(quand(m.received_at))}</p>
        <textarea class="champ" rows="3" id="msg-${m.id}" placeholder="Votre réponse">${esc(m.reply)}</textarea>
        <button class="gros" data-message="${m.id}">Répondre</button></article>`).join("")}
      ${autres.length ? `<h2 class="section">Traités par l'IA</h2>${autres.map(m => `<div class="carte petit">
        <div class="ligne"><span>${puce(m.brand_id)}<b>${esc(m.author)}</b> · ${esc(m.platform)}</span><span class="doux">${esc(quand(m.received_at))}</span></div>
        <p style="margin:6px 0">${esc(m.text)}</p>
        ${m.reply ? `<p class="doux" style="margin:0">↳ ${esc(m.reply)} <span class="etiquette">${m.replied_by === "ia" ? "IA" : "vous"}</span></p>` : ""}</div>`).join("")}` : ""}`;
  } catch (err) { b.innerHTML = `<p class="erreur">${esc(err.message)}</p>`; }
}

$("#v-boite").addEventListener("click", async e => {
  const t = e.target;
  try {
    if (t.dataset.avis) { await api(`/api/avis/${t.dataset.avis}/repondre`, { json: { texte: $("#avis-" + t.dataset.avis).value } }); vueBoite(); pastilleBoite(); }
    if (t.dataset.message) { await api(`/api/boite/${t.dataset.message}/repondre`, { json: { texte: $("#msg-" + t.dataset.message).value } }); vueBoite(); pastilleBoite(); }
  } catch (err) { erreur(err); }
});

VUES.boite = vueBoite;
