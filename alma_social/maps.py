"""Google Maps (§ 16.4) — être trouvé par ceux qui cherchent à côté.

**La position sur une grille.** Un « carreleur Montpellier » tapé à Lattes ne
donne pas le même classement que tapé à Castelnau : on mesure donc la place
de la fiche sur une grille de points autour de son adresse, chaque semaine,
pour quelques requêtes clés par marque. La mesure passe par l'API Places de
Google (`GOOGLE_PLACES_API_KEY`) : une recherche par point et par requête,
la position de NOTRE fiche (son identifiant, `links.google_place_id`) parmi
les vingt premiers résultats. C'est une dépense à l'usage — donc la décision
de Philippe : sans clé, rien ne part, et un relevé saisi à la main reste
possible. La grille fait 3 × 3 points (pas d'un kilomètre) par défaut :
`SOCIAL_MAPS_GRILLE=5` pour 5 × 5.

**L'audit de fiche.** Lu dans la fiche telle que Google la sert (la même API)
ou saisie à la main : catégories, photos, horaires, description, site,
téléphone. Chaque manque devient une recommandation en une phrase.

**Nom, adresse, téléphone : les mêmes partout.** La fiche est comparée à ce
que l'application sait de la marque ; un écart est signalé, jamais corrigé
d'office.

**Les publications Google** partent déjà par le planificateur (réseau `gbp`) ;
l'audit signale une semaine sans publication. Rien n'est bâti sur la
messagerie ni sur les questions-réponses de la fiche : Google les a fermées.
"""
from __future__ import annotations

import datetime as dt
import logging
import math
import os
import re

from sqlalchemy import func, insert, select, update

from . import acces, db, garde_fous, journal

log = logging.getLogger("alma_social.maps")
API = "https://places.googleapis.com/v1"
RAYON_M = 1500
# Les requêtes clés : PROVISOIRES, à relire par chaque responsable (journal `maps_requetes:<marque>`).
REQUETES = {
    "rega": ["entreprise générale du bâtiment Montpellier", "rénovation maison Castelnau-le-Lez"],
    "vipplus": ["serrurier Montpellier", "portail automatique Castelnau-le-Lez"],
    "lms": ["poseur de parquet Montpellier", "pose sol PVC Montpellier"],
    "lms-paca": ["multiservice copropriété Marseille"],
    "sazu": ["bowl Montpellier", "livraison bowl Montpellier"],
}


def cle() -> str:
    return os.environ.get("GOOGLE_PLACES_API_KEY", "").strip()


def requetes(m: dict) -> list:
    return journal.lire(f"maps_requetes:{m['id']}") or REQUETES.get(m["id"], [])


def place_id(m: dict) -> str:
    return ((m.get("links") or {}).get("google_place_id") or "").strip()


def lundi(j: dt.date | None = None) -> str:
    j = j or acces.aujourdhui()
    return (j - dt.timedelta(days=j.weekday())).isoformat()


def grille(lat: float, lng: float, n: int = 3, pas_km: float = 1.0) -> list:
    """n × n points centrés sur (lat, lng), espacés de `pas_km`."""
    dlat = pas_km / 111.32
    dlng = pas_km / (111.32 * math.cos(math.radians(lat)))
    k = (n - 1) / 2
    return [(round(lat + (i - k) * dlat, 6), round(lng + (j - k) * dlng, 6)) for i in range(n) for j in range(n)]


# ── L'API Places (nouvelle version) ──────────────────────────────────────
def _http(methode: str, chemin: str, champs: str, json_=None) -> dict:
    import httpx
    r = httpx.request(methode, API + chemin, json=json_, timeout=20,
                      headers={"X-Goog-Api-Key": cle(), "X-Goog-FieldMask": champs})
    if r.status_code >= 400:
        raise RuntimeError(f"Places {r.status_code}")
    return r.json()


CHAMPS_FICHE = ("id,displayName,formattedAddress,nationalPhoneNumber,websiteUri,regularOpeningHours,types,"
                "primaryTypeDisplayName,photos,rating,userRatingCount,editorialSummary,location,businessStatus")


def relever_fiche(m: dict) -> dict:
    """La fiche telle que Google la sert → `brands.google_listing`."""
    if not cle() or not place_id(m):
        return {}
    d = _http("GET", f"/places/{place_id(m)}", CHAMPS_FICHE)
    fiche = {"nom": (d.get("displayName") or {}).get("text", ""), "adresse": d.get("formattedAddress", ""),
             "telephone": d.get("nationalPhoneNumber", ""), "site": d.get("websiteUri", ""),
             "horaires": bool((d.get("regularOpeningHours") or {}).get("periods")),
             "categories": d.get("types") or [], "categorie": (d.get("primaryTypeDisplayName") or {}).get("text", ""),
             "photos": len(d.get("photos") or []), "note": d.get("rating"), "avis": d.get("userRatingCount"),
             "description": (d.get("editorialSummary") or {}).get("text", ""),
             "statut": d.get("businessStatus", ""), "location": d.get("location") or {},
             "source": "places", "le": db.maintenant().isoformat()}
    poser_fiche(m, fiche, "systeme")
    return fiche


