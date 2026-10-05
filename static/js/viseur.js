/* Le viseur guidé (parcours D) — l'appareil photo de l'application, avec la
 * grille des tiers et des conseils EN DIRECT, calculés sur le téléphone sans
 * rien envoyer : la lumière (trop sombre, trop forte), l'immobilité (le
 * téléphone bouge : la photo sera floue), l'horizon (le téléphone penche).
 * En haut, le brief du coach : ce qu'il manque cette semaine, et comment.
 * Chaque photo prise s'ajoute aux photos prêtes ; on touche ensuite la marque
 * comme d'habitude. */
"use strict";

const Viseur = { flux: null, minuteur: null, avant: null, penche: 0, prises: 0, briefs: [] };

async function ouvrirViseur() {
  if (!navigator.mediaDevices?.getUserMedia) return $("#fichiers").click();
  try {
    if (window.DeviceOrientationEvent?.requestPermission) await DeviceOrientationEvent.requestPermission().catch(() => {});
    Viseur.flux = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" }, width: { ideal: 3024 }, height: { ideal: 4032 } }, audio: false });
  } catch (_) {
    return $("#fichiers").click();          // pas d'accès à l'appareil : la galerie, comme avant
  }
  const v = $("#viseur-video");
  v.srcObject = Viseur.flux;
  $("#viseur").hidden = false;
  document.body.classList.add("sans-defilement");
  Viseur.prises = 0; compte();
  addEventListener("deviceorientation", horizon);
  Viseur.minuteur = setInterval(mesurer, 400);
  afficherBriefViseur();
}

function fermerViseur() {
  clearInterval(Viseur.minuteur);
  removeEventListener("deviceorientation", horizon);
  Viseur.flux?.getTracks().forEach(t => t.stop());
  Viseur.flux = null; Viseur.avant = null;
  $("#viseur").hidden = true;
  document.body.classList.remove("sans-defilement");
}

function horizon(e) {
  // Portrait : gamma = inclinaison gauche-droite. Paysage : beta.
  const paysage = Math.abs(window.orientation || screen.orientation?.angle || 0) === 90;
  Viseur.penche = paysage ? (e.beta || 0) : (e.gamma || 0);
}

/* Une image 64×64 toutes les 400 ms : la luminance moyenne, et l'écart avec
 * l'image d'avant (le téléphone bouge). Rien ne sort du téléphone. */
function mesurer() {
  const v = $("#viseur-video");
  if (!v.videoWidth) return;
  const c = $("#viseur-mesure"), x = c.getContext("2d", { willReadFrequently: true });
  x.drawImage(v, 0, 0, 64, 64);
  const d = x.getImageData(0, 0, 64, 64).data;
  let lum = 0, mouvement = 0, bord = 0;
  const gris = new Float32Array(64 * 64);
  for (let i = 0, k = 0; i < d.length; i += 4, k++) {
    gris[k] = 0.2126 * d[i] + 0.7152 * d[i + 1] + 0.0722 * d[i + 2];
    lum += gris[k];
    if (Viseur.avant) mouvement += Math.abs(gris[k] - Viseur.avant[k]);
    if (k % 64 && k > 64) bord += Math.abs(gris[k] - gris[k - 1]) + Math.abs(gris[k] - gris[k - 64]);
  }
  lum /= 4096; mouvement /= 4096; bord /= 4096;
  Viseur.avant = gris;
  const conseils = [];
  if (lum < 60) conseils.push("Plus de lumière : approche-toi d'une fenêtre");
  else if (lum > 215) conseils.push("Trop de lumière : évite le soleil en face");
  if (mouvement > 14) conseils.push("Ne bouge plus : la photo serait floue");
  if (Math.abs(Viseur.penche) > 5) conseils.push("Redresse le téléphone : l'horizon penche");
  if (bord < 3 && lum >= 60) conseils.push("Rapproche-toi, ou fais la mise au point (touche l'écran)");
  const ok = !conseils.length;
  $("#viseur-conseil").textContent = ok ? "Parfait — déclenche" : conseils[0];
  $("#viseur-conseil").classList.toggle("ok", ok);
}

async function declencher() {
  const v = $("#viseur-video");
  if (!v.videoWidth) return;
  const c = document.createElement("canvas");
  c.width = v.videoWidth; c.height = v.videoHeight;
  c.getContext("2d").drawImage(v, 0, 0);
  const blob = await new Promise(r => c.toBlob(r, "image/jpeg", 0.92));
  const f = new File([blob], `viseur-${Date.now()}.jpg`, { type: "image/jpeg" });
  choisirPhotos([f], true);
  Viseur.prises++; compte();
  $("#viseur").classList.add("flash"); setTimeout(() => $("#viseur").classList.remove("flash"), 120);
}

function compte() {
  $("#viseur-compte").textContent = Viseur.prises ? `${Viseur.prises} prise${Viseur.prises > 1 ? "s" : ""}` : "";
}

async function chargerBriefs() {
  try { Viseur.briefs = (await api("/api/coach")).briefs; } catch (_) { Viseur.briefs = []; }
  const b = Viseur.briefs;
  $("#brief-coach").innerHTML = b.length ? `<details class="carte brief"><summary><b>Le brief du coach</b>
      <span class="doux petit"> · ${b.length} marque${b.length > 1 ? "s" : ""} à nourrir</span></summary>
      ${b.map(x => `<div class="brief-marque">${puce(x.marque)}<b>${esc(nomMarque(x.marque).split(" — ")[0])}</b>
        <span class="doux petit">— ${esc(x.titre.toLowerCase())}</span>
        <ul>${x.plans.map(p => `<li><b>${p.n} ×</b> ${esc(p.quoi)}</li>`).join("")}</ul>
        <p class="petit doux">${x.comment.map(esc).join(" · ")}</p></div>`).join("")}</details>` : "";
}

function afficherBriefViseur() {
  const b = Viseur.briefs[0];
  $("#viseur-brief").innerHTML = b
    ? `<b>${esc(nomMarque(b.marque).split(" — ")[0])}</b> · ${b.plans.slice(0, 2).map(p => `${p.n} × ${esc(p.quoi)}`).join(" ; ")}<br><span>${esc(b.comment[0])}</span>`
    : "Lumière du jour, le sujet au centre, téléphone stable.";
}

$("#ouvrir-viseur").addEventListener("click", ouvrirViseur);
$("#viseur-fermer").addEventListener("click", fermerViseur);
$("#viseur-fini").addEventListener("click", fermerViseur);
$("#viseur-declencher").addEventListener("click", declencher);
const _initDeposer = VUES.deposer_init;
VUES.deposer_init = () => { _initDeposer?.(); chargerBriefs(); };
