"""Le carnet d'apprentissage — la mémoire de chaque marque (§ 6).

Une leçon n'entre qu'avec sa PREUVE : échantillon, période, chiffres. Une
leçon que les chiffres suivants contredisent passe en « contredite » et sort
du contexte des agents — elle reste lisible, on sait ce qu'on a cru.

Une même clé (`format:carrousel`, `heure:mardi-19h`…) n'a qu'une leçon active
à la fois : la nouvelle mesure remplace l'ancienne au lieu de s'empiler.
"""
from __future__ import annotations

from sqlalchemy import desc, insert, select, update

from . import db, journal

ECHANTILLON_MIN = 6         # en dessous, ce n'est pas une leçon, c'est une anecdote


def lecons(marque_id: str, limite: int = 20, toutes: bool = False) -> list:
    t = db.learnings
    q = select(t).where(t.c.brand_id == marque_id)
    if not toutes:
        q = q.where(t.c.statut == "active")
    with db.moteur().connect() as c:
        return db.lignes(c.execute(q.order_by(desc(t.c.updated_at)).limit(limite)))


def apprendre(marque_id: str, cle: str, lecon: str, preuve: dict, par: str = "analyste") -> int | None:
    """→ id de la leçon, ou None si la preuve est trop mince pour l'écrire."""
    if int(preuve.get("echantillon", 0) or 0) < ECHANTILLON_MIN or not preuve.get("periode"):
        return None
    t = db.learnings
    with db.moteur().begin() as c:
        ancienne = db.ligne(c.execute(select(t).where(t.c.brand_id == marque_id, t.c.cle == cle,
                                                     t.c.statut == "active")))
        if ancienne:
            c.execute(update(t).where(t.c.id == ancienne["id"]).values(statut="contredite",
                                                                      updated_at=db.maintenant()))
        lid = c.execute(insert(t).values(brand_id=marque_id, cle=cle, lecon=lecon, preuve=preuve,
                                         statut="active", created_at=db.maintenant(),
                                         updated_at=db.maintenant())).inserted_primary_key[0]
    journal.noter(par, "lecon", "learning", lid, marque_id,
                  avant={"remplace": ancienne["lecon"]} if ancienne else None,
                  apres={"cle": cle, "lecon": lecon, "preuve": preuve})
    return lid


def contredire(lecon_id: int, raison: str, par: str = "analyste"):
    with db.moteur().begin() as c:
        r = db.ligne(c.execute(select(db.learnings).where(db.learnings.c.id == lecon_id)))
        c.execute(update(db.learnings).where(db.learnings.c.id == lecon_id)
                  .values(statut="contredite", updated_at=db.maintenant()))
    journal.noter(par, "lecon_contredite", "learning", lecon_id, (r or {}).get("brand_id"),
                  apres={"raison": raison})