def poser_fiche(m: dict, fiche: dict, par: str):
    with db.moteur().begin() as c:
        c.execute(update(db.brands).where(db.brands.c.id == m["id"]).values(google_listing=fiche))
    journal.noter(par, "fiche_google", "brand", m["id"], m["id"], apres={"source": fiche.get("source", "manuel")})


def rang(requete: str, lat: float, lng: float, pid: str) -> int | None:
    d = _http("POST", "/places:searchText", "places.id",
              {"textQuery": requete, "languageCode": "fr", "pageSize": 20,
               "locationBias": {"circle": {"center": {"latitude": lat, "longitude": lng}, "radius": RAYON_M}}})
    ids = [p.get("id") for p in d.get("places") or []]
    return ids.index(pid) + 1 if pid in ids else None


def releve(m: dict) -> int:
    """Le relevé de la semaine, s'il y a une clé et une fiche. → points relevés."""
    pid = place_id(m)
    if not cle() or not pid or not requetes(m):
        return 0
    semaine = lundi()
    with db.moteur().connect() as c:
        if c.execute(select(db.maps_ranks.c.id).where(db.maps_ranks.c.brand_id == m["id"],
                                                     db.maps_ranks.c.week == semaine,
                                                     db.maps_ranks.c.source == "places")).first():
            return 0
    loc = ((m.get("google_listing") or {}).get("location") or {})
    if not loc:
        loc = relever_fiche(m).get("location") or {}
    if not loc:
        return 0
    n = max(1, min(7, int(os.environ.get("SOCIAL_MAPS_GRILLE", "3") or 3)))
    lignes = []
    for q in requetes(m):
        for lat, lng in grille(loc["latitude"], loc["longitude"], n):
            try:
                r = rang(q, lat, lng, pid)
            except Exception as e:
                log.warning("maps %s : %s", m["id"], e)
                continue
            lignes.append(dict(brand_id=m["id"], query=q[:120], lat=lat, lng=lng, rank=r, source="places",
                               week=semaine, created_at=db.maintenant()))
    if lignes:
        with db.moteur().begin() as c:
            c.execute(insert(db.maps_ranks), lignes)
    return len(lignes)


def saisir(m: dict, requete: str, position, par: str) -> int:
    """Un relevé fait à la main (le téléphone, en navigation privée, au bureau)."""
    requete = (requete or "").strip()[:120]
    if not requete:
        raise ValueError("quelle requête ?")
    loc = ((m.get("google_listing") or {}).get("location") or {})
    r = int(position) if position not in (None, "", "absent") else None
    if r is not None and not 1 <= r <= 100:
        raise ValueError("une position va de 1 à 100 (vide : absent)")
    with db.moteur().begin() as c:
        rid = c.execute(insert(db.maps_ranks).values(
            brand_id=m["id"], query=requete, lat=loc.get("latitude", 0.0), lng=loc.get("longitude", 0.0), rank=r,
            source="manuel", week=lundi(), created_at=db.maintenant())).inserted_primary_key[0]
    journal.noter(par, "maps_releve", "brand", m["id"], m["id"], apres={"requete": requete, "position": r})
    return rid


def resume(m: dict) -> dict:
    """La dernière semaine relevée, requête par requête, et la tendance."""
    with db.moteur().connect() as c:
        semaines = [r[0] for r in c.execute(select(db.maps_ranks.c.week).where(db.maps_ranks.c.brand_id == m["id"])
                                             .group_by(db.maps_ranks.c.week).order_by(db.maps_ranks.c.week.desc())
                                             .limit(2))]
        if not semaines:
            return {"semaine": None, "requetes": [], "phrase": "Position pas encore relevée."}
        rows = db.lignes(c.execute(select(db.maps_ranks).where(db.maps_ranks.c.brand_id == m["id"],
                                                               db.maps_ranks.c.week.in_(semaines))))
    def stats(sem, q):
        rs = [r["rank"] for r in rows if r["week"] == sem and r["query"] == q]
        if not rs:
            return None
        pris = [r for r in rs if r is not None]
        return {"points": len(rs), "top3": sum(1 for r in pris if r <= 3), "absent": len(rs) - len(pris),
                "moyenne": round(sum(pris) / len(pris), 1) if pris else None}
    out = []
    for q in sorted({r["query"] for r in rows if r["week"] == semaines[0]}):
        cur = stats(semaines[0], q)
        prev = stats(semaines[1], q) if len(semaines) > 1 else None
        out.append({"requete": q, **cur, "avant": prev})
    morceaux = []
    for x in out:
        if x["moyenne"] is None:
            morceaux.append(f"« {x['requete']} » : absente")
        else:
            t = f"« {x['requete']} » : {x['moyenne']}ᵉ en moyenne, top 3 sur {x['top3']}/{x['points']} points"
            if x["avant"] and x["avant"]["moyenne"]:
                d = x["avant"]["moyenne"] - x["moyenne"]
                t += f" ({'+' if d > 0 else ''}{d:.1f} place{'s' if abs(d) >= 2 else ''})" if abs(d) >= 0.5 else " (stable)"
            morceaux.append(t)
    return {"semaine": semaines[0], "requetes": out, "phrase": " · ".join(morceaux)}


