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

from . import (acces, alertes, carnet, db, demandes_avis, journal, lecture_avis, maps, mesure, planificateur,
               relation, reseaux)


def objectif(marque_id: str) -> int | None:
    """Les clients visés par mois — posé par le PDG (Marques), jamais deviné."""
    v = journal.lire(f"objectif:{marque_id}")
    try:
        return int(v) if v not in (None, "") else None
    except ValueError:
        return None


def fiche(m: dict) -> dict:
    from . import analyste
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
    obs = analyste.observations(m["id"], 30)
    semaine = acces.aujourdhui() - dt.timedelta(days=acces.aujourdhui().weekday())
    return {
        "marque": m, "chiffre": mesure.resume_marque(m["id"], 30), "valeur": analyste.valeur(m),
        "objectif": objectif(m["id"]),
        "publiees": par_statut.get("publie", 0), "simulees": par_statut.get("simule", 0),
        "echecs": echecs, "refusees": par_statut.get("refuse", 0), "a_venir": a_venir,
        "audience": aud, "piliers_oublies": planificateur.piliers_en_retard(m),
        "stock": planificateur.stock(m), "veille": relation.veille(m), "alertes": nb_alertes,
        "pause": m.get("paused_until"),
        "victoires": sorted(obs, key=lambda o: (-o["clients"], -o["score"]))[:3] if obs else [],
        "anomalies": analyste.anomalies(m),
        "decisions": analyste.proposer_decisions(m, semaine.isoformat()),
        "lecons": carnet.lecons(m["id"], 2),
        "lecture_avis": lecture_avis.lecture(m), "demandes_avis": demandes_avis.bilan(m["id"], 7),
        "maps": maps.resume(m), "delais": relation.delais([m["id"]]),
        "prospects": _prospects(m["id"]), "crise": m.get("crisis_since"),
    }


def _prospects(marque_id: str) -> dict:
    sept = db.maintenant() - dt.timedelta(days=7)
    with db.moteur().connect() as c:
        return dict(c.execute(select(db.leads.c.temperature, func.count()).where(
            db.leads.c.brand_id == marque_id, db.leads.c.created_at >= sept, db.leads.c.temperature != "")
            .group_by(db.leads.c.temperature)).all())


def _duree(s) -> str:
    if s is None:
        return "—"
    return f"{s} s" if s < 90 else f"{round(s / 60)} min" if s < 5400 else f"{round(s / 3600)} h"


def _pourquoi(o: dict) -> str:
    e = o["etiquettes"]
    return f"{e['format']}, {e['moment']}, ouverture en {e['ouverture']}"


