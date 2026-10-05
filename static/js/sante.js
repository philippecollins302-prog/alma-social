/* Santé — files, échecs, jetons qui expirent, stock, coûts de l'IA et
 * sévérité du Critique. Ce qui est rouge se lit en premier. */
"use strict";

const NOMS_CLES = { anthropic: "Claude", upload_post: "Upload-Post", webhook: "Notifications", chiffrement: "Chiffrement",
                    nettoyage: "Nettoyage photo", courrier: "Courrier" };

async function vueSante() {
  const ou = $("#v-sante");
  ou.innerHTML = `<div class="entete-vue"><h1>Santé</h1></div><div id="sante"></div>`;
  const s_ = $("#sante");
  chargement(s_);
  try {
    const [s, eq] = await Promise.all([api("/api/sante"), pdg() ? api("/api/equipe") : Promise.resolve(null)]);
    const rouge = [...s.derniers_echecs.map(x => `${nomMarque(x.brand_id)} · ${x.platform} : ${x.error}`),
                   ...s.jetons_qui_expirent.map(x => `${nomMarque(x.marque)} ${x.reseau} : jeton expire ${quand(x.le)}`),
                   ...(s.horloge.vivante ? [] : ["L'horloge est arrêtée : rien ne part à l'heure."])];
    const manquent = Object.entries(s.cles).filter(([, v]) => !v).map(([k]) => NOMS_CLES[k] || k);
    const ia_ = s.ia, cr = s.critique;
    const parMarque = {};
    s.comptes_a_relier.forEach(x => (parMarque[x.marque] = parMarque[x.marque] || []).push(x.reseau));
    s_.innerHTML = `
      <section class="carte">${rouge.length ? `<h3 class="erreur">À regarder</h3><ul class="petit">${rouge.map(x => `<li>${esc(x)}</li>`).join("")}</ul>`
        : manquent.length ? '<h3 class="attention">Tourne, en mode réduit</h3>' : '<h3 class="ok">Tout tourne</h3>'}
        ${manquent.length ? `<p class="petit attention">Clés pas encore posées : ${esc(manquent.join(", "))}.</p>` : ""}
        <p class="petit">Horloge ${s.horloge.vivante ? '<span class="ok">vivante</span>' : '<span class="erreur">arrêtée</span>'} · ${s.publies_24h} publication(s) en 24 h</p>
        <div>${Object.entries(s.cles).map(([k, v]) => `<span class="etiquette" style="margin:2px">${v ? "✓" : "✗"} ${esc(NOMS_CLES[k] || k)}</span>`).join("")}</div>
      </section>
      ${ia_ ? `<section class="carte"><h3>IA — le mois</h3>
        <div class="ligne"><div class="chiffre" style="font-size:36px">${euros(ia_.mois_usd)} $</div><div class="doux petit">plafond ${euros(ia_.plafond_usd, 0)} $</div></div>
        <div class="barre"><i style="width:${Math.min(100, 100 * ia_.mois_usd / Math.max(1, ia_.plafond_usd))}%"></i></div>
        <table class="equipe">${ia_.agents.map(a => `<tr><td><b>${esc(a.agent)}</b></td><td>${a.appels} appels${a.replis ? ` · <span class="attention">${a.replis} sans modèle</span>` : ""}${a.echecs ? ` · <span class="erreur">${a.echecs} échecs</span>` : ""}</td><td style="text-align:right">${euros(a.cout_usd)} $</td></tr>`).join("") || '<tr><td class="doux">Aucun appel ce mois-ci.</td></tr>'}</table>
      </section>` : ""}
      <section class="carte"><h3>Le Critique</h3>
        ${cr.jugements ? `<p class="petit">${cr.jugements} jugements · note moyenne <b>${esc(cr.note_moyenne)}</b> · ${cr.passe_premier_tour} au premier tour · ${cr.reecritures} réécritures · ${cr.a_la_banque} renvoyées à la banque</p>
          ${cr.trop_indulgent ? '<p class="attention petit">Il n\'a rien refusé depuis 30 jours : il est trop indulgent.</p>' : ""}`
          : '<p class="doux petit">Pas encore de jugement.</p>'}
      </section>
      ${eq ? `<section class="carte"><h3>L'équipe d'agents</h3><table class="equipe">${eq.agents.map(a => `<tr><td><b>${esc(a.nom)}</b><div class="doux">${esc(a.role)}</div></td><td class="petit">${esc(a.modele)}<div class="doux">${esc(a.consignes)}</div></td></tr>`).join("")}</table>
        ${eq.cle ? "" : '<p class="attention petit">Sans clé Claude, chaque agent travaille sur son repli : textes de gabarit, grille locale, lecteur de questions simple.</p>'}</section>` : ""}
      <section class="carte"><h3>Stock</h3>${s.stock.map(x => `<div class="ligne petit"><span>${puce(x.id)}${esc(x.marque)}</span><span class="${x.jours_couverts < 7 ? "attention" : "doux"}">${x.banque} en banque · ${x.jours_couverts} j</span></div>`).join("")}</section>
      ${s.comptes_a_relier.length ? `<section class="carte"><h3>Comptes à relier</h3>${Object.entries(parMarque).map(([m, rs]) => `<p class="petit">${puce(m)}<b>${esc(nomMarque(m))}</b><br><span class="doux">${esc(rs.join(" · "))}</span></p>`).join("")}</section>` : ""}
      ${s.file ? `<p class="doux petit">File : ${esc(JSON.stringify(s.file.compte))}</p>` : ""}`;
  } catch (err) { s_.innerHTML = `<p class="erreur">${esc(err.message)}</p>`; }
}

VUES.sante = vueSante;
