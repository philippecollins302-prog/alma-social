"""La qualification (§ 15.2, § 15.3) — une conversation qui fait d'un « DEVIS »
une fiche de prospect que le responsable peut rappeler.

Trois portes y mènent, et une seule page les sert (`/parler/<marque>`) :
- le **commentaire** « DEVIS » (REGA, LMS) ou « BOWL » (SAZÚ) sous une
  publication : la réponse donne le lien de la conversation (`portes.py`) ;
- le **QR code** d'un camion, d'un chantier, d'un sac : le lien tracé mène
  ici, avec son marqueur — le prospect reste rattaché à son support ;
- le **chat du site** de la marque (`/s/chat.js`) : un bouton qui ouvre la
  même page.

La règle de la page : **le nom et le téléphone d'abord**, la question
ensuite. Un prospect qui s'en va au milieu laisse au moins de quoi le
rappeler — une conversation interrompue avec un téléphone devient quand même
une fiche, au bout de deux heures.

Les questions sont celles de chaque métier (REGA : travaux, surface, commune,
délai, budget, rappel ; LMS : pièce, surface, sol, pose ou fourniture ; SAZÚ :
commande de groupe, entreprise, date). La première réponse est libre (« votre
projet en une phrase ») : le modèle, s'il y a une clé, y lit déjà ce qu'il
peut (« 40 m² de parquet à Lattes avant Noël » remplit trois cases), et on
ne repose jamais une question déjà répondue. Sans clé, des règles simples
lisent la surface et le délai, et la conversation pose le reste dans l'ordre.

La température est une RÈGLE écrite, pas l'humeur du modèle :
- **chaud** : un délai d'un mois au plus (SAZÚ : une date dans les 15 jours
  pour dix personnes ou plus) ;
- **tiède** : un délai de trois mois au plus, ou un budget annoncé ;
- **froid** : le reste (« je me renseigne », « l'an prochain », rien de dit).

La fiche part au responsable de la marque (le PDG en copie), urgente si le
prospect est chaud, avec la publication d'où il vient. Si Philippe branche un
outil (son CRM, un tableur), `SOCIAL_LEADS_WEBHOOK` reçoit la même fiche en
JSON, signée avec `SOCIAL_LEADS_WEBHOOK_SECRET` ; un export CSV existe aussi.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import unicodedata

from pydantic import BaseModel, Field
from sqlalchemy import insert, select, update

from . import acces, alertes, config, db, file, ia, journal, mesure, reseaux

log = logging.getLogger("alma_social.qualification")

MESSAGES_MAX = 40
TEXTE_MAX = 600
ABANDON = dt.timedelta(hours=2)

# Les questions de chaque métier : (champ, question en vouvoiement, en tutoiement).
_COMMUNE = ("commune", "Dans quelle commune ?", "C'est où ?")
_DELAI = ("delai", "Pour quand, idéalement ?", "Pour quand ?")
_RAPPEL = ("rappel", "Quel est le meilleur moment pour vous rappeler ?", "Quand est-ce qu'on peut t'appeler ?")
QUESTIONS = {
    "rega": [("travaux", "Quels travaux envisagez-vous (construction, rénovation, extension…) ?", ""),
             ("surface", "Quelle surface, à peu près (en m²) ?", ""), _COMMUNE, _DELAI,
             ("budget", "Avez-vous une enveloppe en tête ? « Je ne sais pas » est une bonne réponse.", ""), _RAPPEL],
    "vipplus": [("travaux", "De quoi avez-vous besoin (serrurerie, menuiserie, volet, portail, alarme…) ?", ""),
                _COMMUNE, _DELAI, _RAPPEL],
    "lms": [("piece", "Pour quelle pièce (ou quelles pièces) ?", ""),
            ("surface", "Quelle surface, à peu près (en m²) ?", ""),
            ("sol", "Quel sol souhaitez-vous (parquet, PVC, vinyle, stratifié…) ?", ""),
            ("pose", "Avec la pose, ou la fourniture seule ?", ""), _COMMUNE, _DELAI, _RAPPEL],
    "lms-paca": [("copropriete", "Pour quelle copropriété (ou quel immeuble) ?", ""),
                 ("besoin", "Quel est le besoin (entretien, réparation, travaux) ?", ""), _COMMUNE, _DELAI, _RAPPEL],
    "sazu": [("groupe", "", "C'est pour combien de personnes ?"),
             ("entreprise", "", "Pour quelle entreprise (ou à quel nom) ?"),
             ("date", "", "Pour quel jour, et à quelle heure ?")],
}
QUESTIONS_PAR_DEFAUT = [("besoin", "Quel est votre besoin ?", "C'est pour quoi ?"), _COMMUNE, _DELAI, _RAPPEL]
NOMS_CHAMPS = {"travaux": "Travaux", "surface": "Surface", "commune": "Commune", "delai": "Délai", "budget": "Budget",
               "rappel": "Rappel", "piece": "Pièce", "sol": "Sol", "pose": "Pose", "copropriete": "Copropriété",
               "besoin": "Besoin", "groupe": "Personnes", "entreprise": "Entreprise", "date": "Date",
               "projet": "Projet"}


class Lecture(BaseModel):
    """Ce que le modèle lit dans une réponse libre — rien d'inventé : une case
    qu'on ne peut pas remplir avec certitude reste vide."""
    champs: dict[str, str] = Field(description="champ → valeur, SEULEMENT pour ce qui est dit explicitement")


