"""Le pipeline — d'une photo déposée aux publications, sans que personne ne valide.

Chaque étape est un travail de la file (file.py) : reprise automatique en cas
d'échec, chaque passage au journal.

  1. recevoir   — dans la requête du téléphone : l'original rangé intact,
                  l'EXIF lu, l'empreinte calculée. Idempotent (`client_ref`).
  2. analyser   — la lecture d'image ; refus technique, quarantaine, ou banque.
  3. placer     — le meilleur créneau libre (planificateur.py), sinon la banque.
  4. preparer   — retouche et déclinaisons, un texte par réseau, garde-fous,
                  heure ; un post par réseau, chacun indépendant.
  5. publier    — à l'heure dite, réseau par réseau, via le Publisher.
  6. confirmer  — pour un envoi parti en arrière-plan chez l'agrégateur.
  7. mesurer    — +1 h, +24 h, +7 j (mesure.py).
  8. la relation (commentaires, avis) vit dans relation.py.

Un réseau qui tousse ne fait jamais tomber la publication entière : chaque
réseau a son post, son statut et ses réessais.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import logging
import pathlib

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError

from . import (acces, alertes, creneaux, db, file, garde_fous, ia, images, journal, mesure,
               nettoyage, redaction, reseaux, stockage, video, vision)
from . import marque as marque_
from . import publieurs
from .publieurs.bac_a_sable import BacASable
from .publieurs.base import NonBranche, PanneTransitoire, PostPrepare, RefusReseau

log = logging.getLogger("alma_social.pipeline")

TAILLE_MAX = 40 * 1024 * 1024
ESSAIS_PUBLICATION = 3                  # « on réessaie trois fois avec un intervalle croissant »
REFUS_AVANT_PAUSE = 3                   # « trois refus consécutifs : le réseau est mis en pause »
FENETRE_DOUBLON = dt.timedelta(days=90)
SEUIL_DOUBLON = 8                       # bits de pHash : même photo recadrée ou réexportée
SEUIL_RAFALE = 5                        # deux photos d'une même rafale
ATTENTE_RAFALE = dt.timedelta(minutes=10)   # marque produit : le temps que la rafale arrive entière


# ── Petits accès ─────────────────────────────────────────────────────────
def _un(table, id_):
    with db.moteur().begin() as c:
        return db.ligne(c.execute(select(table).where(table.c.id == id_)))


def _maj(table, id_, **vals):
    with db.moteur().begin() as c:
        c.execute(update(table).where(table.c.id == id_).values(**vals))


def asset(aid):
    return _un(db.assets, aid)


def post(pid):
    return _un(db.posts, pid)


def creneau(sid):
    return _un(db.slots, sid)


# ── 1. Réception ─────────────────────────────────────────────────────────
def recevoir(marque_id: str, octets: bytes, nom_fichier: str = "", client_ref: str | None = None,
             auteur: dict | None = None, pilier: str = "", note: str = "") -> dict:
    """La photo arrive : on la range, on la lit, et la suite part en file.
    → l'asset (dict), avec `deja=True` si ce dépôt avait déjà été reçu."""
    m = acces.marque(marque_id)
    if not m:
        raise ValueError("marque inconnue")
    if not octets:
        raise ValueError("fichier vide")
    from . import clips
    if clips.est_video(octets, nom_fichier):
        return recevoir_video(m, octets, nom_fichier, client_ref, auteur, pilier, note)
    if len(octets) > TAILLE_MAX:
        raise ValueError(f"fichier trop lourd ({len(octets) // 1_000_000} Mo, maximum {TAILLE_MAX // 1_000_000} Mo)")
    if client_ref:
        # La file du téléphone renvoie un dépôt tant qu'elle n'a pas eu de
        # réponse : le second envoi ne doit rien créer.
        with db.moteur().begin() as c:
            deja = db.ligne(c.execute(select(db.assets).where(db.assets.c.client_ref == client_ref)))
        if deja:
            return {**deja, "deja": True}
    try:
        img = images.ouvrir(octets)
    except Exception as e:
        raise ValueError("ce fichier n'est pas une photo lisible") from e
    rel, sha = stockage.ranger_original(octets, pathlib.Path(nom_fichier or "x.jpg").suffix)
    with db.moteur().begin() as c:
        meme = db.ligne(c.execute(select(db.assets).where(
            db.assets.c.brand_id == marque_id, db.assets.c.sha256 == sha)))
    if meme:
        journal.noter(_qui(auteur), "depot_en_double", "asset", meme["id"], marque_id,
                      apres={"fichier": nom_fichier})
        return {**meme, "deja": True}
    exif = images.lire_exif(octets)
    vals = dict(
        brand_id=marque_id, uploader_id=(auteur or {}).get("id"), client_ref=client_ref,
        original_path=rel, sha256=sha, phash=images.empreinte(img), width=img.width,
        height=img.height, exif={k: v for k, v in exif.items() if k != "gps"},
        taken_at=images.date_prise(exif), location=exif.get("gps"),
        pillar=pilier if acces.pilier(m, pilier) else "", kind="photo", status="recu",
        note=(note or "").strip()[:500],
        created_at=db.maintenant())
    try:
        with db.moteur().begin() as c:
            aid = c.execute(insert(db.assets).values(**vals)).inserted_primary_key[0]
    except IntegrityError:          # deux envois simultanés du même client_ref
        with db.moteur().begin() as c:
            deja = db.ligne(c.execute(select(db.assets).where(db.assets.c.client_ref == client_ref)))
        return {**deja, "deja": True}
    journal.noter(_qui(auteur), "depot", "asset", aid, marque_id,
                  apres={"fichier": nom_fichier, "sha256": sha, "taille": len(octets),
                         "dimensions": f"{img.width}×{img.height}", "prise_le": vals["taken_at"]})
    file.ajouter("analyser", {"asset_id": aid}, dedup=f"analyser:{aid}")
    return asset(aid)


