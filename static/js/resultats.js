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
          ${valeurBloc(x)}
          ${x.decisions.length ? `<h3 class="petit doux" style="margin:12px 0 4px;font-family:var(--texte)">Décisions de la semaine</h3>
            ${x.decisions.map(d => `<div class="decision"><p class="petit"><b>${esc(d.phrase)}</b><br><span class="doux">${esc(d.pourquoi)}</span></p>
              <div class="actions">${d.auto ? '<span class="petit doux">s\'applique lundi à midi sans réponse</span>' : '<span class="petit attention">une dépense : rien ne part sans vous</span>'}
              <button class="secondaire" data-decision="${d.id}" data-oui="1">Oui</button><button class="secondaire" data-decision="${d.id}" data-oui="0">Non</button></div></div>`).join("")}` : ""}
          ${x.lecons.length ? `<p class="petit"><span class="etiquette or">Appris</span> ${esc(x.lecons[0].lecon)}</p>` : ""}
          ${x.test ? `<p class="petit doux">Test A/B en cours : ${esc(x.test.hypothese)} (${x.test.variantes.map(v => `${esc(v.nom)} ${v.post_ids.length}/${x.test.taille}`).join(" · ")})</p>` : ""}
          <p class="petit">Cette semaine : <b>${x.semaine}</b> publication(s) — cadence ${x.cadence[0]} à ${x.cadence[1]}.</p>
          <p class="petit ${x.stock.jours_couverts < 7 ? "attention" : "doux"}">Stock : ${x.stock.banque} photo(s) en banque, de quoi tenir ${x.stock.jours_couverts} jour(s).</p>
          ${x.piliers_oublies.length ? `<p class="petit attention">Rien depuis 3 semaines : ${esc(x.piliers_oublies.join(", "))}.</p>` : ""}
          <p class="petit doux">${esc(x.veille.phrase)}${x.veille.avis.avis ? ` · Google : ${x.veille.avis.moyenne} ★ (${x.veille.avis.avis})` : ""}</p>
          <details class="terrain" data-terrain="${esc(x.marque.id)}"><summary class="petit">QR codes, numéros, codes promo, livraisons</summary><div></div></details>
          <details class="carnet" data-carnet="${esc(x.marque.id)}"><summary class="petit">Le carnet et les tests A/B</summary><div></div></details>
          <details><summary class="petit">Noter un client (« il nous a vus sur… »)</summary>
            <select class="champ" id="lt-${esc(x.marque.id)}"><option value="${food ? "commande" : "devis"}">${food ? "Commande" : "Demande de devis"}</option><option value="appel">Appel</option>${food ? "" : '<option value="commande">Commande signée</option>'}</select>
            <input class="champ" id="ls-${esc(x.marque.id)}" placeholder="Vu où ? (Instagram, Google…)">
            <button class="secondaire" data-lead="${esc(x.marque.id)}">Enregistrer</button></details>
        </section>`;
      }).join("");
  } catch (err) { t_.innerHTML = `<p class="erreur">${esc(err.message)}</p>`; }
}

/* Ce que ça rapporte, ce que ça coûte (§ 17.2). */
function valeurBloc(x) {
  const v = x.valeur, sources = Object.entries(v.par_reseau);
  const obj = x.objectif ? `<span class="${x.chiffre.clients >= x.objectif ? "ok" : "attention"}">objectif ${x.objectif}</span> · ` : "";
  const morceaux = [v.chiffre ? `<b>${Math.round(v.chiffre).toLocaleString("fr-FR")} €</b> connus` : "",
    v.cout ? `coût (IA + publicité) ${v.cout.toLocaleString("fr-FR")}` : "",
    v.cout_par_client ? `<b>${v.cout_par_client.toLocaleString("fr-FR")} par client</b>` : ""].filter(Boolean);
  if (!obj && !morceaux.length && !Object.keys(v.par_reseau).length) return "";
  return `<p class="petit">${obj}${morceaux.join(" · ")}</p>
    ${sources.length ? `<p class="petit doux">Par source : ${sources.map(([k, n]) => `${esc(k)} ${n}`).join(" · ")}</p>` : ""}`;
}

async function chargerTerrain(ou, id) {
  chargement(ou);
  const t = await api(`/api/terrain?marque=${encodeURIComponent(id)}`);
  const food = marque(id).secteur === "food";
  ou.innerHTML = `
    <h3>QR codes</h3>
    ${t.qr.map(q => `<div class="ligne petit"><span><b>${esc(q.support)}</b> · ${q.scans} scan${q.scans > 1 ? "s" : ""} · ${q.clients} client${q.clients > 1 ? "s" : ""}</span>
      <span><a href="/api/qr/${esc(q.code)}.svg" download="qr-${esc(q.code)}.svg">SVG</a> · <a href="/api/qr/${esc(q.code)}.png" download="qr-${esc(q.code)}.png">PNG</a></span></div>`).join("")
      || '<p class="petit doux">Aucun. Un QR par support : panneau de chantier, camion, flyer, sac de livraison.</p>'}
    <input class="champ" id="qr-support-${esc(id)}" maxlength="60" placeholder="Support (« panneau chantier Lattes »)">
    <button class="secondaire" data-qr="${esc(id)}">Créer le QR</button>
    <h3>Numéros d'appel tracés</h3>
    ${t.numeros.map(n => `<p class="petit"><b>${esc(n.numero)}</b> · ${esc(n.source)} · ${n.appels} appel${n.appels > 1 ? "s" : ""}</p>`).join("")
      || `<p class="petit doux">Aucun. ${t.branche.appels ? "" : "Le fournisseur n'est pas encore branché (voir README)."}</p>`}
    <h3>Codes promo</h3>
    ${t.codes.map(c => `<p class="petit"><b>${esc(c.code)}</b> — ${esc(c.offre)} <span class="doux">· ${esc(NOMS_RESEAU[c.platform] || c.platform || c.createur || "")} · ${c.utilisations} utilisation${c.utilisations > 1 ? "s" : ""}${c.chiffre ? ` · ${Math.round(c.chiffre)} €` : ""}</span></p>`).join("")
      || '<p class="petit doux">Aucun. L\'offre derrière un code est votre décision.</p>'}
    <input class="champ" id="cp-offre-${esc(id)}" maxlength="120" placeholder="L'offre (« -10 % sur le premier bowl »)">
    <input class="champ" id="cp-pour-${esc(id)}" maxlength="60" placeholder="Pour quel réseau ou quel créateur ?">
    <button class="secondaire" data-code="${esc(id)}">Créer le code</button>
    ${food ? `<h3>Rapports de livraison</h3><p class="petit doux">L'export de la semaine, tel quel, depuis l'espace restaurant.</p>
      <select class="champ" id="lv-pf-${esc(id)}"><option value="uber_eats">Uber Eats</option><option value="deliveroo">Deliveroo</option></select>
      <input class="champ" type="file" accept=".csv,text/csv" id="lv-f-${esc(id)}">
      <button class="secondaire" data-livraison="${esc(id)}">Importer</button>` : ""}`;
}

async function chargerCarnet(ou, id) {
  chargement(ou);
  const c = await api(`/api/carnet?marque=${encodeURIComponent(id)}`);
  ou.innerHTML = `
    ${c.lecons.map(l => `<p class="petit ${l.statut === "active" ? "" : "doux"}">${l.statut === "active" ? "" : "<s>"}${esc(l.lecon)}${l.statut === "active" ? "" : "</s> (contredite)"}
      <br><span class="doux">${l.preuve.echantillon} publications · ${esc(l.preuve.periode || "")}${l.preuve.p !== undefined ? ` · p = ${l.preuve.p}` : ""}</span></p>`).join("")
      || '<p class="petit doux">Rien d\'appris encore : une leçon demande huit publications réelles de chaque côté et un écart net.</p>'}
    <h3>Tests A/B</h3>
    ${c.tests.map(t => `<p class="petit"><b>${esc(t.hypothese)}</b><br><span class="doux">${esc({ en_cours: "en cours", nette: "conclu", pas_nette: "pas net" }[t.statut])}
      ${t.conclusion ? " — " + esc(t.conclusion) : ` — ${t.variantes.map(v => `${esc(v.nom)} ${v.post_ids.length}/${t.taille}`).join(" · ")}`}</span></p>`).join("") || '<p class="petit doux">Aucun test.</p>'}
    <select class="champ" id="ab-var-${esc(id)}">${Object.entries(c.variables).map(([k, h]) => `<option value="${esc(k)}">${esc(h)}</option>`).join("")}</select>
    <button class="secondaire" data-ab="${esc(id)}">Lancer ce test</button>`;
}

$("#v-resultats").addEventListener("toggle", e => {
  const d = e.target;
  if (!d.open || d.lastElementChild.childElementCount) return;
  if (d.dataset.terrain) chargerTerrain(d.lastElementChild, d.dataset.terrain).catch(erreur);
  if (d.dataset.carnet) chargerCarnet(d.lastElementChild, d.dataset.carnet).catch(erreur);
}, true);

$("#v-resultats").addEventListener("click", async e => {
  const t = e.target;
  try {
    if (t.dataset.decision) {
      const r = await api(`/api/decisions/${t.dataset.decision}`, { json: { oui: t.dataset.oui === "1" } });
      dire(`<p>${r.statut === "refusee" ? "Refusée : rien ne change." : "Appliquée."}${r.note ? " " + esc(r.note) : ""}</p>`); return vueResultats();
    }
    const id = t.dataset.qr || t.dataset.code || t.dataset.livraison || t.dataset.ab;
    if (id) {
      const ou = t.closest("details").lastElementChild;
      if (t.dataset.qr) await api("/api/terrain/qr", { json: { marque: id, support: $("#qr-support-" + id).value } });
      if (t.dataset.code) {
        const pour = $("#cp-pour-" + id).value.trim(), reseau = Object.keys(NOMS_RESEAU).find(k => NOMS_RESEAU[k].toLowerCase() === pour.toLowerCase());
        const r = await api("/api/terrain/code", { json: { marque: id, offre: $("#cp-offre-" + id).value, reseau: reseau || "", createur: reseau ? "" : pour } });
        dire(`<p>Code créé : <b>${esc(r.code)}</b>.</p>`);
      }
      if (t.dataset.livraison) {
        const f = $("#lv-f-" + id).files[0];
        if (!f) return dire("<p>Choisissez le fichier exporté.</p>");
        const fd = new FormData(); fd.append("marque", id); fd.append("plateforme", $("#lv-pf-" + id).value); fd.append("fichier", f);
        const r = await api("/api/livraisons/import", { method: "POST", body: fd });
        dire(`<h3>Import terminé</h3><p>${r.importees} commande(s) importée(s) pour ${Math.round(r.chiffre)} € · ${r.deja} déjà connue(s) · ${r.annulees} annulée(s) écartée(s)
          · ${r.avec_code} avec un de nos codes.</p>${r.codes_inconnus.length ? `<p class="attention petit">Codes qui ne sont pas à nous : ${esc(r.codes_inconnus.join(", "))}</p>` : ""}`);
      }
      if (t.dataset.ab) { await api("/api/ab", { json: { marque: id, variable: $("#ab-var-" + id).value } }); dire("<p>Test lancé : les variantes alternent créneau après créneau.</p>"); }
      return t.dataset.ab ? chargerCarnet(ou, id) : chargerTerrain(ou, id);
    }
  } catch (err) { return erreur(err); }
  const id = t.dataset.lead;
  if (!id) return;
  try {
    await api("/api/leads", { json: { marque: id, type: $("#lt-" + id).value, canal: "manuel", source: $("#ls-" + id).value } });
    dire("<p>Client enregistré. C'est ce chiffre qui guide tout le reste.</p>"); vueResultats();
  } catch (err) { erreur(err); }
});

VUES.resultats = vueResultats;
