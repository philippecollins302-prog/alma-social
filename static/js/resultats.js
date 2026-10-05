/* Résultats — les clients d'abord, jamais un tableau de likes. Chaque
 * marque : combien de demandes, grâce à quelles publications, et ce qui
 * manque pour tenir le rythme. */
"use strict";

async function vueResultats() {
  const ou = $("#v-resultats");
  ou.innerHTML = `<div class="entete-vue"><h1>Résultats</h1><span class="doux petit">30 jours</span></div><div id="tableau"></div>`;
  const t_ = $("#tableau");
  chargement(t_);
  try {
    const t = await api("/api/tableau");
    const total = t.marques.reduce((s, x) => s + x.chiffre.clients, 0);
    t_.innerHTML = `
      <section class="carte" style="text-align:center">
        <div class="chiffre or">${total}</div>
        <div class="doux">client${total > 1 ? "s" : ""} générés par les réseaux en ${t.jours} jours</div>
        ${t.bac_a_sable ? '<p class="attention petit">🧪 Bac à sable : les publications sont simulées et comptées à part.</p>' : ""}
      </section>`
      + t.marques.map(x => {
        const c = x.chiffre, food = x.marque.secteur === "food";
        const vues = x.audience.reduce((s, a) => s + a.vues, 0);
        return `<section class="carte" style="border-left:6px solid ${esc(marque(x.marque.id).couleur)}">
          <div class="ligne"><h2>${esc(x.marque.nom)}</h2>${x.en_pause ? '<span class="attention">⏸ en pause</span>' : ""}</div>
          <div class="ligne"><div><div class="chiffre">${c.clients}</div><div class="doux petit">client${c.clients > 1 ? "s" : ""}</div></div>
            <div class="petit doux" style="text-align:right">${c.par_type.devis} devis · ${c.par_type.commande} commandes · ${c.par_type.appel} appels<br>
            ${c.clics} clics${food ? ` · ${c.clics_commande} vers les apps` : ""}${vues ? ` · ${vues} vues` : ""}</div></div>
          ${c.top.length ? `<h3 class="petit doux" style="margin:12px 0 4px;font-family:var(--texte)">Grâce à</h3><ol class="petit" style="margin:0;padding-left:20px">${c.top.map(p => `<li><b>${p.clients}</b> — ${esc((p.texte || "").split("\n")[0])} <span class="doux">(${esc(p.platform)})</span></li>`).join("")}</ol>` : '<p class="doux petit">Aucune demande rattachée à une publication pour l\'instant.</p>'}
          <p class="petit">Cette semaine : <b>${x.semaine}</b> publication(s) — cadence ${x.cadence[0]} à ${x.cadence[1]}.</p>
          <p class="petit ${x.stock.jours_couverts < 7 ? "attention" : "doux"}">Stock : ${x.stock.banque} photo(s) en banque, de quoi tenir ${x.stock.jours_couverts} jour(s).</p>
          ${x.piliers_oublies.length ? `<p class="petit attention">Rien depuis 3 semaines : ${esc(x.piliers_oublies.join(", "))}.</p>` : ""}
          <p class="petit doux">${esc(x.veille.phrase)}${x.veille.avis.avis ? ` · Google : ${x.veille.avis.moyenne} ★ (${x.veille.avis.avis})` : ""}</p>
          <details><summary class="petit">Noter un client (« il nous a vus sur… »)</summary>
            <select class="champ" id="lt-${esc(x.marque.id)}"><option value="${food ? "commande" : "devis"}">${food ? "Commande" : "Demande de devis"}</option><option value="appel">Appel</option>${food ? "" : '<option value="commande">Commande signée</option>'}</select>
            <input class="champ" id="ls-${esc(x.marque.id)}" placeholder="Vu où ? (Instagram, Google…)">
            <button class="secondaire" data-lead="${esc(x.marque.id)}">Enregistrer</button></details>
        </section>`;
      }).join("");
  } catch (err) { t_.innerHTML = `<p class="erreur">${esc(err.message)}</p>`; }
}

$("#v-resultats").addEventListener("click", async e => {
  const id = e.target.dataset.lead;
  if (!id) return;
  try {
    await api("/api/leads", { json: { marque: id, type: $("#lt-" + id).value, canal: "manuel", source: $("#ls-" + id).value } });
    dire("<p>Client enregistré. C'est ce chiffre qui guide tout le reste.</p>"); vueResultats();
  } catch (err) { erreur(err); }
});

VUES.resultats = vueResultats;