def recevoir_video(m: dict, octets: bytes, nom_fichier: str, client_ref, auteur, pilier: str, note: str) -> dict:
    """Une vidéo longue : rangée telle quelle (elle ne part jamais entière),
    puis découpée en clips par la file. Ce sont ses images fixes qui entrent
    en banque, chacune portant son clip."""
    from . import clips
    if len(octets) > clips.TAILLE_MAX:
        raise ValueError(f"vidéo trop lourde ({len(octets) // 1_000_000} Mo, maximum "
                         f"{clips.TAILLE_MAX // 1_000_000} Mo) : filmez en 1080p plutôt qu'en 4K")
    if client_ref:
        with db.moteur().begin() as c:
            deja = db.ligne(c.execute(select(db.assets).where(db.assets.c.client_ref == client_ref)))
        if deja:
            return {**deja, "deja": True}
    ext = pathlib.Path(nom_fichier or "").suffix.lower().lstrip(".")
    rel, sha = stockage.ranger_original(octets, ext if ext in clips.EXTENSIONS else "mp4")
    with db.moteur().begin() as c:
        meme = db.ligne(c.execute(select(db.assets).where(
            db.assets.c.brand_id == m["id"], db.assets.c.sha256 == sha)))
    if meme:
        return {**meme, "deja": True}
    try:
        info = clips.sonder(stockage.chemin(rel))
    except Exception as e:
        raise ValueError("cette vidéo ne se lit pas") from e
    if info["duree"] > clips.DUREE_MAX_S:
        raise ValueError(f"vidéo de {info['duree'] / 60:.0f} minutes : au-delà de "
                         f"{clips.DUREE_MAX_S // 60}, coupez-la avant de la déposer")
    vals = dict(brand_id=m["id"], uploader_id=(auteur or {}).get("id"), client_ref=client_ref, original_path=rel,
                sha256=sha, width=info["largeur"], height=info["hauteur"], exif={"duree_s": info["duree"]},
                pillar=pilier if acces.pilier(m, pilier) else "", kind="video", status="decoupage",
                note=(note or "").strip()[:500], created_at=db.maintenant())
    try:
        with db.moteur().begin() as c:
            aid = c.execute(insert(db.assets).values(**vals)).inserted_primary_key[0]
    except IntegrityError:
        with db.moteur().begin() as c:
            deja = db.ligne(c.execute(select(db.assets).where(db.assets.c.client_ref == client_ref)))
        return {**deja, "deja": True}
    journal.noter(_qui(auteur), "depot_video", "asset", aid, m["id"],
                  apres={"fichier": nom_fichier, "sha256": sha, "taille": len(octets), "duree": info["duree"]})
    file.ajouter("decouper", {"asset_id": aid}, dedup=f"decouper:{aid}", essais_max=3)
    return asset(aid)


@file.traitant("decouper")
def decouper(p: dict):
    from . import clips
    a = asset(p["asset_id"])
    if not a or a["kind"] != "video" or a["status"] != "decoupage":
        return
    try:
        faits = clips.decouper(a["id"])
    except ValueError as e:
        _maj(db.assets, a["id"], status="refuse", refusal_reason=str(e)[:300])
        raise file.Abandon(str(e))
    _maj(db.assets, a["id"], status="decoupee" if faits else "refuse",
         refusal_reason="" if faits else "trop courte pour en tirer un clip (3 secondes au moins)")


def _qui(auteur) -> str:
    return (auteur or {}).get("name") or "systeme"


# ── 2. Lecture de l'image ────────────────────────────────────────────────
@file.traitant("analyser")
def analyser(p: dict):
    a = asset(p["asset_id"])
    if not a or a["status"] != "recu":
        return
    m = acces.marque(a["brand_id"])
    img = images.ouvrir(stockage.chemin(a["original_path"]))
    mesures = images.mesurer(img)
    tampon = io.BytesIO()
    images.reduire(img, 1568).save(tampon, "JPEG", quality=88)
    try:
        lecture, modele = vision.lire(m, tampon.getvalue())
    except ia.ErreurIA as e:
        raise file.Reessayer(f"lecture d'image : {e}")
    pilier = a["pillar"] or (lecture.get("pilier") if acces.pilier(m, lecture.get("pilier", "")) else "")
    vals = {"vision": lecture, "vision_model": modele, "usability": int(lecture.get("utilisabilite") or 0),
            "quality": mesures, "tags": lecture.get("etiquettes") or [], "pillar": pilier or ""}

    refus = images.refus_technique(mesures, lecture.get("utilisabilite"))
    if refus:
        # « Non publiée, renvoyée à la banque, consignée. Pas d'alerte, juste le journal. »
        _maj(db.assets, a["id"], status="refuse", refusal_reason=refus, **vals)
        journal.noter("systeme", "refus_technique", "asset", a["id"], m["id"], apres={"raison": refus})
        return
    motif = garde_fous.quarantaine(lecture)
    if motif:
        _maj(db.assets, a["id"], status="quarantaine", refusal_reason=motif, **vals)
        journal.noter("systeme", "quarantaine", "asset", a["id"], m["id"], apres={"raison": motif})
        alertes.alerter(f"{m['name']} : une photo est mise de côté", f"{motif}.\n\nElle ne sera pas publiée. "
                        "Si c'est une erreur, ouvrez la photo dans l'application et libérez-la.",
                        marque=m["id"], type_="quarantaine", dedup=f"quarantaine:{a['id']}")
        return
    proche = _rafale(a)
    if proche:
        raison = f"quasi-identique à la photo n° {proche} déjà reçue (même prise de vue)"
        _maj(db.assets, a["id"], status="refuse", refusal_reason=raison, **vals)
        journal.noter("systeme", "refus_doublon", "asset", a["id"], m["id"], apres={"raison": raison})
        return
    _maj(db.assets, a["id"], status="banque", **vals)
    journal.noter("systeme", "lecture", "asset", a["id"], m["id"],
                  apres={"sujet": lecture.get("sujet"), "pilier": pilier, "note": lecture.get("utilisabilite"),
                         "modele": modele, "simule": lecture.get("simule", False)})
    quand = None
    if marque_.mise_en_scene(m) == "studio_permis" and a["kind"] == "photo":
        # Une marque produit : on laisse dix minutes à la rafale pour arriver
        # entière, le studio en fait un Reel et un carrousel, puis on place.
        file.ajouter("studio_rafale", {"brand_id": m["id"]}, quand=db.maintenant() + ATTENTE_RAFALE,
                     dedup=f"rafale:{a['id']}")
        quand = db.maintenant() + ATTENTE_RAFALE + dt.timedelta(minutes=1)
    file.ajouter("placer", {"asset_id": a["id"]}, quand=quand, dedup=f"placer:{a['id']}")


@file.traitant("studio_rafale")
def studio_rafale(p: dict):
    from . import studio
    try:
        studio.rafale(p["brand_id"])
    except studio.RegleHonnetete:
        return
    except Exception as e:
        log.exception("montage automatique")
        raise file.Reessayer(f"studio : {e}")


def _rafale(a: dict):
    """Deux photos d'une même rafale ne font pas deux publications : la première gagne."""
    depuis = db.maintenant() - FENETRE_DOUBLON
    with db.moteur().begin() as c:
        autres = db.lignes(c.execute(select(db.assets.c.id, db.assets.c.phash).where(
            db.assets.c.brand_id == a["brand_id"], db.assets.c.id != a["id"],
            db.assets.c.kind == "photo", db.assets.c.created_at >= depuis,
            db.assets.c.status.in_(("banque", "programme", "publie", "studio")))))
    for o in autres:
        if images.distance(a["phash"], o["phash"]) <= SEUIL_RAFALE:
            return o["id"]
    return None


# ── 3. Placement ─────────────────────────────────────────────────────────
@file.traitant("placer")
def placer(p: dict):
    a = asset(p["asset_id"])
    if not a or a["status"] != "banque":
        return
    m = acces.marque(a["brand_id"])
    if not m or not m["active"]:
        return
    from . import planificateur
    s = planificateur.creneau_pour(m, a)
    if s is None:
        journal.noter("systeme", "en_banque", "asset", a["id"], m["id"],
                      apres={"raison": "aucun créneau libre dans les 7 jours : la photo attend son tour"})
        return
    attacher(s, a)


