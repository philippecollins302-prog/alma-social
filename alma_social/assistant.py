"""« Demander » — la conversation avec l'application (§ 8 E).

« Combien de devis REGA ce mois-ci, et grâce à quoi ? » · « Mets SAZÚ en
pause » · « Pourquoi LMS PACA baisse ? ». L'agent répond AVEC LES DONNÉES —
un instantané calculé par le code, jamais des chiffres qu'il imaginerait —
et il peut agir, en annonçant ce qu'il fait.

Les actions passent par `pilotage` avec les droits de la personne qui
demande : un responsable ne met en pause que sa marque. La liste des actions
permises est courte et fermée ; le modèle peut en PROPOSER une autre, le
code ne l'exécute pas.

Sans clé, un lecteur de questions simple répond aux questions les plus
fréquentes (chiffres, pause, reprise, pourquoi ça baisse) et dit ce qu'il ne
sait pas faire.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, insert, select

from . import acces, db, ia, journal, mesure, pilotage, planificateur, securite


class Action(BaseModel):
    type: Literal["pause", "reprendre", "aucune"]
    marque: str = Field(description="l'identifiant de la marque (sazu, rega…)")
    heures: int = Field(description="pour une pause : 1 à 48")


class Reponse(BaseModel):
    reponse: str = Field(description="la réponse, en français, vouvoiement, courte, chiffres de l'instantané seulement")
    actions: list[Action]


SYSTEME = """Tu es l'assistant d'ALMA SOCIAL, l'outil qui gère les réseaux sociaux des marques
du Groupe Alma. Philippe (le PDG) ou un responsable de marque te pose une question,
souvent depuis son téléphone.
- Tu réponds en français, au vouvoiement, en trois phrases au plus, chiffres d'abord.
- Tu n'utilises QUE les chiffres de l'instantané fourni. Si la donnée n'y est pas, tu le dis.
- « Clients » = demandes de devis, commandes et appels attribués aux publications.
- Tu peux agir : mettre une marque en pause (48 h au plus) ou la reprendre. Tu n'agis que
  si on te le demande explicitement, et ta réponse annonce ce que tu fais.
- Tu ne promets rien que l'application ne sait pas faire."""


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", (s or "").lower()) if not unicodedata.combining(c))


def instantane(u: dict) -> dict:
    """Les chiffres que l'agent a le droit de citer — calculés ici, pas par lui."""
    out = {"aujourdhui": acces.aujourdhui().isoformat(), "bac_a_sable": journal.bac_a_sable(), "marques": []}
    for mid in securite.marques_de(u):
        m = acces.marque(mid)
        m30 = mesure.resume_marque(mid, 30)
        m7 = mesure.resume_marque(mid, 7)
        m14 = mesure.resume_marque(mid, 14)
        with db.moteur().connect() as c:
            a_venir = c.execute(select(func.count()).select_from(db.posts).where(
                db.posts.c.brand_id == mid, db.posts.c.status == "programme",
                db.posts.c.scheduled_at <= db.maintenant() + dt.timedelta(days=7))).scalar()
        out["marques"].append({
            "id": mid, "nom": m["name"], "en_pause": acces.en_pause(m),
            "clients_30j": m30["clients"], "par_type_30j": m30["par_type"], "clics_30j": m30["clics"],
            "clients_7j": m7["clients"], "clients_7j_precedents": m14["clients"] - m7["clients"],
            "clics_7j": m7["clics"], "clics_7j_precedents": m14["clics"] - m7["clics"],
            "publications_30j": m30["publications"] + m30["publications_simulees"],
            "meilleures_publications": [{"reseau": t["platform"], "clients": t["clients"], "texte": t["texte"]}
                                        for t in m30["top"]],
            "programmees_7j": a_venir, "photos_en_banque": planificateur.stock(m)})
    return out


def _marque_citee(question: str, u: dict) -> dict | None:
    q = _norm(question)
    candidates = []
    for mid in securite.marques_de(u):
        m = acces.marque(mid)
        noms = {_norm(m["name"]), mid.replace("-", " "), _norm(m["name"].split("—")[0].strip())}
        if mid == "lms-paca":
            noms |= {"lms paca", "paca", "marseille"}
        if mid == "lms":
            noms |= {"maison des sols"}
        for n in noms:
            if n and re.search(r"\b" + re.escape(n) + r"\b", q):
                candidates.append((len(n), m))
    return max(candidates, key=lambda x: x[0])[1] if candidates else None