def _tu(m: dict) -> bool:
    return (m.get("voice") or {}).get("address") == "tu"


def questions(m: dict) -> list:
    return QUESTIONS.get(m["id"], QUESTIONS_PAR_DEFAUT)


def _q(m: dict, champ: str) -> str:
    for c_, vous, tu in questions(m):
        if c_ == champ:
            return (tu or vous) if _tu(m) else (vous or tu)
    return ""


def type_de(m: dict) -> str:
    return "commande" if m.get("sector") == "food" else "devis"


# ── Ouvrir, répondre ─────────────────────────────────────────────────────
def ouvrir(m: dict, porte: str = "chat", source: str = "", post_id=None, marqueur: str = "") -> dict:
    """Une conversation neuve. → la conversation, avec son premier message."""
    porte = porte if porte in ("chat", "qr", "commentaire", "message") else "chat"
    lien = None
    if marqueur:
        with db.moteur().connect() as c:
            lien = db.ligne(c.execute(select(db.links).where(db.links.c.code == marqueur[:40])))
        if lien and lien["brand_id"] != m["id"]:
            lien = None
    if lien:
        post_id = post_id or lien["post_id"]
        if (lien["kind"] or "") == "qr" and porte == "chat":
            porte = "qr"
            source = source or (lien["platform"] or "").removeprefix("terrain:")
        elif (lien["kind"] or "") == "chat" and porte == "chat":
            # le lien donné en réponse à un « DEVIS » sous une publication
            porte = "commentaire"
            source = source or reseaux.NOMS.get(lien["platform"], lien["platform"] or "")
    bonjour = (f"Salut ! Ici {m['name']}. Pour qu'on puisse te répondre, ton prénom ?" if _tu(m) else
               f"Bonjour, ici {m['name']}. Pour pouvoir vous répondre : votre nom ?")
    jeton = secrets.token_urlsafe(18)
    maintenant = db.maintenant()
    with db.moteur().begin() as c:
        cid = c.execute(insert(db.chats).values(
            brand_id=m["id"], token=jeton, entry_door=porte, source=source[:200], post_id=post_id,
            link_id=lien["id"] if lien else None, answers={}, status="en_cours",
            messages=[{"de": "marque", "texte": bonjour, "le": maintenant.isoformat()}],
            created_at=maintenant, updated_at=maintenant)).inserted_primary_key[0]
    journal.noter("systeme", "chat_ouvert", "chat", cid, m["id"], apres={"porte": porte, "source": source,
                                                                         "post_id": post_id})
    return chat(jeton)


def chat(jeton: str) -> dict | None:
    with db.moteur().connect() as c:
        return db.ligne(c.execute(select(db.chats).where(db.chats.c.token == jeton)))


def vue(ch: dict) -> dict:
    """Ce que voit le prospect : les messages et l'état, rien d'interne."""
    return {"messages": [{"de": x["de"], "texte": x["texte"]} for x in ch["messages"]],
            "fini": ch["status"] != "en_cours", "marque": ch["brand_id"]}


