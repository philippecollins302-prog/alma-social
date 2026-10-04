"""Le récapitulatif du lundi matin — combien de clients, et grâce à quoi.

Le PDG reçoit les six marques ; chaque responsable reçoit la sienne. Le
chiffre du haut est celui qui compte (demandes, commandes, appels sur 30
jours, et les trois publications responsables). En dessous : ce qui est
sorti, ce qui a échoué, les piliers oubliés, le stock, les avis, la veille.
Les publications simulées du bac à sable sont comptées À PART, jamais mêlées.
"""
from __future__ import annotations

import datetime as dt
import html

from sqlalchemy import func, select

from . import acces, alertes, db, journal, mesure, planificateur, relation, reseaux


def fiche(m: dict) -> dict:
    sept = db.maintenant() - dt.timedelta(days=7)
    with db.moteur().begin() as c:
        par_statut = dict(c.execute(select(db.posts.c.status, func.count()).where(
            db.posts.c.brand_id == m["id"], db.posts.c.created_at >= sept)
            .group_by(db.posts.c.status)).all())
        echecs = db.lignes(c.execute(select(db.posts.c.platform, db.posts.c.error).where(
            db.posts.c.brand_id == m["id"], db.posts.c.status == "echec", db.posts.c.created_at >= sept)))
        a_venir = c.execute(select(func.count()).select_from(db.posts).where(
            db.posts.c.brand_id == m["id"], db.posts.c.status == "programme",
            db.posts.c.scheduled_at <= db.maintenant() + dt.timedelta(days=7))).scalar_one()
        nb_alertes = c.execute(select(func.count()).select_from(db.alerts).where(
            db.alerts.c.brand_id == m["id"], db.alerts.c.created_at >= sept)).scalar_one()
    aud = mesure.audience([m["id"]], 7)["lignes"]
    return {
        "marque": m, "chiffre": mesure.resume_marque(m["id"], 30),
        "publiees": par_statut.get("publie", 0), "simulees": par_statut.get("simule", 0),
        "echecs": echecs, "refusees": par_statut.get("refuse", 0), "a_venir": a_venir,
        "audience": aud, "piliers_oublies": planificateur.piliers_en_retard(m),
        "stock": planificateur.stock(m), "veille": relation.veille(m), "alertes": nb_alertes,
        "pause": m.get("paused_until"),
    }


def _texte(f: dict) -> str:
    m, ch = f["marque"], f["chiffre"]
    l = [f"■ {m['name']}"]
    pt = ch["par_type"]
    l.append(f"  {ch['clients']} client(s) générés sur 30 jours — {pt.get('devis', 0)} devis, "
             f"{pt.get('commande', 0)} commandes, {pt.get('appel', 0)} appels"
             + (f" ; {ch['clics_commande']} clics vers Uber Eats / Deliveroo" if m.get("sector") == "food" else ""))
    for i, t in enumerate(ch["top"], 1):
        l.append(f"   {i}. {reseaux.NOMS.get(t['platform'], t['platform'])} : {t['clients']} client(s) — « {t['texte'][:80]} »")
    l.append(f"  Semaine : {f['publiees']} publiées" + (f", {f['simulees']} simulées (bac à sable)" if f["simulees"] else "")
             + (f", {len(f['echecs'])} échecs" if f["echecs"] else "") + f" ; {f['a_venir']} prévues cette semaine.")
    for e in f["echecs"][:3]:
        l.append(f"   ✗ {reseaux.NOMS.get(e['platform'], e['platform'])} : {(e['error'] or '')[:100]}")
    vues = sum(a["vues"] for a in f["audience"])
    if vues:
        l.append(f"  Audience 7 j : {vues} vues, {sum(a['engagement'] for a in f['audience'])} interactions, "
                 f"+{sum(a['abonnes'] for a in f['audience'])} abonnés.")
    if f["piliers_oublies"]:
        l.append(f"  Rien depuis 3 semaines sur : {', '.join(f['piliers_oublies'])}.")
    s = f["stock"]
    l.append(f"  Stock : {s['banque']} photo(s) en banque, de quoi tenir {s['jours_couverts']} jour(s).")
    av = f["veille"]["avis"]
    if av["avis"]:
        l.append(f"  Avis Google : {av['moyenne']} ★ ({av['avis']} avis).")
    l.append(f"  Veille : {f['veille']['phrase']}")
    if f["pause"]:
        l.append("  ⏸ Marque en pause — rien ne repart sans votre action.")
    return "\n".join(l)


def _html(fiches: list, titre: str) -> str:
    morceaux = [f"<h2 style='font-family:sans-serif'>{html.escape(titre)}</h2>"]
    for f in fiches:
        morceaux.append("<pre style='font-family:ui-monospace,monospace;font-size:13px;white-space:pre-wrap'>"
                        + html.escape(_texte(f)) + "</pre>")
    return "\n".join(morceaux)


def composer(marque_ids: list) -> tuple:
    fiches = [fiche(m) for m in acces.marques() if m["id"] in marque_ids]
    lundi = db.maintenant().date()
    titre = f"ALMA SOCIAL — semaine du {lundi:%d/%m/%Y}"
    entete = []
    if journal.bac_a_sable():
        entete.append("⚠ Bac à sable ouvert : rien n'est encore sorti pour de vrai. Les publications "
                      "simulées sont comptées à part.")
    if journal.arret_general():
        entete.append("⛔ Arrêt général actif : aucune publication ne part.")
    corps = "\n".join(entete + [""] + [_texte(f) for f in fiches])
    return titre, corps, _html(fiches, titre), fiches


def envoyer(par: str = "systeme") -> dict:
    """Le PDG : tout. Chaque responsable : sa marque. → {destinataire: nb marques}."""
    with db.moteur().begin() as c:
        gens = db.lignes(c.execute(select(db.users).where(db.users.c.active.is_(True))))
    envois = {}
    toutes = [m["id"] for m in acces.marques()]
    for u in gens:
        a = alertes.adresse(u)
        if not a:
            continue
        ids = toutes if u["role"] == "pdg" else [b for b in (u["brands"] or []) if b in toutes]
        if not ids:
            continue
        titre, corps, html_, _ = composer(ids)
        alertes.envoyer_courrier([a], titre, corps, html_)
        envois[a] = len(ids)
    journal.noter(par, "rapport_lundi", "rapport", db.maintenant().date().isoformat(), None,
                  apres={"destinataires": len(envois)})
    return envois