def _sans_modele(question: str, u: dict, inst: dict) -> Reponse:
    q = _norm(question)
    m = _marque_citee(question, u)
    fiche = next((x for x in inst["marques"] if m and x["id"] == m["id"]), None)
    if re.search(r"\b(pause|arrete|stoppe|suspend)", q) and m:
        return Reponse(reponse=f"Je mets {m['name']} en pause 48 h : plus rien ne part, rien ne repart sans votre geste.",
                       actions=[Action(type="pause", marque=m["id"], heures=48)])
    if re.search(r"\b(reprend|relance|redemarre|reactive)", q) and m:
        return Reponse(reponse=f"Je relance {m['name']} : les publications retenues repartent.",
                       actions=[Action(type="reprendre", marque=m["id"], heures=0)])
    if re.search(r"pourquoi.*(baisse|recul|moins)", q) and fiche:
        c7, cp = fiche["clients_7j"], fiche["clients_7j_precedents"]
        k7, kp = fiche["clics_7j"], fiche["clics_7j_precedents"]
        raisons = []
        if fiche["en_pause"]:
            raisons.append("la marque est en pause")
        if fiche["photos_en_banque"] < 3:
            raisons.append(f"il ne reste que {fiche['photos_en_banque']} photo(s) en banque")
        if fiche["programmees_7j"] == 0:
            raisons.append("aucune publication programmée cette semaine")
        return Reponse(reponse=f"{fiche['nom']} : {c7} client(s) et {k7} clic(s) ces 7 jours, contre {cp} et {kp} "
                               f"la semaine d'avant. " + (("Piste : " + " ; ".join(raisons) + ".") if raisons else
                                                         "Rien d'anormal côté rythme ni stock ; l'analyse fine demande la clé IA."),
                       actions=[])
    if re.search(r"\b(combien|chiffre|devis|client|commande|appel|resultat)", q):
        cibles = [fiche] if fiche else inst["marques"]
        morceaux = []
        for f in cibles:
            t = f["par_type_30j"]
            morceaux.append(f"{f['nom']} : {f['clients_30j']} client(s) sur 30 jours "
                            f"({t.get('devis', 0)} devis, {t.get('commande', 0)} commandes, {t.get('appel', 0)} appels)")
        meilleur = (fiche or {}).get("meilleures_publications") or []
        fin = (f" Meilleure publication : {meilleur[0]['reseau']}, {meilleur[0]['clients']} client(s)." if meilleur else "")
        return Reponse(reponse=" · ".join(morceaux) + "." + fin, actions=[])
    return Reponse(reponse="Sans la clé IA, je sais répondre aux chiffres (« combien de devis REGA ? »), "
                           "mettre une marque en pause ou la relancer, et dire pourquoi elle baisse.", actions=[])


def demander(u: dict, question: str) -> dict:
    question = (question or "").strip()[:1000]
    if not question:
        raise ValueError("Posez une question.")
    inst = instantane(u)
    try:
        obj, modele = ia.appeler(SYSTEME, [{"type": "text", "text": "INSTANTANÉ (les seuls chiffres citables) :\n"
                                            + json.dumps(inst, ensure_ascii=False, default=str)
                                            + f"\n\nQUESTION : {question}"}],
                                 Reponse, max_tokens=2000, agent="assistant", objet=f"user:{u['id']}")
    except ia.SansCle:
        obj, modele = _sans_modele(question, u, inst), "lecteur-local"
    faites = []
    for a in obj.actions:
        if a.type == "aucune":
            continue
        if not securite.peut_voir(u, a.marque):
            faites.append({"type": a.type, "marque": a.marque, "fait": False, "raison": "marque hors de vos droits"})
            continue
        m = acces.marque(a.marque)
        par = f"{u['name']} (via Demander)"
        if a.type == "pause":
            pilotage.pause(m, par, a.heures or 48, "demandé à l'assistant")
        else:
            pilotage.reprendre(m, par)
        faites.append({"type": a.type, "marque": a.marque, "fait": True})
    with db.moteur().begin() as c:
        c.execute(insert(db.ask_threads).values(user_id=u["id"], question=question, reponse=obj.reponse,
                                                actions=faites, model=modele, created_at=db.maintenant()))
    return {"reponse": obj.reponse, "actions": faites, "modele": modele}


def historique(u: dict, limite: int = 20) -> list:
    t = db.ask_threads
    with db.moteur().connect() as c:
        return db.lignes(c.execute(select(t.c.question, t.c.reponse, t.c.actions, t.c.created_at)
                                   .where(t.c.user_id == u["id"]).order_by(t.c.id.desc()).limit(limite)))