def _prochain(m: dict, rep: dict) -> str | None:
    """Le prochain champ à demander, dans l'ordre : nom, téléphone, projet, puis le métier."""
    for champ in ["nom", "telephone", "projet"] + [q[0] for q in questions(m)]:
        if not rep.get(champ):
            return champ
    return None


def _question(m: dict, champ: str, rep: dict) -> str:
    tu = _tu(m)
    if champ == "telephone":
        prenom = (rep.get("nom") or "").split(" ")[0]
        return (f"Merci {prenom} ! Ton numéro de téléphone, pour te rappeler si besoin ?" if tu else
                f"Merci{(' ' + prenom) if prenom else ''}. Votre numéro de téléphone, pour vous rappeler ?")
    if champ == "projet":
        return ("Dis-moi en une phrase ce que tu cherches." if tu else
                "Décrivez-moi votre projet en une phrase : je ne vous poserai ensuite que ce qui manque.")
    return _q(m, champ)


def telephone_valide(t: str) -> str:
    """→ le numéro au format +33…, ou '' s'il ne ressemble pas à un numéro."""
    chiffres = re.sub(r"[^\d+]", "", t or "")
    if chiffres.startswith("00"):
        chiffres = "+" + chiffres[2:]
    if re.fullmatch(r"0[1-9]\d{8}", chiffres):
        return "+33" + chiffres[1:]
    if re.fullmatch(r"\+33[1-9]\d{8}", chiffres) or re.fullmatch(r"\+\d{9,14}", chiffres):
        return chiffres
    return ""


def repondre(jeton: str, texte: str) -> dict:
    """Le prospect écrit. → la vue de la conversation (avec la réponse de la marque)."""
    ch = chat(jeton)
    if not ch:
        raise LookupError("conversation inconnue")
    texte = re.sub(r"\s+", " ", (texte or "").strip())[:TEXTE_MAX]
    if not texte or ch["status"] != "en_cours" or len(ch["messages"]) >= MESSAGES_MAX:
        return vue(ch)
    m = acces.marque(ch["brand_id"])
    rep = dict(ch["answers"] or {})
    msgs = list(ch["messages"]) + [{"de": "client", "texte": texte, "le": db.maintenant().isoformat()}]
    champ = _prochain(m, rep)
    reponse = ""
    if champ == "nom":
        rep["nom"] = texte[:80]
    elif champ == "telephone":
        tel = telephone_valide(texte)
        if tel:
            rep["telephone"] = tel
        else:
            reponse = ("Je n'arrive pas à lire ce numéro : tu peux le réécrire (ex. 06 12 34 56 78) ?" if _tu(m) else
                       "Je n'arrive pas à lire ce numéro : pouvez-vous le réécrire (ex. 06 12 34 56 78) ?")
    elif champ == "projet":
        rep["projet"] = texte
        rep.update({k: v for k, v in lire(m, texte).items() if not rep.get(k)})
    elif champ:
        rep[champ] = texte[:200]
        # Une réponse peut en contenir d'autres (« 30 m², à Lattes ») : on ne les repose pas.
        rep.update({k: v for k, v in _regles(m, texte).items() if not rep.get(k)})
    suivant = _prochain(m, rep)
    if not reponse:
        reponse = _question(m, suivant, rep) if suivant else _merci(m, rep)
    msgs.append({"de": "marque", "texte": reponse, "le": db.maintenant().isoformat()})
    vals = {"answers": rep, "messages": msgs, "updated_at": db.maintenant(),
            "name": (rep.get("nom") or "")[:120], "phone": (rep.get("telephone") or "")[:30]}
    with db.moteur().begin() as c:
        c.execute(update(db.chats).where(db.chats.c.id == ch["id"]).values(**vals))
    if not suivant:
        conclure(ch["id"])
    return vue(chat(jeton))


def _merci(m: dict, rep: dict) -> str:
    if _tu(m):
        return "Merci, c'est noté ! Quelqu'un de l'équipe te recontacte très vite."
    return "Merci, c'est noté. Le responsable vous rappelle très rapidement, au moment que vous avez indiqué."


