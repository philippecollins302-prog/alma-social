"""Les temps forts de l'année (§ 13.3) — fêtes, saisons, rentrée.

Chaque matin, les temps forts des trois semaines à venir posent leur créneau
pour les marques concernées, avec leur consigne. Un créneau déjà posé ne
l'est pas deux fois (clé du temps fort + année). Les dates incertaines —
salons, événements locaux — restent « à confirmer » et ne posent rien :
une date inventée serait pire qu'une date absente.
"""
from __future__ import annotations

import datetime as dt
import json

from sqlalchemy import select

from . import acces, config, db, journal

FENETRE = dt.timedelta(days=21)


def _fichier() -> dict:
    try:
        return json.loads((config.GRAINES / "temps_forts.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"temps_forts": [], "a_confirmer": []}


def a_venir(marque_id: str, debut: dt.date, fin: dt.date) -> list:
    """[{cle, nom, jour, consigne}] pour cette marque entre deux dates (incluses)."""
    out = []
    for t in _fichier()["temps_forts"]:
        if marque_id not in (t.get("marques") or []):
            continue
        mois, jour = (int(x) for x in t["date"].split("-"))
        for annee in (debut.year, debut.year + 1):
            try:
                d = dt.date(annee, mois, jour)
            except ValueError:
                continue
            if debut <= d <= fin:
                out.append({"cle": t["cle"], "nom": t["nom"], "jour": d, "consigne": t["consigne"]})
    return sorted(out, key=lambda x: x["jour"])


def poser(m: dict, par: str = "systeme") -> list:
    """Pose les créneaux des temps forts des trois semaines à venir. → les créneaux posés."""
    from . import planificateur
    j0 = acces.aujourdhui()
    poses = []
    for t in a_venir(m["id"], j0, j0 + FENETRE):
        cle = f"{t['cle']}-{t['jour'].year}"
        with db.moteur().connect() as c:
            deja = c.execute(select(db.slots.c.id).where(db.slots.c.brand_id == m["id"],
                                                         db.slots.c.source == "temps_fort",
                                                         db.slots.c.campaign_step == cle)).first()
        if deja:
            continue
        depart = planificateur.calendrier_des(m)
        if depart and t["jour"] < depart:
            continue
        sid = planificateur._poser(m, t["jour"], "temps_fort", topic=t["nom"], brief=t["consigne"],
                                   campaign_step=cle, platforms=m.get("active_platforms") or [])
        poses.append(sid)
        journal.noter(par, "temps_fort", "slot", sid, m["id"], apres={"nom": t["nom"], "jour": t["jour"]})
    return poses


def a_confirmer() -> list:
    return _fichier().get("a_confirmer") or []
