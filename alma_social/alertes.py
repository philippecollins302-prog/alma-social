"""Être prévenu — le lundi matin, et quand quelque chose casse ou dérape. Rien d'autre.

Pas de notification à chaque publication : seulement les urgences (plainte,
demande de devis, gros compte, avis ≤ 3 étoiles, réseau en panne, quarantaine,
stock épuisé) et le récapitulatif du lundi. Une alerte s'écrit en base (elle
s'affiche dans l'application) et part par courrier si un serveur SMTP est
configuré et que le mode test est levé (`MAIL_TEST_MODE=0`).
"""
from __future__ import annotations

import datetime as dt
import logging
import smtplib
from email.message import EmailMessage

from sqlalchemy import insert, select

from . import config, db

log = logging.getLogger("alma_social.alertes")
ENVOYES = []        # les bancs lisent ici ce qui « serait parti »


def destinataires(marque_id: str | None) -> list:
    """Le PDG toujours ; le responsable de la marque quand il y en a un."""
    with db.moteur().begin() as c:
        gens = db.lignes(c.execute(select(db.users).where(db.users.c.active.is_(True))))
    out = []
    for u in gens:
        if u["role"] == "pdg" or (marque_id and marque_id in (u["brands"] or [])):
            if adresse(u):
                out.append(adresse(u))
    return out


def adresse(u: dict) -> str:
    """L'e-mail d'une personne. Celui du PDG peut ne vivre que dans
    l'environnement (`SOCIAL_EMAIL_PDG`) : jamais dans le dépôt."""
    return u.get("email") or (config.email_pdg() if u.get("role") == "pdg" else "")


def alerter(sujet: str, corps: str = "", marque: str | None = None, niveau: str = "urgent",
            type_: str = "", dedup: str | None = None, delai_dedup: dt.timedelta = dt.timedelta(hours=12)):
    """→ id de l'alerte, ou None si la même alerte est déjà partie récemment."""
    if dedup:
        with db.moteur().begin() as c:
            deja = c.execute(select(db.alerts.c.id).where(
                db.alerts.c.dedup_key == dedup,
                db.alerts.c.created_at >= db.maintenant() - delai_dedup)).first()
        if deja:
            return None
    a_qui = destinataires(marque)
    with db.moteur().begin() as c:
        r = c.execute(insert(db.alerts).values(
            brand_id=marque, level=niveau, kind=type_, subject=sujet, body=corps,
            sent_to=a_qui, dedup_key=dedup, created_at=db.maintenant()))
        aid = r.inserted_primary_key[0]
    envoyer_courrier(a_qui, ("🔴 " if niveau in ("urgent", "panne") else "") + sujet, corps)
    return aid


def envoyer_courrier(a_qui: list, sujet: str, corps: str, html: str | None = None):
    ENVOYES.append({"a": list(a_qui), "sujet": sujet, "corps": corps})
    del ENVOYES[:-200]
    s = config.SMTP
    if not a_qui or not s["hote"] or config.courrier_en_test():
        return False
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s["expediteur"], ", ".join(a_qui), sujet
    msg.set_content(corps or sujet)
    if html:
        msg.add_alternative(html, subtype="html")
    try:
        with smtplib.SMTP(s["hote"], s["port"], timeout=20) as srv:
            srv.starttls()
            if s["utilisateur"]:
                srv.login(s["utilisateur"], s["mot_de_passe"])
            srv.send_message(msg)
        return True
    except Exception as e:          # une alerte qui ne part pas reste visible dans l'app
        log.warning("courrier non parti : %s", e)
        return False