def attacher(s: dict, a: dict, par: str = "systeme"):
    with db.moteur().begin() as c:
        r = c.execute(update(db.slots).where(db.slots.c.id == s["id"], db.slots.c.status.in_(("libre", "manque")))
                      .values(asset_id=a["id"], status="rempli"))
        if r.rowcount != 1:
            return False
        c.execute(update(db.assets).where(db.assets.c.id == a["id"]).values(status="programme"))
    journal.noter(par, "placement", "slot", s["id"], s["brand_id"],
                  apres={"asset": a["id"], "jour": s["day"], "pilier": s["pillar"], "source": s["source"]})
    file.ajouter("preparer", {"slot_id": s["id"]}, dedup=f"preparer:{s['id']}:{a['id']}")
    return True


# ── 4. Préparation ───────────────────────────────────────────────────────
@file.traitant("preparer")
def preparer(p: dict):
    s = creneau(p["slot_id"])
    if not s or s["status"] != "rempli" or not s["asset_id"]:
        return
    preparer_creneau(s)


def statuts_doublon() -> tuple:
    """Ce qui compte comme « déjà sorti » : en bac à sable, les publications
    simulées comptent aussi — sinon la semaine d'essai ne montrerait pas ce
    que fera la vraie."""
    base = ("publie", "programme", "envoi", "a_valider", "suspendu")
    return base + ("simule",) if journal.bac_a_sable() else base


def fenetre_doublon(a: dict) -> dt.timedelta:
    """90 jours entre deux sorties d'une même image sur un réseau — sauf une
    seconde chance (21 jours : c'est l'heure qui avait échoué, pas l'image) et
    un intemporel (45 jours : il est fait pour revenir)."""
    from . import recyclage
    if a.get("recyclage") == "seconde_chance":
        return recyclage.DELAI_SECONDE_CHANCE
    if a.get("pillar") and a["pillar"] in recyclage.piliers_evergreen(a["brand_id"]):
        return recyclage.ECART_EVERGREEN
    return FENETRE_DOUBLON


def variante_cadrage(a: dict) -> int:
    """Une photo qui ressort (seconde chance, gagnant, intemporel) change de cadrage."""
    return 1 if a.get("recyclage") or _deja_sortie(a["id"]) else 0


def _deja_sortie(asset_id: int) -> bool:
    with db.moteur().begin() as c:
        return c.execute(select(db.posts.c.id).where(db.posts.c.asset_id == asset_id,
                                                     db.posts.c.status.in_(("publie", "simule")))).first() is not None


def doublons(a: dict, plateformes: list, sauf_creneau: int | None = None) -> dict:
    """{réseau: post_id} — la même image (empreinte visuelle) déjà sortie ou
    programmée sur ce réseau depuis moins de 90 jours (voir `fenetre_doublon`)."""
    depuis = db.maintenant() - fenetre_doublon(a)
    with db.moteur().begin() as c:
        q = (select(db.posts.c.id, db.posts.c.platform, db.assets.c.phash)
             .join(db.assets, db.assets.c.id == db.posts.c.asset_id)
             .where(db.posts.c.brand_id == a["brand_id"], db.posts.c.platform.in_(plateformes),
                    db.posts.c.status.in_(statuts_doublon()), db.posts.c.created_at >= depuis))
        if sauf_creneau:
            q = q.where(db.posts.c.slot_id != sauf_creneau)
        lignes = db.lignes(c.execute(q))
    out = {}
    for pf in plateformes:
        pid = garde_fous.doublon(a["phash"], [(l["phash"], l["id"]) for l in lignes if l["platform"] == pf],
                                 SEUIL_DOUBLON)
        if pid:
            out[pf] = pid
    return out


def _rythme_atteint(m: dict, plateforme: str, jour: dt.date) -> bool:
    """Le rythme propre à un réseau, quand la marque en fixe un (SAZÚ : une
    publication Google par semaine). → True si la semaine est pleine."""
    plafond = ((m.get("voice") or {}).get("rythme") or {}).get(plateforme)
    if not plafond:
        return False
    lundi = jour - dt.timedelta(days=jour.weekday())
    debut = creneaux.utc(dt.datetime.combine(lundi, dt.time(0), tzinfo=creneaux.PARIS))
    from sqlalchemy import func
    with db.moteur().begin() as c:
        n = c.execute(select(func.count()).select_from(db.posts).where(
            db.posts.c.brand_id == m["id"], db.posts.c.platform == plateforme,
            db.posts.c.status.in_(("programme", "a_valider", "envoi", "publie", "simule")),
            db.posts.c.scheduled_at >= debut, db.posts.c.scheduled_at < debut + dt.timedelta(days=7))).scalar_one()
    return n >= int(plafond)


def contexte_du_creneau(s: dict, m: dict) -> dict:
    """Ce que le texte doit savoir en plus de la photo — et les seuls chiffres
    qu'il pourra écrire en plus de ceux de la marque."""
    ctx = {}
    if s.get("topic"):
        ctx["sujet proposé"] = s["topic"]
    if s.get("brief"):
        ctx["consigne"] = s["brief"]
    if s.get("source") == "temps_fort" and s.get("topic"):
        ctx["temps fort"] = s["topic"]
    if s.get("series_id"):
        se = _un(db.series, s["series_id"])
        if se:
            ctx["rendez-vous"] = se["label"]
    if s.get("campaign_id"):
        ca = _un(db.campaigns, s["campaign_id"])
        if ca:
            ctx["campagne"] = ca["name"]
            if s.get("campaign_step"):
                ctx["étape"] = s["campaign_step"]
            if ca.get("event_at"):
                h = creneaux.paris(ca["event_at"])
                ctx["annonce"] = f"{_JOURS[h.weekday()]} {h.day} {_MOIS[h.month - 1]} {h.year} à {h.hour}h{h.minute:02d}"
            if ca.get("brief"):
                ctx["brief de campagne"] = ca["brief"]
    return ctx


_JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
         "octobre", "novembre", "décembre"]


def _declencheur(s: dict, a: dict) -> str:
    if a.get("last_used_at"):
        return "recyclage"
    return {"plan": "calendrier", "depot": "depot", "serie": "serie", "campagne": "campagne",
            "temps_fort": "calendrier"}.get(s["source"], "depot")


def _anciens_textes(asset_id: int) -> list:
    with db.moteur().begin() as c:
        return [r[0] for r in c.execute(select(db.posts.c.text).where(
            db.posts.c.asset_id == asset_id, db.posts.c.status.in_(("publie", "simule"))))]


def _occupes(marque_id: str, plateforme: str, jour: dt.date) -> list:
    """Les heures déjà prises par la marque sur ce réseau, à ±2 jours."""
    debut = creneaux.utc(dt.datetime.combine(jour - dt.timedelta(days=2), dt.time(0), tzinfo=creneaux.PARIS))
    fin = creneaux.utc(dt.datetime.combine(jour + dt.timedelta(days=3), dt.time(0), tzinfo=creneaux.PARIS))
    with db.moteur().begin() as c:
        rows = c.execute(select(db.posts.c.scheduled_at).where(
            db.posts.c.brand_id == marque_id, db.posts.c.platform == plateforme,
            db.posts.c.status.in_(("programme", "envoi", "publie", "simule", "a_valider")),
            db.posts.c.scheduled_at >= debut, db.posts.c.scheduled_at < fin)).scalars().all()
    return [creneaux.paris(t) for t in rows if t]