# ── Lire une réponse libre ───────────────────────────────────────────────
def lire(m: dict, texte: str) -> dict:
    """Les cases qu'une phrase remplit déjà. Le modèle si on en a un, des règles sinon."""
    champs = [q[0] for q in questions(m)]
    out = _regles(m, texte)
    try:
        obj, _ = ia.appeler(
            "Tu lis la première phrase d'un prospect et tu remplis, parmi ces cases, SEULEMENT celles que la "
            "phrase dit explicitement : " + ", ".join(champs) + ". Valeurs courtes, dans les mots du prospect. "
            "N'invente rien : une case incertaine est absente.",
            [{"type": "text", "text": f"Marque : {m['name']} ({m.get('activity', '')[:200]})\nPhrase : {texte}"}],
            Lecture, max_tokens=600, usage="relation", marque_id=m["id"], objet="qualification")
        out.update({k: str(v)[:200] for k, v in obj.champs.items() if k in champs and str(v).strip()})
    except ia.ErreurIA:
        pass
    return out


def _sans_accents(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def _regles(m: dict, texte: str) -> dict:
    t = _sans_accents(texte.lower())
    champs = {q[0] for q in questions(m)}
    out = {}
    s = re.search(r"(\d+(?:[.,]\d+)?)\s*(m2|m²|metres? carres?|mq)\b", t.replace("m²", "m2"))
    if s and "surface" in champs:
        out["surface"] = f"{s.group(1)} m²"
    g = re.search(r"\b(\d{1,3})\s*(personnes|pers|couverts|collegues|salaries)\b", t)
    if g and "groupe" in champs:
        out["groupe"] = g.group(1)
    if "delai" in champs and _mois_de_delai(texte) is not None:
        out["delai"] = _extrait_delai(texte)
    # « à Lattes », « sur Castelnau-le-Lez », « vers Pérols » : un nom propre après la préposition.
    c_ = re.search(r"\b(?:à|a|sur|vers|dans)\s+((?:[A-ZÉÈÀ][\w'’-]+)(?:[\s-](?:le|la|les|de|du|des|en|sur|[A-ZÉÈÀ][\w'’-]+))*)",
                   texte)
    if c_ and "commune" in champs:
        out["commune"] = c_.group(1).strip()[:80]
    for champ, mots in _MOTS_METIER.items():
        if champ in champs:
            vus = [m for m in mots if re.search(rf"\b{m}", t)]
            if vus:
                out[champ] = ", ".join(dict.fromkeys(_JOLI.get(v, v) for v in vus))[:120]
    return out


# Les mots du métier qui remplissent une case d'eux-mêmes (sans accents, en minuscules).
_MOTS_METIER = {
    "travaux": ["extension", "renovation", "construction", "surelevation", "toiture", "facade", "maconnerie",
                "isolation", "salle de bains?", "cuisine", "garage", "piscine", "terrasse", "rehabilitation"],
    "piece": ["salon", "sejour", "chambres?", "cuisine", "salle de bains?", "couloir", "entree", "bureau",
              "escalier", "toute la maison", "appartement"],
    "sol": ["parquet", "pvc", "vinyle", "stratifie", "carrelage", "moquette", "lino", "beton cire", "sol souple"],
    "pose": ["pose comprise", "avec pose", "fourniture seule", "fourniture et pose", "sans pose"],
}
_JOLI = {"renovation": "rénovation", "surelevation": "surélévation", "facade": "façade", "maconnerie": "maçonnerie",
         "rehabilitation": "réhabilitation", "salle de bains?": "salle de bains", "sejour": "séjour",
         "chambres?": "chambre", "entree": "entrée", "stratifie": "stratifié", "beton cire": "béton ciré"}


def _extrait_delai(texte: str) -> str:
    """Le morceau de phrase qui dit le délai (« urgent », « avant Noël », « en mars »), pas toute la phrase."""
    t = _sans_accents(texte.lower())
    m = re.search(r"\b((?:avant|pour|d'ici|en|dans|le|des|au)\s+)?\b(urgent\w*|vite|des que possible|asap|"
                  r"au plus tot|cette semaine|semaine prochaine|tout de suite|demain|noel|printemps|ete|"
                  r"\d{1,2}\s*(?:jours?|semaines?|mois|ans?)|(?:\d{1,2}(?:er)?\s+)?(?:" + "|".join(_MOIS) + r")|"
                  r"je me renseigne|pas presse|l'an prochain)\b", t)
    if not m:
        return texte[:120]
    return texte[m.start():m.end()].strip()[:60]


_MOIS = ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet", "aout", "septembre", "octobre",
         "novembre", "decembre"]


