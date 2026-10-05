"""Les gestes de pilotage, écrits une fois — l'écran, « Demander » et le
serveur MCP passent tous par ici : mêmes règles, même journal (§ 18)."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import update

from . import db, journal

PAUSE_MAX_H = 48


def pause(m: dict, par: str, heures: int = 48, raison: str = "") -> dict:
    """Rien ne part pour cette marque, et rien ne repart sans un geste."""
    heures = max(1, min(PAUSE_MAX_H, int(heures or PAUSE_MAX_H)))
    jusqua = db.maintenant() + dt.timedelta(hours=heures)
    raison = (raison or f"pause {heures} h")[:200]
    with db.moteur().begin() as c:
        c.execute(update(db.brands).where(db.brands.c.id == m["id"]).values(paused_until=jusqua, paused_reason=raison))
    journal.noter(par, "pause", "brand", m["id"], m["id"], apres={"jusqua": jusqua, "raison": raison})
    return {"en_pause": True, "jusqua": jusqua}


def reprendre(m: dict, par: str) -> dict:
    from . import pipeline
    with db.moteur().begin() as c:
        c.execute(update(db.brands).where(db.brands.c.id == m["id"]).values(paused_until=None, paused_reason=None))
    journal.noter(par, "reprise", "brand", m["id"], m["id"])
    return {"en_pause": False, "repris": pipeline.reprendre(par, m["id"])}


def copilote(m: dict, actif: bool, par: str) -> dict:
    """L'interrupteur « copilote » (§ 4) : les publications de la marque passent
    par un aperçu avant envoi. Désactivé partout par défaut — la règle reste
    « aucune validation » ; il existe pour le jour où Philippe changerait
    d'avis sur une marque, sans redévelopper."""
    with db.moteur().begin() as c:
        c.execute(update(db.brands).where(db.brands.c.id == m["id"]).values(requires_approval=bool(actif)))
    journal.noter(par, "copilote", "brand", m["id"], m["id"],
                  avant={"actif": bool(m.get("requires_approval"))}, apres={"actif": bool(actif)})
    return {"copilote": bool(actif)}