def format_pour(plateforme: str, cts: dict) -> str:
    f = (cts.get(plateforme) or {}).get("preferred_format") or reseaux.FORMAT_DEFAUT.get(plateforme, "4:5")
    return f if f in images.FORMATS else reseaux.FORMAT_DEFAUT.get(plateforme, "4:5")


def preparer_creneau(s: dict, par: str = "systeme") -> dict:
    """Un créneau rempli devient un post par réseau, prêt à partir à son heure."""
    m = acces.marque(s["brand_id"])
    a = asset(s["asset_id"])
    cts = acces.contraintes()
    jour = s["day"]
    bac = journal.bac_a_sable()
    voulus = [r for r in (s["platforms"] or m["active_platforms"] or []) if r in (m["active_platforms"] or [])]
    retenus, ecartes = [], {}
    deja = doublons(a, voulus, sauf_creneau=s["id"])
    for pf in voulus:
        cpt = acces.compte(m["id"], pf)
        if cpt and cpt["status"] == "pause":
            ecartes[pf] = "réseau en pause après des refus répétés"
        elif not bac and (not cpt or cpt["status"] != "actif"):
            ecartes[pf] = "compte pas encore relié"
        elif pf in reseaux.VIDEO_SEULEMENT and not video.disponible():
            ecartes[pf] = "encodeur vidéo indisponible"
        elif pf in deja:
            ecartes[pf] = f"même photo déjà sortie sur ce réseau il y a moins de 90 jours (publication n° {deja[pf]})"
        elif _rythme_atteint(m, pf, jour):
            ecartes[pf] = "rythme de la semaine atteint sur ce réseau (fiche de la marque)"
        else:
            retenus.append(pf)
    if not retenus:
        _liberer(s, a, ecartes, par)
        return {"posts": [], "ecartes": ecartes}

    pilier = acces.pilier(m, s["pillar"] or a["pillar"])
    contexte = contexte_du_creneau(s, m)
    if a.get("note"):
        # Ce que le terrain a dit en déposant : le texte peut s'en servir, ses
        # chiffres deviennent citables (c'est un fait rapporté par l'équipe).
        contexte["dit par l'équipe au dépôt"] = a["note"]
    reprise = a.get("recyclage") in ("seconde_chance", "gagnant") or _deja_sortie(a["id"])
    if reprise:
        contexte["reprise"] = ("cette photo est déjà sortie : écris un texte NEUF, sous un autre angle "
                               "(les anciens textes sont fournis pour ne pas les répéter)")
    variante = variante_cadrage(a)
    from . import studio
    montages = studio.montages_de(a["id"])
    if marque_.mise_en_scene(m) != "studio_permis":
        # Une réalisation : seul le clip (des images réelles, coupées, jamais
        # retouchées) la porte ; les montages du studio restent aux produits.
        montages = {t: j for t, j in montages.items() if t == "clip"}
    from . import ab
    test = ab.assigner(m["id"], peut_monter=bool(montages))
    if test:
        if test["consigne"]:
            contexte["test A/B en cours"] = test["consigne"]
        if test["variable"] == "format" and test["nom"] == "photo":
            montages = {}               # la variante « photo seule » du test de format
    if montages:
        choix = {pf: studio.montage_pour(pf, montages) for pf in retenus}
        contexte["format"] = "selon le réseau : " + " ; ".join(
            f"{reseaux.NOMS.get(pf, pf)} → " + ("clip vidéo extrait d'une vidéo filmée sur place" if j["type"] == "clip"
                                               else f"{j['type']} de {len(j['asset_ids'])} photos")
            for pf, j in choix.items() if j)
    lecture = a["vision"] or {}
    textes = redaction.ecrire(m, lecture, retenus, cts, pilier, contexte, _anciens_textes(a["id"]), jour,
                              slot_id=s["id"])

    maintenant = creneaux.paris(db.maintenant())
    apres = maintenant + dt.timedelta(minutes=10)
    profils = mesure.profils(m["id"])
    imposee = s.get("time") or ""
    soeurs, crees = [], []
    for pf in retenus:
        t = textes.get(pf)
        base = {"brand_id": m["id"], "asset_id": a["id"], "slot_id": s["id"], "platform": pf,
                "pillar": s["pillar"] or a["pillar"] or "", "trigger": _declencheur(s, a),
                "created_at": db.maintenant()}
        if not t or t["violations"]:
            par_critique = bool(t) and all(str(x).startswith("critique") for x in t["violations"])
            pid = _inserer(base, status="refuse", text=(t or {}).get("texte", ""),
                           error=("texte refusé par le Critique après trois tours" if par_critique
                                  else "texte refusé par le garde-fou de langage"),
                           model=(t or {}).get("modele", ""), prompt_version=(t or {}).get("prompt_version", ""),
                           guard_report={"violations": (t or {}).get("violations") or ["aucun texte produit"],
                                         "critique": (t or {}).get("critique")})
            journal.noter(par, "texte_refuse", "post", pid, m["id"],
                          apres={"reseau": pf, "violations": (t or {}).get("violations")})
            continue
        # Une seconde chance part sur un des meilleurs créneaux : c'est l'heure qui avait échoué.
        explore = not imposee and a.get("recyclage") != "seconde_chance" \
            and creneaux.explorer(f"{s['id']}:{a['id']}:{pf}")
        heure = creneaux.choisir_heure(m["sector"], pf, jour, _occupes(m["id"], pf, jour), soeurs,
                                       profils.get(pf), apres, imposee, exploration=explore)
        if heure is None:
            ecartes[pf] = "aucune heure libre ce jour-là (espacement de 16 h sur un même réseau)"
            continue
        soeurs.append(heure)
        avec_logo = acces.logo_permis(m, heure)
        fmt = format_pour(pf, cts)
        est_video = pf in reseaux.VIDEO_SEULEMENT
        montage = studio.montage_pour(pf, montages) if montages else None
        if montage and not avec_logo and montage["sortie"].get("params", {}).get("avec_logo", True):
            montage = None          # le logo n'est pas encore permis à cette heure-là : la photo seule
        extras, forme = [], ("video" if est_video else "image")
        try:
            if montage:
                rs = [_un(db.renditions, f["rendition_id"]) for f in montage["fichiers"]]
                rendu = {**_info_rendu(rs[0]), "vues": len(rs)}
                extras, forme = [r["id"] for r in rs[1:]], montage["type"]
            else:
                rendu = declinaison(a, m, "9:16" if est_video else fmt, en_video=est_video, avec_logo=avec_logo,
                                    variante=variante)
        except Exception as e:
            log.exception("déclinaison %s/%s", a["id"], pf)
            raise file.Reessayer(f"retouche : {e}")
        v_media = garde_fous.verifier_media(rendu, cts.get(pf))
        if v_media:
            pid = _inserer(base, status="refuse", text=t["texte"], rendition_id=rendu["id"],
                           error="image refusée par les contraintes du réseau", guard_report={"media": v_media})
            journal.noter(par, "media_refuse", "post", pid, m["id"], apres={"reseau": pf, "violations": v_media})
            continue
        pid = _inserer(base, status="preparation", text=t["texte"], title=t.get("titre", ""),
                       rendition_id=rendu["id"], scheduled_at=creneaux.utc(heure), model=t["modele"],
                       post_format=forme, media_job_id=(montage or {}).get("id"), extra_renditions=extras,
                       prompt_version=t["prompt_version"],
                       guard_report={"violations": [], "essais": t["essais"], "traitements": rendu["traitements"],
                                     "critique": t.get("critique"),
                                     "creneau": "impose" if imposee else ("exploration" if explore else "meilleur"),
                                     "ab": {"experience": test["experience"], "variante": test["nom"]} if test else None})
        lien = mesure.liens_de_publication(m, pid, pf)
        texte = redaction.poser_lien(t["texte"], pf, lien["url"])
        texte = redaction.ajouter_mentions(texte, m, (cts.get(pf) or {}).get("caption_max"))
        finales = garde_fous.verifier_texte(texte, pf, m, cts.get(pf), contexte, None, jour)
        if finales:
            _maj(db.posts, pid, status="refuse", text=texte, link_id=lien["id"],
                 error="texte final refusé", guard_report={"violations": finales})
            journal.noter(par, "texte_refuse", "post", pid, m["id"], apres={"reseau": pf, "violations": finales})
            continue
        statut = "a_valider" if m.get("requires_approval") else "programme"
        _maj(db.posts, pid, status=statut, text=texte, link_id=lien["id"])
        if statut == "programme":
            file.ajouter("publier", {"post_id": pid}, quand=creneaux.utc(heure), dedup=f"publier:{pid}",
                         essais_max=10)
        crees.append(pid)
    if test and crees:
        ab.enregistrer(test["experience"], test["nom"], crees)
    with db.moteur().begin() as c:
        vals = {"status": "programme", "last_used_at": db.maintenant()}
        if crees and a.get("recyclage") == "seconde_chance":
            vals["recyclage"] = "seconde_chance_faite"      # une seule seconde chance
        c.execute(update(db.assets).where(db.assets.c.id == a["id"]).values(**vals))
    if not crees:
        _liberer(s, a, ecartes, par)
        return {"posts": [], "ecartes": ecartes}
    journal.noter(par, "preparation", "slot", s["id"], m["id"],
                  apres={"asset": a["id"], "posts": crees, "ecartes": ecartes, "contexte": contexte})
    return {"posts": crees, "ecartes": ecartes}


