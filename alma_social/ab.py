"""Les tests A/B (§ 11.3) — deux manières de faire, sur des contenus comparables.

Un test : une HYPOTHÈSE écrite d'avance, deux variantes, un échantillon
visé, puis un résultat et une conclusion au carnet — OU PAS : un résultat
qui n'est pas net est déclaré « pas net », il n'entre pas au carnet.

Comment on compare sans fausser :
- les variantes alternent créneau après créneau (A, B, A, B…) : même
  période, mêmes piliers, mêmes saisons ;
- le score de chaque publication est relatif à la médiane de la marque sur
  SON réseau (`analyste.observations`) ;
- la conclusion passe par `analyste.comparer` (huit publications au moins de
  chaque côté, 20 % d'écart, test de rangs) ;
- un test ne dure jamais plus de dix semaines : au-delà, ce qu'il mesure a
  changé sous lui. Il s'arrête « pas net ».

Les variables :
- `accroche` : la première phrase en question, ou en affirmation concrète
  (consigne donnée au rédacteur) ;
- `format` : le montage du studio (Reel, carrousel, clip) contre la photo
  seule, là où un montage existe ;
- `longueur` : un texte court contre un texte développé.
Une seule expérience active par marque : deux tests à la fois se mêlent.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import insert, select, update

from . import acces, analyste, carnet, db, journal

VARIABLES = {
    "accroche": {"hypothese": "Une première phrase en question fait réagir davantage qu'une affirmation.",
                 "variantes": [("question", "Ouvre par une question que le client se pose vraiment."),
                               ("affirmation", "Ouvre par un fait concret, sans question.")]},
    "format": {"hypothese": "Un montage (Reel, carrousel, clip) fait plus qu'une photo seule.",
               "variantes": [("montage", ""), ("photo", "")]},
    "longueur": {"hypothese": "Un texte court fait plus qu'un texte développé.",
                 "variantes": [("court", "Trois lignes au plus, hashtags compris."),
                               ("long", "Développe : le contexte, le geste, le résultat, en cinq à huit lignes.")]},
}
TAILLE = 10                 # publications visées par variante
DUREE_MAX = dt.timedelta(weeks=10)


def actif(marque_id: str) -> dict | None:
    with db.moteur().connect() as c:
        return db.ligne(c.execute(select(db.experiments).where(
            db.experiments.c.brand_id == marque_id, db.experiments.c.statut == "en_cours")))


def lancer(m: dict, variable: str, par: str = "analyste", hypothese: str = "") -> dict:
    if variable not in VARIABLES:
        raise ValueError(f"variable inconnue : {variable}")
    if actif(m["id"]):
        raise ValueError("un test est déjà en cours pour cette marque : deux tests à la fois se mêlent")
    v = VARIABLES[variable]
    with db.moteur().begin() as c:
        eid = c.execute(insert(db.experiments).values(
            brand_id=m["id"], hypothese=hypothese or v["hypothese"], variable=variable,
            variantes=[{"nom": n, "consigne": k, "post_ids": []} for n, k in v["variantes"]],
            taille=TAILLE, resultat={}, statut="en_cours", created_at=db.maintenant())).inserted_primary_key[0]
    journal.noter(par, "ab_lance", "experiment", eid, m["id"], apres={"variable": variable})
    return actif(m["id"])


def assigner(marque_id: str, peut_monter: bool = False) -> dict | None:
    """La variante du prochain créneau : celle qui a le moins de publications.
    → {experience, nom, consigne, variable} ou None. Pour `format`, un créneau
    sans montage possible ne compte pas dans le test."""
    e = actif(marque_id)
    if not e:
        return None
    if e["variable"] == "format" and not peut_monter:
        return None
    v = min(e["variantes"], key=lambda x: (len(x["post_ids"]), e["variantes"].index(x)))
    return {"experience": e["id"], "nom": v["nom"], "consigne": v["consigne"], "variable": e["variable"]}


def enregistrer(experience_id: int, nom: str, post_ids: list):
    with db.moteur().begin() as c:
        e = db.ligne(c.execute(select(db.experiments).where(db.experiments.c.id == experience_id)))
        if not e:
            return
        vs = [dict(v) for v in e["variantes"]]
        for v in vs:
            if v["nom"] == nom:
                v["post_ids"] = list(v["post_ids"]) + [p for p in post_ids if p not in v["post_ids"]]
        c.execute(update(db.experiments).where(db.experiments.c.id == experience_id).values(variantes=vs))


def conclure(e: dict, par: str = "analyste") -> dict:
    """→ le résultat (et la conclusion, si le test est fini)."""
    m = acces.marque(e["brand_id"])
    obs = {o["post"]["id"]: o for o in analyste.observations(e["brand_id"], 120)}
    a, b = e["variantes"][0], e["variantes"][1]
    sa = [obs[p]["score"] for p in a["post_ids"] if p in obs]
    sb = [obs[p]["score"] for p in b["post_ids"] if p in obs]
    r = analyste.comparer(sa, sb)
    fini_taille = len(sa) >= e["taille"] and len(sb) >= e["taille"]
    trop_vieux = db.maintenant() - e["created_at"] >= DUREE_MAX
    resultat = {**r, "mesurees": [len(sa), len(sb)], "visees": e["taille"]}
    vals = {"resultat": resultat}
    if fini_taille or trop_vieux:
        if r["net"]:
            gagnant, perdant = (a, b) if r["ecart"] > 0 else (b, a)
            conclusion = (f"« {gagnant['nom']} » l'emporte sur « {perdant['nom']} » : "
                          f"{abs(round(100 * r['ecart']))} % d'engagement en plus "
                          f"({r['na']} contre {r['nb']} publications, p = {r['p']}).")
            vals.update(statut="nette", conclusion=conclusion)
            carnet.apprendre(e["brand_id"], f"ab:{e['variable']}", f"Chez {m['name']}, test A/B : {conclusion}",
                             {"echantillon": r["na"] + r["nb"], "periode":
                              f"{e['created_at']:%d/%m/%Y} → {db.maintenant():%d/%m/%Y}", "experience": e["id"],
                              "p": r["p"], "ecart": r["ecart"]}, par)
        else:
            raison = "pas d'écart net" if fini_taille else "dix semaines écoulées sans échantillon suffisant"
            vals.update(statut="pas_nette", conclusion=f"Pas net ({raison}) : rien n'entre au carnet.")
        journal.noter(par, "ab_conclu", "experiment", e["id"], e["brand_id"], apres=vals)
    with db.moteur().begin() as c:
        c.execute(update(db.experiments).where(db.experiments.c.id == e["id"]).values(**vals))
    return {**resultat, **{k: v for k, v in vals.items() if k != "resultat"}}


def conclure_tout(m: dict, par: str = "analyste") -> str:
    e = actif(m["id"])
    if not e:
        return ""
    return conclure(e, par).get("statut", "en_cours")


def liste(marque_ids: list) -> list:
    with db.moteur().connect() as c:
        return db.lignes(c.execute(select(db.experiments).where(db.experiments.c.brand_id.in_(marque_ids))
                                   .order_by(db.experiments.c.id.desc()).limit(30)))
