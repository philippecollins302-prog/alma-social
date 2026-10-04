"""Le choix de l'heure — il part du bon sens du secteur, puis apprend sur VOS chiffres.

Au départ, des heures raisonnables par secteur : avant midi et avant le soir
pour SAZÚ (le moment où l'on commande), les débuts de journée en semaine pour
le BTP et le B2B. Ensuite, chaque mois, le profil se recale sur les résultats
réels de la marque sur ce réseau : une heure qui marche mieux que la médiane
monte, une heure qui marche moins bien descend. Les premières observations
pèsent peu (quatre « observations fictives » d'a priori) : on ne bouleverse
pas un calendrier sur la foi de deux publications.

Les résultats SIMULÉS du bac à sable ne sont jamais appris.
"""
from __future__ import annotations

import datetime as dt
import math
import statistics
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
DEBUT, FIN = 6 * 60 + 30, 22 * 60 + 30          # fenêtre de publication (minutes)
PAS = 15
ESPACEMENT_RESEAU = dt.timedelta(hours=16)       # même marque, même réseau
DECALAGE_SOEURS = dt.timedelta(minutes=25)       # même publication, réseaux différents
POIDS_A_PRIORI = 4.0

# (heure, hauteur, largeur en heures) — des bosses, pas des créneaux rigides.
_PICS = {
    "food":   {"semaine": [(11.0, 1.0, 0.7), (18.0, 0.95, 0.8)],
               "vendredi": [(11.0, 1.0, 0.7), (18.25, 1.0, 0.9)],
               "samedi": [(11.5, 0.95, 0.8), (18.5, 1.0, 0.9)],
               "dimanche": [(11.5, 0.9, 0.8), (18.0, 0.95, 0.8)]},
    "btp":    {"semaine": [(7.75, 1.0, 0.9), (12.5, 0.6, 0.8), (18.5, 0.55, 1.0)],
               "samedi": [(10.0, 0.35, 1.5)], "dimanche": [(10.5, 0.25, 1.5)]},
    "b2b":    {"semaine": [(8.0, 1.0, 0.9), (12.25, 0.7, 0.7), (17.5, 0.5, 0.8)],
               "samedi": [(10.0, 0.25, 1.5)], "dimanche": [(10.0, 0.15, 1.5)]},
    "retail": {"semaine": [(12.5, 0.8, 0.8), (19.0, 1.0, 1.0)],
               "samedi": [(10.0, 1.0, 1.0), (17.0, 0.6, 1.2)], "dimanche": [(10.5, 0.7, 1.0), (20.0, 0.7, 1.0)]},
    "b2c":    {"semaine": [(12.5, 0.8, 0.8), (19.5, 1.0, 1.0)],
               "samedi": [(11.0, 0.9, 1.0), (20.0, 0.8, 1.0)], "dimanche": [(11.0, 0.9, 1.0), (20.0, 0.8, 1.0)]},
}


def _pics(secteur: str, jour_semaine: int):
    s = _PICS.get(secteur) or _PICS["b2c"]
    nom = {4: "vendredi", 5: "samedi", 6: "dimanche"}.get(jour_semaine, "semaine")
    return s.get(nom) or s["semaine"]


def a_priori(secteur: str, reseau: str, jour_semaine: int, minute: int) -> float:
    h = minute / 60.0
    w = max([haut * math.exp(-((h - pic) / larg) ** 2) for pic, haut, larg in _pics(secteur, jour_semaine)] + [0.0])
    w = 0.04 + 0.96 * w
    if reseau in ("linkedin", "linkedin_perso"):
        if jour_semaine >= 5:
            w *= 0.1                     # LinkedIn ne travaille pas le week-end
        elif jour_semaine in (1, 2, 3):
            w *= 1.1
        if h >= 17:
            w *= 0.6
    elif reseau == "gbp":
        w *= 1.15 if 8 <= h <= 10.5 else 0.9   # une fiche se consulte en préparant sa journée
    elif reseau == "pinterest":
        w *= 1.1 if (h >= 19 or jour_semaine >= 5) else 0.9
    elif reseau == "tiktok":
        w *= 1.2 if 18 <= h <= 21.5 else 1.0
    return w