def _inserer(base: dict, **vals) -> int:
    with db.moteur().begin() as c:
        return c.execute(insert(db.posts).values(**base, **vals)).inserted_primary_key[0]


def _liberer(s, a, ecartes, par):
    """Rien n'a pu partir de ce créneau : la photo retourne en banque, le
    créneau redevient libre (le planificateur le remplira avec une autre)."""
    with db.moteur().begin() as c:
        c.execute(update(db.slots).where(db.slots.c.id == s["id"]).values(status="manque", asset_id=None))
        c.execute(update(db.assets).where(db.assets.c.id == a["id"], db.assets.c.status == "programme")
                  .values(status="banque"))
    journal.noter(par, "creneau_sans_publication", "slot", s["id"], s["brand_id"],
                  apres={"asset": a["id"], "ecartes": ecartes})


# ── Retouche et déclinaisons (cache : jamais deux fois la même image) ────
def _niveau(m: dict) -> str:
    return (m.get("kit") or {}).get("retouche", "complete")


def base_retouchee(a: dict, m: dict):
    """La photo corrigée et nettoyée, une fois pour toutes les déclinaisons :
    le nettoyage payant ne se paie qu'une fois par photo, pas par format.
    → (image, traitements)."""
    niveau = _niveau(m)
    parasites = (a["vision"] or {}).get("parasites") or []
    nett = nettoyage.nettoyeur() if niveau == "complete" and parasites else None
    source = a["blurred_path"] or a["original_path"]
    cle = stockage.cle_cache(a["sha256"], "base", images.VERSION_TRAITEMENTS, source, niveau,
                             nett.nom if nett else "")
    r = _rendu_en_cache(cle)
    if r:
        return images.ouvrir(stockage.chemin(r["path"])), list(r["treatments"] or [])
    img = images.ouvrir(stockage.chemin(source))
    img, faits = images.corriger(img, lumiere_seulement=(niveau == "lumiere"))
    if a["blurred_path"]:
        faits.insert(0, "visages et plaques floutés")
    if nett:
        try:
            img, effaces, laisses = nett.nettoyer(img, parasites)
            faits += [f"effacé : {x}" for x in effaces]
            if laisses:
                faits.append("laissé (trop grand pour l'effacement local) : " + ", ".join(laisses))
        except Exception as e:      # le service tousse : la photo part propre mais non nettoyée
            log.warning("nettoyage indisponible : %s", e)
            faits.append("nettoyage indisponible")
    rel = stockage.chemin_declinaison(a["id"], "base", cle)
    octets = images.enregistrer_jpeg(img, stockage.racine() / rel, 95)
    _ranger_rendu(a["id"], "base", rel, faits, cle, octets)
    return img, faits


def declinaison(a: dict, m: dict, fmt: str, en_video: bool = False, avec_logo: bool = True,
                variante: int = 0) -> dict:
    """→ {id, chemin, format, largeur, hauteur, poids_mo, video, duree, traitements, public_token}.
    `variante` 1 : un cadrage resserré sur le sujet (une photo qui ressort ne
    doit pas ressembler à sa première sortie)."""
    kit = m.get("kit") or {}
    carte = (a["vision"] or {}).get("carte") if a["kind"] == "carte" else None
    cle = stockage.cle_cache(a["sha256"], fmt, images.VERSION_TRAITEMENTS, m.get("kit_version", 1),
                             f"variante-{variante}" if variante else "",
                             a["blurred_path"] or "", _niveau(m), "logo" if avec_logo else "sans-logo",
                             "video" if en_video else "", json.dumps(carte, sort_keys=True) if carte else "",
                             json.dumps(kit, sort_keys=True, default=str))
    r = _rendu_en_cache(cle)
    if r is None:
        if carte:
            img = images.carte(kit, m["name"], carte.get("titre", ""), carte.get("sous_titre", ""),
                               carte.get("detail", ""), fmt, avec_logo)
            faits = ["carte typographique à la charte"]
        else:
            base, faits = base_retouchee(a, m)
            sujet = (a["vision"] or {}).get("sujet_boite")
            if variante:
                sujet = images.resserrer(sujet)
            img = images.recadrer(base, fmt, sujet)
            faits = faits + [f"recadrage {fmt} sur le sujet" + (" (cadrage resserré : nouvelle sortie)" if variante else "")]
            img, habillage = images.habiller(img, kit, m["name"], fmt, avec_logo)
            faits += habillage
        rel = stockage.chemin_declinaison(a["id"], fmt, cle, en_video)
        chemin = stockage.racine() / rel
        if en_video:
            images.enregistrer_jpeg(img, chemin.with_suffix(".jpg"), 92)   # l'image du clip, pour l'aperçu
            duree = video.clip(img, chemin)
            octets = chemin.read_bytes()
            faits = faits + [f"clip vertical de {duree:.0f} s (lent zoom)"]
        else:
            octets = images.enregistrer_jpeg(img, chemin, 90)
        r = _ranger_rendu(a["id"], fmt + ("v" if en_video else ""), rel, faits, cle, octets)
    return _info_rendu(r)


