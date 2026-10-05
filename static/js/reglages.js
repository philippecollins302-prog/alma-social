/* Réglages — l'arrêt général, le bac à sable, les pauses, le mode crise, les comptes, le
 * copilote, les modèles des agents et le plafond de l'IA, le journal. */
"use strict";

async function vueReglages() {
  const ou = $("#v-reglages");
  await rafraichirMoi();
  const moi = ETAT.moi, chef = pdg();
  const eq = chef ? await api("/api/equipe").catch(() => null) : null;
  ou.innerHTML = `<div class="entete-vue"><h1>Réglages</h1></div>
    ${chef ? `<section class="carte">
      <button class="stop ${moi.arret_general ? "leve" : ""}" data-arret="${moi.arret_general ? 0 : 1}">
        ${moi.arret_general ? "▶ Lever l'arrêt général" : "⛔ ARRÊT GÉNÉRAL"}</button>
      <p class="doux petit">${moi.arret_general ? "Rien ne part en ce moment, nulle part." : "Un geste, et plus aucune publication ne sort, sur aucun réseau."}</p>
      <div class="interrupteur"><span>${moi.bac_a_sable ? "🧪 Bac à sable <b>ouvert</b> : tout est simulé." : "✅ Les publications sortent pour de vrai."}</span>
        <button class="secondaire" data-bac="${moi.bac_a_sable ? 0 : 1}">${moi.bac_a_sable ? "Ouvrir les vannes" : "Revenir au bac à sable"}</button></div>
    </section>` : ""}
    <h2 class="section">Marques</h2>
    ${ETAT.marques.map(m => `<section class="carte" style="border-left:6px solid ${esc(m.couleur)}">
      <div class="ligne"><h3>${esc(m.nom)}</h3>
        ${m.crise ? "" : m.en_pause ? `<button class="secondaire" data-reprendre="${esc(m.id)}">▶ Reprendre</button>`
                     : `<button class="secondaire" data-pause="${esc(m.id)}">⏸ Pause 48 h</button>`}</div>
      ${m.crise ? `<div class="crise"><b>🚨 Mode crise</b> depuis ${esc(quand(m.crise_depuis))} — ${esc(m.crise_raison || "")}.
          Rien ne part, aucune réponse automatique.
          <p class="petit">Brouillon de prise de parole (rien n'est parti) :</p>
          <textarea class="champ" rows="5" readonly>${esc(m.crise_brouillon)}</textarea>
          <button class="secondaire" data-lever-crise="${esc(m.id)}">Lever la crise</button></div>`
        : m.en_pause ? `<p class="attention petit">En pause${m.pause_raison ? " (" + esc(m.pause_raison) + ")" : ""}. Rien ne repart sans « Reprendre ».</p>` : ""}
      ${m.crise ? "" : `<button class="crise-bouton" data-crise="${esc(m.id)}">🚨 Mode crise</button>`}
      <ul class="pubs">${m.reseaux.map(r => `<li class="ligne"><span>${esc(r.nom)} ${r.poignee ? `<span class="doux">${esc(r.poignee)}</span>` : ""}</span>
        <span class="${r.etat === "actif" ? "ok" : r.etat === "a_relier" ? "doux" : "attention"}">${esc({ actif: "relié", a_relier: "à relier", pause: "en pause", erreur: "à reconnecter" }[r.etat] || r.etat)}</span></li>`).join("")}</ul>
      <div class="actions"><button class="secondaire" data-relier="${esc(m.id)}">Relier les réseaux</button>
        <button class="secondaire" data-verifier="${esc(m.id)}">Vérifier</button>
        <button class="secondaire" data-comptes="${esc(m.id)}">Détails</button></div>
      ${chef ? `<label class="interrupteur petit"><span><b>Copilote</b> — un aperçu avant chaque envoi. Désactivé par défaut : la règle reste « aucune validation ».</span>
        <input type="checkbox" data-copilote="${esc(m.id)}" ${m.validation ? "checked" : ""}></label>` : ""}
    </section>`).join("")}
    ${eq ? `<h2 class="section">L'IA</h2><section class="carte">
      <div class="ligne"><span>Plafond du mois : <b>${euros(eq.couts.plafond_usd, 0)} $</b> <span class="doux petit">(dépensé : ${euros(eq.couts.mois_usd)} $)</span></span>
        <button class="secondaire" data-plafond="1">Changer</button></div>
      <p class="doux petit">Au-delà, chaque agent passe sur son repli sans modèle, et une alerte part. Une dépense que vous n'avez pas décidée n'a pas lieu.</p>
      ${eq.agents.map(a => `<div class="interrupteur petit"><span><b>${esc(a.nom)}</b><br><span class="doux">${esc(a.modele)}</span></span>
        <select class="champ" style="width:auto;margin:0" data-agent="${esc(a.cle)}">${Object.keys(eq.niveaux).map(n => `<option value="${n}" ${eq.niveaux[n] === a.modele ? "selected" : ""}>${{ fort: "le plus capable", rapide: "rapide", tri: "petit" }[n]}</option>`).join("")}</select></div>`).join("")}
    </section>` : ""}
    <h2 class="section">Journal</h2>
    <section class="carte">
      <p class="doux petit">Tout ce qui est sorti en votre nom : le texte exact, l'image, le réseau, l'heure. Non modifiable.</p>
      <div class="actions"><a class="secondaire" href="/api/journal?format=csv" download>Exporter (CSV)</a>
      ${chef ? '<button class="secondaire" data-chaine="1">Vérifier l\'intégrité</button>' : ""}
      <a class="secondaire" href="/api/rapport" target="_blank">Le récapitulatif du lundi</a></div></section>
    <section class="carte"><button class="secondaire" data-sortir="1">Se déconnecter</button>
      <p class="doux petit">${esc(moi.utilisateur.nom)} · ALMA SOCIAL ${esc(moi.version)}</p></section>`;
}

