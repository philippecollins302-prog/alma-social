"""L'horloge — ce qui tourne tout seul, jour et nuit, dans le processus web.

Un seul fil, une seule instance (DECISIONS.md) : pas de second service à
payer ni à surveiller. Chaque tâche est protégée : une qui tombe n'arrête pas
les autres, et sa trace va dans les journaux et sur la page santé.

  toutes les 5 s    la file de travaux (étapes du pipeline, relevés)
  chaque minute     réponses aux avis dues, échéances de pause
  toutes les 5 min  commentaires des publications de moins de 48 h (les « DEVIS »)
  toutes les 30 min commentaires et messages ; toutes les heures, les avis
  toutes les heures les conversations interrompues avec un téléphone → une fiche
  chaque jour 6 h   le tour du matin du planificateur (Paris)
  chaque jour 7 h   l'Analyste : carnet d'apprentissage, conclusions des tests A/B
  le lundi 8 h      la note du lundi ; à midi, ses décisions non refusées s'appliquent
  toutes les 30 min les pics de messages (avec d'où ils viennent), la vague négative → mode crise
  le lundi 5 h      Google Maps : fiche relue, position relevée (seulement avec une clé Places)
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
    from . import analyste, crise, maps, planificateur, qualification, rapport, relation
    file.vider(limite=20)
    if maintenant_s - compteur.get("minute", 0) >= 60:
        compteur["minute"] = maintenant_s
        _tache("avis_dus", relation.repondre_aux_avis_dus)
        _tache("pauses", echeances_de_pause)
        _une_fois_par_jour("tour_du_matin", 6, lambda: planificateur.tour_du_matin())
        _une_fois_par_jour("rapport_lundi_envoye", 8, lambda: rapport.envoyer(), jour_semaine=0)
        _une_fois_par_jour("decisions_lundi", 12, lambda: analyste.appliquer_decisions_dues(), jour_semaine=0)
        _une_fois_par_jour("analyste", 7, lambda: analyste.tour())
        _une_fois_par_jour("menage", 3, file.menage)
        _une_fois_par_jour("maps", 5, maps.tour, jour_semaine=0)
    if maintenant_s - compteur.get("chauds", 0) >= 300:
        compteur["chauds"] = maintenant_s
        _tache("commentaires_chauds", lambda: [relation.relever(m, relation.FENETRE_CHAUDE) for m in acces.marques()])
    if maintenant_s - compteur.get("commentaires", 0) >= 1800:
        compteur["commentaires"] = maintenant_s
        _tache("commentaires", lambda: [relation.relever(m) for m in acces.marques()])
        _tache("pics", lambda: [analyste.pic_de_mentions(m) for m in acces.marques()])
        _tache("crise", crise.surveiller_tout)
    if maintenant_s - compteur.get("avis", 0) >= 3600:
        compteur["avis"] = maintenant_s
        _tache("avis", lambda: [relation.relever_avis(m) for m in acces.marques()])
        _tache("abandons", qualification.abandons)


def _boucle():
    compteur = {"commentaires": time.monotonic() - 1700, "avis": time.monotonic() - 3500,
                "chauds": time.monotonic() - 240}
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
