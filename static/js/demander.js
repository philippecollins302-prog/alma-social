/* Demander — une question, à l'écrit ou à la voix. L'agent répond avec les
 * chiffres de l'application, et agit (pause, reprise) en l'annonçant. */
"use strict";

const IDEES = ["Combien de clients ce mois-ci, et grâce à quoi ?", "Pourquoi SAZÚ baisse ?", "Mets REGA en pause"];

async function vueDemander() {
  const ou = $("#v-demander");
  ou.innerHTML = `<div class="entete-vue"><h1>Demander</h1></div>
    <div class="suggestions">${IDEES.map(q => `<button data-idee="${esc(q)}">${esc(q)}</button>`).join("")}</div>
    <div class="fil" id="fil"></div>
    <form class="saisie" id="f-demander"><button class="micro" id="micro-q" type="button" aria-label="Dicter">🎙</button>
      <input class="champ" id="question" placeholder="Votre question…" autocomplete="off">
      <button class="demander-puce" style="padding:0 16px">✦</button></form>`;
  dicter($("#micro-q"), $("#question"), poser);
  try {
    const h = await api("/api/demander");
    $("#fil").innerHTML = h.fil.slice().reverse().map(x => bulles(x.question, x.reponse, x.actions)).join("");
    scrollTo(0, document.body.scrollHeight);
  } catch (_) { /* un fil vide n'empêche pas de demander */ }
}

function bulles(q, r, actions = []) {
  const faits = (actions || []).map(a => a.fait ? `✓ ${a.type === "pause" ? "Pause" : "Reprise"} : ${esc(nomMarque(a.marque))}`
    : `✗ ${esc(a.raison || "non fait")}`).join("<br>");
  return `<div class="bulle moi">${esc(q)}</div><div class="bulle app">${esc(r)}${faits ? `<span class="fait">${faits}</span>` : ""}</div>`;
}

async function poser(question) {
  question = (question || "").trim();
  if (!question) return;
  $("#question").value = "";
  $("#fil").insertAdjacentHTML("beforeend", `<div class="bulle moi">${esc(question)}</div><div class="bulle app doux" id="attente-rep">…</div>`);
  scrollTo(0, document.body.scrollHeight);
  try {
    const r = await api("/api/demander", { json: { question } });
    $("#attente-rep").outerHTML = bulles("", r.reponse, r.actions).replace('<div class="bulle moi"></div>', "");
    if (r.actions.some(a => a.fait)) rafraichirMoi();
  } catch (err) { $("#attente-rep").outerHTML = `<div class="bulle app erreur">${esc(err.message)}</div>`; }
  scrollTo(0, document.body.scrollHeight);
}

$("#v-demander").addEventListener("submit", e => { e.preventDefault(); poser($("#question").value); });
$("#v-demander").addEventListener("click", e => { if (e.target.dataset.idee) poser(e.target.dataset.idee); });

VUES.demander = vueDemander;
