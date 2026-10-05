/* Marques — la plateforme de chaque marque : positionnement, personas,
 * voix, direction artistique, carnet d'apprentissage. Ce que TOUS les agents
 * lisent avant de travailler. Philippe la relit une fois ; le Stratège la
 * réécrit sur demande, et chaque version reste. */
"use strict";

async function vueMarques() {
  const ou = $("#v-marques");
  ou.innerHTML = `<div class="entete-vue"><h1>Marques</h1></div><div class="filtres" id="mq-filtres"></div><div id="mq"></div>`;
  const id = filtres($("#mq-filtres"), "marques", () => vueMarques(), false);
  const mq = $("#mq");
  chargement(mq);
  try {
    const j = await api(`/api/marque/${encodeURIComponent(id)}/plateforme`);
    const c = j.courante || {}, p = c.plateforme || {}, v = p.voix || {}, da = p.direction_artistique || {};
    const couleurs = (j.kit.colors || []).map(x => `<span title="${esc(x.name)}" style="background:${esc(x.hex)}"></span>`).join("");
    mq.innerHTML = `
      <section class="carte" style="border-top:6px solid ${esc(marque(id).couleur)}">
        <div class="ligne"><span class="etiquette">Version ${esc(c.version || "–")} · ${esc(c.auteur || "")}</span>
          <span class="petit ${c.relue_le ? "ok" : "attention"}">${c.relue_le ? "relue ✓" : "à relire une fois"}</span></div>
        <h2 style="margin-top:10px">${esc(p.positionnement || "")}</h2>
        <p class="doux">${esc(p.difference || "")}</p>
        <p><b>Promesse.</b> ${esc(p.promesse || "")}</p>
        ${(p.preuves || []).length ? `<p class="petit"><b>Preuves citables :</b> ${p.preuves.map(k => esc(j.faits[k] || k)).join(" · ")}</p>` : '<p class="petit attention">Aucune preuve vérifiée : les textes n\'écriront aucun chiffre.</p>'}
        ${pdg() ? `<div class="actions">${c.relue_le ? "" : '<button class="secondaire" data-relire="1">Je l\'ai relue</button>'}
          <button class="secondaire" data-rediger="1">Faire réécrire par le Stratège</button></div>` : ""}
      </section>
      <h2 class="section">Personas</h2>
      ${(p.personas || []).map(x => `<div class="persona"><b>${esc(x.nom)}</b> <span class="doux">— ${esc(x.qui)}</span>
        <div class="petit" style="margin-top:4px">Veut : ${esc(x.veut)}<br>Bloque : ${esc(x.bloque)}<br>Où : ${esc(x.ou)} · Quand : ${esc(x.quand)}</div></div>`).join("")}
      <h2 class="section">Voix</h2>
      <div class="dit"><div><b class="ok">On dit</b><ul>${(v.on_dit || []).map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>
        <div><b class="erreur">On ne dit jamais</b><ul>${(v.on_ne_dit_pas || []).concat(j.voix.forbidden || []).map(x => `<li>${esc(x)}</li>`).join("")}</ul></div></div>
      <p class="petit doux">${j.voix.address === "tu" ? "Tutoiement" : "Vouvoiement"} · ${j.voix.emojis ? "emojis avec mesure" : "aucun emoji"} · textes ${esc(j.voix.target_length || v.longueur || "moyens")}</p>
      ${(p.accroches || []).length ? `<p class="petit"><b>Le niveau attendu :</b> ${p.accroches.map(a => `« ${esc(a)} »`).join(" · ")}</p>` : ""}
      ${(p.objections || []).length ? `<h2 class="section">Objections</h2>${p.objections.map(o => `<div class="persona"><b>« ${esc(o.objection)} »</b><div class="petit">→ ${esc(o.reponse)}</div></div>`).join("")}` : ""}
      <h2 class="section">Direction artistique</h2>
      <div class="nuancier">${couleurs}</div>
      <p class="petit">${esc(da.style_photo || "")}<br><span class="doux">${esc(da.style_video || "")}</span></p>
      <p class="petit"><span class="etiquette ${da.mise_en_scene === "studio_permis" ? "or" : ""}">${da.mise_en_scene === "studio_permis" ? "Fond studio permis — le plat reste le vrai plat" : "Décor réel — on améliore l'image, on ne remplace jamais le lieu"}</span></p>
      <h2 class="section">Mix et parcours</h2>
      ${p.mix ? `<div class="barre" title="utile / communauté / vente"><i style="width:${p.mix.utile}%"></i></div>
        <p class="petit doux">Utile ${p.mix.utile} % · communauté ${p.mix.communaute} % · vente ${p.mix.vente} %</p>` : ""}
      ${p.parcours ? `<p class="petit">Connaître : ${esc(p.parcours.connaitre)}<br>Hésiter : ${esc(p.parcours.hesiter)}<br>Agir : ${esc(p.parcours.agir)}<br>Revenir : ${esc(p.parcours.revenir)}</p>` : ""}
      ${p.objectifs ? `<p class="petit doux">Objectifs — 30 j : ${esc(p.objectifs.j30)} · 90 j : ${esc(p.objectifs.j90)}</p>` : ""}
      <h2 class="section">Carnet d'apprentissage</h2>
      ${j.lecons.map(l => `<div class="persona ${l.statut === "contredite" ? "doux" : ""}">${l.statut === "contredite" ? "<s>" : ""}${esc(l.lecon)}${l.statut === "contredite" ? "</s>" : ""}
        <div class="petit doux">${esc(l.preuve.echantillon)} publications · ${esc(l.preuve.periode)}</div></div>`).join("") || '<p class="doux petit">Rien encore : une leçon n\'entre qu\'avec au moins six publications et sa période.</p>'}
      ${j.corrections.length ? `<h2 class="section">Ce que vos corrections ont appris</h2>
        <ul class="petit">${j.corrections.slice(0, 10).map(x => `<li>${esc(x.regle)} ${x.appliquee ? '<span class="ok">— appliqué</span>' : '<span class="doux">— à confirmer</span>'}</li>`).join("")}</ul>` : ""}
      ${j.a_completer.length ? `<details class="carte"><summary>À compléter (${j.a_completer.length})</summary><ul class="petit">${j.a_completer.map(x => `<li>${esc(x)}</li>`).join("")}</ul></details>` : ""}`;
    mq.dataset.marque = id;
  } catch (err) { mq.innerHTML = `<p class="erreur">${esc(err.message)}</p>`; }
}

$("#v-marques").addEventListener("click", async e => {
  const t = e.target, id = $("#mq")?.dataset.marque;
  try {
    if (t.dataset.relire) { await api(`/api/marque/${id}/plateforme/relire`, { json: {} }); vueMarques(); }
    if (t.dataset.rediger) {
      const consigne = prompt("Une consigne pour le Stratège ? (facultatif)") ?? null;
      if (consigne === null) return;
      t.textContent = "Le Stratège écrit…"; t.disabled = true;
      await api(`/api/marque/${id}/plateforme/rediger`, { json: { consigne } });
      vueMarques();
    }
  } catch (err) { erreur(err); }
});

VUES.marques = vueMarques;