def _mois_de_delai(texte: str, aujourd_hui: dt.date | None = None) -> float | None:
    """Combien de mois d'ici le délai dit ? None s'il ne dit rien de lisible."""
    t = _sans_accents((texte or "").lower())
    j = aujourd_hui or acces.aujourdhui()
    if re.search(r"\b(je me renseigne|pas presse|aucune idee|un jour|pas de date|plus tard|l'an prochain|"
                 r"l'annee prochaine)\b", t):
        return 12.0
    if re.search(r"\b(urgent|urgence|vite|des que possible|asap|au plus tot|cette semaine|semaine prochaine|"
                 r"tout de suite|immediat|ce mois|demain|aujourd'hui|ce soir|ce midi|"
                 r"(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)( prochain)?)\b", t):
        return 0.3
    d = re.search(r"\b(\d{1,2})\s*/\s*(\d{1,2})\b", t) or re.search(
        r"\b(\d{1,2})(?:er)?\s+(" + "|".join(_MOIS) + r")\b", t)
    if d:
        jour = int(d.group(1))
        mois = int(d.group(2)) if d.group(2).isdigit() else _MOIS.index(d.group(2)) + 1
        if 1 <= mois <= 12 and 1 <= jour <= 31:
            try:
                cible = dt.date(j.year, mois, jour)
            except ValueError:
                cible = None
            if cible:
                if cible < j:
                    cible = dt.date(j.year + 1, mois, min(jour, 28))
                return (cible - j).days / 30
    n = re.search(r"\b(\d{1,2})\s*(jours?|semaines?|mois|ans?)\b", t)
    if n:
        k = int(n.group(1))
        unite = n.group(2)
        return k / 30 if unite.startswith("jour") else k / 4.3 if unite.startswith("semaine") else \
            k if unite == "mois" else 12.0 * k
    if "noel" in t:
        cible = dt.date(j.year, 12, 25)
        return max(0.0, (cible - j).days / 30)
    for i, nom in enumerate(_MOIS, start=1):
        if re.search(rf"\b{nom}\b", t):
            an = j.year if i >= j.month else j.year + 1
            return max(0.0, (dt.date(an, i, 15) - j).days / 30)
    if re.search(r"\b(printemps)\b", t):
        an = j.year if j.month < 4 else j.year + 1
        return (dt.date(an, 4, 15) - j).days / 30
    if re.search(r"\b(ete)\b", t):
        an = j.year if j.month < 7 else j.year + 1
        return (dt.date(an, 7, 15) - j).days / 30
    return None


def temperature(m: dict, rep: dict) -> tuple:
    """→ (chaud | tiede | froid, la raison en une phrase). Une règle, écrite ici."""
    if m.get("sector") == "food":
        n = int(re.sub(r"\D", "", rep.get("groupe") or "") or 0)
        jours = None
        d = _mois_de_delai(rep.get("date") or "")
        if d is not None:
            jours = d * 30
        if n >= 10 and jours is not None and jours <= 15:
            return "chaud", f"{n} personnes, dans les 15 jours"
        if n >= 10:
            return "tiede", f"{n} personnes, date à préciser ou lointaine"
        return "froid", "petit groupe" if n else "nombre de personnes non dit"
    mois = _mois_de_delai(rep.get("delai") or "") if rep.get("delai") else _mois_de_delai(rep.get("projet") or "")
    budget = rep.get("budget") and not re.search(r"sai[st] pas|aucune|\?", _sans_accents(rep["budget"].lower()))
    if mois is not None and mois <= 1:
        return "chaud", "délai d'un mois au plus"
    if (mois is not None and mois <= 3) or budget:
        return "tiede", "délai de trois mois au plus" if (mois is not None and mois <= 3) else "budget annoncé"
    return "froid", "délai lointain" if mois is not None else "aucun délai dit"