async function verifierComptes(id) {
  try {
    const r = await api(`/api/comptes/verifier/${id}`, { json: {} });
    dire(`<h3>Réseaux de ${esc(nomMarque(id))}</h3>${Object.entries(r.relies).map(([k, v]) => `<p>${esc(k)} : <b>${esc({ actif: "relié", a_relier: "pas encore relié", erreur: "à reconnecter", pause: "en pause" }[v] || v)}</b></p>`).join("")}`);
    vueReglages();
  } catch (err) { erreur(err); }
}

$("#v-reglages").addEventListener("change", async e => {
  const t = e.target;
  try {
    if (t.dataset.copilote) {
      if (t.checked && !confirm("Activer le copilote : chaque publication de cette marque attendra votre aperçu avant de partir. Continuer ?")) { t.checked = false; return; }
      await api(`/api/marque/${t.dataset.copilote}/copilote`, { json: { actif: t.checked } });
    }
    if (t.dataset.agent) { await api("/api/reglages/agents", { json: { agent: t.dataset.agent, niveau: t.value } }); vueReglages(); }
  } catch (err) { erreur(err); }
});

$("#v-reglages").addEventListener("click", async e => {
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
    if (d.plafond) {
      const v = prompt("Plafond IA du mois, en dollars :");
      if (v === null) return;
      await api("/api/reglages/plafond", { json: { usd: Number(v.replace(",", ".")) } });
    }
    if (d.crise) {
      const raison = prompt(`Mode crise pour ${nomMarque(d.crise)} : tout s'arrête, plus aucune réponse automatique, et un brouillon de prise de parole vous attend. Pourquoi ?`);
      if (raison === null) return;
      const r = await api(`/api/marque/${d.crise}/crise`, { json: { raison } });
      dire(`<p><b>Mode crise activé.</b> ${r.retenues} publication(s) retenue(s).</p><p class="petit">Brouillon de prise de parole :</p><textarea class="champ" rows="6" readonly>${esc(r.brouillon)}</textarea>`);
    }
    if (d.leverCrise) {
      if (!confirm("Lever la crise : les publications retenues repartent, étalées dans le temps, et les réponses automatiques reprennent. Continuer ?")) return;
      const r = await api(`/api/marque/${d.leverCrise}/crise/lever`, { json: {} });
      dire(`<p>Crise levée. ${r.repris} publication(s) repartent.</p>`);
    }
    if (d.pause) await api(`/api/marque/${d.pause}/pause`, { json: {} });
    if (d.reprendre) await api(`/api/marque/${d.reprendre}/reprendre`, { json: {} });
    if (d.relier) { const r = await api(`/api/comptes/relier/${d.relier}`, { json: {} }); location.href = r.url; return; }
    if (d.verifier) return verifierComptes(d.verifier);
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
  } catch (err) { erreur(err); }
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

VUES.reglages = vueReglages;