def _rendu_en_cache(cle: str):
    with db.moteur().begin() as c:
        r = db.ligne(c.execute(select(db.renditions).where(db.renditions.c.cache_key == cle)))
    if r and stockage.chemin(r["path"]).exists():
        return r
    return None


def _ranger_rendu(asset_id, fmt, rel, faits, cle, octets) -> dict:
    import hashlib
    vals = dict(asset_id=asset_id, format=fmt, path=str(rel), public_token=stockage.jeton_public(),
                treatments=faits, cache_key=cle, sha256=hashlib.sha256(octets).hexdigest(),
                created_at=db.maintenant())
    try:
        with db.moteur().begin() as c:
            existe = c.execute(select(db.renditions.c.id).where(db.renditions.c.cache_key == cle)).first()
            if existe:
                c.execute(update(db.renditions).where(db.renditions.c.id == existe[0]).values(
                    path=str(rel), treatments=faits, sha256=vals["sha256"]))
                rid = existe[0]
            else:
                rid = c.execute(insert(db.renditions).values(**vals)).inserted_primary_key[0]
    except IntegrityError:
        pass
    with db.moteur().begin() as c:
        return db.ligne(c.execute(select(db.renditions).where(db.renditions.c.cache_key == cle)))


def _info_rendu(r: dict) -> dict:
    chemin = stockage.chemin(r["path"])
    est_video = r["format"].endswith("v")
    if est_video:
        largeur, hauteur, duree = 1080, 1920, float(r.get("duration_s") or video.DUREE_S)
    else:
        from PIL import Image
        with Image.open(chemin) as im:
            largeur, hauteur = im.size
        duree = None
    return {"id": r["id"], "chemin": str(chemin), "format": r["format"], "largeur": largeur,
            "hauteur": hauteur, "poids_mo": chemin.stat().st_size / 1_000_000, "video": est_video,
            "duree": duree, "traitements": r["treatments"] or [], "public_token": r["public_token"],
            "sha256": r["sha256"]}


def url_media(r: dict) -> str:
    """Le nom public d'une déclinaison : un jeton qui ne se devine pas."""
    return f"{r['public_token']}.{'mp4' if r['format'].endswith('v') else 'jpg'}"


# ── 5. Publication ───────────────────────────────────────────────────────
def _publieur(p: dict, cpt: dict | None, forcer_reel: bool = False):
    cts = acces.contraintes()
    c = acces.contraintes_publieur(cts.get(p["platform"]), p["platform"])
    if p.get("simulated") and not forcer_reel:
        return BacASable(p["platform"], c)
    return publieurs.pour(cpt or {"platform": p["platform"], "mode": "agregateur"}, c, forcer_reel=forcer_reel)


@file.traitant("publier")
def publier(pl: dict):
    p = post(pl["post_id"])
    if not p or p["status"] != "programme":
        return
    m = acces.marque(p["brand_id"])
    if journal.arret_general():
        _suspendre(p, "arrêt général")
        return
    if acces.en_pause(m) or not m["active"]:
        _suspendre(p, f"mode crise : {m.get('crisis_reason') or 'crise'}" if m.get("crisis_since") else
                   f"marque en pause : {m.get('paused_reason') or 'pause 48 h'}")
        return
    bac = journal.bac_a_sable()
    cpt = acces.compte(m["id"], p["platform"])
    if not bac and (not cpt or cpt["status"] != "actif"):
        etat = (cpt or {}).get("status", "absent")
        _echec(p, f"compte {reseaux.NOMS.get(p['platform'])} {'en pause' if etat == 'pause' else 'pas relié'}")
        return
    c = acces.contraintes().get(p["platform"]) or {}
    if not bac and c.get("posts_per_day") and _sortis_24h(m["id"], p["platform"]) >= c["posts_per_day"]:
        raise file.Reessayer("plafond quotidien du réseau atteint", dans=dt.timedelta(hours=3))
    from . import conditions
    verdict = conditions.verifier(p)
    if verdict == "attendre":
        raise file.Reessayer("condition de publication pas encore mesurable", dans=dt.timedelta(hours=3))
    if verdict:
        _maj(db.posts, p["id"], status="annule", error=f"condition non remplie : {verdict}")
        journal.noter("systeme", "condition_non_remplie", "post", p["id"], m["id"], apres={"raison": verdict})
        return
    r = _un(db.renditions, p["rendition_id"])
    info = _info_rendu(r)
    lien = _un(db.links, p["link_id"]) if p["link_id"] else None
    prep = PostPrepare(post_id=p["id"], brand_id=m["id"], platform=p["platform"], text=p["text"],
                       title=p["title"] or "", media_url=f"{_url_publique()}/m/{url_media(r)}",
                       media_path=info["chemin"], is_video=info["video"],
                       link_url=mesure.url_courte(lien["code"]) if lien else "",
                       options={"cta": "ORDER" if m["sector"] == "food" else "LEARN_MORE"},
                       extra_paths=[_info_rendu(_un(db.renditions, x))["chemin"]
                                    for x in (p.get("extra_renditions") or [])])
    try:
        pub = BacASable(p["platform"], acces.contraintes_publieur(c, p["platform"])) if bac \
            else _publieur(p, cpt)
    except NonBranche as e:
        _echec(p, str(e))
        return
    _maj(db.posts, p["id"], status="envoi", attempts=p["attempts"] + 1, simulated=bac)
    try:
        res = pub.publish(prep)
    except PanneTransitoire as e:
        if p["attempts"] + 1 >= ESSAIS_PUBLICATION + 2:
            _echec(p, f"réseau injoignable après {p['attempts'] + 1} essais : {e}")
            return
        _maj(db.posts, p["id"], status="programme", error=str(e))
        raise file.Reessayer(str(e))
    except NonBranche as e:
        _echec(p, str(e))
        return
    except RefusReseau as e:
        en_pause = _compter_refus(m, cpt, str(e)) if not bac else False
        if p["attempts"] + 1 < ESSAIS_PUBLICATION and not en_pause:
            _maj(db.posts, p["id"], status="programme", error=str(e))
            raise file.Reessayer(str(e))
        _echec(p, str(e))
        return
    if res.raw.get("en_attente"):
        _maj(db.posts, p["id"], request_ref=res.raw.get("request_id", ""))
        file.ajouter("confirmer", {"post_id": p["id"]}, quand=db.maintenant() + dt.timedelta(minutes=2),
                     dedup=f"confirmer:{p['id']}", essais_max=40)
        return
    marquer_publie(p, res, bac, info, cpt)


def _url_publique() -> str:
    from . import config
    return config.url_publique()