def cle(jour_semaine: int, heure: int) -> str:
    return f"{jour_semaine}-{heure}"


def poids(secteur: str, reseau: str, jour_semaine: int, minute: int, profil: dict | None = None) -> float:
    """A priori × ce que les chiffres de la marque ont appris de cette heure."""
    w = a_priori(secteur, reseau, jour_semaine, minute)
    if profil:
        p = profil.get(cle(jour_semaine, minute // 60))
        if p:
            n, rel = p["n"], p["rel"]
            w *= (POIDS_A_PRIORI + n * rel) / (POIDS_A_PRIORI + n)
    return w


def apprendre(observations: list) -> dict:
    """`observations` : [(jour_semaine, heure, score)] des publications RÉELLES.
    → profil {"j-h": {"n": …, "rel": …}} où `rel` compare à la médiane."""
    if not observations:
        return {}
    med = statistics.median([s for _, _, s in observations]) or 1e-9
    seaux = {}
    for j, h, s in observations:
        seaux.setdefault(cle(j, h), []).append(s / med)
    return {k: {"n": len(v), "rel": round(statistics.fmean(v), 3)} for k, v in seaux.items()}


def score_engagement(m: dict) -> float:
    """Ce qui compte vraiment, pondéré : un clic ou un partage vaut plus qu'un like."""
    base = max(m.get("reach") or m.get("views") or 0, 1)
    utile = (m.get("likes", 0) + 2 * m.get("comments", 0) + 3 * m.get("shares", 0)
             + 2 * m.get("saves", 0) + 4 * m.get("clicks", 0))
    return utile / base


def paris(instant_utc: dt.datetime) -> dt.datetime:
    return instant_utc.replace(tzinfo=dt.timezone.utc).astimezone(PARIS)


def utc(instant_paris: dt.datetime) -> dt.datetime:
    return instant_paris.astimezone(dt.timezone.utc).replace(tzinfo=None)


def choisir_heure(secteur: str, reseau: str, jour: dt.date, occupes: list, soeurs: list,
                  profil: dict | None = None, apres: dt.datetime | None = None,
                  heure_imposee: str = ""):
    """→ l'heure (Paris, avec fuseau) la meilleure de ce jour, ou None.

    `occupes` : instants déjà pris par la MÊME marque sur le MÊME réseau ;
    `soeurs` : instants des autres réseaux de la même publication (on ne sort
    pas tout à la même minute) ; `apres` : rien avant (maintenant + marge).
    """
    meilleur, choix = -1.0, None
    if heure_imposee:
        h, m = (int(x) for x in heure_imposee.split(":"))
        candidats = [h * 60 + m + d for d in (0, 30, 60, 90, -30)]
    else:
        candidats = range(DEBUT, FIN + 1, PAS)
    for minute in candidats:
        if not DEBUT - 60 <= minute <= FIN:
            continue
        t = dt.datetime.combine(jour, dt.time(minute // 60, minute % 60), tzinfo=PARIS)
        if apres and t < apres:
            continue
        if any(abs(t - o) < ESPACEMENT_RESEAU for o in occupes):
            continue
        if any(abs(t - s) < DECALAGE_SOEURS for s in soeurs):
            continue
        w = 1.0 if heure_imposee else poids(secteur, reseau, jour.weekday(), minute, profil)
        if w > meilleur:
            meilleur, choix = w, t
        if heure_imposee:
            break
    return choix


def poids_du_jour(secteur: str, reseaux: list, jour_semaine: int, profils: dict | None = None) -> float:
    """La valeur d'un jour pour la marque : le meilleur moment de chaque réseau, additionné."""
    total = 0.0
    for r in reseaux:
        total += max(poids(secteur, r, jour_semaine, m, (profils or {}).get(r))
                     for m in range(DEBUT, FIN + 1, 60))
    return total
