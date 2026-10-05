"""La banque qui travaille seule (§ 13.6) — les malchanceux, les gagnants, l'intemporel.

Chaque matin, on relit les publications RÉELLES sorties il y a 7 à 30 jours
(le bac à sable n'apprend rien) et on compare chacune à la médiane de sa
marque sur son réseau :

- **le malchanceux** [FeedHive] — un bon texte (le Critique lui a donné 75 ou
  plus) qui a fait moins de 60 % de la médiane : le contenu n'était pas en
  cause, l'heure ou l'actualité l'étaient. La photo revient en banque UNE
  fois, au moins 21 jours après, avec un texte neuf, un autre cadrage, et sur
  un des meilleurs créneaux (jamais en exploration) ;
- **le gagnant** — 1,5 fois la médiane ou plus : il reviendra après 90 jours,
  en tête des recyclables, nouveau texte et nouveau cadrage ;
- **l'intemporel** (evergreen) [SocialBee] — une photo d'un pilier qui ne
  vieillit pas (savoir-faire, méthode, équipe) : elle entre au fichier
  evergreen et ressort seule quand le stock frais manque, au plus tous les
  45 jours.

Aucun chiffre n'est inventé : sans mesure réelle, rien n'est classé.
"""
from __future__ import annotations

import datetime as dt
import json
import statistics

from sqlalchemy import insert, select, update

from . import config, creneaux, db, journal

SEUIL_MALCHANCE = 0.6
SEUIL_GAGNANT = 1.5
NOTE_MIN = 75
DELAI_SECONDE_CHANCE = dt.timedelta(days=21)
ECART_EVERGREEN = dt.timedelta(days=45)
MIN_COMPARABLES = 5            # sans cinq publications à comparer, pas de médiane digne de ce nom


