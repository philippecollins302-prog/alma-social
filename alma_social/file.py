"""La file de travaux — chaque étape reprise automatiquement en cas d'échec.

Une table `jobs` en base, pas de Redis : un service de moins à payer et à
surveiller, et la file survit à un redémarrage (elle est dans la base). Un seul
processus la dépile (l'hébergement tourne en une seule instance, voir
DECISIONS.md) ; la réservation d'un travail passe quand même par un UPDATE
conditionnel, de sorte qu'un second dépileur ne prendrait jamais le même.
"""
from __future__ import annotations

import datetime as dt
import logging
import traceback

from sqlalchemy import and_, delete, insert, select, update
from sqlalchemy.exc import IntegrityError

from . import db

log = logging.getLogger("alma_social.file")
TRAITANTS = {}          # kind → fonction(payload) ; rempli par pipeline.py et les autres


def traitant(kind: str):
    def deco(f):
        TRAITANTS[kind] = f
        return f
    return deco


class Reessayer(Exception):
    """Lever ceci pour demander un nouvel essai plus tard sans compter d'erreur
    grave (exemple : réseau qui tousse)."""
    def __init__(self, message, dans: dt.timedelta | None = None):
        super().__init__(message)
        self.dans = dans


class Abandon(Exception):
    """Inutile de réessayer : l'échec est définitif (le traitant l'a consigné)."""


def ajouter(kind: str, payload: dict | None = None, quand: dt.datetime | None = None,
            dedup: str | None = None, essais_max: int = 4) -> int | None:
    try:
        with db.moteur().begin() as c:
            r = c.execute(insert(db.jobs).values(
                kind=kind, payload=payload or {}, run_at=quand or db.maintenant(),
                max_attempts=essais_max, dedup_key=dedup, status="attente",
                created_at=db.maintenant(), updated_at=db.maintenant()))
            return r.inserted_primary_key[0]
    except IntegrityError:
        return None         # déjà en file sous cette clé : rien à faire


def _delai(essai: int) -> dt.timedelta:
    """Intervalle croissant : 2 min, 10 min, 30 min, 2 h."""
    return [dt.timedelta(minutes=2), dt.timedelta(minutes=10),
            dt.timedelta(minutes=30), dt.timedelta(hours=2)][min(essai - 1, 3)]


def reserver():
    """Le prochain travail dû, réservé pour nous — ou None."""
    with db.moteur().begin() as c:
        candidats = db.lignes(c.execute(select(db.jobs).where(
            db.jobs.c.status == "attente", db.jobs.c.run_at <= db.maintenant())
            .order_by(db.jobs.c.run_at, db.jobs.c.id).limit(5)))
        for j in candidats:
            r = c.execute(update(db.jobs).where(and_(
                db.jobs.c.id == j["id"], db.jobs.c.status == "attente")).values(
                status="encours", attempts=j["attempts"] + 1, updated_at=db.maintenant()))
            if r.rowcount == 1:
                j["attempts"] += 1
                return j
    return None


def traiter_un() -> bool:
    j = reserver()
    if not j:
        return False
    f = TRAITANTS.get(j["kind"])
    try:
        if f is None:
            raise Abandon(f"aucun traitant pour « {j['kind']} »")
        f(j["payload"] or {})
        _fin(j["id"], "fait", "")
    except Reessayer as e:
        if j["attempts"] >= j["max_attempts"]:
            _fin(j["id"], "echec", str(e))
        else:
            _fin(j["id"], "attente", str(e), quand=db.maintenant() + (e.dans or _delai(j["attempts"])))
    except Abandon as e:
        _fin(j["id"], "echec", str(e))
    except Exception as e:
        log.exception("travail %s (%s) en erreur", j["id"], j["kind"])
        detail = f"{type(e).__name__}: {e}\n" + traceback.format_exc(limit=3)
        if j["attempts"] >= j["max_attempts"]:
            _fin(j["id"], "echec", detail)
            from . import alertes
            alertes.alerter(f"Étape « {j['kind']} » en échec après {j['attempts']} essais",
                            detail[:1500], niveau="panne", type_="file",
                            dedup=f"file:{j['kind']}", delai_dedup=dt.timedelta(hours=6))
        else:
            _fin(j["id"], "attente", detail, quand=db.maintenant() + _delai(j["attempts"]))
    return True


def _fin(jid, statut, erreur, quand=None):
    vals = {"status": statut, "last_error": erreur[:4000], "updated_at": db.maintenant()}
    if quand:
        vals["run_at"] = quand
    with db.moteur().begin() as c:
        c.execute(update(db.jobs).where(db.jobs.c.id == jid).values(**vals))


def vider(limite: int = 500) -> int:
    """Dépile tout ce qui est dû (bancs, démarrage). → nombre traité."""
    n = 0
    while n < limite and traiter_un():
        n += 1
    return n


def relever_les_orphelins():
    """Au démarrage : un travail resté « en cours » appartient à un processus
    mort. On le remet en file."""
    with db.moteur().begin() as c:
        c.execute(update(db.jobs).where(
            db.jobs.c.status == "encours",
            db.jobs.c.updated_at < db.maintenant() - dt.timedelta(minutes=10)).values(status="attente"))


def menage():
    with db.moteur().begin() as c:
        c.execute(delete(db.jobs).where(db.jobs.c.status == "fait",
                                        db.jobs.c.updated_at < db.maintenant() - dt.timedelta(days=30)))


def etat() -> dict:
    with db.moteur().begin() as c:
        rows = db.lignes(c.execute(select(db.jobs.c.status, db.jobs.c.kind)))
        derniers = db.lignes(c.execute(select(db.jobs).where(db.jobs.c.status == "echec")
                                       .order_by(db.jobs.c.updated_at.desc()).limit(10)))
    compte = {}
    for r in rows:
        compte.setdefault(r["status"], 0)
        compte[r["status"]] += 1
    return {"compte": compte, "echecs": [{"id": d["id"], "kind": d["kind"], "erreur": d["last_error"][:300],
                                          "le": d["updated_at"].isoformat()} for d in derniers]}