# ── L'audit ──────────────────────────────────────────────────────────────
def _norm_tel(t: str) -> str:
    d = re.sub(r"\D", "", t or "")
    return "0" + d[2:] if d.startswith("33") else d


def _norm_adr(t: str) -> str:
    t = garde_fous._sans_accents((t or "").lower())
    t = re.sub(r"\b(avenue|av)\b", "av", t)
    t = re.sub(r"\b(rue)\b", "r", t)
    return re.sub(r"[^a-z0-9]", "", t)


def audit(m: dict) -> list:
    """→ [{gravite, phrase}] : ce qui manque à la fiche, et ce qui ne colle pas."""
    f = m.get("google_listing") or {}
    l_ = m.get("links") or {}
    recos = []
    if not place_id(m):
        return [{"gravite": "bloquant", "phrase": "Identifiant de la fiche Google (place ID) inconnu : sans lui, "
                                                  "ni relevé de position, ni lien direct vers les avis."}]
    if not f:
        return [{"gravite": "info", "phrase": "Fiche pas encore lue : elle le sera au prochain relevé, ou se saisit "
                                              "à la main."}]
    if f.get("statut") and f["statut"] != "OPERATIONAL":
        recos.append({"gravite": "bloquant", "phrase": f"Google affiche la fiche comme « {f['statut']} »."})
    if (f.get("photos") or 0) < 10:
        recos.append({"gravite": "important", "phrase": f"{f.get('photos') or 0} photo(s) sur la fiche : visez dix "
                                                        "au moins (façade, équipe, réalisations)."})
    if not f.get("horaires"):
        recos.append({"gravite": "important", "phrase": "Horaires absents : la fiche est moins montrée."})
    if not f.get("description"):
        recos.append({"gravite": "conseil", "phrase": "Pas de description : deux phrases qui disent le métier et "
                                                      "la zone."})
    if not f.get("site"):
        recos.append({"gravite": "conseil", "phrase": "Aucun site sur la fiche."})
    if len(f.get("categories") or []) < 2:
        recos.append({"gravite": "conseil", "phrase": "Une seule catégorie : ajoutez les catégories secondaires du "
                                                      "métier."})
    # Nom, adresse, téléphone : la même chose partout.
    if l_.get("telephone") and f.get("telephone") and _norm_tel(l_["telephone"]) != _norm_tel(f["telephone"]):
        recos.append({"gravite": "important", "phrase": f"Téléphone différent : {f['telephone']} sur Google, "
                                                        f"{l_['telephone']} ailleurs."})
    adr = l_.get("adresse_publique") or l_.get("adresse")
    if adr and f.get("adresse") and _norm_adr(adr)[:12] not in _norm_adr(f["adresse"]):
        recos.append({"gravite": "important", "phrase": f"Adresse différente : « {f['adresse']} » sur Google, "
                                                        f"« {adr} » ailleurs."})
    if f.get("nom") and garde_fous._sans_accents(m["name"].lower()) not in garde_fous._sans_accents(f["nom"].lower()):
        recos.append({"gravite": "conseil", "phrase": f"Nom sur Google : « {f['nom']} » — vérifiez qu'il est le même "
                                                      "partout."})
    depuis = db.maintenant() - dt.timedelta(days=7)
    with db.moteur().connect() as c:
        n = c.execute(select(func.count()).where(db.posts.c.brand_id == m["id"], db.posts.c.platform == "gbp",
                                                 db.posts.c.status == "publie",
                                                 db.posts.c.published_at >= depuis)).scalar_one()
    if "gbp" in (m.get("active_platforms") or []) and n == 0:
        recos.append({"gravite": "conseil", "phrase": "Aucune publication Google cette semaine."})
    return recos


def tour():
    """Le lundi matin : la fiche relue, la position relevée — seulement avec une clé."""
    if not cle():
        return 0
    n = 0
    for m in acces.marques():
        if place_id(m):
            try:
                relever_fiche(m)
            except Exception as e:
                log.warning("fiche %s : %s", m["id"], e)
            n += releve(acces.marque(m["id"]))
    return n