def piliers_evergreen(marque_id: str) -> list:
    try:
        d = json.loads((config.RACINE / "graines" / "evergreen.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return d.get(marque_id) or []


def perf(post_id: int, simules: bool = False) -> float | None:
    """Le score d'engagement du dernier relevé RÉEL (7 j de préférence)."""
    q = select(db.metrics).where(db.metrics.c.post_id == post_id)
    if not simules:
        q = q.where(db.metrics.c.simulated.is_(False))
    with db.moteur().connect() as c:
        ms = db.lignes(c.execute(q))
    if not ms:
        return None
    ordre = {"7j": 3, "24h": 2, "1h": 1}
    m = max(ms, key=lambda x: (ordre.get(x["checkpoint"], 0), x["measured_at"]))
    return creneaux.score_engagement(m)


def _publies(marque_id: str, plateforme: str | None, depuis: dt.datetime, jusqua: dt.datetime) -> list:
    q = select(db.posts).where(db.posts.c.brand_id == marque_id, db.posts.c.status == "publie",
                               db.posts.c.simulated.is_(False), db.posts.c.published_at >= depuis,
                               db.posts.c.published_at < jusqua)
    if plateforme:
        q = q.where(db.posts.c.platform == plateforme)
    with db.moteur().connect() as c:
        return db.lignes(c.execute(q))


def mediane(marque_id: str, plateforme: str, jours: int = 60) -> float | None:
    fin = db.maintenant()
    scores = [x for x in (perf(p["id"]) for p in _publies(marque_id, plateforme, fin - dt.timedelta(days=jours), fin))
              if x is not None]
    return statistics.median(scores) if len(scores) >= MIN_COMPARABLES else None


def classer(m: dict, par: str = "systeme") -> dict:
    """Le tri du matin pour une marque. → {malchanceux: [...], gagnants: [...], evergreen: n}."""
    maintenant = db.maintenant()
    posts = _publies(m["id"], None, maintenant - dt.timedelta(days=30), maintenant - dt.timedelta(days=7))
    out = {"malchanceux": [], "gagnants": [], "evergreen": 0}
    medianes = {}
    for p in posts:
        if not p["asset_id"]:
            continue
        with db.moteur().connect() as c:
            a = db.ligne(c.execute(select(db.assets).where(db.assets.c.id == p["asset_id"])))
        if not a or a["kind"] != "photo" or a["status"] in ("retire", "quarantaine"):
            continue
        if a["pillar"] in piliers_evergreen(m["id"]) and _entrer_evergreen(m, a, p):
            out["evergreen"] += 1
        if p["platform"] not in medianes:
            medianes[p["platform"]] = mediane(m["id"], p["platform"])
        med, x = medianes[p["platform"]], perf(p["id"])
        if not med or x is None:
            continue
        note = (((p["guard_report"] or {}).get("critique") or {}).get("note")) or 0
        if x >= SEUIL_GAGNANT * med and a["recyclage"] != "gagnant":
            _maj_asset(a["id"], recyclage="gagnant")
            out["gagnants"].append(a["id"])
            journal.noter(par, "gagnant", "asset", a["id"], m["id"],
                          apres={"post": p["id"], "reseau": p["platform"], "score": round(x, 4), "mediane": round(med, 4)})
        elif x < SEUIL_MALCHANCE * med and note >= NOTE_MIN and not a["recyclage"] and a["status"] == "publie":
            _maj_asset(a["id"], recyclage="seconde_chance", status="banque")
            out["malchanceux"].append(a["id"])
            journal.noter(par, "seconde_chance", "asset", a["id"], m["id"],
                          apres={"post": p["id"], "reseau": p["platform"], "score": round(x, 4),
                                 "mediane": round(med, 4), "note_critique": note,
                                 "raison": "bon contenu, sous la médiane : l'heure ou l'actualité, pas le contenu"})
    return out


def _maj_asset(aid: int, **vals):
    with db.moteur().begin() as c:
        c.execute(update(db.assets).where(db.assets.c.id == aid).values(**vals))


def _entrer_evergreen(m: dict, a: dict, p: dict) -> bool:
    with db.moteur().begin() as c:
        deja = c.execute(select(db.evergreen.c.id).join(db.posts, db.posts.c.id == db.evergreen.c.post_source_id)
                         .where(db.evergreen.c.brand_id == m["id"], db.posts.c.asset_id == a["id"])).first()
        if deja:
            return False
        c.execute(insert(db.evergreen).values(brand_id=m["id"], categorie=a["pillar"], post_source_id=p["id"],
                                              derniere_sortie=p["published_at"], sorties=1))
    return True


def evergreen_disponibles(m: dict) -> list:
    """Les intemporels qui peuvent ressortir : plus de 45 jours depuis la dernière fois, le plus ancien d'abord."""
    limite = db.maintenant() - ECART_EVERGREEN
    with db.moteur().connect() as c:
        lignes = db.lignes(c.execute(
            select(db.evergreen, db.posts.c.asset_id).join(db.posts, db.posts.c.id == db.evergreen.c.post_source_id)
            .where(db.evergreen.c.brand_id == m["id"], db.evergreen.c.derniere_sortie < limite)
            .order_by(db.evergreen.c.derniere_sortie)))
        out = []
        for l in lignes:
            a = db.ligne(c.execute(select(db.assets).where(db.assets.c.id == l["asset_id"])))
            if a and a["status"] in ("publie", "banque"):
                out.append({**a, "_evergreen": l["id"]})
    return out


def evergreen_sorti(evergreen_id: int):
    with db.moteur().begin() as c:
        e = db.ligne(c.execute(select(db.evergreen).where(db.evergreen.c.id == evergreen_id)))
        if e:
            c.execute(update(db.evergreen).where(db.evergreen.c.id == evergreen_id)
                      .values(derniere_sortie=db.maintenant(), sorties=(e["sorties"] or 0) + 1))


def etat(marque_ids: list) -> dict:
    """Pour l'écran : ce que la banque garde en réserve, marque par marque."""
    out = {}
    with db.moteur().connect() as c:
        for mid in marque_ids:
            n = lambda **w: c.execute(select(db.assets.c.id).where(db.assets.c.brand_id == mid, *[
                getattr(db.assets.c, k) == v for k, v in w.items()])).all()
            out[mid] = {"seconde_chance": len(n(recyclage="seconde_chance")), "gagnants": len(n(recyclage="gagnant")),
                        "evergreen": len(c.execute(select(db.evergreen.c.id).where(db.evergreen.c.brand_id == mid)).all())}
    return out