def _texte(f: dict) -> str:
    """La note d'un directeur commercial à son PDG : deux minutes de lecture."""
    m, ch, v = f["marque"], f["chiffre"], f["valeur"]
    l = [f"■ {m['name']}"]
    pt = ch["par_type"]
    obj = f["objectif"]
    if obj:
        manque = obj - ch["clients"]
        ecart = f" — objectif {obj} : " + ("atteint" if manque <= 0 else f"il en manque {manque}")
    else:
        ecart = " — pas d'objectif fixé (Marques → objectif)"
    l.append(f"  LE CHIFFRE : {ch['clients']} client(s) en 30 jours{ecart}. "
             f"{pt.get('devis', 0)} devis, {pt.get('commande', 0)} commandes, {pt.get('appel', 0)} appels"
             + (f" ; {ch['clics_commande']} clics vers Uber Eats / Deliveroo" if m.get("sector") == "food" else "")
             + (f" ; {v['chiffre']:.0f} € connus" if v["chiffre"] else "") + ".")
    if f["prospects"]:
        pr = f["prospects"]
        l.append(f"  Prospects qualifiés (7 j) : {pr.get('chaud', 0)} chaud(s), {pr.get('tiede', 0)} tiède(s), "
                 f"{pr.get('froid', 0)} froid(s).")
    if v["par_reseau"]:
        l.append("  Par source : " + ", ".join(f"{k} {n}" for k, n in list(v["par_reseau"].items())[:5]) + ".")
    l.append("  VICTOIRES :")
    if f["victoires"]:
        for i, o in enumerate(f["victoires"], 1):
            p = o["post"]
            l.append(f"   {i}. {reseaux.NOMS.get(p['platform'], p['platform'])} du {p['published_at']:%d/%m} — "
                     f"{o['clients']} client(s), {o['score']:.1f}× la médiane ({_pourquoi(o)}). "
                     f"« {(p['text'] or '').splitlines()[0][:70] if p['text'] else ''} »")
    else:
        l.append("   aucune publication réelle mesurée sur 30 jours.")
    l.append("  PROBLÈMES :")
    pbs = [f"{reseaux.NOMS.get(e['platform'], e['platform'])} en échec : {(e['error'] or '')[:90]}" for e in f["echecs"][:2]]
    pbs += [f"décrochage — {a}" for a in f["anomalies"][:2]]
    s = f["stock"]
    if s["jours_couverts"] < 7:
        pbs.append(f"stock bas : {s['banque']} photo(s), de quoi tenir {s['jours_couverts']} jour(s) — le brief du coach dit quoi filmer")
    if f["piliers_oublies"]:
        pbs.append(f"rien depuis 3 semaines sur : {', '.join(f['piliers_oublies'])}")
    for x in pbs[:3] or ["rien à signaler."]:
        l.append(f"   • {x}")
    l.append("  DÉCISIONS PROPOSÉES (appliquées à midi sauf refus dans l'application) :")
    if f["decisions"]:
        for d in f["decisions"][:3]:
            l.append(f"   → {d['phrase']}. {d['pourquoi']}" + ("" if d["auto"] else " [à décider : rien ne part seul]"))
    else:
        l.append("   aucune cette semaine : rien de net dans les chiffres.")
    if f["lecons"]:
        l.append(f"  Appris : {f['lecons'][0]['lecon']}")
    l.append(f"  Semaine : {f['publiees']} publiées" + (f", {f['simulees']} simulées (bac à sable)" if f["simulees"] else "")
             + f" ; {f['a_venir']} prévues.")
    vues = sum(a["vues"] for a in f["audience"])
    if vues:
        l.append(f"  Audience 7 j : {vues} vues, {sum(a['engagement'] for a in f['audience'])} interactions, "
                 f"+{sum(a['abonnes'] for a in f['audience'])} abonnés.")
    l.append(f"  Concurrents : {f['veille']['phrase']}")
    av = f["veille"]["avis"]
    da = f["demandes_avis"]
    l.append((f"  Avis : {av['moyenne']} ★ ({av['avis']} avis). " if av["avis"] else "  Avis : aucun relevé. ")
             + f["lecture_avis"]["phrase"]
             + (f" Demandes envoyées (7 j) : {da['parties']}, ouvertes : {da['ouvertes']}." if da["demandes"] else ""))
    if f["lecture_avis"]["idees"]:
        l.append(f"  Idée de contenu qui répond aux avis : {f['lecture_avis']['idees'][0]}")
    l.append(f"  Google Maps : {f['maps']['phrase']}")
    dq, dd = f["delais"]["question"], f["delais"]["devis"]
    if dq["messages"] or dd["messages"]:
        l.append(f"  Délai de réponse (7 j) : questions {_duree(dq['mediane_s'])} (objectif 15 min, "
                 f"{dq['en_retard']} en retard) ; devis {_duree(dd['mediane_s'])} (objectif 5 min, "
                 f"{dd['en_retard']} en retard).")
    l.append(f"  Stock : {s['banque']} photo(s), {s['jours_couverts']} jour(s) d'avance.")
    l.append(f"  Dépenses 30 j : {v['cout_ia']:.2f} $ d'IA, {v['cout_pub']:.0f} € de publicité"
             + (f" — {v['cout_par_client']:.2f} par client" if v["cout_par_client"] else "") + ".")
    if f["crise"]:
        l.append("  🚨 MODE CRISE en cours — rien ne part, aucune réponse automatique.")
    elif f["pause"]:
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