def _sortis_24h(marque_id, plateforme) -> int:
    from sqlalchemy import func
    with db.moteur().begin() as c:
        return c.execute(select(func.count()).select_from(db.posts).where(
            db.posts.c.brand_id == marque_id, db.posts.c.platform == plateforme,
            db.posts.c.status == "publie",
            db.posts.c.published_at >= db.maintenant() - dt.timedelta(hours=24))).scalar_one()


def marquer_publie(p: dict, res, simule: bool, info: dict, cpt: dict | None):
    maintenant = db.maintenant()
    _maj(db.posts, p["id"], status="simule" if simule else "publie", simulated=simule,
         published_at=maintenant, external_id=res.external_id or "", permalink=res.permalink or "",
         sent_image_sha=info["sha256"], error="")
    if cpt and not simule:
        _maj(db.accounts, cpt["id"], consecutive_failures=0, last_error="", updated_at=maintenant)
    with db.moteur().begin() as c:
        c.execute(update(db.assets).where(db.assets.c.id == p["asset_id"]).values(status="publie"))
        if p["slot_id"]:
            c.execute(update(db.slots).where(db.slots.c.id == p["slot_id"]).values(status="publie"))
    # Le journal intégral : l'image exacte, le texte exact, le réseau, l'heure,
    # l'identifiant externe, le lien permanent, et ce qui l'a déclenchée.
    journal.noter("systeme", "publication_simulee" if simule else "publication", "post", p["id"], p["brand_id"],
                  apres={"reseau": p["platform"], "texte": p["text"], "titre": p["title"],
                         "image_sha256": info["sha256"], "image": info["chemin"].split("/declinaisons/")[-1],
                         "identifiant_externe": res.external_id, "lien_permanent": res.permalink,
                         "declencheur": p["trigger"], "asset": p["asset_id"], "modele": p["model"],
                         "prompt": p["prompt_version"], "avertissements": res.raw.get("warnings") or []})
    mesure.programmer_releves(p["id"], maintenant)


def _suspendre(p, raison):
    _maj(db.posts, p["id"], status="suspendu", error=raison)
    journal.noter("systeme", "publication_suspendue", "post", p["id"], p["brand_id"], apres={"raison": raison})


def _echec(p, raison):
    _maj(db.posts, p["id"], status="echec", error=raison[:2000])
    journal.noter("systeme", "publication_echec", "post", p["id"], p["brand_id"],
                  apres={"reseau": p["platform"], "raison": raison[:500]})


def _compter_refus(m: dict, cpt: dict | None, erreur: str) -> bool:
    """« Trois refus consécutifs d'un même réseau : ce réseau est mis en pause
    automatiquement, et alerte. Mieux vaut un réseau muet qu'un compte suspendu. »
    → True si le réseau vient d'être mis en pause."""
    if not cpt:
        return False
    with db.moteur().begin() as c:
        c.execute(update(db.accounts).where(db.accounts.c.id == cpt["id"]).values(
            consecutive_failures=db.accounts.c.consecutive_failures + 1, last_error=erreur[:2000],
            updated_at=db.maintenant()))
        n = c.execute(select(db.accounts.c.consecutive_failures).where(db.accounts.c.id == cpt["id"])).scalar_one()
    if n < REFUS_AVANT_PAUSE:
        return False
    _maj(db.accounts, cpt["id"], status="pause")
    nom = reseaux.NOMS.get(cpt["platform"], cpt["platform"])
    journal.noter("systeme", "reseau_en_pause", "account", cpt["id"], m["id"],
                  apres={"reseau": cpt["platform"], "refus": n, "derniere_erreur": erreur[:500]})
    alertes.alerter(f"{m['name']} : {nom} mis en pause après {n} refus", f"Dernière réponse du réseau :\n{erreur}\n\n"
                    "Plus rien ne part sur ce réseau tant qu'il n'est pas relancé (Réglages → comptes). "
                    "Les autres réseaux continuent.", marque=m["id"], niveau="panne", type_="reseau",
                    dedup=f"pause:{cpt['id']}")
    return True


# ── 6. Confirmation d'un envoi parti en arrière-plan ─────────────────────
@file.traitant("confirmer")
def confirmer(pl: dict):
    p = post(pl["post_id"])
    if not p or p["status"] != "envoi" or not p["request_ref"]:
        return
    cpt = acces.compte(p["brand_id"], p["platform"])
    pub = _publieur(p, cpt)
    if not hasattr(pub, "confirmer"):
        return
    try:
        res = pub.confirmer(p["request_ref"])
    except RefusReseau as e:
        _compter_refus(acces.marque(p["brand_id"]), cpt, str(e))
        _echec(p, str(e))
        return
    except PanneTransitoire as e:
        raise file.Reessayer(str(e))
    if res is None:
        if db.maintenant() - (p["scheduled_at"] or db.maintenant()) > dt.timedelta(hours=2):
            _echec(p, "l'agrégateur n'a jamais confirmé l'envoi")
            return
        raise file.Reessayer("envoi en cours chez l'agrégateur", dans=dt.timedelta(minutes=2))
    r = _un(db.renditions, p["rendition_id"])
    marquer_publie(p, res, False, _info_rendu(r), cpt)


# ── 7. Relevés ───────────────────────────────────────────────────────────
@file.traitant("mesurer")
def mesurer(pl: dict):
    p = post(pl["post_id"])
    if not p or p["status"] not in ("publie", "simule"):
        return
    cpt = acces.compte(p["brand_id"], p["platform"])
    try:
        pub = _publieur(p, cpt)
        m = pub.metrics(p["external_id"])
    except PanneTransitoire as e:
        raise file.Reessayer(str(e))
    except NonBranche:
        return
    mesure.enregistrer_mesures(p["id"], pl["jalon"], m)
    if pl["jalon"] in ("1h", "24h") and not m.simulated:
        from . import analyste
        analyste.emballement(p["id"])
    if pl["jalon"] == "7j" and not m.simulated:
        score = creneaux.score_engagement(vars(m))
        with db.moteur().begin() as c:
            c.execute(update(db.assets).where(db.assets.c.id == p["asset_id"], db.assets.c.score < score)
                      .values(score=score))


# ── Les gestes en un tap ─────────────────────────────────────────────────
def retirer_partout(asset_id: int, par: str) -> dict:
    """« Retirer cette publication partout » — en un clic. Ce qui est programmé
    est annulé ; ce qui est sorti est retiré là où le réseau le permet ; là où
    il ne le permet pas (Instagram, TikTok, Threads), on le DIT, avec le lien
    à ouvrir, au lieu de prétendre l'avoir fait."""
    a = asset(asset_id)
    if not a:
        raise ValueError("photo inconnue")
    with db.moteur().begin() as c:
        ps = db.lignes(c.execute(select(db.posts).where(db.posts.c.asset_id == asset_id)))
    rapport = {"annules": [], "retires": [], "a_la_main": [], "erreurs": []}
    for p in ps:
        nom = reseaux.NOMS.get(p["platform"], p["platform"])
        if p["status"] in ("programme", "a_valider", "suspendu", "preparation"):
            _maj(db.posts, p["id"], status="annule", error=f"retiré par {par}")
            rapport["annules"].append(nom)
        elif p["status"] in ("publie", "simule", "envoi"):
            try:
                pub = _publieur(p, acces.compte(p["brand_id"], p["platform"]), forcer_reel=not p["simulated"])
                fait = pub.delete(p["external_id"]) if p["external_id"] else False
            except Exception as e:
                rapport["erreurs"].append(f"{nom} : {e}")
                continue
            if fait:
                _maj(db.posts, p["id"], status="retire")
                rapport["retires"].append(nom)
            else:
                rapport["a_la_main"].append({"reseau": nom, "lien": p["permalink"]})
    with db.moteur().begin() as c:
        c.execute(update(db.assets).where(db.assets.c.id == asset_id).values(status="retire"))
        c.execute(update(db.slots).where(db.slots.c.asset_id == asset_id, db.slots.c.status.in_(("rempli",)))
                  .values(status="annule"))
    journal.noter(par, "retirer_partout", "asset", asset_id, a["brand_id"], apres=rapport)
    return rapport


