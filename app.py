"""ALMA SOCIAL — l'application web : l'écran du téléphone, l'API, les liens tracés.

    python -m uvicorn app:app --port 8002

Trois sortes de routes :
  · l'écran (`/`, `/static/…`) et son API (`/api/…`), derrière un code personnel ;
  · les routes PUBLIQUES qui font marcher la mesure : `/go/<code>` (lien tracé),
    `/c/<code>` (le choix Uber Eats / Deliveroo de SAZÚ), `/b/<marque>` (lien en
    bio), `/s/marqueur.js` et `/api/leads/web` (les formulaires des sites), `/m/…`
    (les images que l'agrégateur vient chercher, derrière un jeton imprévisible) ;
  · le webhook d'Upload-Post, signé.

Le cloisonnement tient en une règle : toute route qui touche une marque passe
par `_voir()`, qui demande à `securite.peut_voir`. Le PDG voit tout ; un
responsable ne voit que sa marque — une autre lui répond 404, pas 403 : on ne
lui confirme même pas qu'elle existe.
"""
from __future__ import annotations

import contextlib
import csv
import datetime as dt
import html
import io
import json
import logging
import time
import uuid

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse,
                               Response, StreamingResponse)
from fastapi.staticfiles import StaticFiles
from sqlalchemy import desc, func, select, update

from alma_social import (ab, acces, agents, analyste, carnet, conversions, crise, demandes_avis, lecture_avis, maps,
                         qualification, assistant, critique, ia, marque as marque_, pilotage, repetition, studio, voix, coach, conditions, recyclage, temps_forts, alertes, campagnes, config, creneaux, db, file, graines, horloge, images, journal,
                         mesure, pipeline, planificateur, rapport, relation, reseaux, securite, stockage)
from alma_social.publieurs import upload_post
from alma_social.publieurs.base import ErreurPublication

log = logging.getLogger("alma_social.app")
VERSION = "1.0.0"
COOKIE = "alma_social"

# ── Démarrage ────────────────────────────────────────────────────────────
def _demarrer():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    panne = stockage.verifier_le_montage()
    if panne:
        log.critical("DISQUE : %s", panne)
        raise RuntimeError(panne)
    graines.semer()
    for m in acces.marques():
        if not planificateur.plan_du_mois(m["id"], acces.aujourdhui().year, acces.aujourdhui().month):
            planificateur.demarrer(m, "demarrage")
    if config.horloge_active():
        horloge.demarrer()
    log.info("ALMA SOCIAL %s prêt — bac à sable %s, arrêt général %s", VERSION,
             "OUVERT" if journal.bac_a_sable() else "fermé", "ACTIF" if journal.arret_general() else "non")


@contextlib.asynccontextmanager
async def _vie(_app):
    _demarrer()
    yield
    horloge.arreter()


app = FastAPI(title="ALMA SOCIAL", docs_url=None, redoc_url=None, openapi_url=None, lifespan=_vie)


# Les portes que des machines extérieures appellent : chacune porte sa propre
# garde (rien à lire pour le formulaire, signature HMAC, jeton du fournisseur).
PORTES_EXTERIEURES = ("/api/leads/web", "/api/conversions", "/api/appels/entrant", "/api/avis/evenement")


@app.middleware("http")
async def _entetes(request: Request, appel):
    """Les écritures de l'API exigent l'en-tête `X-Alma` : un formulaire d'un
    autre site ne peut pas le poser (CSRF), notre écran le pose toujours."""
    if request.method in ("POST", "PUT", "DELETE") and request.url.path.startswith("/api/") \
            and not request.url.path.startswith(PORTES_EXTERIEURES) and request.headers.get("x-alma") != "1":
        return JSONResponse({"erreur": "requête refusée"}, status_code=403)
    reponse = await appel(request)
    reponse.headers.setdefault("X-Content-Type-Options", "nosniff")
    reponse.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return reponse


def _ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "")


# ── Qui est là ───────────────────────────────────────────────────────────
def _moi(request: Request) -> dict:
    u = securite.session(request.cookies.get(COOKIE, ""))
    if not u:
        raise HTTPException(401, "Session expirée : retapez votre code.")
    return u


def _pdg(u: dict):
    if u["role"] != "pdg":
        raise HTTPException(403, "Réservé au PDG.")


def _voir(u: dict, marque_id: str) -> dict:
    m = acces.marque(marque_id) if marque_id else None
    if not m or not securite.peut_voir(u, marque_id):
        raise HTTPException(404, "Marque inconnue.")
    return m


def _qui(u: dict) -> str:
    return u.get("name") or f"utilisateur {u.get('id')}"


def _iso(v):
    if isinstance(v, dt.datetime):
        return creneaux.paris(v).isoformat(timespec="minutes")
    if isinstance(v, dt.date):
        return v.isoformat()
    return v


def _json(obj, code: int = 200):
    return JSONResponse(json.loads(json.dumps(obj, default=_iso, ensure_ascii=False)), status_code=code)


@app.exception_handler(HTTPException)
def _erreur(request: Request, e: HTTPException):
    return JSONResponse({"erreur": e.detail}, status_code=e.status_code)


@app.exception_handler(ValueError)
def _erreur_valeur(request: Request, e: ValueError):
    return JSONResponse({"erreur": str(e)}, status_code=400)


# ── Connexion ────────────────────────────────────────────────────────────
@app.post("/api/connexion")
async def connexion(request: Request):
    ip = _ip(request)
    if securite.trop_d_essais(ip):
        raise HTTPException(429, "Trop d'essais. Réessayez dans quelques minutes.")
    corps = await request.json()
    u = securite.identifier(str(corps.get("code", "")).strip())
    securite.noter_essai(ip, bool(u))
    if not u:
        raise HTTPException(401, "Code inconnu.")
    jeton = securite.ouvrir_session(u["id"])
    journal.noter(_qui(u), "connexion", "user", u["id"])
    r = _json({"ok": True})
    r.set_cookie(COOKIE, jeton, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 60,
                 secure=config.url_publique().startswith("https"))
    return r


@app.post("/api/deconnexion")
def deconnexion(request: Request):
    securite.fermer_session(request.cookies.get(COOKIE, ""))
    r = _json({"ok": True})
    r.delete_cookie(COOKIE)
    return r


def _fiche_marque(m: dict) -> dict:
    coul = images.couleurs(m.get("kit") or {})
    hexa = lambda t: "#%02x%02x%02x" % t
    cpts = acces.comptes(m["id"])
    return {"id": m["id"], "nom": m["name"], "secteur": m["sector"],
            "couleur": hexa(coul["primaire"]), "fond": hexa(coul["fond"]), "accent": hexa(coul["accent"]),
            "logo": f"/logo/{m['id']}" if (m.get("kit") or {}).get("logo") else "",
            "en_pause": acces.en_pause(m), "pause_jusqua": m.get("paused_until"),
            "pause_raison": m.get("paused_reason"), "validation": bool(m.get("requires_approval")),
            "crise": bool(m.get("crisis_since")), "crise_depuis": m.get("crisis_since"),
            "crise_raison": m.get("crisis_reason"), "crise_brouillon": m.get("crisis_draft") or "",
            "piliers": [{"cle": p["key"], "nom": p["label"], "photo": p.get("photo", "")}
                        for p in m.get("pillars") or []],
            "reseaux": [{"cle": c["platform"], "nom": reseaux.NOMS.get(c["platform"], c["platform"]),
                         "etat": c["status"], "poignee": c["handle"]} for c in cpts],
            "a_completer": m.get("todo") or []}


@app.get("/api/moi")
def moi(request: Request):
    u = _moi(request)
    ids = securite.marques_de(u)
    ms = [m for m in acces.marques(actives_seulement=False) if m["id"] in ids]
    # Les boutons dans un ordre stable : SAZÚ en dernier n'aurait aucun sens
    # pour la responsable SAZÚ ; on garde l'ordre alphabétique des noms.
    return _json({"utilisateur": {"nom": u["name"], "role": u["role"]},
                  "marques": [_fiche_marque(m) for m in ms],
                  "bac_a_sable": journal.bac_a_sable(), "arret_general": journal.arret_general(),
                  "horloge": horloge.vivante(), "version": VERSION})


@app.get("/logo/{marque_id}")
def logo(marque_id: str, request: Request):
    u = _moi(request)
    m = _voir(u, marque_id)
    chemin = (m.get("kit") or {}).get("logo")
    p = (config.GRAINES / chemin) if chemin else None
    if not p or not p.exists():
        raise HTTPException(404, "Pas de logo.")
    return FileResponse(p, headers={"Cache-Control": "private, max-age=86400"})


# ── Le dépôt ─────────────────────────────────────────────────────────────
@app.post("/api/depot")
async def depot(request: Request, marque: str = Form(...), pilier: str = Form(""), note: str = Form(""),
                photos: list[UploadFile] = File(...), refs: list[str] = Form(default=[])):
    """Une ou plusieurs photos, une marque. Chaque fichier a sa référence
    (posée par le téléphone) : un renvoi après une coupure ne crée rien."""
    u = _moi(request)
    m = _voir(u, marque)
    out = []
    for i, f in enumerate(photos):
        ref = refs[i] if i < len(refs) and refs[i] else None
        octets = await f.read()
        try:
            a = pipeline.recevoir(m["id"], octets, f.filename or "", client_ref=ref, auteur=u, pilier=pilier,
                                  note=note)
            out.append({"ref": ref, "id": a["id"], "deja": bool(a.get("deja")), "ok": True})
        except ValueError as e:
            out.append({"ref": ref, "ok": False, "erreur": str(e)})
    return _json({"resultats": out})


_ETATS = {"recu": "Reçue — lecture en cours", "banque": "En banque : elle sortira au prochain créneau libre",
          "programme": "Programmée", "publie": "Publiée", "refuse": "Écartée", "quarantaine": "Mise de côté",
          "retire": "Retirée partout", "studio": "Dans un montage du studio (Reel et carrousel)",
          "decoupage": "Vidéo reçue — découpage en clips en cours",
          "decoupee": "Vidéo découpée : ses clips sont en banque, chacun avec son image"}
_ETATS_POST = {"preparation": "en préparation", "programme": "programmée", "a_valider": "à valider",
               "envoi": "en cours d'envoi", "publie": "publiée", "simule": "simulée (bac à sable)",
               "suspendu": "suspendue", "echec": "échec", "refuse": "texte refusé", "retire": "retirée",
               "annule": "annulée"}


