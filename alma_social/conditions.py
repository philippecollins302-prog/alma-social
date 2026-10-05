"""La publication conditionnelle (§ 13.6) [FeedHive Post Conditions].

« Ne publier la partie 2 que si la partie 1 a dépassé tel engagement. » Une
condition s'attache à un post programmé ; au moment de partir, le post la
vérifie :

- remplie → il part ;
- pas encore mesurable (la partie 1 n'a pas son relevé de 24 h) → il attend,
  trois heures de plus, jusqu'à 48 h après son heure prévue ;
- non remplie, ou toujours pas mesurable passé ce délai → il est ANNULÉ, avec
  la raison écrite au journal. On ne publie pas une suite que personne n'a
  attendue.

En bac à sable, la condition se juge sur les chiffres simulés : la répétition
montre ce que fera la vraie.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import insert, select, update

from . import db, journal

DELAI_MAX = dt.timedelta(hours=48)


def poser(post_id: int, apres_post: int, engagement_min: float = 0.0, vues_min: int = 0, par: str = "systeme") -> dict:
    if not (engagement_min or vues_min):
        raise ValueError("une condition demande un seuil (engagement ou vues)")
    with db.moteur().begin() as c:
        p = db.ligne(c.execute(select(db.posts).where(db.posts.c.id == post_id)))
        a = db.ligne(c.execute(select(db.posts).where(db.posts.c.id == apres_post)))
        if not p or not a or p["brand_id"] != a["brand_id"]:
            raise ValueError("les deux publications doivent exister et être de la même marque")
        if p["status"] not in ("programme", "a_valider", "preparation"):
            raise ValueError("on ne pose une condition que sur une publication qui n'est pas encore partie")
        cid = c.execute(insert(db.post_conditions).values(
            post_id=post_id, condition={"apres_post": apres_post, "engagement_min": engagement_min,
                                        "vues_min": vues_min}, etat="attente")).inserted_primary_key[0]
    journal.noter(par, "condition", "post", post_id, p["brand_id"],
                  apres={"apres_post": apres_post, "engagement_min": engagement_min, "vues_min": vues_min})
    return {"id": cid, "post_id": post_id}


def _releve(post_id: int, simules: bool):
    q = select(db.metrics).where(db.metrics.c.post_id == post_id, db.metrics.c.checkpoint.in_(("24h", "7j")))
    if not simules:
        q = q.where(db.metrics.c.simulated.is_(False))
    with db.moteur().connect() as c:
        ms = db.lignes(c.execute(q.order_by(db.metrics.c.measured_at.desc())))
    return ms[0] if ms else None


def verifier(p: dict) -> str:
    """'' = rien ne retient ce post ; 'attendre' ; sinon la raison de l'annulation."""
    from . import creneaux
    with db.moteur().connect() as c:
        conds = db.lignes(c.execute(select(db.post_conditions).where(db.post_conditions.c.post_id == p["id"],
                                                                    db.post_conditions.c.etat.in_(("attente", "non")))))
    if not conds:
        return ""
    tranchee = next((k for k in conds if k["etat"] == "non"), None)
    if tranchee:
        return (tranchee["condition"] or {}).get("raison") or "condition déjà jugée non remplie"
    trop_tard = p["scheduled_at"] and db.maintenant() > p["scheduled_at"] + DELAI_MAX
    for k in conds:
        cond = k["condition"] or {}
        with db.moteur().connect() as c:
            source = db.ligne(c.execute(select(db.posts).where(db.posts.c.id == cond["apres_post"])))
        if not source or source["status"] not in ("publie", "simule"):
            if trop_tard or (source and source["status"] in ("annule", "retire", "echec", "refuse")):
                return _fin(k, "non", f"la publication n° {cond['apres_post']} n'est pas sortie")
            return "attendre"
        m = _releve(source["id"], simules=bool(source["simulated"]))
        if not m:
            if trop_tard:
                return _fin(k, "non", f"la publication n° {source['id']} n'a pas été mesurée à temps")
            return "attendre"
        score = creneaux.score_engagement(m)
        if cond.get("engagement_min") and score < cond["engagement_min"]:
            return _fin(k, "non", f"engagement {score:.1%} sous le seuil de {cond['engagement_min']:.1%}")
        if cond.get("vues_min") and (m["views"] or m["reach"] or 0) < cond["vues_min"]:
            return _fin(k, "non", f"{m['views'] or m['reach'] or 0} vues, sous le seuil de {cond['vues_min']}")
        _fin(k, "remplie", "")
    return ""


def _fin(k: dict, etat: str, raison: str) -> str:
    with db.moteur().begin() as c:
        c.execute(update(db.post_conditions).where(db.post_conditions.c.id == k["id"])
                  .values(etat=etat, condition={**(k["condition"] or {}), "raison": raison}))
    return raison