# ── La fiche ─────────────────────────────────────────────────────────────
def conclure(chat_id: int, interrompue: bool = False) -> int | None:
    """La conversation devient une fiche (un client, au sens de la mesure)."""
    with db.moteur().connect() as c:
        ch = db.ligne(c.execute(select(db.chats).where(db.chats.c.id == chat_id)))
    if not ch or ch["lead_id"]:
        return ch["lead_id"] if ch else None
    m = acces.marque(ch["brand_id"])
    rep = ch["answers"] or {}
    temp, raison = temperature(m, rep)
    marqueur = ""
    if ch["link_id"]:
        with db.moteur().connect() as c:
            l = db.ligne(c.execute(select(db.links).where(db.links.c.id == ch["link_id"])))
        marqueur = l["code"] if l else ""
    source = ch["source"] or {"commentaire": "commentaire", "qr": "QR", "chat": "chat du site",
                              "message": "message privé"}[ch["entry_door"]]
    lid = mesure.enregistrer_lead(m["id"], type_de(m), ch["entry_door"], marqueur=marqueur, post_id=ch["post_id"],
                                  source=source, note=("conversation interrompue — " if interrompue else "")
                                  + (rep.get("projet") or "")[:500], par="qualification")
    qualif = {k: v for k, v in rep.items() if k not in ("nom", "telephone")}
    with db.moteur().begin() as c:
        c.execute(update(db.leads).where(db.leads.c.id == lid).values(
            temperature=temp, entry_door=ch["entry_door"], first_reply_s=0,
            qualification={**qualif, "contact": {"nom": rep.get("nom", ""), "telephone": rep.get("telephone", "")},
                           "raison": raison}))
        c.execute(update(db.chats).where(db.chats.c.id == chat_id).values(
            status="abandonne" if interrompue else "qualifie", temperature=temp, lead_id=lid))
    journal.noter("qualification", "prospect", "lead", lid, m["id"],
                  apres={"temperature": temp, "raison": raison, "porte": ch["entry_door"], "interrompue": interrompue})
    fiche = fiche_texte(m, {**ch, "answers": rep}, temp, raison, interrompue)
    alertes.alerter(f"{m['name']} — prospect {_ICONES[temp]} {temp.replace('tiede', 'tiède')} : "
                    f"{rep.get('nom') or 'sans nom'}", fiche, marque=m["id"],
                    niveau="urgent" if temp == "chaud" else "info", type_="prospect", dedup=f"lead:{lid}")
    if os.environ.get("SOCIAL_LEADS_WEBHOOK", "").strip():
        file.ajouter("webhook_lead", {"lead_id": lid}, dedup=f"webhook_lead:{lid}", essais_max=6)
    return lid


_ICONES = {"chaud": "🔥", "tiede": "🌤", "froid": "❄"}


def origine(post_id) -> str:
    if not post_id:
        return ""
    with db.moteur().connect() as c:
        p = db.ligne(c.execute(select(db.posts).where(db.posts.c.id == post_id)))
    if not p:
        return ""
    quand = f"{p['published_at']:%d/%m}" if p.get("published_at") else "à venir"
    return (f"{reseaux.NOMS.get(p['platform'], p['platform'])}, publiée le {quand} : "
            f"« {(p['text'] or '').splitlines()[0][:120] if p['text'] else ''} »")


def fiche_texte(m: dict, ch: dict, temp: str, raison: str, interrompue: bool = False) -> str:
    rep = ch["answers"] or {}
    lignes = [f"{_ICONES[temp]} {temp.replace('tiede', 'tiède').upper()} — {raison}",
              f"Nom : {rep.get('nom') or '—'}", f"Téléphone : {rep.get('telephone') or '—'}", ""]
    lignes += [f"{NOMS_CHAMPS.get(k, k)} : {v}" for k, v in rep.items() if k not in ("nom", "telephone") and v]
    porte = {"commentaire": "un commentaire", "qr": "un QR code", "chat": "le chat du site",
             "message": "un message privé"}[ch["entry_door"]]
    lignes += ["", f"Arrivé par {porte}" + (f" ({ch['source']})" if ch.get("source") else "") + "."]
    o = origine(ch.get("post_id"))
    if o:
        lignes.append(f"Publication d'origine — {o}")
    if interrompue:
        lignes.append("La conversation s'est arrêtée avant la fin : rappelez pour compléter.")
    return "\n".join(lignes)


