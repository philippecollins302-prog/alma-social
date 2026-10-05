"""Lire les avis (§ 16.3) — ce que les clients aiment, ce qui les agace, et
ce que les concurrents font mieux.

Les thèmes se reconnaissent à leurs mots (une liste écrite ici, par métier),
le sentiment à la note : 4–5 ★ pour, 1–2 ★ contre, 3 ★ partagé. C'est
volontairement simple et vérifiable : chaque thème cité dans la note du lundi
renvoie à des avis qu'on peut relire, et rien ne dépend d'un modèle.

Les avis des concurrents ne sont PAS aspirés (les conditions de Google
l'interdisent) : un responsable colle ceux qu'il a lus, l'application les
range. Ce qui revient chez eux et pas chez nous est ce qu'ils font mieux.

Chaque objection récurrente devient une idée de contenu qui y répond — c'est
le Stratège qui la reprend, pas un texte écrit d'office.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re

from sqlalchemy import insert, select

from . import db, garde_fous, journal

THEMES = {
    "délais": r"retard|attente|attendu|rapide|rapidite|delai|a l'heure|ponctuel|vite|long|lent",
    "propreté": r"propre|sale|nettoy|poussiere|degat|salete",
    "prix": r"prix|cher|tarif|rapport qualite|abordable|couteux|facture",
    "finition": r"finition|soign|malfacon|defaut|travail bien fait|du beau travail|qualite du travail|precis",
    "écoute": r"ecoute|conseil|explique|explication|rappel|joignable|repondu|reponse|injoignable|devis",
    "équipe": r"equipe|sympa|aimable|gentil|professionnel|poli|accueil|souriant|serviable",
    "goût": r"delicieux|savoureux|gout|fade|trop sale|epice|bon(ne)?s?\b|excellent|recette",
    "quantité": r"portion|copieux|quantite|faim|genereu|petit bowl|rassasi",
    "livraison": r"livraison|livreur|livre|froid|tiede|emballage|renvers",
}
METIERS = {"food": ("délais", "goût", "quantité", "livraison", "prix", "équipe", "propreté"),
           "btp": ("délais", "propreté", "prix", "finition", "écoute", "équipe"),
           "b2b": ("délais", "prix", "finition", "écoute", "équipe")}
IDEES = {
    "délais": "Montrer un chantier tenu à la date, jour par jour (ou, pour SAZÚ, le chrono d'une commande).",
    "propreté": "Avant/après du nettoyage de fin de chantier : la pièce rendue.",
    "prix": "Expliquer ce que comprend un devis, ligne par ligne, sans chiffre inventé.",
    "finition": "Gros plan sur une finition : le joint, l'angle, la plinthe.",
    "écoute": "Présenter la personne qui répond au téléphone et rappelle.",
    "équipe": "Présenter l'équipe, un visage par semaine.",
    "goût": "Les coulisses d'une recette : la cuisson du matin.",
    "quantité": "Montrer la vraie portion d'un bowl, dans la main.",
    "livraison": "Montrer l'emballage et le trajet : le bowl arrive chaud.",
}
MIN_MENTIONS = 2


def themes_de(texte: str, secteur: str = "") -> list:
    t = garde_fous._sans_accents((texte or "").lower())
    permis = METIERS.get(secteur, tuple(THEMES))
    return [th for th in permis if re.search(rf"\b(?:{THEMES[th]})", t)]


def _sens(note) -> int:
    if note is None:
        return 0
    return 1 if note >= 4 else -1 if note <= 2 else 0


def compter(avis: list, secteur: str) -> dict:
    """avis : [(note, texte)] → thème → {pour, contre}."""
    out = {}
    for note, texte in avis:
        s = _sens(note)
        for th in themes_de(texte, secteur):
            d = out.setdefault(th, {"pour": 0, "contre": 0})
            if s > 0:
                d["pour"] += 1
            elif s < 0:
                d["contre"] += 1
    return out


def ajouter_concurrent(concurrent_id: int, note, texte: str, par: str = "") -> bool:
    """Un avis de concurrent, collé à la main. → False s'il était déjà là."""
    texte = (texte or "").strip()
    if not texte:
        return False
    empreinte = hashlib.sha256(f"{concurrent_id}:{texte.lower()}".encode()).hexdigest()
    with db.moteur().begin() as c:
        if c.execute(select(db.competitor_reviews.c.id).where(db.competitor_reviews.c.fingerprint == empreinte)).first():
            return False
        c.execute(insert(db.competitor_reviews).values(
            competitor_id=concurrent_id, rating=int(note) if note not in (None, "") else None, text=texte[:3000],
            fingerprint=empreinte, created_at=db.maintenant()))
    journal.noter(par or "systeme", "avis_concurrent", "competitor", concurrent_id)
    return True


def lecture(m: dict, jours: int = 90) -> dict:
    """→ {aiment, agacent, eux_mieux, idees, phrase, avis}."""
    depuis = db.maintenant() - dt.timedelta(days=jours)
    secteur = m.get("sector") or ""
    with db.moteur().connect() as c:
        nous = [(r["rating"], r["text"]) for r in db.lignes(c.execute(select(db.reviews).where(
            db.reviews.c.brand_id == m["id"], db.reviews.c.received_at >= depuis)))]
        conc = [x["id"] for x in db.lignes(c.execute(select(db.competitors).where(db.competitors.c.brand_id == m["id"])))]
        eux = [(r["rating"], r["text"]) for r in db.lignes(c.execute(select(db.competitor_reviews).where(
            db.competitor_reviews.c.competitor_id.in_(conc or [0]))))]
    a, b = compter(nous, secteur), compter(eux, secteur)
    aiment = sorted([t for t, d in a.items() if d["pour"] >= MIN_MENTIONS], key=lambda t: -a[t]["pour"])[:3]
    agacent = sorted([t for t, d in a.items() if d["contre"] >= MIN_MENTIONS], key=lambda t: -a[t]["contre"])[:3]
    # Ce qu'ils font mieux : un thème loué chez eux, et chez nous absent ou critiqué.
    eux_mieux = [t for t, d in sorted(b.items(), key=lambda x: -x[1]["pour"])
                 if d["pour"] >= MIN_MENTIONS and a.get(t, {}).get("pour", 0) <= a.get(t, {}).get("contre", 0)][:2]
    idees = [IDEES[t] for t in (agacent + [t for t in eux_mieux if t not in agacent])][:3]
    if not nous:
        phrase = "Aucun avis relevé sur la période."
    else:
        morceaux = []
        if aiment:
            morceaux.append("ils aiment " + ", ".join(aiment))
        if agacent:
            morceaux.append("ce qui agace : " + ", ".join(agacent))
        if eux_mieux:
            morceaux.append("les concurrents sont mieux notés sur " + ", ".join(eux_mieux))
        phrase = (f"{len(nous)} avis — " + " ; ".join(morceaux) + ".") if morceaux else \
            f"{len(nous)} avis, aucun thème qui revienne au moins deux fois."
    return {"aiment": aiment, "agacent": agacent, "eux_mieux": eux_mieux, "idees": idees, "phrase": phrase,
            "nous": a, "eux": b, "avis": len(nous), "avis_concurrents": len(eux)}
