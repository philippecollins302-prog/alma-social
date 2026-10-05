"""Obtenir des avis (§ 16.2) — l'événement déclenche, la machine relance.

Trois événements ouvrent une demande : le **procès-verbal de fin de
chantier**, la **facture payée**, la **commande livrée**. Ils arrivent par le
formulaire de l'application (« chantier livré », un geste du responsable) ou
par le serveur d'un outil (facturation, caisse), signé comme les conversions
(`SOCIAL_CONVERSIONS_SECRET`).

**À tous les clients, sans contrepartie, sans tri.** C'est la règle de Google
(le « review gating » — ne demander qu'aux contents — est interdit et fait
retirer des avis), c'est la règle de la loi française sur les avis en ligne,
et c'est la seule façon d'avoir une note qui dit vrai. Le message ne demande
donc JAMAIS « êtes-vous satisfait ? » avant d'envoyer vers Google : le lien
mène droit à la fiche, pour tout le monde.

Un premier envoi deux heures après l'événement, à une heure décente (9 h –
19 h, jamais le dimanche), puis deux relances à J+3 et J+5 — sauf si le
client a ouvert le lien, ou demandé qu'on arrête (un lien « ne plus
recevoir » à chaque message).

Le courrier part par le serveur SMTP de l'application. Le SMS attend un
fournisseur (une dépense, donc la décision de Philippe) : une demande qui
n'a qu'un téléphone est gardée, et l'écran dit pourquoi elle n'est pas partie.
Le QR code et la puce NFC (factures, sacs, véhicules) portent le lien
générique de la marque, `/avis/m/<marque>`.
"""
from __future__ import annotations

import datetime as dt
import html
import re
import secrets

from sqlalchemy import insert, select, update

from . import acces, alertes, config, creneaux, db, file, journal

EVENEMENTS = {"pv_chantier": "fin de chantier", "facture_payee": "facture payée", "commande_livree": "commande livrée"}
RELANCES_J = (3, 5)
PREMIER_ENVOI = dt.timedelta(hours=2)
HEURES = (9, 19)


def lien_google(m: dict) -> str:
    """Le lien qui ouvre directement la fenêtre « écrire un avis » de la fiche.
    Il faut l'identifiant de la fiche Google (place ID) de la marque."""
    pid = ((m.get("links") or {}).get("google_place_id") or "").strip()
    return f"https://search.google.com/local/writereview?placeid={pid}" if pid else ""


def _heure_decente(t: dt.datetime) -> dt.datetime:
    """Le premier instant à partir de `t` qui tombe entre 9 h et 19 h, hors dimanche (Paris)."""
    for _ in range(14 * 24):
        p = creneaux.paris(t)
        if p.weekday() != 6 and HEURES[0] <= p.hour < HEURES[1]:
            return t
        t = (t + dt.timedelta(hours=1)).replace(minute=5, second=0, microsecond=0)
    return t


def email_valide(e: str) -> str:
    e = (e or "").strip().lower()
    return e if re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", e) else ""


def demander(m: dict, evenement: str, nom: str = "", email: str = "", telephone: str = "",
             external_id: str = "", par: str = "") -> dict:
    """→ la demande (ou celle qui existait pour ce même événement)."""
    from . import qualification
    if evenement not in EVENEMENTS:
        raise ValueError("événement inconnu : pv_chantier, facture_payee ou commande_livree")
    email = email_valide(email)
    tel = qualification.telephone_valide(telephone) if telephone else ""
    if not email and not tel:
        raise ValueError("il faut un e-mail ou un téléphone pour demander un avis")
    external_id = (external_id or "").strip()[:120]
    if external_id:
        with db.moteur().connect() as c:
            deja = db.ligne(c.execute(select(db.review_requests).where(
                db.review_requests.c.brand_id == m["id"], db.review_requests.c.external_id == external_id)))
        if deja:
            return {**deja, "deja": True}
    jeton = secrets.token_urlsafe(16)
    with db.moteur().begin() as c:
        rid = c.execute(insert(db.review_requests).values(
            brand_id=m["id"], event=evenement, external_id=external_id, client_name=(nom or "").strip()[:120],
            email=email, phone=tel, channel="email" if email else "sms", token=jeton, sends=[],
            status="a_envoyer", created_by=par or "systeme", created_at=db.maintenant())).inserted_primary_key[0]
    journal.noter(par or "systeme", "demande_avis", "review_request", rid, m["id"],
                  apres={"evenement": evenement, "canal": "email" if email else "sms"})
    debut = db.maintenant() + PREMIER_ENVOI
    quand = _heure_decente(debut)
    file.ajouter("demande_avis", {"id": rid, "rang": 0}, quand=quand, dedup=f"demande_avis:{rid}:0", essais_max=4)
    for i, j in enumerate(RELANCES_J, start=1):
        file.ajouter("demande_avis", {"id": rid, "rang": i}, quand=_heure_decente(debut + dt.timedelta(days=j)),
                     dedup=f"demande_avis:{rid}:{i}", essais_max=4)
    return {**_une(rid), "deja": False}


def _une(rid: int) -> dict | None:
    with db.moteur().connect() as c:
        return db.ligne(c.execute(select(db.review_requests).where(db.review_requests.c.id == rid)))


