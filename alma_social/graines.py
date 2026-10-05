"""Les graines — ce qu'une base vide reçoit au premier démarrage.

Six marques (tirées du Google Drive le 04/10/2026), les contraintes des
réseaux, le PDG, un compte « à relier » par marque et par réseau, les
concurrents à suivre, les rendez-vous fixes de SAZÚ et sa campagne
d'ouverture.

Tout est idempotent : on peut semer à chaque démarrage. Une marque déjà en
base n'est JAMAIS réécrite — ce qu'on a corrigé à l'écran l'emporte sur le
fichier. Seules les contraintes des réseaux se mettent à jour, et seulement
quand le fichier a été vérifié plus récemment que la base.

Aucun code ni e-mail réel ici : le code du PDG et son adresse viennent de
l'environnement (`SOCIAL_CODE_PDG`, `SOCIAL_EMAIL_PDG`). Sur un poste de
développement (base SQLite), deux codes d'essai existent pour l'écran :
101010 (PDG) et 202020 (responsable SAZÚ). Ils n'existent jamais en production.
"""
from __future__ import annotations

import datetime as dt
import json
import logging

from sqlalchemy import insert, select, update

from . import config, db, journal, securite

log = logging.getLogger("alma_social.graines")

CODES_DEV = {"pdg": "101010", "sazu": "202020"}


def _lire(nom: str):
    return json.loads((config.GRAINES / nom).read_text(encoding="utf-8"))


def contraintes() -> int:
    """→ le nombre de réseaux insérés ou mis à jour."""
    n = 0
    colonnes = {c.name for c in db.platform_constraints.columns}
    with db.moteur().begin() as c:
        en_base = {r["platform"]: r for r in db.lignes(c.execute(select(db.platform_constraints)))}
        for ligne in _lire("contraintes.json"):
            vals = {k: v for k, v in ligne.items() if k in colonnes}
            deja = en_base.get(ligne["platform"])
            if not deja:
                c.execute(insert(db.platform_constraints).values(**vals))
                n += 1
            elif (ligne.get("verified_on") or "") > (deja.get("verified_on") or ""):
                c.execute(update(db.platform_constraints)
                          .where(db.platform_constraints.c.platform == ligne["platform"]).values(**vals))
                n += 1
    return n


def marques() -> list:
    """→ les identifiants des marques créées (les existantes ne bougent pas)."""
    colonnes = {c.name for c in db.brands.columns}
    creees = []
    for fiche in _lire("marques.json"):
        vals = {k: v for k, v in fiche.items() if k in colonnes}
        with db.moteur().begin() as c:
            if c.execute(select(db.brands.c.id).where(db.brands.c.id == fiche["id"])).first():
                continue
            c.execute(insert(db.brands).values(created_at=db.maintenant(), **vals))
        creees.append(fiche["id"])
        _comptes(fiche)
        _concurrents(fiche)
        _series(fiche)
        journal.noter("graines", "marque_creee", "brand", fiche["id"], fiche["id"],
                      apres={"nom": fiche["name"], "reseaux": fiche.get("active_platforms"),
                             "a_completer": fiche.get("todo")})
    return creees


def _comptes(fiche: dict):
    poignees = fiche.get("_comptes") or {}
    with db.moteur().begin() as c:
        for pf in fiche.get("active_platforms") or []:
            if c.execute(select(db.accounts.c.id).where(db.accounts.c.brand_id == fiche["id"],
                                                        db.accounts.c.platform == pf)).first():
                continue
            c.execute(insert(db.accounts).values(brand_id=fiche["id"], platform=pf, handle=poignees.get(pf, ""),
                                                 status="a_relier", options={}, updated_at=db.maintenant()))


def _concurrents(fiche: dict):
    with db.moteur().begin() as c:
        for nom in fiche.get("_concurrents") or []:
            if not c.execute(select(db.competitors.c.id).where(db.competitors.c.brand_id == fiche["id"],
                                                               db.competitors.c.name == nom)).first():
                c.execute(insert(db.competitors).values(brand_id=fiche["id"], name=nom))


def _series(fiche: dict):
    with db.moteur().begin() as c:
        for se in fiche.get("_series") or []:
            if c.execute(select(db.series.c.id).where(db.series.c.brand_id == fiche["id"],
                                                      db.series.c.label == se["label"])).first():
                continue
            c.execute(insert(db.series).values(
                brand_id=fiche["id"], label=se["label"], weekday=se["weekday"], time=se.get("time", ""),
                platforms=se.get("platforms") or [], pillar=se.get("pillar", ""), tags=se.get("tags") or [],
                starts_on=dt.date.fromisoformat(se["starts_on"]) if se.get("starts_on") else None, active=True))


def utilisateurs() -> list:
    """Le PDG, depuis l'environnement. En développement seulement : deux codes d'essai."""
    faits = []
    with db.moteur().begin() as c:
        pdg = db.ligne(c.execute(select(db.users).where(db.users.c.role == "pdg").limit(1)))
    code = config.code_pdg_initial()
    email = config.email_pdg()
    if not pdg and (code or config.env_dev()):
        code = code or CODES_DEV["pdg"]
        if securite.code_acceptable(code):
            log.error("SOCIAL_CODE_PDG refusé : %s", securite.code_acceptable(code))
        else:
            with db.moteur().begin() as c:
                c.execute(insert(db.users).values(name="Philippe Testino", email=email, role="pdg", brands=[],
                                                  code_hash=securite.hacher_code(code), active=True,
                                                  created_at=db.maintenant()))
            faits.append("pdg")
    elif pdg and email and not pdg["email"]:
        with db.moteur().begin() as c:
            c.execute(update(db.users).where(db.users.c.id == pdg["id"]).values(email=email))
    if config.env_dev():
        with db.moteur().begin() as c:
            if not c.execute(select(db.users.c.id).where(db.users.c.role == "responsable")).first():
                c.execute(insert(db.users).values(name="Responsable SAZÚ (essai)", email="", role="responsable",
                                                  brands=["sazu"], code_hash=securite.hacher_code(CODES_DEV["sazu"]),
                                                  active=True, created_at=db.maintenant()))
                faits.append("responsable_essai")
    return faits


def campagnes() -> list:
    """Les campagnes du fichier, créées une seule fois (repérées par leur clé)."""
    from . import acces, campagnes as camp
    faites = []
    for ca in _lire("campagnes.json"):
        cle = f"graine_campagne:{ca['cle']}"
        if journal.lire(cle):
            continue
        if not all(acces.marque(mid) for mid in ca["marques"]):
            continue
        evenement = dt.datetime.fromisoformat(ca["evenement"]) if ca.get("evenement") else None
        c = camp.creer(ca["nom"], ca["marques"], ca["sorte"], evenement, dt.date.fromisoformat(ca["debut"]),
                       dt.date.fromisoformat(ca["fin"]), ca.get("reseaux"), ca.get("brief", ""),
                       ca.get("etapes"), par="graines")
        journal.ecrire(cle, c["id"], par="graines", journaliser=False)
        faites.append(c["id"])
    return faites


def semer() -> dict:
    db.initialiser()
    out = {"contraintes": contraintes(), "marques": marques(), "utilisateurs": utilisateurs(),
           "campagnes": campagnes()}
    from . import acces, marque
    out["plateformes"] = marque.semer(acces.marques(), par="graines")
    if any(out.values()):
        log.info("graines : %s", out)
    return out
