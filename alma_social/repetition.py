"""La répétition générale d'une campagne — tout ce qui partira, avant que ça parte.

Philippe veut VOIR l'ouverture de SAZÚ avant le 30 octobre : chaque étape,
son visuel, son texte réseau par réseau, son heure. La répétition rejoue la
préparation telle que l'horloge la fera le jour venu — même rédaction, mêmes
garde-fous, même Critique, même règle du logo à l'heure de l'étape — mais
n'écrit AUCUN post, ne pose aucun créneau et n'envoie rien. Elle range ses
visuels à part (`repetitions/<campagne>/…`) et sa trace dans `rehearsals`.

Ce qu'elle dit franchement : une étape sans photo du bon sujet partira en
carte à la charte (c'est prévu, pas une panne) ; une étape dont un texte
est refusé est « à revoir », avec la raison.
"""
from __future__ import annotations

import datetime as dt
import secrets

from sqlalchemy import insert, select

from . import acces, campagnes, creneaux, db, garde_fous, images, journal, pipeline, redaction, stockage


def _heure(s: dict, m: dict) -> dt.datetime:
    hh, mm = (s.get("time") or "18:00").split(":")
    return dt.datetime.combine(s["day"], dt.time(int(hh), int(mm)), tzinfo=creneaux.PARIS)


def _visuel(m: dict, s: dict, avec_logo: bool, dossier: str) -> dict:
    """La photo prévue si le créneau en a une, sinon la carte de l'étape."""
    if s.get("asset_id"):
        a = pipeline.asset(s["asset_id"])
        img = images.ouvrir(stockage.chemin(a["blurred_path"] or a["original_path"]))
        img = images.recadrer(images.corriger(img)[0], "4:5", (a["vision"] or {}).get("sujet_boite"))
        source = "photo"
    else:
        titre, accroche, detail = campagnes.parametres_carte(m, s)
        img = images.carte(m.get("kit") or {}, m["name"], titre, accroche, detail, "4:5", avec_logo)
        source = "carte"
    rel = f"{dossier}/{s['id']}-{secrets.token_hex(6)}.jpg"
    images.enregistrer_jpeg(img, stockage.racine() / rel, 88)
    return {"source": source, "chemin": rel}


def repeter(cid: int, par: str = "systeme") -> dict:
    ca = campagnes.campagne(cid)
    if not ca:
        raise ValueError("campagne inconnue")
    cts = acces.contraintes()
    with db.moteur().connect() as c:
        slots = db.lignes(c.execute(select(db.slots).where(db.slots.c.campaign_id == cid,
                                                           db.slots.c.status != "annule",
                                                           db.slots.c.day >= acces.aujourdhui())
                                    .order_by(db.slots.c.day, db.slots.c.time, db.slots.c.id)))
    dossier = f"repetitions/{cid}/{db.maintenant():%Y%m%d%H%M%S}"
    etapes = []
    for s in slots:
        m = acces.marque(s["brand_id"])
        heure = _heure(s, m)
        avec_logo = acces.logo_permis(m, heure)
        visuel = _visuel(m, s, avec_logo, dossier)
        reseaux = [r for r in (s["platforms"] or []) if r in (m.get("active_platforms") or [])]
        ctx = pipeline.contexte_du_creneau(s, m)
        lecture = (pipeline.asset(s["asset_id"]) or {}).get("vision") if s.get("asset_id") else \
            {"sujet": s.get("topic") or s.get("campaign_step"), "type_contenu": "annonce", "elements": [],
             "simule": False}
        textes = redaction.ecrire(m, lecture or {}, reseaux, cts, acces.pilier(m, s["pillar"]), ctx, [], s["day"])
        par_reseau = {}
        for pf in reseaux:
            t = textes.get(pf) or {}
            texte = t.get("texte", "")
            violations = list(t.get("violations") or [])
            if texte and not violations:
                texte = redaction.poser_lien(texte, pf, f"{_base()}/go/xxxxxx")
                texte = redaction.ajouter_mentions(texte, m, (cts.get(pf) or {}).get("caption_max"))
                violations = garde_fous.verifier_texte(texte, pf, m, cts.get(pf), ctx, None, s["day"])
            crit = t.get("critique") or {}
            par_reseau[pf] = {"texte": texte, "violations": violations, "note": crit.get("note"),
                              "juge": crit.get("juge"), "remarques": crit.get("remarques") or [],
                              "modele": t.get("modele", "")}
        refus = {pf: r["violations"] for pf, r in par_reseau.items() if r["violations"]}
        etapes.append({
            "slot_id": s["id"], "marque": m["id"], "etiquette": s["campaign_step"], "jour": s["day"].isoformat(),
            "heure": heure.strftime("%H:%M"), "accroche": s.get("topic") or "", "consigne": s.get("brief") or "",
            "reseaux": reseaux, "logo": avec_logo, "visuel": visuel, "textes": par_reseau,
            "verdict": "a_revoir" if refus or not reseaux else "pret",
            "raisons": ([f"{pf} : {', '.join(v)}" for pf, v in refus.items()]
                        + ([] if reseaux else ["aucun réseau actif pour cette étape"]))})
    resume = {"etapes": len(etapes), "pretes": sum(e["verdict"] == "pret" for e in etapes),
              "cartes": sum(e["visuel"]["source"] == "carte" for e in etapes),
              "photos": sum(e["visuel"]["source"] == "photo" for e in etapes),
              "publications": sum(len(e["reseaux"]) for e in etapes),
              "premiere_etape_avec_logo": next((e["etiquette"] for e in etapes if e["logo"]), None),
              "a_revoir": [e["etiquette"] for e in etapes if e["verdict"] != "pret"]}
    with db.moteur().begin() as c:
        rid = c.execute(insert(db.rehearsals).values(campaign_id=cid, etapes=etapes, resume=resume, par=par,
                                                     created_at=db.maintenant())).inserted_primary_key[0]
    journal.noter(par, "repetition", "campaign", cid, (ca["brand_ids"] or [None])[0], apres=resume)
    return derniere(cid) | {"id": rid}


def _base() -> str:
    from . import config
    return config.url_publique()


def derniere(cid: int) -> dict | None:
    with db.moteur().connect() as c:
        r = db.ligne(c.execute(select(db.rehearsals).where(db.rehearsals.c.campaign_id == cid)
                               .order_by(db.rehearsals.c.id.desc()).limit(1)))
    if r:
        r["campagne"] = campagnes.campagne(cid)
    return r