def message(m: dict, r: dict, rang: int) -> tuple:
    """→ (sujet, texte, html). Le même message pour tous : aucune question de
    satisfaction avant le lien, aucune contrepartie."""
    tu = (m.get("voice") or {}).get("address") == "tu"
    prenom = (r["client_name"] or "").split(" ")[0]
    base = config.url_publique()
    lien, stop = f"{base}/avis/{r['token']}", f"{base}/avis/{r['token']}/stop"
    contexte = {"pv_chantier": "Votre chantier est terminé" if not tu else "Ton chantier est terminé",
                "facture_payee": "Merci pour votre confiance" if not tu else "Merci pour ta confiance",
                "commande_livree": "Votre commande est arrivée" if not tu else "Ta commande est arrivée"}[r["event"]]
    if tu:
        corps = (f"{'Salut ' + prenom if prenom else 'Salut'} !\n\n{contexte}. Ton avis compte beaucoup pour nous — et "
                 f"pour ceux qui hésitent encore. Ça prend une minute :\n\n{lien}\n\nMerci !\nL'équipe {m['name']}")
    else:
        corps = (f"{'Bonjour ' + prenom if prenom else 'Bonjour'},\n\n{contexte}. Votre avis compte beaucoup pour nous, "
                 f"et pour les personnes qui hésitent encore. Une minute suffit :\n\n{lien}\n\n"
                 f"Merci,\nL'équipe {m['name']}")
    corps += f"\n\nNe plus recevoir ces messages : {stop}"
    sujet = (f"{m['name']} — votre avis" if not tu else f"{m['name']} — ton avis") + (" (petit rappel)" if rang else "")
    h = "<p>" + html.escape(corps).replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"
    h = h.replace(html.escape(lien), f'<a href="{html.escape(lien)}">Laisser un avis</a>')
    h = h.replace(html.escape(stop), f'<a href="{html.escape(stop)}">ne plus recevoir</a>')
    return sujet, corps, h


@file.traitant("demande_avis")
def envoyer(pl: dict):
    r = _une(pl["id"])
    if not r or r["status"] in ("clique", "stop"):
        return                      # il a déjà ouvert le lien, ou demandé qu'on arrête
    rang = int(pl.get("rang", 0))
    if any(s_.get("rang") == rang and s_.get("ok") for s_ in r["sends"] or []):
        return
    m = acces.marque(r["brand_id"])
    erreur, simule = "", False
    if r["channel"] == "email":
        sujet, texte, h = message(m, r, rang)
        if not config.SMTP["hote"] or config.courrier_en_test():
            alertes.ENVOYES.append({"a": [r["email"]], "sujet": sujet, "corps": texte})
            simule = True
        elif not alertes.envoyer_courrier([r["email"]], sujet, texte, html=h):
            erreur = "le serveur de courrier a refusé l'envoi"
    else:
        erreur = "SMS : aucun fournisseur branché (décision de Philippe)"
    envois = list(r["sends"] or []) + [{"le": db.maintenant().isoformat(), "rang": rang, "ok": not erreur,
                                        "simule": simule, "erreur": erreur}]
    statut = r["status"]
    if not erreur:
        statut = "envoye"
    elif statut == "a_envoyer":
        statut = "echec"
    with db.moteur().begin() as c:
        c.execute(update(db.review_requests).where(db.review_requests.c.id == r["id"]).values(sends=envois, status=statut))
    journal.noter("reputation", "demande_avis_envoyee" if not erreur else "demande_avis_echec", "review_request",
                  r["id"], r["brand_id"], apres={"rang": rang, "erreur": erreur, "simule": simule})


def ouvrir(jeton: str) -> tuple:
    """Le client clique : → (marque, lien Google). Les relances s'arrêtent."""
    with db.moteur().connect() as c:
        r = db.ligne(c.execute(select(db.review_requests).where(db.review_requests.c.token == jeton)))
    if not r:
        return None, ""
    m = acces.marque(r["brand_id"])
    if r["status"] not in ("clique", "stop"):
        with db.moteur().begin() as c:
            c.execute(update(db.review_requests).where(db.review_requests.c.id == r["id"]).values(
                status="clique", clicked_at=db.maintenant()))
        journal.noter("client", "demande_avis_ouverte", "review_request", r["id"], r["brand_id"])
    return m, lien_google(m)


def arreter(jeton: str) -> dict | None:
    with db.moteur().begin() as c:
        r = db.ligne(c.execute(select(db.review_requests).where(db.review_requests.c.token == jeton)))
        if not r:
            return None
        c.execute(update(db.review_requests).where(db.review_requests.c.id == r["id"]).values(status="stop"))
    journal.noter("client", "demande_avis_stop", "review_request", r["id"], r["brand_id"])
    return acces.marque(r["brand_id"])


def liste(marque_ids: list, limite: int = 50) -> list:
    with db.moteur().connect() as c:
        rs = db.lignes(c.execute(select(db.review_requests).where(db.review_requests.c.brand_id.in_(marque_ids))
                                 .order_by(db.review_requests.c.id.desc()).limit(limite)))
    return [{"id": r["id"], "marque": r["brand_id"], "evenement": EVENEMENTS[r["event"]], "client": r["client_name"],
             "canal": r["channel"], "statut": r["status"], "envois": len([s_ for s_ in r["sends"] if s_.get("ok")]),
             "erreur": next((s_["erreur"] for s_ in reversed(r["sends"] or []) if s_.get("erreur")), ""),
             "cree_le": r["created_at"]} for r in rs]


def bilan(marque_id: str, jours: int = 30) -> dict:
    """Combien de demandes, combien d'ouvertures — le taux qui dit si le message porte."""
    depuis = db.maintenant() - dt.timedelta(days=jours)
    with db.moteur().connect() as c:
        rs = db.lignes(c.execute(select(db.review_requests).where(
            db.review_requests.c.brand_id == marque_id, db.review_requests.c.created_at >= depuis)))
    parties = [r for r in rs if any(s_.get("ok") for s_ in r["sends"] or [])]
    ouvertes = [r for r in rs if r["status"] == "clique"]
    return {"demandes": len(rs), "parties": len(parties), "ouvertes": len(ouvertes),
            "taux": round(len(ouvertes) / len(parties), 2) if parties else None}
