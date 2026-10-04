"""Le journal intégral, et les réglages qui pilotent toute l'application.

Le journal est chaîné : chaque ligne porte l'empreinte de la précédente. La
base refuse déjà toute modification (déclencheurs, voir db.py) ; la chaîne
prouve en plus, à l'export, qu'aucune ligne n'a été retirée ou insérée après
coup. C'est la seule preuve de ce qui est sorti en votre nom.
"""
from __future__ import annotations

import hashlib
import json
import threading

from sqlalchemy import insert, select

from . import db

_verrou = threading.Lock()


def _canon(v) -> str:
    return json.dumps(v, sort_keys=True, ensure_ascii=False, default=str)


def noter(acteur: str, action: str, objet_type: str = "", objet_id="",
          marque: str | None = None, avant=None, apres=None) -> int:
    # Ce qui est écrit est exactement ce qui sera relu : les dates et objets
    # deviennent du texte AVANT le calcul de l'empreinte.
    avant = json.loads(_canon(avant)) if avant is not None else None
    apres = json.loads(_canon(apres)) if apres is not None else None
    with _verrou, db.moteur().begin() as c:
        prec = c.execute(select(db.audit_log.c.hash).order_by(
            db.audit_log.c.id.desc()).limit(1)).scalar()
        prec = prec or ""
        at = db.maintenant()
        corps = _canon([prec, at.isoformat(), acteur, action, objet_type,
                        str(objet_id), marque, avant, apres])
        h = hashlib.sha256(corps.encode()).hexdigest()
        r = c.execute(insert(db.audit_log).values(
            at=at, actor=acteur, action=action, object_type=objet_type,
            object_id=str(objet_id), brand_id=marque, before=avant, after=apres,
            prev_hash=prec, hash=h))
        return r.inserted_primary_key[0]


def verifier_chaine() -> dict:
    """Relit tout le journal et recalcule chaque maillon."""
    with db.moteur().begin() as c:
        rows = db.lignes(c.execute(select(db.audit_log).order_by(db.audit_log.c.id)))
    prec = ""
    for r in rows:
        corps = _canon([prec, r["at"].isoformat(), r["actor"], r["action"],
                        r["object_type"], r["object_id"], r["brand_id"],
                        r["before"], r["after"]])
        if r["prev_hash"] != prec or hashlib.sha256(corps.encode()).hexdigest() != r["hash"]:
            return {"intact": False, "rompu_a": r["id"], "lignes": len(rows)}
        prec = r["hash"]
    return {"intact": True, "lignes": len(rows), "dernier": prec}


# ── Réglages ─────────────────────────────────────────────────────────────
DEFAUTS = {
    # Le bac à sable est OUVERT au premier démarrage : tout le pipeline tourne,
    # rien ne sort. On regarde une semaine de publications simulées, puis on
    # ouvre les vannes d'un geste — et ce geste est au journal.
    "bac_a_sable": True,
    "arret_general": False,
    "derniere_horloge": None,
    "rapport_lundi_envoye": None,
}


def lire(cle: str):
    with db.moteur().begin() as c:
        r = db.ligne(c.execute(select(db.settings).where(db.settings.c.key == cle)))
    return r["value"] if r else DEFAUTS.get(cle)


def ecrire(cle: str, valeur, par: str = "systeme", journaliser: bool = True):
    avant = lire(cle)
    with db.moteur().begin() as c:
        existe = c.execute(select(db.settings.c.key).where(db.settings.c.key == cle)).first()
        if existe:
            c.execute(db.settings.update().where(db.settings.c.key == cle).values(
                value=valeur, updated_at=db.maintenant(), updated_by=par))
        else:
            c.execute(insert(db.settings).values(
                key=cle, value=valeur, updated_at=db.maintenant(), updated_by=par))
    if journaliser and avant != valeur:
        noter(par, "reglage", "reglage", cle, avant={"valeur": avant}, apres={"valeur": valeur})


def bac_a_sable() -> bool:
    return bool(lire("bac_a_sable"))


def arret_general() -> bool:
    return bool(lire("arret_general"))