def _vue_photo(a: dict, posts: list) -> dict:
    etat = _ETATS.get(a["status"], a["status"])
    if a["status"] in ("refuse", "quarantaine") and a["refusal_reason"]:
        etat += f" : {a['refusal_reason']}"
    lecture = a.get("vision") or {}
    return {"id": a["id"], "marque": a["brand_id"], "etat": etat, "statut": a["status"], "sorte": a["kind"],
            "depose_le": a["created_at"], "pilier": a["pillar"], "sujet": lecture.get("sujet", ""),
            "simule": bool(lecture.get("simule")), "vignette": f"/api/photo/{a['id']}/vignette",
            "floutee": bool(a.get("blurred_path")),
            "publications": [{"id": p["id"], "reseau": reseaux.NOMS.get(p["platform"], p["platform"]),
                              "cle": p["platform"], "etat": _ETATS_POST.get(p["status"], p["status"]),
                              "statut": p["status"], "quand": p["published_at"] or p["scheduled_at"],
                              "lien": p["permalink"], "erreur": p["error"] if p["status"] in ("echec", "refuse", "suspendu") else "",
                              "texte": p["text"], "apercu": f"/apercu/{p['id']}" if p["rendition_id"] else "",
                              "format": p.get("post_format") or "image"}
                             for p in posts]}


@app.get("/api/photos")
def photos(request: Request, marque: str = "", limite: int = 40):
    """« Qu'est-il arrivé à mes photos ? » — les dernières, et ce qu'elles sont devenues."""
    u = _moi(request)
    ids = [marque] if marque else securite.marques_de(u)
    for i in ids:
        _voir(u, i)
    with db.moteur().begin() as c:
        assets = db.lignes(c.execute(select(db.assets).where(db.assets.c.brand_id.in_(ids))
                                     .order_by(desc(db.assets.c.created_at)).limit(min(limite, 200))))
        posts = db.lignes(c.execute(select(db.posts).where(db.posts.c.asset_id.in_([a["id"] for a in assets]))
                                    .order_by(db.posts.c.scheduled_at)))
    par = {}
    for p in posts:
        par.setdefault(p["asset_id"], []).append(p)
    return _json({"photos": [_vue_photo(a, par.get(a["id"], [])) for a in assets]})


def _asset_visible(u, asset_id: int) -> dict:
    a = pipeline.asset(asset_id)
    if not a or not securite.peut_voir(u, a["brand_id"]):
        raise HTTPException(404, "Photo inconnue.")
    return a