def flouter(asset_id: int, par: str, boites: list | None = None) -> dict:
    """Le bouton « flouter » : visages et plaques, sur demande seulement.
    Les publications encore à venir repartent avec la version floutée."""
    a = asset(asset_id)
    if not a:
        raise ValueError("photo inconnue")
    img = images.ouvrir(stockage.chemin(a["original_path"]))
    if boites is None:
        boites = images.visages(img)
        lecture = a["vision"] or {}
        for b in (lecture.get("visages") or []) + (lecture.get("plaques") or []):
            box = b.get("box") if isinstance(b, dict) else None
            if box and len(box) == 4 and not any(images._recouvre(box, o) for o in boites):
                boites.append(box)
    if not boites:
        journal.noter(par, "flouter_rien", "asset", asset_id, a["brand_id"])
        return {"boites": 0, "reprogrammes": 0}
    flou = images.flouter(img, boites)
    rel = f"originaux/flou/{a['sha256'][:2]}/{a['sha256']}-{stockage.cle_cache(boites)[:10]}.jpg"
    images.enregistrer_jpeg(flou, stockage.racine() / rel, 95)
    _maj(db.assets, asset_id, blurred_path=rel)
    a = asset(asset_id)
    m = acces.marque(a["brand_id"])
    n = 0
    with db.moteur().begin() as c:
        ps = db.lignes(c.execute(select(db.posts).where(
            db.posts.c.asset_id == asset_id, db.posts.c.status.in_(("programme", "a_valider", "suspendu")))))
    deja_sortis = 0
    for p in ps:
        r = _un(db.renditions, p["rendition_id"])
        fmt = r["format"].rstrip("v")
        nouveau = declinaison(a, m, fmt, en_video=r["format"].endswith("v"),
                              avec_logo=acces.logo_permis(m, creneaux.paris(p["scheduled_at"])))
        _maj(db.posts, p["id"], rendition_id=nouveau["id"])
        n += 1
    with db.moteur().begin() as c:
        deja_sortis = len(c.execute(select(db.posts.c.id).where(
            db.posts.c.asset_id == asset_id, db.posts.c.status.in_(("publie", "simule")))).all())
    journal.noter(par, "flouter", "asset", asset_id, a["brand_id"],
                  apres={"boites": len(boites), "reprogrammes": n, "deja_sortis": deja_sortis})
    return {"boites": len(boites), "reprogrammes": n, "deja_sortis": deja_sortis}


def creer_carte(m: dict, titre: str, sous_titre: str = "", detail: str = "", pilier: str = "",
                par: str = "systeme") -> dict:
    """Un visuel 100 % charte quand il n'y a pas de photo (compte à rebours,
    annonce). Une carte n'est PAS une image générée par IA : du texte et les
    couleurs de la marque, rien d'autre."""
    img = images.carte(m.get("kit") or {}, m["name"], titre, sous_titre, detail, "4:5",
                       acces.logo_permis(m, None))
    tampon = io.BytesIO()
    img.save(tampon, "JPEG", quality=95)
    octets = tampon.getvalue()
    rel, sha = stockage.ranger_original(octets, "jpg")
    with db.moteur().begin() as c:
        deja = db.ligne(c.execute(select(db.assets).where(db.assets.c.brand_id == m["id"],
                                                          db.assets.c.sha256 == sha)))
    if deja:
        return deja
    lecture = {"sujet": titre, "type_contenu": "annonce", "pilier": pilier, "lieu_probable": m.get("zone", ""),
               "elements": [x for x in (sous_titre, detail) if x], "sujet_boite": [0, 0, 1, 1],
               "utilisabilite": 90, "visages": [], "plaques": [], "parasites": [], "logos_tiers": [],
               "document_confidentiel": "", "simule": False, "prompt_version": "carte",
               "carte": {"titre": titre, "sous_titre": sous_titre, "detail": detail}}
    with db.moteur().begin() as c:
        aid = c.execute(insert(db.assets).values(
            brand_id=m["id"], original_path=rel, sha256=sha, phash=images.empreinte(img),
            width=img.width, height=img.height, vision=lecture, vision_model="carte", usability=90,
            pillar=pilier, kind="carte", status="banque", created_at=db.maintenant())).inserted_primary_key[0]
    journal.noter(par, "carte", "asset", aid, m["id"], apres={"titre": titre, "sous_titre": sous_titre})
    return asset(aid)


def valider(post_id: int, par: str) -> dict:
    """Seulement pour une marque réglée « validation requise » (désactivé par défaut)."""
    p = post(post_id)
    if not p or p["status"] != "a_valider":
        raise ValueError("rien à valider")
    quand = max(p["scheduled_at"] or db.maintenant(), db.maintenant() + dt.timedelta(minutes=2))
    _maj(db.posts, post_id, status="programme", scheduled_at=quand)
    file.ajouter("publier", {"post_id": post_id}, quand=quand, dedup=f"publier:{post_id}", essais_max=10)
    journal.noter(par, "validation", "post", post_id, p["brand_id"])
    return post(post_id)


def reprendre(par: str, marque_id: str | None = None) -> int:
    """Après un arrêt général ou une pause : ce qui a été suspendu repart,
    à une heure future — jamais tout à la même minute."""
    q = select(db.posts).where(db.posts.c.status == "suspendu")
    if marque_id:
        q = q.where(db.posts.c.brand_id == marque_id)
    with db.moteur().begin() as c:
        ps = db.lignes(c.execute(q.order_by(db.posts.c.scheduled_at)))
    base = db.maintenant() + dt.timedelta(minutes=10)
    n = 0
    for i, p in enumerate(ps):
        if journal.arret_general():
            break
        m = acces.marque(p["brand_id"])
        if acces.en_pause(m):
            continue
        quand = p["scheduled_at"] if p["scheduled_at"] and p["scheduled_at"] > base else base + dt.timedelta(minutes=25 * i)
        _maj(db.posts, p["id"], status="programme", scheduled_at=quand, error="")
        file.ajouter("publier", {"post_id": p["id"]}, quand=quand, dedup=f"publier:{p['id']}:{quand:%Y%m%d%H%M}",
                     essais_max=10)
        n += 1
    journal.noter(par, "reprise", "marque" if marque_id else "tout", marque_id or "*", marque_id,
                  apres={"reprogrammes": n})
    return n
