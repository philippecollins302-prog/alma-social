"""Le coup de pub (parcours C) — un événement devient une série de publications coordonnées.

Une campagne = une ou plusieurs marques, un événement (l'heure H), une période,
et des ÉTAPES : J-21, J-14, J-7, la veille, le jour J, le lendemain… Chaque
étape pose un créneau, avec sa consigne d'écriture et, si la marque l'a
prévu, son heure. Le planificateur la remplit avec une photo du bon pilier ;
à défaut, une carte à la charte (« J-7 », la date, l'adresse) — jamais un
créneau de campagne vide.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import insert, select, update

from . import acces, creneaux, db, journal

# Les étapes par défaut, par sorte d'événement : (décalage en jours, étiquette, consigne).
ETAPES = {
    "ouverture": [
        (-28, "J-28", "Premier signe : quelque chose se prépare. Ne révéler que la date."),
        (-21, "J-21", "Le compte à rebours commence : un détail du lieu ou de l'équipe, rien de plus."),
        (-14, "J-14", "Deux semaines : on révèle une chose concrète (ce qu'on va proposer)."),
        (-7, "J-7", "Une semaine : ce qui attend les gens, et comment en profiter le jour venu."),
        (-3, "J-3", "Trois jours : l'impatience, un produit en avant."),
        (-1, "J-1", "Demain : comment faire, très concrètement."),
        (0, "Jour J", "C'est aujourd'hui : l'appel à l'action le plus direct possible."),
        (1, "J+1", "Merci : les premières réactions, sans en rajouter."),
        (3, "J+3", "Rappel : ce qui vient d'ouvrir, et comment en profiter."),
    ],
    "promo": [
        (-7, "J-7", "Annonce de l'offre : ce qu'elle est, jusqu'à quand."),
        (-1, "J-1", "Demain commence l'offre."),
        (0, "Jour J", "L'offre commence aujourd'hui."),
        (3, "Derniers jours", "Il reste peu de temps pour en profiter."),
    ],
    "emploi": [
        (0, "Annonce", "L'offre d'emploi : le poste, ce qu'on fait au quotidien, comment postuler."),
        (4, "Relance", "Le métier vu de l'intérieur : une photo de chantier ou d'équipe."),
        (10, "Dernier appel", "Le poste est toujours ouvert : à qui s'adresser."),
    ],
    "chantier": [
        (0, "Livraison", "Le chantier est livré : le résultat, le délai tenu, le savoir-faire."),
        (3, "Avant / après", "Ce qu'il y avait avant, ce qu'il y a maintenant."),
        (10, "Le détail", "Un détail de finition qui fait la différence."),
    ],
    "evenement": [
        (-14, "J-14", "Annonce de l'événement : quoi, où, quand."),
        (-7, "J-7", "Une semaine avant : ce qu'on y verra."),
        (-1, "J-1", "Demain : les infos pratiques."),
        (0, "Jour J", "C'est aujourd'hui."),
        (1, "J+1", "Merci à ceux qui étaient là."),
    ],
}


def etapes_par_defaut(sorte: str, evenement: dt.date, debut: dt.date, fin: dt.date) -> list:
    out = []
    for decalage, etiquette, consigne in ETAPES.get(sorte, ETAPES["evenement"]):
        jour = evenement + dt.timedelta(days=decalage)
        if debut <= jour <= fin:
            out.append({"jour": jour, "etiquette": etiquette, "consigne": consigne, "heure": "",
                        "pilier": "", "accroche": ""})
    return out


def creer(nom: str, marque_ids: list, sorte: str, evenement_paris: dt.datetime | None, debut: dt.date,
          fin: dt.date, reseaux: list | None = None, brief: str = "", etapes: list | None = None,
          par: str = "systeme") -> dict:
    """→ la campagne. `evenement_paris` : l'heure H, à Paris (avec fuseau).
    `etapes` : [{jour, etiquette, consigne, heure, pilier, accroche}] ou None (par défaut)."""
    if fin < debut:
        raise ValueError("la fin précède le début")
    jour_h = evenement_paris.date() if evenement_paris else fin
    etapes = etapes if etapes is not None else etapes_par_defaut(sorte, jour_h, debut, fin)
    with db.moteur().begin() as c:
        cid = c.execute(insert(db.campaigns).values(
            name=nom, brand_ids=marque_ids, kind=sorte,
            event_at=creneaux.utc(evenement_paris) if evenement_paris else None,
            start=debut, end=fin, platforms=reseaux or [], brief=brief, status="active",
            created_by=par, created_at=db.maintenant())).inserted_primary_key[0]
    n = 0
    for mid in marque_ids:
        m = acces.marque(mid)
        if not m:
            continue
        for e in etapes:
            jour = e["jour"] if isinstance(e["jour"], dt.date) else dt.date.fromisoformat(e["jour"])
            if jour < acces.aujourdhui():
                continue
            pf = [r for r in (e.get("reseaux") or reseaux or []) if r in (m.get("active_platforms") or [])]
            with db.moteur().begin() as c:
                c.execute(insert(db.slots).values(
                    brand_id=mid, day=jour, platforms=pf, pillar=e.get("pilier") or "",
                    topic=e.get("accroche") or e["etiquette"], source="campagne", campaign_id=cid,
                    campaign_step=e["etiquette"], time=e.get("heure") or "", brief=e.get("consigne") or "",
                    status="libre", created_at=db.maintenant()))
            n += 1
    journal.noter(par, "campagne", "campaign", cid, marque_ids[0] if len(marque_ids) == 1 else None,
                  apres={"nom": nom, "marques": marque_ids, "sorte": sorte, "etapes": n,
                         "evenement": evenement_paris})
    return campagne(cid)


def campagne(cid: int):
    with db.moteur().begin() as c:
        return db.ligne(c.execute(select(db.campaigns).where(db.campaigns.c.id == cid)))


def annuler(cid: int, par: str) -> int:
    """Les créneaux pas encore préparés tombent ; ce qui est programmé se retire
    par « retirer partout » (une décision photo par photo, pas un effet de bord)."""
    with db.moteur().begin() as c:
        c.execute(update(db.campaigns).where(db.campaigns.c.id == cid).values(status="annulee"))
        n = c.execute(update(db.slots).where(db.slots.c.campaign_id == cid,
                                             db.slots.c.status.in_(("libre", "manque"))).values(status="annule")).rowcount
    journal.noter(par, "campagne_annulee", "campaign", cid, None, apres={"creneaux_annules": n})
    return n


def _date_courte(instant_utc: dt.datetime | None) -> str:
    if not instant_utc:
        return ""
    h = creneaux.paris(instant_utc)
    return f"{h:%d.%m} — {h.hour}h{h.minute:02d}"


def carte_pour(m: dict, s: dict):
    """La carte d'une étape de campagne : l'étiquette en grand, l'accroche,
    et la date de l'événement en détail. Le nom de la marque n'y est jamais
    retapé (son logo, lui, apparaît quand la marque le permet)."""
    from . import pipeline
    ca = campagne(s["campaign_id"]) if s.get("campaign_id") else None
    titre = s.get("campaign_step") or "Bientôt"
    if titre == "Jour J" and ca and ca["kind"] == "ouverture":
        titre = "C'est ouvert"
    accroche = s.get("topic") if s.get("topic") and s.get("topic") != s.get("campaign_step") else (ca or {}).get("name", "")
    detail = _date_courte((ca or {}).get("event_at"))
    adresse = (m.get("links") or {}).get("adresse_publique")
    if adresse and detail:
        detail = f"{detail} · {adresse}"
    return pipeline.creer_carte(m, titre, accroche, detail, s.get("pillar") or "")