def abandons() -> int:
    """Une conversation arrêtée en route, mais avec un téléphone : c'est une fiche
    quand même. Sans téléphone, il n'y a personne à rappeler — on la clôt."""
    limite = db.maintenant() - ABANDON
    with db.moteur().connect() as c:
        vieux = db.lignes(c.execute(select(db.chats).where(db.chats.c.status == "en_cours",
                                                           db.chats.c.updated_at <= limite)))
    n = 0
    for ch in vieux:
        if (ch["answers"] or {}).get("telephone"):
            conclure(ch["id"], interrompue=True)
            n += 1
        else:
            with db.moteur().begin() as c:
                c.execute(update(db.chats).where(db.chats.c.id == ch["id"]).values(status="abandonne"))
    return n


# ── Vers l'extérieur ─────────────────────────────────────────────────────
def charge_utile(lead_id: int) -> dict:
    with db.moteur().connect() as c:
        l = db.ligne(c.execute(select(db.leads).where(db.leads.c.id == lead_id)))
    if not l:
        return {}
    q = dict(l["qualification"] or {})
    contact = q.pop("contact", {})
    raison = q.pop("raison", "")
    return {"id": l["id"], "marque": l["brand_id"], "type": l["type"], "temperature": l["temperature"],
            "raison": raison, "porte": l["entry_door"], "source": l["source"], "nom": contact.get("nom", ""),
            "telephone": contact.get("telephone", ""), "reponses": q, "publication_id": l["post_id"],
            "publication": origine(l["post_id"]), "cree_le": l["created_at"].isoformat()}


@file.traitant("webhook_lead")
def envoyer_webhook(pl: dict):
    """La fiche, en JSON, vers l'outil de Philippe. Signée si un secret est posé."""
    url = os.environ.get("SOCIAL_LEADS_WEBHOOK", "").strip()
    if not url:
        return
    corps = json.dumps(charge_utile(pl["lead_id"]), ensure_ascii=False).encode()
    entetes = {"Content-Type": "application/json"}
    secret = os.environ.get("SOCIAL_LEADS_WEBHOOK_SECRET", "").strip()
    if secret:
        entetes["X-Alma-Signature"] = "sha256=" + hmac.new(secret.encode(), corps, hashlib.sha256).hexdigest()
    try:
        r = _http_post(url, corps, entetes)
    except Exception as e:
        raise file.Reessayer(f"webhook injoignable : {type(e).__name__}")
    if r >= 500 or r == 429:
        raise file.Reessayer(f"webhook {r}")
    if r >= 400:
        raise file.Abandon(f"webhook refusé ({r})")


def _http_post(url: str, corps: bytes, entetes: dict) -> int:
    import httpx
    return httpx.post(url, content=corps, headers=entetes, timeout=15).status_code


def export_csv(marque_ids: list, jours: int = 90) -> str:
    import csv
    import io
    depuis = db.maintenant() - dt.timedelta(days=jours)
    with db.moteur().connect() as c:
        ids = [r[0] for r in c.execute(select(db.leads.c.id).where(
            db.leads.c.brand_id.in_(marque_ids), db.leads.c.created_at >= depuis,
            db.leads.c.temperature != "").order_by(db.leads.c.id.desc()))]
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["id", "date", "marque", "température", "raison", "nom", "téléphone", "porte", "source",
                "réponses", "publication"])
    for i in ids:
        d = charge_utile(i)
        w.writerow([d["id"], d["cree_le"][:16].replace("T", " "), d["marque"], d["temperature"], d["raison"],
                    d["nom"], d["telephone"], d["porte"], d["source"],
                    " · ".join(f"{NOMS_CHAMPS.get(k, k)} : {v}" for k, v in d["reponses"].items()), d["publication"]])
    return "﻿" + buf.getvalue()


def url(marque_id: str) -> str:
    return f"{config.url_publique()}/parler/{marque_id}"
