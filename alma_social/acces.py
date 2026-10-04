"""Les lectures que tout le monde fait — une seule écriture de chacune.

Une marque, ses comptes, les contraintes des réseaux, « aujourd'hui » à Paris :
le pipeline, le planificateur, la relation et l'écran en ont tous besoin, et
deux définitions d'« aujourd'hui » finiraient par ne plus dire le même jour.
"""
from __future__ import annotations

import dataclasses
import datetime as dt

from sqlalchemy import select

from . import creneaux, db
from .publieurs.base import Contraintes


def aujourdhui() -> dt.date:
    """Le jour à PARIS, d'après l'horloge du produit. La seule définition."""
    return creneaux.paris(db.maintenant()).date()


def marque(marque_id: str) -> dict | None:
    with db.moteur().begin() as c:
        return db.ligne(c.execute(select(db.brands).where(db.brands.c.id == marque_id)))


def marques(actives_seulement: bool = True) -> list:
    q = select(db.brands).order_by(db.brands.c.name)
    if actives_seulement:
        q = q.where(db.brands.c.active.is_(True))
    with db.moteur().begin() as c:
        return db.lignes(c.execute(q))


def en_pause(m: dict) -> bool:
    return bool(m.get("paused_until"))


def pilier(m: dict, cle: str) -> dict | None:
    for p in m.get("pillars") or []:
        if p.get("key") == cle:
            return p
    return None


def compte(marque_id: str, plateforme: str) -> dict | None:
    with db.moteur().begin() as c:
        return db.ligne(c.execute(select(db.accounts).where(
            db.accounts.c.brand_id == marque_id, db.accounts.c.platform == plateforme)))


def comptes(marque_id: str) -> list:
    with db.moteur().begin() as c:
        return db.lignes(c.execute(select(db.accounts).where(db.accounts.c.brand_id == marque_id)
                                   .order_by(db.accounts.c.platform)))


def contraintes() -> dict:
    """{réseau: ligne de platform_constraints}."""
    with db.moteur().begin() as c:
        return {r["platform"]: r for r in db.lignes(c.execute(select(db.platform_constraints)))}


def contraintes_publieur(ligne: dict | None, plateforme: str) -> Contraintes:
    if not ligne:
        return Contraintes(platform=plateforme, formats=["jpeg"], caption_max=2000)
    champs = {f.name for f in dataclasses.fields(Contraintes)}
    return Contraintes(**{k: v for k, v in ligne.items() if k in champs})


def logo_permis(m: dict, quand=None) -> bool:
    """Une marque peut cacher son logo jusqu'à un instant (SAZÚ le révèle le
    13/11/2026 à 18 h : le montrer avant gâcherait la révélation).
    `quand` : un instant de Paris (avec fuseau), un jour, ou None = maintenant."""
    debut = (m.get("kit") or {}).get("logo_from")
    if not debut:
        return True
    try:
        reveal = dt.datetime.fromisoformat(debut)
    except ValueError:
        return True
    if reveal.tzinfo is None:
        reveal = reveal.replace(tzinfo=creneaux.PARIS)
    if quand is None:
        quand = creneaux.paris(db.maintenant())
    if isinstance(quand, dt.datetime):
        return quand >= reveal
    return quand > reveal.date()     # un jour entier : seulement les jours APRÈS la révélation
