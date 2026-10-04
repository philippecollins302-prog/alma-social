"""L'horloge — ce qui tourne tout seul, jour et nuit, dans le processus web.

Un seul fil, une seule instance (DECISIONS.md) : pas de second service à
payer ni à surveiller. Chaque tâche est protégée : une qui tombe n'arrête pas
les autres, et sa trace va dans les journaux et sur la page santé.

  toutes les 5 s    la file de travaux (étapes du pipeline, relevés)
  chaque minute     réponses aux avis dues, échéances de pause
  toutes les 30 min commentaires et messages ; toutes les heures, les avis
  chaque jour 6 h   le tour du matin du planificateur (Paris)
  le lundi 8 h      le récapitulatif
  chaque nuit 3 h   le ménage de la file
"""
from __future__ import annotations

import datetime as dt
import logging
import threading
import time

from . import acces, alertes, creneaux, db, file, journal

log = logging.getLogger("alma_social.horloge")
_arret = threading.Event()
_fil = None
DERNIERS = {}           # tâche → {le, ok, erreur} — lu par la page santé


def _tache(nom: str, f):
    debut = time.monotonic()
    try:
        f()
        DERNIERS[nom] = {"le": db.maintenant().isoformat(), "ok": True,
                         "secondes": round(time.monotonic() - debut, 2)}
    except Exception as e:      # une tâche qui tombe n'arrête pas l'horloge
        log.exception("tâche %s", nom)
        DERNIERS[nom] = {"le": db.maintenant().isoformat(), "ok": False, "erreur": f"{type(e).__name__}: {e}"}


def _une_fois_par_jour(cle: str, heure: int, f, jour_semaine: int | None = None):
    """Lance `f` une fois par jour à partir de `heure` (Paris). Le jour du dernier
    passage est en base : un redémarrage ne le relance pas, une coupure le rattrape."""
    p = creneaux.paris(db.maintenant())
    if p.hour < heure or (jour_semaine is not None and p.weekday() != jour_semaine):
        return
    if journal.lire(cle) == p.date().isoformat():
        return
    journal.ecrire(cle, p.date().isoformat(), journaliser=False)
    _tache(cle, f)


def echeances_de_pause():
    """« Rien ne repart sans mon action » : à l'échéance des 48 h, la marque
    reste en pause et on le rappelle, une fois."""
    for m in acces.marques():
        if m["paused_until"] and m["paused_until"] <= db.maintenant():
            cle = f"rappel_pause:{m['id']}"
            if journal.lire(cle) == m["paused_until"].isoformat():
                continue
            journal.ecrire(cle, m["paused_until"].isoformat(), journaliser=False)
            alertes.alerter(f"{m['name']} : la pause de 48 h est arrivée à échéance",
                            "Rien n'est reparti. Pour reprendre les publications : ALMA SOCIAL → la marque → "
                            "« Reprendre ». Pour prolonger, ne faites rien.",
                            marque=m["id"], niveau="info", type_="pause", dedup=f"echeance:{m['id']}")


def un_tour(maintenant_s: float, compteur: dict):
    from . import planificateur, rapport, relation
    file.vider(limite=20)
    if maintenant_s - compteur.get("minute", 0) >= 60:
        compteur["minute"] = maintenant_s
        _tache("avis_dus", relation.repondre_aux_avis_dus)
        _tache("pauses", echeances_de_pause)
        _une_fois_par_jour("tour_du_matin", 6, lambda: planificateur.tour_du_matin())
        _une_fois_par_jour("rapport_lundi_envoye", 8, lambda: rapport.envoyer(), jour_semaine=0)
        _une_fois_par_jour("menage", 3, file.menage)
    if maintenant_s - compteur.get("commentaires", 0) >= 1800:
        compteur["commentaires"] = maintenant_s
        _tache("commentaires", lambda: [relation.relever(m) for m in acces.marques()])
    if maintenant_s - compteur.get("avis", 0) >= 3600:
        compteur["avis"] = maintenant_s
        _tache("avis", lambda: [relation.relever_avis(m) for m in acces.marques()])


def _boucle():
    compteur = {"commentaires": time.monotonic() - 1700, "avis": time.monotonic() - 3500}
    file.relever_les_orphelins()
    while not _arret.is_set():
        try:
            un_tour(time.monotonic(), compteur)
        except Exception:
            log.exception("horloge")
        _arret.wait(5)


def demarrer():
    global _fil
    if _fil and _fil.is_alive():
        return
    _arret.clear()
    _fil = threading.Thread(target=_boucle, name="horloge-alma-social", daemon=True)
    _fil.start()


def arreter():
    _arret.set()


def vivante() -> bool:
    return bool(_fil and _fil.is_alive())