@app.get("/api/photo/{asset_id}/vignette")
def vignette(asset_id: int, request: Request):
    u = _moi(request)
    a = _asset_visible(u, asset_id)
    rel = a.get("blurred_path") or a["original_path"]
    cle = stockage.cle_cache("vignette", rel)
    chemin = stockage.racine() / "vignettes" / f"{cle}.jpg"
    if not chemin.exists():
        if a["kind"] == "video":
            from alma_social import clips
            duree = (a.get("exif") or {}).get("duree_s") or 2
            img = images.ouvrir(clips.image_a(stockage.chemin(rel), min(1.0, duree / 2)))
        else:
            img = images.ouvrir(stockage.chemin(rel))
        img.thumbnail((480, 480))
        images.enregistrer_jpeg(img, chemin, 82)
    return FileResponse(chemin, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@app.post("/api/photo/{asset_id}/retirer")
def retirer(asset_id: int, request: Request):
    u = _moi(request)
    _asset_visible(u, asset_id)
    return _json(pipeline.retirer_partout(asset_id, _qui(u)))


@app.post("/api/photo/{asset_id}/flouter")
def flouter(asset_id: int, request: Request):
    u = _moi(request)
    _asset_visible(u, asset_id)
    return _json(pipeline.flouter(asset_id, _qui(u)))


@app.get("/apercu/{post_id}")
def apercu(post_id: int, request: Request):
    """L'image exacte qui part (ou est partie) sur ce réseau."""
    u = _moi(request)
    p = pipeline.post(post_id)
    if not p or not securite.peut_voir(u, p["brand_id"]) or not p["rendition_id"]:
        raise HTTPException(404, "Aperçu indisponible.")
    r = pipeline._un(db.renditions, p["rendition_id"])
    chemin = stockage.chemin(r["path"])
    # Un Reel : l'aperçu en <img> montre sa couverture ; `?video=1` rend la vidéo.
    couverture = chemin.with_suffix(".jpg")
    if chemin.suffix == ".mp4" and couverture.exists() and request.query_params.get("video") != "1":
        chemin = couverture
    return FileResponse(chemin, headers={"Cache-Control": "private, max-age=3600"})


# ── Les médias publics, pour l'agrégateur ────────────────────────────────
@app.get("/m/{nom}")
def media(nom: str):
    """`/m/<jeton>.jpg` : le jeton (32 caractères aléatoires) EST la permission.
    Il ne dit rien de la marque ni de la photo, et ne se devine pas."""
    jeton = nom.rsplit(".", 1)[0]
    with db.moteur().begin() as c:
        r = db.ligne(c.execute(select(db.renditions).where(db.renditions.c.public_token == jeton)))
    if not r:
        raise HTTPException(404, "Introuvable.")
    chemin = stockage.chemin(r["path"])
    if nom.endswith(".jpg") and chemin.suffix == ".mp4" and chemin.with_suffix(".jpg").exists():
        chemin = chemin.with_suffix(".jpg")         # la couverture d'un Reel (poster, vignette)
    if not chemin.exists():
        raise HTTPException(404, "Introuvable.")
    return FileResponse(chemin, headers={"Cache-Control": "public, max-age=604800"})


# ── Les gestes de pilotage ───────────────────────────────────────────────
@app.post("/api/arret")
async def arret(request: Request):
    """Le bouton STOP général : plus rien ne part, nulle part, tant qu'on ne relance pas."""
    u = _moi(request)
    _pdg(u)
    actif = bool((await request.json()).get("actif"))
    journal.ecrire("arret_general", actif, par=_qui(u))
    repris = 0
    if not actif:
        repris = pipeline.reprendre(_qui(u))
    else:
        alertes.alerter("Arrêt général activé", f"Par {_qui(u)}. Plus rien ne part tant qu'il n'est pas levé.",
                        niveau="info", type_="arret")
    return _json({"arret_general": actif, "repris": repris})


@app.post("/api/bac-a-sable")
async def bac_a_sable(request: Request):
    """Ouvrir les vannes (ou les refermer). Le geste est au journal."""
    u = _moi(request)
    _pdg(u)
    ouvert = bool((await request.json()).get("ouvert"))
    journal.ecrire("bac_a_sable", ouvert, par=_qui(u))
    return _json({"bac_a_sable": ouvert})


@app.post("/api/marque/{marque_id}/pause")
async def pause(marque_id: str, request: Request):
    """« Pause 48 h » : rien ne part pour cette marque, et rien ne repart sans une action."""
    u = _moi(request)
    m = _voir(u, marque_id)
    try:
        corps = await request.json()
    except ValueError:
        corps = {}
    return _json(pilotage.pause(m, _qui(u), 48, corps.get("raison") or ""))


@app.post("/api/marque/{marque_id}/reprendre")
def reprendre(marque_id: str, request: Request):
    u = _moi(request)
    return _json(pilotage.reprendre(_voir(u, marque_id), _qui(u)))


@app.post("/api/carte")
async def carte(request: Request):
    """Une carte à la charte quand il n'y a pas de photo (annonce, compte à rebours)."""
    u = _moi(request)
    c = await request.json()
    m = _voir(u, c.get("marque", ""))
    titre = (c.get("titre") or "").strip()
    if not titre:
        raise HTTPException(400, "Il faut au moins un titre.")
    a = pipeline.creer_carte(m, titre[:40], (c.get("sous_titre") or "")[:120], (c.get("detail") or "")[:80],
                             c.get("pilier") or "", par=_qui(u))
    s = planificateur.creneau_pour(m, a)
    if s:
        pipeline.attacher(s, a, _qui(u))
    return _json({"id": a["id"], "place": bool(s)})


@app.post("/api/valider/{post_id}")
def valider(post_id: int, request: Request):
    """N'existe que pour une marque réglée « validation requise » — aucune ne l'est par défaut."""
    u = _moi(request)
    p = pipeline.post(post_id)
    if not p or not securite.peut_voir(u, p["brand_id"]):
        raise HTTPException(404, "Publication inconnue.")
    return _json(pipeline.valider(post_id, _qui(u)))


# ── Le calendrier ────────────────────────────────────────────────────────
@app.get("/api/calendrier")
def calendrier(request: Request, marque: str, mois: str = ""):
    u = _moi(request)
    m = _voir(u, marque)
    j = acces.aujourdhui()
    annee, mo = (int(mois[:4]), int(mois[5:7])) if mois else (j.year, j.month)
    debut = dt.date(annee, mo, 1)
    fin = (dt.date(annee + (mo == 12), mo % 12 + 1, 1)) - dt.timedelta(days=1)
    creneaux_ = planificateur.creneaux_de(m["id"], debut, fin)
    with db.moteur().begin() as c:
        posts = db.lignes(c.execute(select(db.posts).where(db.posts.c.slot_id.in_([s["id"] for s in creneaux_]))))
    par = {}
    for p in posts:
        par.setdefault(p["slot_id"], []).append({"reseau": reseaux.NOMS.get(p["platform"]), "etat": p["status"],
                                                 "quand": p["scheduled_at"], "id": p["id"]})
    plan = planificateur.plan_du_mois(m["id"], annee, mo)
    suivant = planificateur.plan_du_mois(m["id"], *planificateur.mois_suivant(j))
    return _json({"mois": f"{annee:04d}-{mo:02d}", "creneaux": [
        {"id": s["id"], "jour": s["day"], "heure": s["time"], "pilier": (acces.pilier(m, s["pillar"]) or {}).get("label", ""),
         "sujet": s["topic"], "source": s["source"], "etape": s["campaign_step"], "statut": s["status"],
         "photo": f"/api/photo/{s['asset_id']}/vignette" if s["asset_id"] else "", "publications": par.get(s["id"], [])}
        for s in creneaux_], "plan": plan, "plan_suivant": suivant, "stock": planificateur.stock(m)})


@app.get("/api/moments")
def moments(request: Request, marque: str):
    """Quand publier et avec quoi : les sept meilleurs créneaux de chaque
    réseau relié (appris sur la marque quand il y a assez de mesures), ce que
    la banque garde en réserve, et les temps forts des deux mois à venir."""
    u = _moi(request)
    m = _voir(u, marque)
    profils = mesure.profils(m["id"])
    pfs = [c["platform"] for c in acces.comptes(m["id"]) if c["platform"] in reseaux.NOMS]
    j = acces.aujourdhui()
    return _json({
        "reseaux": [{"cle": pf, "nom": reseaux.NOMS.get(pf, pf), "appris": bool(profils.get(pf)),
                     "creneaux": creneaux.sept_meilleurs(m.get("sector") or "", pf, profils.get(pf))}
                    for pf in dict.fromkeys(pfs)],
        "exploration": round(creneaux.PART_EXPLORATION * 100),
        "banque": {**recyclage.etat([m["id"]])[m["id"]], **planificateur.stock(m)},
        "temps_forts": temps_forts.a_venir(m["id"], j, j + dt.timedelta(days=60)),
        "a_confirmer": temps_forts.a_confirmer()})


@app.post("/api/plan/{plan_id}/valider")
def valider_plan(plan_id: int, request: Request):
    """Valider le calendrier proposé le 25. Sans validation, il s'applique quand même le 1er."""
    u = _moi(request)
    with db.moteur().begin() as c:
        plan = db.ligne(c.execute(select(db.plans).where(db.plans.c.id == plan_id)))
    if not plan or not securite.peut_voir(u, plan["brand_id"]):
        raise HTTPException(404, "Plan inconnu.")
    return _json(planificateur.valider(plan_id, _qui(u)))


@app.get("/api/series")
def series(request: Request, marque: str):
    u = _moi(request)
    m = _voir(u, marque)
    with db.moteur().begin() as c:
        return _json({"series": db.lignes(c.execute(select(db.series).where(db.series.c.brand_id == m["id"])))})


@app.post("/api/series")
async def creer_serie(request: Request):
    """Un rendez-vous fixe (« Chaud devant », le mardi à 11 h 15)."""
    u = _moi(request)
    c_ = await request.json()
    m = _voir(u, c_.get("marque", ""))
    jour = int(c_.get("jour", -1))
    if not 0 <= jour <= 6 or not (c_.get("nom") or "").strip():
        raise HTTPException(400, "Un nom et un jour de la semaine.")
    heure = (c_.get("heure") or "")[:5]
    if heure and not (len(heure) == 5 and heure[2] == ":"):
        raise HTTPException(400, "L'heure s'écrit HH:MM.")
    from sqlalchemy import insert
    with db.moteur().begin() as c:
        sid = c.execute(insert(db.series).values(
            brand_id=m["id"], label=c_["nom"].strip()[:120], weekday=jour, time=heure,
            platforms=[r for r in c_.get("reseaux") or [] if r in (m.get("active_platforms") or [])],
            pillar=c_.get("pilier") or "", tags=[], active=True,
            starts_on=dt.date.fromisoformat(c_["debut"]) if c_.get("debut") else None)).inserted_primary_key[0]
    journal.noter(_qui(u), "serie", "series", sid, m["id"], apres=c_)
    return _json({"id": sid})


@app.post("/api/series/{serie_id}/arreter")
def arreter_serie(serie_id: int, request: Request):
    u = _moi(request)
    with db.moteur().begin() as c:
        se = db.ligne(c.execute(select(db.series).where(db.series.c.id == serie_id)))
        if not se or not securite.peut_voir(u, se["brand_id"]):
            raise HTTPException(404, "Rendez-vous inconnu.")
        c.execute(update(db.series).where(db.series.c.id == serie_id).values(active=False))
    journal.noter(_qui(u), "serie_arretee", "series", serie_id, se["brand_id"])
    return _json({"ok": True})


@app.get("/api/campagnes")
def liste_campagnes(request: Request):
    u = _moi(request)
    ids = set(securite.marques_de(u))
    with db.moteur().begin() as c:
        tout = db.lignes(c.execute(select(db.campaigns).order_by(desc(db.campaigns.c.start))))
    return _json({"campagnes": [ca for ca in tout if set(ca["brand_ids"] or []) & ids],
                  "sortes": list(campagnes.ETAPES)})


@app.post("/api/campagnes")
async def creer_campagne(request: Request):
    """Le coup de pub : un événement, des marques, une période — les étapes par défaut suivent."""
    u = _moi(request)
    c_ = await request.json()
    mids = c_.get("marques") or []
    for mid in mids:
        _voir(u, mid)
    if not mids or not (c_.get("nom") or "").strip():
        raise HTTPException(400, "Un nom et au moins une marque.")
    ev = dt.datetime.fromisoformat(c_["evenement"]).replace(tzinfo=creneaux.PARIS) if c_.get("evenement") else None
    debut = dt.date.fromisoformat(c_.get("debut") or acces.aujourdhui().isoformat())
    fin = dt.date.fromisoformat(c_.get("fin") or ((ev.date() if ev else debut) + dt.timedelta(days=3)).isoformat())
    ca = campagnes.creer(c_["nom"].strip()[:200], mids, c_.get("sorte") or "evenement", ev, debut, fin,
                         c_.get("reseaux") or None, c_.get("brief") or "", None, par=_qui(u))
    return _json(ca)


@app.post("/api/campagnes/{cid}/annuler")
def annuler_campagne(cid: int, request: Request):
    u = _moi(request)
    ca = campagnes.campagne(cid)
    if not ca or not all(securite.peut_voir(u, mid) for mid in ca["brand_ids"] or []):
        raise HTTPException(404, "Campagne inconnue.")
    return _json({"creneaux_annules": campagnes.annuler(cid, _qui(u))})


def _campagne_visible(u: dict, cid: int) -> dict:
    ca = campagnes.campagne(cid)
    if not ca or not all(securite.peut_voir(u, mid) for mid in ca["brand_ids"] or []):
        raise HTTPException(404, "Campagne inconnue.")
    return ca


@app.post("/api/campagnes/{cid}/repetition")
def repeter_campagne(cid: int, request: Request):
    """La répétition générale : chaque étape rendue (visuel, textes, heure),
    rien de publié, rien de programmé."""
    u = _moi(request)
    _campagne_visible(u, cid)
    return _json(_vue_repetition(repetition.repeter(cid, _qui(u))))


@app.get("/api/campagnes/{cid}/repetition")
def derniere_repetition(cid: int, request: Request):
    u = _moi(request)
    _campagne_visible(u, cid)
    r = repetition.derniere(cid)
    return _json(_vue_repetition(r) if r else {"etapes": [], "campagne": campagnes.campagne(cid)})


def _vue_repetition(r: dict) -> dict:
    for e in r["etapes"]:
        e["visuel"] = {"source": e["visuel"]["source"],
                       "url": f"/api/repetitions/{r['id']}/{e['slot_id']}.jpg"}
    return r


@app.get("/api/repetitions/{rid}/{nom}")
def visuel_repetition(rid: int, nom: str, request: Request):
    u = _moi(request)
    with db.moteur().connect() as c:
        r = db.ligne(c.execute(select(db.rehearsals).where(db.rehearsals.c.id == rid)))
    if not r:
        raise HTTPException(404, "Introuvable.")
    _campagne_visible(u, r["campaign_id"])
    e = next((x for x in r["etapes"] if f"{x['slot_id']}.jpg" == nom), None)
    if not e:
        raise HTTPException(404, "Introuvable.")
    return FileResponse(stockage.chemin(e["visuel"]["chemin"]), headers={"Cache-Control": "private, max-age=86400"})


# ── Le coach terrain ─────────────────────────────────────────────────────
@app.get("/api/coach")
def brief_coach(request: Request, marque: str = ""):
    """Ce qu'il faut photographier cette semaine, marque par marque — et comment."""
    u = _moi(request)
    ids = [marque] if marque else securite.marques_de(u)
    for mid in ids:
        _voir(u, mid)
    return _json({"briefs": coach.briefs(ids)})


# ── Le studio ────────────────────────────────────────────────────────────
@app.get("/api/studio")
def liste_studio(request: Request, marque: str = ""):
    u = _moi(request)
    ids = [marque] if marque else securite.marques_de(u)
    for mid in ids:
        _voir(u, mid)
    return _json({"travaux": studio.travaux(ids), "types": ["reel", "carrousel", "avant_apres", "rideau", "declinaison"],
                  "declinaisons": [{"cle": k, "nom": n, "taille": f"{t[0]}×{t[1]}"} for k, n, t, _ in studio.DECLINAISONS]})


@app.post("/api/studio")
async def fabriquer_studio(request: Request):
    """Un montage à la demande : des photos de la marque → Reel, carrousel,
    avant/après. Le fond studio n'est permis qu'à une marque produit."""
    u = _moi(request)
    c_ = await request.json()
    m = _voir(u, c_.get("marque") or "")
    photos = [int(x) for x in (c_.get("photos") or [])][:10]
    for aid in photos:
        a = _asset_visible(u, aid)
        if a["brand_id"] != m["id"]:
            raise HTTPException(400, "Toutes les photos doivent être de la même marque.")
    if not photos:
        raise HTTPException(400, "Choisissez au moins une photo.")
    p = {k: c_[k] for k in ("accroche", "phrases", "titre", "legendes", "cta", "studio") if k in c_}
    return _json(studio.fabriquer(c_.get("type") or "carrousel", m["id"], photos, p, par=_qui(u)))


# ── La relation ──────────────────────────────────────────────────────────
@app.get("/api/boite")
def boite(request: Request, marque: str = ""):
    u = _moi(request)
    ids = [_voir(u, marque)["id"]] if marque else securite.marques_de(u)
    return _json({"messages": relation.boite(ids), "delais": relation.delais(ids),
                  "prospects": _prospects(ids, 20),
                  "crises": [m["id"] for m in acces.marques() if m["id"] in ids and m.get("crisis_since")]})


def _prospects(ids: list, limite: int = 50) -> list:
    with db.moteur().connect() as c:
        lids = [r[0] for r in c.execute(select(db.leads.c.id).where(
            db.leads.c.brand_id.in_(ids), db.leads.c.temperature != "").order_by(desc(db.leads.c.id)).limit(limite))]
    return [qualification.charge_utile(i) for i in lids]


@app.post("/api/boite/{conv_id}/traite")
def message_traite(conv_id: int, request: Request):
    """« Réglé » : appelé au téléphone, vu en boutique — il sort de la liste."""
    u = _moi(request)
    with db.moteur().begin() as c:
        cv = db.ligne(c.execute(select(db.conversations).where(db.conversations.c.id == conv_id)))
    if not cv or not securite.peut_voir(u, cv["brand_id"]):
        raise HTTPException(404, "Message inconnu.")
    return _json({"ok": relation.traiter(conv_id, _qui(u))})


@app.get("/api/prospects.csv")
def prospects_csv(request: Request, marque: str = ""):
    u = _moi(request)
    ids = [_voir(u, marque)["id"]] if marque else securite.marques_de(u)
    return Response(qualification.export_csv(ids), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="prospects.csv"'})


@app.post("/api/boite/{conv_id}/repondre")
async def repondre(conv_id: int, request: Request):
    u = _moi(request)
    with db.moteur().begin() as c:
        cv = db.ligne(c.execute(select(db.conversations).where(db.conversations.c.id == conv_id)))
    if not cv or not securite.peut_voir(u, cv["brand_id"]):
        raise HTTPException(404, "Message inconnu.")
    texte = ((await request.json()).get("texte") or "").strip()
    if not texte:
        raise HTTPException(400, "La réponse est vide.")
    if cv.get("reply") and cv["reply"].strip() != texte:
        voix.noter_correction(cv["brand_id"], "reponse", cv["reply"], texte, _qui(u))   # la voix apprend
    return _json({"ok": relation.repondre(conv_id, texte, par=_qui(u))})


@app.get("/api/avis")
def avis(request: Request, marque: str = ""):
    u = _moi(request)
    ids = [_voir(u, marque)["id"]] if marque else securite.marques_de(u)
    with db.moteur().begin() as c:
        lignes = db.lignes(c.execute(select(db.reviews).where(db.reviews.c.brand_id.in_(ids))
                                     .order_by(desc(db.reviews.c.received_at)).limit(200)))
    return _json({"avis": lignes, "notes": {i: relation.note_moyenne(i) for i in ids}})


@app.post("/api/avis/{avis_id}/repondre")
async def repondre_avis(avis_id: int, request: Request):
    """Pour un avis de 3 étoiles ou moins : on relit le brouillon, on l'envoie."""
    u = _moi(request)
    with db.moteur().begin() as c:
        r = db.ligne(c.execute(select(db.reviews).where(db.reviews.c.id == avis_id)))
    if not r or not securite.peut_voir(u, r["brand_id"]):
        raise HTTPException(404, "Avis inconnu.")
    texte = ((await request.json()).get("texte") or r["draft"] or "").strip()
    if not texte:
        raise HTTPException(400, "La réponse est vide.")
    if r.get("draft") and r["draft"].strip() != texte:
        voix.noter_correction(r["brand_id"], "avis", r["draft"], texte, _qui(u))       # la voix apprend
    return _json({"ok": relation.envoyer_reponse_avis(avis_id, texte, _qui(u))})


# ── La mesure ────────────────────────────────────────────────────────────
@app.get("/api/tableau")
def tableau(request: Request, marque: str = "", jours: int = 30):
    """Le chiffre qui compte d'abord : les clients générés, et grâce à quoi."""
    u = _moi(request)
    ids = [_voir(u, marque)["id"]] if marque else securite.marques_de(u)
    out = []
    for i in ids:
        m = acces.marque(i)
        out.append({"marque": {"id": m["id"], "nom": m["name"], "secteur": m["sector"]},
                    "chiffre": mesure.resume_marque(i, jours), "audience": mesure.audience([i], jours)["lignes"],
                    "stock": planificateur.stock(m), "piliers_oublies": planificateur.piliers_en_retard(m),
                    "semaine": planificateur.nb_publications_semaine(i, acces.aujourdhui()),
                    "cadence": [m["cadence_min"], m["cadence_max"]], "veille": relation.veille(m),
                    "en_pause": acces.en_pause(m), "valeur": analyste.valeur(m, jours),
                    "objectif": rapport.objectif(i), "lecons": carnet.lecons(i, 3),
                    "decisions": [d for d in analyste.lister(i) if d["statut"] in ("proposee", "a_decider")][:3],
                    "test": ab.actif(i)})
    return _json({"jours": jours, "marques": out, "bac_a_sable": journal.bac_a_sable()})


@app.post("/api/decisions/{decision_id}")
async def trancher_decision(decision_id: int, request: Request):
    """Oui ou non à une décision du lundi. Sans réponse, elle s'applique à midi."""
    u = _moi(request)
    with db.moteur().begin() as c:
        d = db.ligne(c.execute(select(db.decisions).where(db.decisions.c.id == decision_id)))
    if not d or not securite.peut_voir(u, d["brand_id"]):
        raise HTTPException(404, "Décision inconnue.")
    if d["type"] == "budget":
        _pdg(u)                                 # une dépense : le PDG seul
    try:
        return _json(analyste.trancher(decision_id, bool((await request.json()).get("oui")), _qui(u)))
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.post("/api/marque/{marque_id}/objectif")
async def poser_objectif(marque_id: str, request: Request):
    u = _moi(request)
    _pdg(u)
    m = _voir(u, marque_id)
    n = (await request.json()).get("clients")
    n = int(n) if str(n or "").isdigit() else None
    journal.ecrire(f"objectif:{m['id']}", str(n) if n else "")
    return _json({"objectif": n})


@app.get("/api/carnet")
def lire_carnet(request: Request, marque: str):
    u = _moi(request)
    m = _voir(u, marque)
    return _json({"lecons": carnet.lecons(m["id"], 30, toutes=True), "tests": ab.liste([m["id"]]),
                  "variables": {k: v["hypothese"] for k, v in ab.VARIABLES.items()}})


@app.post("/api/ab")
async def lancer_test(request: Request):
    u = _moi(request)
    c_ = await request.json()
    m = _voir(u, c_.get("marque", ""))
    try:
        return _json(ab.lancer(m, c_.get("variable", ""), _qui(u), (c_.get("hypothese") or "")[:300]))
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.post("/api/leads")
async def lead_manuel(request: Request):
    """« Il nous a vus sur Instagram » : la saisie qui complète la mesure automatique."""
    u = _moi(request)
    c_ = await request.json()
    m = _voir(u, c_.get("marque", ""))
    type_ = c_.get("type") if c_.get("type") in ("devis", "commande", "appel") else "devis"
    canal = c_.get("canal") or "manuel"
    montant = float(c_["montant"]) if c_.get("montant") not in (None, "") else None
    lid = mesure.enregistrer_lead(m["id"], type_, canal, marqueur=(c_.get("marqueur") or "")[:40],
                                  montant=montant, source=(c_.get("source") or "")[:300],
                                  note=(c_.get("note") or "")[:1000], par=_qui(u))
    return _json({"id": lid})


# ── Les routes publiques de la mesure ────────────────────────────────────
@app.get("/go/{code}")
def lien_trace(code: str, request: Request, q: str = ""):
    l = mesure.noter_clic(code, request.headers.get("user-agent", ""), request.headers.get("referer", ""),
                          _ip(request), source="qr" if q == "1" else "lien")
    if not l:
        return HTMLResponse(_page("Lien expiré", "<p>Ce lien n'existe plus.</p>"), status_code=404)
    return RedirectResponse(mesure.cible_avec_marqueur(l), status_code=302)


@app.get("/c/{code}")
def choix_commande(code: str):
    """SAZÚ : un seul lien dans la publication, deux boutons — chacun tracé à part."""
    with db.moteur().begin() as c:
        principal = db.ligne(c.execute(select(db.links).where(db.links.c.code == code)))
        if not principal:
            return HTMLResponse(_page("Lien expiré", "<p>Ce lien n'existe plus.</p>"), status_code=404)
        freres = db.lignes(c.execute(select(db.links).where(
            db.links.c.post_id == principal["post_id"], db.links.c.platform == principal["platform"],
            db.links.c.brand_id == principal["brand_id"], db.links.c.kind.in_(("uber_eats", "deliveroo")))))
    m = acces.marque(principal["brand_id"])
    noms = {"uber_eats": "Uber Eats", "deliveroo": "Deliveroo"}
    boutons = "".join(f'<a class="b" href="/go/{html.escape(f["code"])}">Commander sur {noms[f["kind"]]}</a>'
                      for f in sorted(freres, key=lambda f: f["kind"], reverse=True))
    return HTMLResponse(_page(m["name"], f"<h1>{html.escape(m['name'])}</h1>"
                              f"<p>Choisis ton application :</p>{boutons}", m))


@app.get("/b/{marque_id}")
def lien_en_bio(marque_id: str):
    """La page « lien en bio » : les dernières publications, chacune avec son lien tracé."""
    m = acces.marque(marque_id)
    if not m or not m["active"]:
        raise HTTPException(404, "Marque inconnue.")
    with db.moteur().begin() as c:
        ps = db.lignes(c.execute(select(db.posts).where(
            db.posts.c.brand_id == m["id"], db.posts.c.status == "publie", db.posts.c.link_id.is_not(None))
            .order_by(desc(db.posts.c.published_at)).limit(12)))
    vus, items = set(), []
    for p in ps:
        if p["asset_id"] in vus:
            continue
        vus.add(p["asset_id"])
        l = pipeline._un(db.links, p["link_id"])
        r = pipeline._un(db.renditions, p["rendition_id"]) if p["rendition_id"] else None
        img = f'<img src="/m/{pipeline.url_media(r)}" alt="">' if r else ""
        items.append(f'<a class="t" href="/go/{html.escape(l["code"])}">{img}'
                     f'<span>{html.escape((p["text"] or "").splitlines()[0][:90])}</span></a>')
    principal = (m.get("links") or {}).get("site") or (m.get("links") or {}).get("devis")
    tete = ""
    if principal:
        l = mesure.creer_lien(m, None, "bio", "site", principal)
        tete = f'<a class="b" href="/go/{l["code"]}">Notre site</a>'
    corps = f"<h1>{html.escape(m['name'])}</h1>{tete}<div class='g'>{''.join(items) or '<p>Bientôt ici.</p>'}</div>"
    return HTMLResponse(_page(m["name"], corps, m))


def _page(titre: str, corps: str, m: dict | None = None) -> str:
    coul = images.couleurs((m or {}).get("kit") or {})
    hexa = lambda t: "#%02x%02x%02x" % t
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(titre)}</title>
<style>body{{margin:0;font:16px/1.45 system-ui,sans-serif;background:{hexa(coul['fond'])};color:{hexa(coul['encre'])};
padding:24px 16px;max-width:560px;margin:auto}}h1{{font-size:26px;margin:8px 0 16px}}
.b{{display:block;text-align:center;padding:16px;margin:10px 0;border-radius:14px;background:{hexa(coul['primaire'])};
color:#fff;text-decoration:none;font-weight:700}}.g{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:16px}}
.t{{color:inherit;text-decoration:none;font-size:13px}}.t img{{width:100%;aspect-ratio:4/5;object-fit:cover;border-radius:10px;display:block}}
</style></head><body>{corps}</body></html>"""


@app.get("/s/marqueur.js")
def marqueur_js():
    """À coller sur le site d'une marque : le marqueur `am` du lien tracé est
    gardé 30 jours et repart avec chaque formulaire envoyé. C'est ce qui permet
    de dire « cette demande de devis vient de cette publication »."""
    js = f"""(function(){{try{{var k='alma_am',q=new URLSearchParams(location.search).get('am');
if(q){{localStorage.setItem(k,JSON.stringify({{v:q,t:Date.now()}}));}}
var s=JSON.parse(localStorage.getItem(k)||'null');if(!s||Date.now()-s.t>2592e6)return;
document.addEventListener('submit',function(e){{var f=e.target;if(!f||f.querySelector('input[name=alma_marqueur]'))return;
var i=document.createElement('input');i.type='hidden';i.name='alma_marqueur';i.value=s.v;f.appendChild(i);
var m=f.getAttribute('data-alma-marque');if(m&&navigator.sendBeacon){{var d=new FormData();d.append('marque',m);
d.append('marqueur',s.v);d.append('type',f.getAttribute('data-alma-type')||'devis');
navigator.sendBeacon('{config.url_publique()}/api/leads/web',d);}}}},true);}}catch(e){{}}}})();"""
    return Response(js, media_type="application/javascript", headers={"Cache-Control": "public, max-age=3600"})


@app.post("/api/leads/web")
async def lead_web(request: Request):
    """Le formulaire d'un site envoie sa demande ici (via marqueur.js). Ouvert,
    mais ne fait qu'ajouter une ligne : pas de lecture, pas de réponse bavarde."""
    form = await request.form()
    mid = str(form.get("marque", ""))[:40]
    if not acces.marque(mid):
        return Response(status_code=204)
    type_ = str(form.get("type", "devis"))
    mesure.enregistrer_lead(mid, type_ if type_ in ("devis", "commande", "appel") else "devis", "formulaire",
                            marqueur=str(form.get("marqueur", ""))[:40], source=request.headers.get("referer", "")[:300])
    return Response(status_code=204, headers={"Access-Control-Allow-Origin": "*"})


# ── J4 : les cinq portes du client ───────────────────────────────────────
@app.post("/api/conversions")
async def conversion_serveur(request: Request):
    """Le SERVEUR du site d'une marque annonce une demande, signée
    (`X-Alma-Signature: sha256=<hmac du corps>`). À l'abri des bloqueurs."""
    corps = await request.body()
    try:
        r = conversions.conversion_serveur(corps, request.headers.get("x-alma-signature", ""))
    except PermissionError as e:
        raise HTTPException(401, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _json(r)


@app.post("/api/appels/entrant")
async def appel_entrant(request: Request, jeton: str = ""):
    """Le webhook du fournisseur de numéros tracés (JSON ou formulaire)."""
    try:
        d = await request.json()
    except Exception:
        d = dict(await request.form())
    try:
        r = conversions.appel_entrant(d if isinstance(d, dict) else {},
                                      jeton or request.headers.get("x-alma-jeton", ""))
    except PermissionError as e:
        raise HTTPException(401, str(e))
    return _json(r)


@app.get("/api/terrain")
def terrain(request: Request, marque: str = ""):
    """Les QR codes, les numéros tracés et les codes promo des marques visibles."""
    u = _moi(request)
    ids = [_voir(u, marque)["id"]] if marque else securite.marques_de(u)
    with db.moteur().begin() as c:
        nums = db.lignes(c.execute(select(db.tracking_numbers).where(db.tracking_numbers.c.brand_id.in_(ids))))
        appels = dict(c.execute(select(db.leads.c.source, func.count()).where(
            db.leads.c.brand_id.in_(ids), db.leads.c.channel == "telephone").group_by(db.leads.c.source)).all())
    return _json({
        "qr": conversions.liens_terrain(ids),
        "numeros": [{"id": n["id"], "marque": n["brand_id"], "numero": n["numero"], "source": n["source"],
                     "fournisseur": n["fournisseur"], "actif": n["actif"], "appels": appels.get(n["source"], 0)}
                    for n in nums],
        "codes": [{k: x[k] for k in ("id", "brand_id", "code", "platform", "createur", "offre", "utilisations",
                                     "chiffre", "post_id", "actif")} for x in conversions.codes(ids)],
        "branche": {"conversions": bool(conversions.secret_conversions()), "appels": bool(conversions.secret_appels())},
    })


@app.post("/api/terrain/qr")
async def creer_qr(request: Request):
    u = _moi(request)
    c_ = await request.json()
    m = _voir(u, c_.get("marque", ""))
    try:
        return _json(conversions.lien_terrain(m, c_.get("support", ""), (c_.get("cible") or "")[:500], _qui(u)))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/qr/{code}.{sorte}")
def image_qr(code: str, sorte: str, request: Request):
    u = _moi(request)
    with db.moteur().begin() as c:
        l = db.ligne(c.execute(select(db.links).where(db.links.c.code == code)))
    if not l or not securite.peut_voir(u, l["brand_id"]) or sorte not in ("svg", "png"):
        raise HTTPException(404, "QR inconnu.")
    coul = images.couleurs((acces.marque(l["brand_id"]) or {}).get("kit") or {})["encre"]
    return Response(conversions.qr(code, sorte, "#%02x%02x%02x" % coul),
                    media_type="image/svg+xml" if sorte == "svg" else "image/png",
                    headers={"Content-Disposition": f'inline; filename="qr-{code}.{sorte}"'})


@app.post("/api/terrain/numero")
async def poser_numero(request: Request):
    u = _moi(request)
    c_ = await request.json()
    m = _voir(u, c_.get("marque", ""))
    try:
        return _json({"id": conversions.poser_numero(m, c_.get("numero", ""), c_.get("source", ""),
                                                     c_.get("fournisseur", ""), c_.get("renvoi", ""), _qui(u))})
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception:
        raise HTTPException(409, "Ce numéro est déjà posé.")


@app.post("/api/terrain/code")
async def creer_code(request: Request):
    u = _moi(request)
    c_ = await request.json()
    m = _voir(u, c_.get("marque", ""))
    try:
        return _json(conversions.creer_code(m, c_.get("offre", ""), c_.get("post_id"), c_.get("reseau", ""),
                                            c_.get("createur", ""), c_.get("code", ""), _qui(u)))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/livraisons/import")
async def import_livraisons(request: Request, marque: str = Form(...), plateforme: str = Form(...),
                            fichier: UploadFile = File(...)):
    u = _moi(request)
    m = _voir(u, marque)
    octets = await fichier.read()
    if len(octets) > 10 * 1024 * 1024:
        raise HTTPException(400, "Fichier trop lourd (10 Mo maximum).")
    try:
        return _json(conversions.importer_livraisons(m, plateforme, octets, _qui(u)))
    except ValueError as e:
        raise HTTPException(400, str(e))


# ── J5 : la crise ────────────────────────────────────────────────────────
@app.post("/api/marque/{marque_id}/crise")
async def declencher_crise(marque_id: str, request: Request):
    """Le bouton rouge : tout s'arrête pour la marque, un brouillon de prise de parole attend."""
    u = _moi(request)
    m = _voir(u, marque_id)
    try:
        corps = await request.json()
    except ValueError:
        corps = {}
    return _json(crise.declencher(m, _qui(u), (corps.get("raison") or "déclenché à la main").strip()[:300]))


@app.post("/api/marque/{marque_id}/crise/lever")
def lever_crise(marque_id: str, request: Request):
    u = _moi(request)
    return _json(crise.lever(_voir(u, marque_id), _qui(u)))


# ── J5 : la réputation ───────────────────────────────────────────────────
@app.get("/api/reputation")
def reputation(request: Request, marque: str):
    """Pour une marque : ce que disent les avis, la position sur Maps, l'audit de la fiche, les demandes d'avis."""
    u = _moi(request)
    m = _voir(u, marque)
    with db.moteur().connect() as c:
        conc = db.lignes(c.execute(select(db.competitors).where(db.competitors.c.brand_id == m["id"])))
    return _json({"lecture": lecture_avis.lecture(m), "maps": maps.resume(m), "audit": maps.audit(m),
                  "fiche": m.get("google_listing") or {}, "requetes": maps.requetes(m),
                  "place_id": maps.place_id(m), "cle_places": bool(maps.cle()),
                  "lien_avis": demandes_avis.lien_google(m), "lien_avis_qr": f"{config.url_publique()}/avis/m/{m['id']}",
                  "demandes": demandes_avis.liste([m["id"]]), "bilan": demandes_avis.bilan(m["id"]),
                  "concurrents": [{"id": x["id"], "nom": x["name"]} for x in conc]})


@app.post("/api/demandes-avis")
async def demander_avis(request: Request):
    """« Chantier livré » : la demande d'avis part, à tous, sans tri."""
    u = _moi(request)
    c_ = await request.json()
    m = _voir(u, c_.get("marque", ""))
    r = demandes_avis.demander(m, c_.get("evenement") or "pv_chantier", c_.get("nom", ""), c_.get("email", ""),
                               c_.get("telephone", ""), c_.get("reference", ""), _qui(u))
    return _json({"id": r["id"], "deja": r.get("deja", False), "canal": r["channel"]})


@app.post("/api/avis/evenement")
async def evenement_avis(request: Request):
    """Le serveur d'un outil (facturation, caisse) annonce un événement, signé
    comme les conversions : `X-Alma-Signature: sha256=<hmac du corps>`."""
    import hmac as _hmac
    corps = await request.body()
    secret = conversions.secret_conversions()
    sig = request.headers.get("x-alma-signature", "").removeprefix("sha256=")
    if not secret or not _hmac.compare_digest(sig, conversions.signer(corps, secret)):
        raise HTTPException(401, "signature absente ou fausse")
    try:
        d = json.loads(corps)
    except ValueError:
        raise HTTPException(400, "JSON illisible")
    m = acces.marque(str(d.get("marque", ""))[:40])
    if not m:
        raise HTTPException(400, "marque inconnue")
    r = demandes_avis.demander(m, d.get("evenement", ""), d.get("nom", ""), d.get("email", ""),
                               d.get("telephone", ""), str(d.get("id") or ""), "serveur")
    return _json({"id": r["id"], "deja": r.get("deja", False)})


@app.post("/api/marque/{marque_id}/google")
async def poser_google(marque_id: str, request: Request):
    """L'identifiant de la fiche Google (place ID), et la fiche saisie à la main si besoin."""
    import re as _re
    u = _moi(request)
    m = _voir(u, marque_id)
    c_ = await request.json()
    if "place_id" in c_:
        pid = (c_.get("place_id") or "").strip()
        if pid and not _re.fullmatch(r"[A-Za-z0-9_-]{10,250}", pid):
            raise HTTPException(400, "Ce n'est pas un identifiant de fiche Google (place ID).")
        liens = dict(m.get("links") or {})
        liens["google_place_id"] = pid
        with db.moteur().begin() as c:
            c.execute(update(db.brands).where(db.brands.c.id == m["id"]).values(links=liens))
        journal.noter(_qui(u), "google_place_id", "brand", m["id"], m["id"], apres={"place_id": pid})
    if isinstance(c_.get("fiche"), dict):
        f = c_["fiche"]
        fiche = {"nom": str(f.get("nom", ""))[:200], "adresse": str(f.get("adresse", ""))[:300],
                 "telephone": str(f.get("telephone", ""))[:30], "site": str(f.get("site", ""))[:300],
                 "horaires": bool(f.get("horaires")), "photos": int(f.get("photos") or 0),
                 "categories": [str(x)[:60] for x in (f.get("categories") or [])][:10],
                 "description": str(f.get("description", ""))[:750], "source": "manuel",
                 "le": db.maintenant().isoformat(),
                 "location": (m.get("google_listing") or {}).get("location") or {}}
        maps.poser_fiche(m, fiche, _qui(u))
    if isinstance(c_.get("requetes"), list):
        rq = [str(x).strip()[:120] for x in c_["requetes"] if str(x).strip()][:5]
        journal.ecrire(f"maps_requetes:{m['id']}", rq, par=_qui(u))
    return _json({"ok": True})


@app.post("/api/maps/releve")
async def releve_maps(request: Request):
    u = _moi(request)
    c_ = await request.json()
    m = _voir(u, c_.get("marque", ""))
    return _json({"id": maps.saisir(m, c_.get("requete", ""), c_.get("position"), _qui(u))})


@app.post("/api/concurrents/{cid}/avis")
async def avis_concurrent(cid: int, request: Request):
    u = _moi(request)
    with db.moteur().connect() as c:
        k = db.ligne(c.execute(select(db.competitors).where(db.competitors.c.id == cid)))
    if not k or not securite.peut_voir(u, k["brand_id"]):
        raise HTTPException(404, "Concurrent inconnu.")
    c_ = await request.json()
    textes = [t for t in (c_.get("textes") or [c_.get("texte", "")]) if (t or "").strip()][:50]
    n = sum(1 for t in textes if lecture_avis.ajouter_concurrent(cid, c_.get("note"), t, _qui(u)))
    return _json({"ajoutes": n})


# ── J5 : les routes publiques de la relation ─────────────────────────────
_OUVERTURES = {}            # ip → [instants] : une page ouverte en boucle ne remplit pas la base


def _trop(ip: str, n: int = 20, fenetre: int = 3600) -> bool:
    maintenant = time.monotonic()
    l = [t for t in _OUVERTURES.get(ip, []) if maintenant - t < fenetre]
    l.append(maintenant)
    _OUVERTURES[ip] = l[-n - 1:]
    if len(_OUVERTURES) > 5000:
        _OUVERTURES.clear()
    return len(l) > n


@app.get("/parler/{marque_id}")
def page_parler(marque_id: str):
    """La conversation qui qualifie : nom et téléphone d'abord, puis le projet."""
    m = acces.marque(marque_id)
    if not m or not m["active"]:
        raise HTTPException(404, "Marque inconnue.")
    corps = f"""<h1>{html.escape(m['name'])}</h1><div id="fil" class="fil" aria-live="polite"></div>
<form id="f" class="saisie"><input id="t" autocomplete="off" maxlength="600" placeholder="Votre réponse" required>
<button>Envoyer</button></form><p class="petit">Vos réponses ne servent qu'à vous recontacter.</p>
<script>
(function(){{var M={json.dumps(m['id'])},k='alma_chat_'+M,fil=document.getElementById('fil'),f=document.getElementById('f'),t=document.getElementById('t');
var q=new URLSearchParams(location.search);
function h(x){{var d=document.createElement('div');d.textContent=x;return d.innerHTML}}
function voir(v){{fil.innerHTML=v.messages.map(function(x){{return '<p class="'+(x.de==='client'?'moi':'eux')+'">'+h(x.texte)+'</p>'}}).join('');
if(v.fini){{f.style.display='none';fil.insertAdjacentHTML('beforeend','<p><a href="#" id="neuf">Une autre demande ?</a></p>');
document.getElementById('neuf').onclick=function(e){{e.preventDefault();try{{localStorage.removeItem(k)}}catch(x){{}}f.style.display='';ouvrir()}};}}window.scrollTo(0,document.body.scrollHeight);t.focus();}}
function api(u,c){{return fetch(u,{{method:c?'POST':'GET',headers:{{'Content-Type':'application/json','X-Alma':'1'}},body:c?JSON.stringify(c):undefined}})
.then(function(r){{if(!r.ok)throw r;return r.json()}})}}
var j=null;try{{j=localStorage.getItem(k)}}catch(e){{}}
function ouvrir(){{return api('/api/chat/ouvrir',{{marque:M,am:q.get('am')||'',source:q.get('src')||''}}).then(function(v){{j=v.jeton;try{{localStorage.setItem(k,j)}}catch(e){{}}voir(v)}})}}
(j?api('/api/chat/'+j).then(voir).catch(ouvrir):ouvrir()).catch(function(){{fil.innerHTML='<p class="eux">Le service est momentanément indisponible. Merci de réessayer plus tard.</p>'}});
f.addEventListener('submit',function(e){{e.preventDefault();var x=t.value.trim();if(!x)return;t.value='';
api('/api/chat/'+j,{{texte:x}}).then(voir).catch(function(){{t.value=x}})}});}})();
</script>"""
    page = _page(m["name"], corps, m).replace("</style>", """.fil p{padding:10px 14px;border-radius:16px;margin:8px 0;max-width:85%}
.fil .eux{background:rgba(0,0,0,.06)}.fil .moi{background:rgba(0,0,0,.14);margin-left:auto}
.saisie{display:flex;gap:8px;position:sticky;bottom:0;padding:10px 0}.saisie input{flex:1;font:inherit;padding:14px;border-radius:12px;border:1px solid rgba(0,0,0,.2)}
.saisie button{font:inherit;font-weight:700;padding:0 18px;border-radius:12px;border:0;background:rgba(0,0,0,.8);color:#fff}
.petit{font-size:12px;opacity:.7}</style>""")
    return HTMLResponse(page, headers={"Cache-Control": "no-store"})


@app.post("/api/chat/ouvrir")
async def chat_ouvrir(request: Request):
    if _trop(_ip(request)):
        raise HTTPException(429, "Trop de conversations ouvertes : réessayez dans une heure.")
    c_ = await request.json()
    m = acces.marque(str(c_.get("marque", ""))[:40])
    if not m or not m["active"]:
        raise HTTPException(404, "Marque inconnue.")
    ch = qualification.ouvrir(m, "chat", str(c_.get("source") or "")[:100], marqueur=str(c_.get("am") or "")[:40])
    return _json({**qualification.vue(ch), "jeton": ch["token"]})


@app.get("/api/chat/{jeton}")
def chat_lire(jeton: str):
    ch = qualification.chat(jeton[:60])
    if not ch:
        raise HTTPException(404, "Conversation inconnue.")
    return _json(qualification.vue(ch))


@app.post("/api/chat/{jeton}")
async def chat_ecrire(jeton: str, request: Request):
    c_ = await request.json()
    try:
        return _json(qualification.repondre(jeton[:60], str(c_.get("texte") or "")))
    except LookupError:
        raise HTTPException(404, "Conversation inconnue.")


@app.get("/s/chat.js")
def chat_js(marque: str = ""):
    """À coller sur le site d'une marque : un bouton « Une question ? » qui ouvre la conversation."""
    m = acces.marque(marque[:40])
    if not m:
        return Response("", media_type="application/javascript")
    coul = "#%02x%02x%02x" % images.couleurs(m.get("kit") or {})["primaire"]
    url = qualification.url(m["id"])
    js = f"""(function(){{var a=document.createElement('a');a.href={json.dumps(url)}+'?src='+encodeURIComponent(location.hostname);
a.target='_blank';a.rel='noopener';a.textContent={json.dumps("Une question ? Un devis ?" if m.get("sector") != "food" else "Une commande de groupe ?")};
a.style.cssText='position:fixed;right:16px;bottom:16px;z-index:99999;padding:14px 18px;border-radius:999px;background:{coul};color:#fff;font:600 15px system-ui,sans-serif;text-decoration:none;box-shadow:0 4px 14px rgba(0,0,0,.25)';
document.body.appendChild(a);}})();"""
    return Response(js, media_type="application/javascript", headers={"Cache-Control": "public, max-age=3600"})


@app.get("/avis/m/{marque_id}")
def avis_marque(marque_id: str):
    """Le lien du QR code et de la puce NFC : droit vers la fiche Google."""
    m = acces.marque(marque_id)
    if not m:
        raise HTTPException(404, "Marque inconnue.")
    lien = demandes_avis.lien_google(m)
    if not lien:
        return HTMLResponse(_page(m["name"], f"<h1>{html.escape(m['name'])}</h1><p>Merci ! Notre page d'avis "
                                             "arrive très bientôt.</p>", m))
    return RedirectResponse(lien, status_code=302)


@app.get("/avis/{jeton}")
def avis_client(jeton: str):
    m, lien = demandes_avis.ouvrir(jeton[:60])
    if not m:
        return HTMLResponse(_page("Lien expiré", "<p>Ce lien n'existe plus.</p>"), status_code=404)
    if not lien:
        return HTMLResponse(_page(m["name"], f"<h1>{html.escape(m['name'])}</h1><p>Merci ! Notre page d'avis "
                                             "arrive très bientôt.</p>", m))
    return RedirectResponse(lien, status_code=302)


@app.get("/avis/{jeton}/stop")
def avis_stop(jeton: str):
    m = demandes_avis.arreter(jeton[:60])
    if not m:
        return HTMLResponse(_page("Lien expiré", "<p>Ce lien n'existe plus.</p>"), status_code=404)
    return HTMLResponse(_page(m["name"], f"<h1>{html.escape(m['name'])}</h1><p>C'est noté : vous ne recevrez "
                                         "plus ces messages.</p>", m))


# ── Les comptes des réseaux ──────────────────────────────────────────────
@app.get("/api/comptes")
def comptes(request: Request, marque: str):
    u = _moi(request)
    m = _voir(u, marque)
    out = []
    for c in acces.comptes(m["id"]):
        out.append({"id": c["id"], "reseau": reseaux.NOMS.get(c["platform"], c["platform"]), "cle": c["platform"],
                    "poignee": c["handle"], "etat": c["status"], "mode": c["mode"],
                    "profil": securite.masquer(securite.dechiffrer(c["external_profile_enc"])),
                    "jeton_expire_le": c["token_expires_at"], "refus_consecutifs": c["consecutive_failures"],
                    "derniere_erreur": c["last_error"], "options": c["options"] or {}})
    return _json({"comptes": out, "agregateur": "Upload-Post", "cle_presente": bool(config.cle_upload_post())})


OPTIONS_COMPTE = {"facebook_page_id", "linkedin_page_id", "pinterest_board_id", "gbp_location_id", "tiktok_privacy"}


@app.post("/api/comptes/{compte_id}")
async def regler_compte(compte_id: int, request: Request):
    """Les identifiants NON secrets qu'exige l'agrégateur (page Facebook, tableau
    Pinterest…), la poignée, et la relance d'un réseau mis en pause."""
    u = _moi(request)
    with db.moteur().begin() as c:
        cpt = db.ligne(c.execute(select(db.accounts).where(db.accounts.c.id == compte_id)))
    if not cpt or not securite.peut_voir(u, cpt["brand_id"]):
        raise HTTPException(404, "Compte inconnu.")
    c_ = await request.json()
    vals = {"updated_at": db.maintenant()}
    if "options" in c_:
        vals["options"] = {k: str(v)[:120] for k, v in (c_["options"] or {}).items() if k in OPTIONS_COMPTE and v}
    if "poignee" in c_:
        vals["handle"] = str(c_["poignee"])[:200]
    if c_.get("relancer") and cpt["status"] in ("pause", "erreur"):
        vals.update(status="actif" if cpt["external_profile_enc"] or cpt["tokens_enc"] else "a_relier",
                    consecutive_failures=0, last_error="")
    with db.moteur().begin() as c:
        c.execute(update(db.accounts).where(db.accounts.c.id == compte_id).values(**vals))
    journal.noter(_qui(u), "compte_regle", "account", compte_id, cpt["brand_id"],
                  apres={k: v for k, v in vals.items() if k != "updated_at"})
    return _json({"ok": True})


@app.post("/api/comptes/relier/{marque_id}")
def relier(marque_id: str, request: Request):
    """Le lien (48 h) que le responsable ouvre pour relier les comptes de sa
    marque chez l'agrégateur. Aucun mot de passe ne transite par nous."""
    u = _moi(request)
    m = _voir(u, marque_id)
    profil = upload_post.profil_de(m["id"])
    try:
        url = upload_post.lien_de_connexion(profil, f"{config.url_publique()}/?relie={m['id']}",
                                            f"{m['name']} — relier les réseaux")
    except ErreurPublication as e:
        raise HTTPException(503, str(e))
    with db.moteur().begin() as c:
        c.execute(update(db.accounts).where(db.accounts.c.brand_id == m["id"], db.accounts.c.mode == "agregateur")
                  .values(external_profile_enc=securite.chiffrer(profil), updated_at=db.maintenant()))
    journal.noter(_qui(u), "lien_de_liaison", "brand", m["id"], m["id"])
    return _json({"url": url})


@app.post("/api/comptes/verifier/{marque_id}")
def verifier_comptes(marque_id: str, request: Request):
    """Après la liaison : relit chez l'agrégateur quels réseaux sont reliés."""
    u = _moi(request)
    m = _voir(u, marque_id)
    try:
        relies = upload_post.comptes_relies(upload_post.profil_de(m["id"]))
    except ErreurPublication as e:
        raise HTTPException(503, str(e))
    return _json({"relies": _appliquer_liaisons(m, relies, _qui(u))})


def _appliquer_liaisons(m: dict, relies: dict, par: str) -> dict:
    etats = {}
    for c in acces.comptes(m["id"]):
        if c["mode"] != "agregateur":
            continue
        r = relies.get(c["platform"])
        if c["platform"] == "linkedin_perso":
            r = relies.get("linkedin") if not c["options"].get("linkedin_page_id") else None
        nouveau = ("erreur" if r and r["reauth"] else "actif" if r else "a_relier") if c["status"] != "pause" else "pause"
        if nouveau != c["status"] or (r and r["nom"] and r["nom"] != c["handle"]):
            with db.moteur().begin() as cx:
                cx.execute(update(db.accounts).where(db.accounts.c.id == c["id"]).values(
                    status=nouveau, handle=(r or {}).get("nom") or c["handle"],
                    last_error="à reconnecter" if r and r["reauth"] else c["last_error"], updated_at=db.maintenant()))
            journal.noter(par, "compte_etat", "account", c["id"], m["id"], avant={"etat": c["status"]},
                          apres={"etat": nouveau})
        etats[c["platform"]] = nouveau
    return etats


# ── Le webhook d'Upload-Post ─────────────────────────────────────────────
_LIVRAISONS_VUES: dict = {}


def _secret_webhook() -> str:
    """L'environnement d'abord (UPLOAD_POST_WEBHOOK_SECRET) ; sinon celui que le
    bouton « Brancher les notifications » a rangé, chiffré, en base."""
    return config.secret_webhook_upload_post() or securite.dechiffrer(journal.lire("webhook_upload_post") or "")


@app.post("/api/webhook/brancher")
def brancher_webhook(request: Request):
    """PDG : un geste, et Upload-Post nous prévient (publication confirmée,
    compte déconnecté) au lieu d'attendre qu'on aille lui demander."""
    u = _moi(request)
    _pdg(u)
    adresse = f"{config.url_publique()}/webhooks/upload-post"
    if not adresse.startswith("https://"):
        raise HTTPException(400, "SOCIAL_URL_PUBLIQUE doit être une adresse https publique.")
    try:
        secret = upload_post.enregistrer_webhook(adresse)
    except ErreurPublication as e:
        raise HTTPException(503, str(e))
    journal.ecrire("webhook_upload_post", securite.chiffrer(secret), par=_qui(u), journaliser=False)
    journal.noter(_qui(u), "webhook_branche", "reglage", "webhook_upload_post", apres={"adresse": adresse})
    return _json({"ok": True, "adresse": adresse})


@app.post("/webhooks/upload-post")
async def webhook_upload_post(request: Request):
    corps = await request.body()
    horodatage = request.headers.get("x-upload-post-timestamp", "")
    if not upload_post.verifier_signature(_secret_webhook(), horodatage, corps,
                                          request.headers.get("x-upload-post-signature", "")):
        return Response(status_code=401)
    try:
        if abs(time.time() - int(horodatage)) > 300:
            return Response(status_code=401)
    except ValueError:
        return Response(status_code=401)
    livraison = request.headers.get("x-upload-post-delivery", "")
    if livraison and livraison in _LIVRAISONS_VUES:
        return Response(status_code=200)
    if livraison:
        _LIVRAISONS_VUES[livraison] = time.time()
        for k in [k for k, t in _LIVRAISONS_VUES.items() if time.time() - t > 3600]:
            _LIVRAISONS_VUES.pop(k, None)
    ev = json.loads(corps or b"{}")
    traiter_evenement_upload_post(ev)
    return Response(status_code=200)


def traiter_evenement_upload_post(ev: dict):
    profil = ev.get("profile_username", "")
    if not profil.startswith("alma-"):
        return
    m = acces.marque(profil[len("alma-"):])
    if not m:
        return
    leur = ev.get("platform", "")
    notre = {v: k for k, v in upload_post.NOMS.items() if k != "linkedin_perso"}.get(leur, leur)
    if ev.get("event") == "upload_completed":
        with db.moteur().begin() as c:
            p = db.ligne(c.execute(select(db.posts).where(
                db.posts.c.brand_id == m["id"], db.posts.c.platform == notre, db.posts.c.status == "envoi")
                .order_by(db.posts.c.scheduled_at).limit(1)))
        if not p:
            return
        res = ev.get("result") or {}
        from alma_social.publieurs.base import Resultat
        if res.get("success"):
            r = pipeline._un(db.renditions, p["rendition_id"])
            pipeline.marquer_publie(p, Resultat(external_id=str(res.get("post_id") or res.get("publish_id") or ""),
                                                permalink=res.get("url") or "", raw={"webhook": True}),
                                    False, pipeline._info_rendu(r), acces.compte(m["id"], notre))
        else:
            pipeline._compter_refus(m, acces.compte(m["id"], notre), str(res.get("error") or "refus"))
            pipeline._echec(p, f"{reseaux.NOMS.get(notre, notre)} : {res.get('error') or 'refus'}")
    elif ev.get("event", "").startswith("social_account_"):
        statut = ev.get("status") or ev["event"].removeprefix("social_account_")
        relies = {notre: {"nom": ev.get("account_name", ""), "reauth": statut != "connected"}} \
            if statut in ("connected", "reauth_required") else {}
        cpt = acces.compte(m["id"], notre)
        if not cpt:
            return
        if statut == "connected":
            _appliquer_liaisons(m, {**{c["platform"]: {"nom": c["handle"], "reauth": False}
                                       for c in acces.comptes(m["id"]) if c["status"] == "actif"}, **relies},
                                "upload-post")
        else:
            with db.moteur().begin() as c:
                c.execute(update(db.accounts).where(db.accounts.c.id == cpt["id"]).values(
                    status="erreur", last_error=f"{statut} : {ev.get('reason', '')}", updated_at=db.maintenant()))
            nom = reseaux.NOMS.get(notre, notre)
            alertes.alerter(f"{m['name']} : {nom} est à reconnecter",
                            f"Le réseau a coupé l'accès ({ev.get('reason') or statut}). Plus rien n'y part.\n"
                            "ALMA SOCIAL → Réglages → la marque → « Relier les réseaux ».",
                            marque=m["id"], niveau="panne", type_="compte", dedup=f"reco:{cpt['id']}")


# ── La santé ─────────────────────────────────────────────────────────────
@app.get("/sante")
def sante_publique():
    """Pour l'hébergeur : 200 si la base répond. Rien d'autre n'est dit."""
    with db.moteur().begin() as c:
        c.execute(select(func.count()).select_from(db.brands)).scalar_one()
    return PlainTextResponse("ok")


@app.get("/api/sante")
def sante(request: Request):
    """La page santé : files en attente, échecs récents par réseau, jetons qui
    expirent, stock par marque, l'horloge. Ce qui est rouge se lit en premier."""
    u = _moi(request)
    ids = securite.marques_de(u)
    jour = db.maintenant() - dt.timedelta(days=1)
    semaine = db.maintenant() - dt.timedelta(days=7)
    with db.moteur().begin() as c:
        echecs = db.lignes(c.execute(select(db.posts.c.brand_id, db.posts.c.platform, func.count().label("n"))
                                     .where(db.posts.c.status == "echec", db.posts.c.created_at >= semaine,
                                            db.posts.c.brand_id.in_(ids))
                                     .group_by(db.posts.c.brand_id, db.posts.c.platform)))
        derniers = db.lignes(c.execute(select(db.posts.c.id, db.posts.c.brand_id, db.posts.c.platform,
                                              db.posts.c.error, db.posts.c.created_at)
                                       .where(db.posts.c.status == "echec", db.posts.c.brand_id.in_(ids))
                                       .order_by(desc(db.posts.c.created_at)).limit(10)))
        cpts = db.lignes(c.execute(select(db.accounts).where(db.accounts.c.brand_id.in_(ids))))
        alertes_ = db.lignes(c.execute(select(db.alerts).where(
            (db.alerts.c.brand_id.in_(ids)) | (db.alerts.c.brand_id.is_(None)))
            .order_by(desc(db.alerts.c.created_at)).limit(20)))
        publies_24h = c.execute(select(func.count()).select_from(db.posts).where(
            db.posts.c.status.in_(("publie", "simule")), db.posts.c.published_at >= jour,
            db.posts.c.brand_id.in_(ids))).scalar_one()
    expirent = [{"marque": c["brand_id"], "reseau": reseaux.NOMS.get(c["platform"]), "le": c["token_expires_at"]}
                for c in cpts if c["token_expires_at"] and c["token_expires_at"] < db.maintenant() + dt.timedelta(days=14)]
    a_relier = [{"marque": c["brand_id"], "reseau": reseaux.NOMS.get(c["platform"]), "etat": c["status"],
                 "erreur": c["last_error"]} for c in cpts if c["status"] != "actif"]
    stock = []
    for i in ids:
        m = acces.marque(i)
        stock.append({"marque": m["name"], "id": i, **planificateur.stock(m), "en_pause": acces.en_pause(m)})
    return _json({
        "horloge": {"vivante": horloge.vivante(), "taches": horloge.DERNIERS},
        "file": file.etat() if u["role"] == "pdg" else None,
        "publies_24h": publies_24h, "echecs_7j": echecs, "derniers_echecs": derniers,
        "jetons_qui_expirent": expirent, "comptes_a_relier": a_relier, "stock": stock, "alertes": alertes_,
        "bac_a_sable": journal.bac_a_sable(), "arret_general": journal.arret_general(),
        "ia": ia.couts() if u["role"] == "pdg" else None,
        "critique": critique.taux(),
        "cles": {"anthropic": bool(config.cle_anthropic()), "upload_post": bool(config.cle_upload_post()),
                 "webhook": bool(_secret_webhook()), "chiffrement": bool(config.cle_chiffrement()),
                 "nettoyage": bool(config.cle_nettoyage()), "courrier": bool(config.SMTP["hote"]) and not config.courrier_en_test()},
    })


# ── Le journal ───────────────────────────────────────────────────────────
@app.get("/api/journal")
def lire_journal(request: Request, marque: str = "", format: str = "json", limite: int = 300):
    """Intégral, non modifiable, exportable. Le PDG lit tout ; un responsable, sa marque."""
    u = _moi(request)
    q = select(db.audit_log).order_by(desc(db.audit_log.c.id))
    if marque:
        _voir(u, marque)
        q = q.where(db.audit_log.c.brand_id == marque)
    elif u["role"] != "pdg":
        q = q.where(db.audit_log.c.brand_id.in_(securite.marques_de(u)))
    if format != "csv":
        q = q.limit(min(limite, 2000))
    with db.moteur().begin() as c:
        lignes = db.lignes(c.execute(q))
    if format == "csv":
        tampon = io.StringIO()
        w = csv.writer(tampon, delimiter=";")
        w.writerow(["id", "le (UTC)", "qui", "action", "objet", "id objet", "marque", "avant", "après",
                    "empreinte précédente", "empreinte"])
        for r in reversed(lignes):
            w.writerow([r["id"], r["at"].isoformat(), r["actor"], r["action"], r["object_type"], r["object_id"],
                        r["brand_id"] or "", json.dumps(r["before"], ensure_ascii=False) if r["before"] else "",
                        json.dumps(r["after"], ensure_ascii=False) if r["after"] else "", r["prev_hash"], r["hash"]])
        nom = f"journal-alma-social-{acces.aujourdhui():%Y%m%d}.csv"
        return Response("﻿" + tampon.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{nom}"'})
    return _json({"lignes": lignes})


@app.get("/api/journal/verifier")
def verifier_journal(request: Request):
    u = _moi(request)
    _pdg(u)
    return _json(journal.verifier_chaine())


@app.get("/api/alertes")
def lire_alertes(request: Request):
    u = _moi(request)
    ids = securite.marques_de(u)
    cond = db.alerts.c.brand_id.in_(ids)
    if u["role"] == "pdg":
        cond = cond | db.alerts.c.brand_id.is_(None)
    with db.moteur().begin() as c:
        lignes = db.lignes(c.execute(select(db.alerts).where(cond).order_by(desc(db.alerts.c.created_at)).limit(50)))
    return _json({"alertes": lignes})


@app.get("/api/rapport")
def apercu_rapport(request: Request):
    """Le récapitulatif du lundi, tel qu'il partirait maintenant."""
    u = _moi(request)
    titre, corps, _, _ = rapport.composer(securite.marques_de(u))
    return PlainTextResponse(f"{titre}\n\n{corps}")


# ── L'écran ──────────────────────────────────────────────────────────────
# ── v3 : l'équipe, la plateforme de marque, Demander, Aujourd'hui ─────────
@app.get("/api/equipe")
def equipe(request: Request):
    """Les agents, leur modèle, leurs coûts, la sévérité du Critique."""
    u = _moi(request)
    _pdg(u)
    return _json({"agents": agents.tableau(), "niveaux": agents.NIVEAUX, "couts": ia.couts(),
                  "critique": critique.taux(), "cle": ia.disponible()})


@app.post("/api/reglages/agents")
async def regler_agent(request: Request):
    u = _moi(request)
    _pdg(u)
    c_ = await request.json()
    cle, niveau = c_.get("agent", ""), c_.get("niveau", "")
    if cle not in agents.EQUIPE or niveau not in agents.NIVEAUX:
        raise HTTPException(400, "Agent ou niveau inconnu.")
    regles = dict(journal.lire("agents.modeles") or {})
    regles[cle] = niveau
    journal.ecrire("agents.modeles", regles, par=_qui(u))
    return _json({"agent": cle, "modele": agents.modele(cle)})


@app.post("/api/reglages/plafond")
async def regler_plafond(request: Request):
    """Le plafond IA du mois : une dépense, donc un geste du PDG, journalisé."""
    u = _moi(request)
    _pdg(u)
    usd = float((await request.json()).get("usd"))
    if not 0 <= usd <= 5000:
        raise HTTPException(400, "Plafond entre 0 et 5 000 $.")
    journal.ecrire("ia.plafond_mois_usd", usd, par=_qui(u))
    return _json({"plafond_usd": ia.plafond_usd(), "mois_usd": ia.depense_du_mois()})


@app.post("/api/marque/{marque_id}/copilote")
async def copilote(marque_id: str, request: Request):
    u = _moi(request)
    _pdg(u)
    return _json(pilotage.copilote(_voir(u, marque_id), bool((await request.json()).get("actif")), _qui(u)))


@app.get("/api/marque/{marque_id}/plateforme")
def plateforme(marque_id: str, request: Request):
    u = _moi(request)
    m = _voir(u, marque_id)
    from alma_social import carnet
    return _json({"courante": marque_.courante(m["id"]), "versions": marque_.versions(m["id"]),
                  "voix": m.get("voice") or {}, "corrections": voix.historique(m["id"]),
                  "lecons": carnet.lecons(m["id"], toutes=True), "faits": m.get("facts") or {},
                  "kit": m.get("kit") or {}, "a_completer": m.get("todo") or [],
                  "copilote": bool(m.get("requires_approval"))})


@app.post("/api/marque/{marque_id}/plateforme/{geste}")
async def plateforme_geste(marque_id: str, geste: str, request: Request):
    u = _moi(request)
    _pdg(u)
    m = _voir(u, marque_id)
    try:
        c_ = await request.json()
    except ValueError:
        c_ = {}
    if geste == "rediger":
        return _json(marque_.rediger(m["id"], _qui(u), (c_.get("consigne") or "")[:1000]))
    if geste == "corriger":
        return _json(marque_.corriger(m["id"], c_.get("champs") or {}, _qui(u)))
    if geste == "relire":
        return _json(marque_.relire(m["id"], _qui(u)))
    raise HTTPException(404, "Geste inconnu.")


@app.post("/api/demander")
async def demander(request: Request):
    u = _moi(request)
    return _json(assistant.demander(u, (await request.json()).get("question") or ""))


@app.get("/api/demander")
def demandes(request: Request):
    return _json({"fil": assistant.historique(_moi(request))})


@app.get("/api/aujourdhui")
def aujourdhui(request: Request, marque: str = ""):
    """Ce qui sort aujourd'hui et demain : visuels et textes, heure par heure."""
    u = _moi(request)
    ids = [_voir(u, marque)["id"]] if marque else securite.marques_de(u)
    debut = creneaux.utc(dt.datetime.combine(acces.aujourdhui(), dt.time(0, 0), tzinfo=creneaux.PARIS))
    fin = debut + dt.timedelta(days=2)
    with db.moteur().begin() as c:
        lignes = db.lignes(c.execute(select(db.posts).where(
            db.posts.c.brand_id.in_(ids),
            ((db.posts.c.scheduled_at >= debut) & (db.posts.c.scheduled_at < fin))
            | ((db.posts.c.published_at >= debut) & (db.posts.c.published_at < fin)))
            .order_by(db.posts.c.scheduled_at)))
    out = []
    for p in lignes:
        if p["status"] in ("annule", "retire"):
            continue
        out.append({"id": p["id"], "marque": p["brand_id"], "reseau": p["platform"],
                    "nom_reseau": reseaux.NOMS.get(p["platform"], p["platform"]), "statut": p["status"],
                    "heure": p["published_at"] or p["scheduled_at"], "texte": p["text"],
                    "vignette": f"/api/photo/{p['asset_id']}/vignette" if p["asset_id"] else "",
                    "apercu": f"/apercu/{p['id']}", "lien": p["permalink"], "format": p.get("post_format") or "image",
                    "note": ((p["guard_report"] or {}).get("critique") or {}).get("note"),
                    "juge": ((p["guard_report"] or {}).get("critique") or {}).get("juge"),
                    "simule": bool(p["simulated"])})
    return _json({"publications": out, "bac_a_sable": journal.bac_a_sable()})



@app.get("/")
def accueil():
    return FileResponse(config.STATIQUES / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/sw.js")
def service_worker():
    return FileResponse(config.STATIQUES / "sw.js", media_type="application/javascript",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


@app.get("/manifest.webmanifest")
def manifeste():
    return FileResponse(config.STATIQUES / "manifest.webmanifest", media_type="application/manifest+json")


app.mount("/static", StaticFiles(directory=config.STATIQUES), name="static")
