"""Upload-Post — l'agrégateur retenu (DECISIONS.md : le budget, et tous nos réseaux).

Référence lue le 2026-10-04 : docs/recherche/upload-post-api.md, tirée de
https://docs.upload-post.com/llms-full.txt et de l'OpenAPI publiée.

Un profil Upload-Post = une marque. Son nom (`user`) est rangé chiffré sur
chaque compte ; ce que l'agrégateur réclame à chaque envoi et qui n'est pas
secret (page Facebook, page LinkedIn, tableau Pinterest, établissement Google)
vit dans `accounts.options`.

Ce qui compte dans ce fichier :
- une réponse 200 ne prouve RIEN : chaque réseau a son propre `success` ;
- un `warnings` est un succès avec réserve, jamais un échec (sinon on republie) ;
- un réseau non relié revient en `skipped` : c'est un réglage manquant, pas un refus ;
- Instagram, TikTok et Threads ne se retirent pas par API : on le dit.
"""
from __future__ import annotations

import json
import mimetypes
import pathlib

import httpx

from .. import config
from .base import (Avis, Commentaire, Mesures, NonBranche, PanneTransitoire, Publisher,
                   RefusReseau, Resultat)

BASE = "https://api.upload-post.com/api"
NOMS = {"gbp": "google_business", "linkedin_perso": "linkedin"}
SANS_SUPPRESSION = {"instagram", "tiktok", "threads"}
SANS_COMMENTAIRES = {"gbp", "pinterest"}
ETOILES = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}


def _http(methode: str, chemin: str, cle: str, data=None, files=None, json_=None, params=None,
          entetes: dict | None = None):
    """Le seul point de contact réseau — les bancs le remplacent.
    → (code HTTP, corps JSON)."""
    h = {"Authorization": f"Apikey {cle}"}
    h.update(entetes or {})
    try:
        url = chemin if chemin.startswith("https://") else BASE + chemin
        r = httpx.request(methode, url, headers=h, data=data, files=files, json=json_,
                          params=params, timeout=120)
    except httpx.HTTPError as e:
        raise PanneTransitoire(f"Upload-Post injoignable : {e}") from e
    if r.status_code >= 500:
        raise PanneTransitoire(f"Upload-Post {r.status_code}")
    try:
        return r.status_code, r.json()
    except ValueError:
        raise PanneTransitoire(f"Upload-Post {r.status_code} : réponse illisible")


def _fichier(chemin: str, champ: str):
    p = pathlib.Path(chemin)
    type_ = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    return (champ, (p.name, p.read_bytes(), type_))


def _identifiant(res: dict) -> str:
    for k in ("post_id", "publish_id", "video_id", "container_id"):
        v = res.get(k)
        if v:
            return str(v[0] if isinstance(v, list) else v)
    ids = res.get("post_ids")
    return str(ids[0]) if isinstance(ids, list) and ids else ""


class UploadPost(Publisher):
    mode = "agregateur"

    def __init__(self, platform, constraints, profile=""):
        super().__init__(platform, constraints, profile)
        self.cle = config.cle_upload_post()
        if not self.cle:
            raise NonBranche("UPLOAD_POST_API_KEY absente de l'environnement")
        if not profile:
            raise NonBranche(f"aucun profil Upload-Post relié pour {platform}")
        self.leur_nom = NOMS.get(platform, platform)
        self.options = {}               # posé par publieurs.pour (accounts.options)

    # ── Publier ──────────────────────────────────────────────────────────
    def _champs(self, post) -> list:
        """Les champs du formulaire, en liste de paires : `platform[]` peut se répéter."""
        o = {**self.options, **(post.options or {})}
        p = self.name
        f = [("user", self.profile), ("platform[]", self.leur_nom),
             ("request_id", f"alma-{post.post_id}"), ("external_id", f"alma-post-{post.post_id}"),
             ("title", post.text)]
        if p == "instagram":
            f.append(("media_type", "STORIES" if o.get("story") else ("REELS" if post.is_video else "IMAGE")))
        elif p == "facebook":
            if o.get("facebook_page_id"):
                f.append(("facebook_page_id", str(o["facebook_page_id"])))
        elif p == "linkedin":
            # La PAGE de l'entreprise. Sans cet identifiant, Upload-Post publie
            # sur le profil personnel : on préfère refuser que se tromper de voix.
            if not o.get("linkedin_page_id"):
                raise NonBranche("page LinkedIn non choisie (Réglages → comptes)")
            f += [("target_linkedin_page_id", str(o["linkedin_page_id"])),
                  ("linkedin_description", post.text)]
        elif p == "linkedin_perso":
            f.append(("linkedin_description", post.text))
        elif p == "tiktok":
            # En photo, le « titre » TikTok ne prend que 90 caractères : la
            # légende complète part en description.
            premiere = post.text.strip().split("\n")[0]
            f = [x for x in f if x[0] != "title"]
            f += [("title", premiere[:90]), ("tiktok_description", post.text),
                  ("privacy_level", o.get("tiktok_privacy", "PUBLIC_TO_EVERYONE"))]
        elif p == "pinterest":
            if not o.get("pinterest_board_id"):
                raise NonBranche("tableau Pinterest non choisi (Réglages → comptes)")
            f += [("pinterest_board_id", str(o["pinterest_board_id"])),
                  ("pinterest_title", (post.title or post.text)[:100]),
                  ("pinterest_description", post.text)]
            if post.link_url:
                f.append(("pinterest_link", post.link_url))
        elif p == "gbp":
            f.append(("gbp_language_code", "fr"))
            if o.get("gbp_location_id"):
                f.append(("gbp_location_id", str(o["gbp_location_id"])))
            if post.link_url:
                f += [("gbp_cta_type", o.get("cta", "LEARN_MORE")), ("gbp_cta_url", post.link_url)]
        elif p == "youtube":
            titre = (post.title or post.text.split("\n")[0])[:100]
            f = [x for x in f if x[0] != "title"]
            f += [("title", titre), ("youtube_title", titre), ("youtube_description", post.text),
                  ("privacyStatus", "public"), ("selfDeclaredMadeForKids", "false"),
                  ("containsSyntheticMedia", "false")]
        return f

    def publish(self, post):
        champs = self._champs(post)
        if post.is_video:
            chemin, fichiers = "/upload", [_fichier(post.media_path, "video")]
        else:
            chemin, fichiers = "/upload_photos", [_fichier(post.media_path, "photos[]")]
        code, rep = _http("POST", chemin, self.cle, data=champs, files=fichiers,
                          entetes={"Idempotency-Key": f"alma-post-{post.post_id}"})
        return self._lire_envoi(code, rep, post.post_id)

    def _lire_envoi(self, code, rep, post_id):
        rep = rep or {}
        if code == 429:
            # Plafond du jour atteint, ou trop de requêtes : rien n'est refusé,
            # c'est trop tôt. La file reprendra plus tard.
            raise PanneTransitoire(f"Upload-Post 429 : {rep.get('message', 'plafond atteint')}")
        if code in (401, 403):
            raise NonBranche(f"Upload-Post {code} : {rep.get('message', 'accès refusé')} (clé ou offre)")
        if code == 400 and rep.get("invalid_platforms"):
            raise NonBranche(f"{self.name} non relié chez Upload-Post : {rep['invalid_platforms']}")
        if code >= 400:
            raise RefusReseau(f"Upload-Post {code} : {rep.get('message') or rep.get('error') or 'refus'}")
        res = (rep.get("results") or {}).get(self.leur_nom)
        if res is None:
            if rep.get("request_id"):
                # Parti en arrière-plan (au-delà de 59 s, l'API bascule d'elle-même) :
                # la confirmation viendra de l'historique ou du webhook.
                return Resultat(external_id="", permalink="",
                                raw={"en_attente": True, "request_id": rep["request_id"]})
            raise RefusReseau(f"Upload-Post : aucune réponse pour {self.leur_nom}")
        if res.get("skipped"):
            raise NonBranche(f"{self.name} non relié au profil : {res.get('error', res.get('skip_reason'))}")
        if not res.get("success"):
            raise RefusReseau(f"{self.name} : {res.get('error') or res.get('error_code') or 'refus'}")
        return Resultat(external_id=_identifiant(res), permalink=res.get("url") or "",
                        raw={"request_id": f"alma-{post_id}", "warnings": res.get("warnings") or []})

    def confirmer(self, request_id: str):
        """Pour un envoi parti en arrière-plan : l'historique dit ce qu'il est devenu.
        → Resultat, None (pas encore), ou RefusReseau."""
        _, rep = _http("GET", "/uploadposts/history", self.cle, params={"request_id": request_id})
        lignes = [l for l in (rep or {}).get("history") or (rep or {}).get("data") or []
                  if l.get("platform") == self.leur_nom]
        if not lignes:
            return None
        l = lignes[0]
        if l.get("success"):
            pid = l.get("platform_post_id")
            pid = pid[0] if isinstance(pid, list) and pid else pid
            return Resultat(external_id=str(pid or ""), permalink=l.get("post_url") or "",
                            raw={"request_id": request_id})
        if l.get("error_message"):
            raise RefusReseau(f"{self.name} : {l['error_message']}")
        return None

    # ── Mesurer ──────────────────────────────────────────────────────────
    def metrics(self, external_id):
        if self.name == "gbp" or not external_id:
            return Mesures(raw={"note": "pas de statistiques par publication sur Google Business"})
        _, rep = _http("GET", "/uploadposts/post-analytics", self.cle,
                       params={"platform_post_id": external_id, "platform": self.leur_nom, "user": self.profile})
        bloc = (rep or {}).get("platforms", {}).get(self.leur_nom) or (rep or {}).get("metrics") or {}
        m = bloc.get("post_metrics") if isinstance(bloc, dict) and "post_metrics" in bloc else bloc
        m = m if isinstance(m, dict) else {}
        def n(*cles):
            for k in cles:
                if isinstance(m.get(k), (int, float)):
                    return int(m[k])
            return 0
        return Mesures(views=n("views", "impressions", "plays"), reach=n("reach", "unique_impressions"),
                       likes=n("likes", "reactions"), comments=n("comments", "replies"),
                       shares=n("shares", "reposts"), saves=n("saves", "saved"),
                       clicks=n("clicks", "outbound_clicks", "link_clicks"),
                       followers_gained=n("follows", "followers_gained", "subscribers_gained"), raw=m)

    # ── Conversations ────────────────────────────────────────────────────
    def comments(self, external_id):
        if self.name in SANS_COMMENTAIRES or not external_id:
            return []
        _, rep = _http("GET", "/uploadposts/comments", self.cle,
                       params={"platform": self.leur_nom, "user": self.profile, "post_id": external_id})
        out = []
        for c in (rep or {}).get("comments") or []:
            cid = str(c.get("id") or "")
            if not cid:
                continue
            auteur = c.get("user") or c.get("from") or {}
            # TikTok veut l'identifiant du post ET celui du commentaire pour répondre.
            ext = f"{external_id}:{cid}" if self.name == "tiktok" else cid
            out.append(Commentaire(external_id=ext, author=auteur.get("username") or auteur.get("name") or "",
                                   text=c.get("text") or c.get("message") or "",
                                   author_meta={"id": auteur.get("id")}, post_external_id=external_id))
        return out

    def reply(self, target_id, text):
        corps = {"platform": self.leur_nom, "user": self.profile, "message": text}
        if self.name == "tiktok" and ":" in target_id:
            corps["post_id"], corps["comment_id"] = target_id.split(":", 1)
        else:
            corps["comment_id"] = target_id
        code, rep = _http("POST", "/uploadposts/comments/create", self.cle, json_=corps)
        if code >= 400 or not (rep or {}).get("success", True):
            raise RefusReseau(f"réponse refusée : {(rep or {}).get('message', code)}")

    def delete(self, external_id):
        if self.name in SANS_SUPPRESSION:
            return False
        code, rep = _http("POST", "/uploadposts/posts/unpublish", self.cle,
                          json_={"platform": self.leur_nom, "user": self.profile, "post_id": external_id})
        if code == 404:
            return True             # déjà parti : le but est atteint
        if code >= 400:
            raise RefusReseau(f"retrait refusé : {(rep or {}).get('message', code)}")
        return True

    # ── Avis Google ──────────────────────────────────────────────────────
    def reviews(self):
        if self.name != "gbp":
            return []
        params = {"user": self.profile, "orderBy": "updateTime desc", "pageSize": 50}
        if self.options.get("gbp_location_id"):
            params["location_id"] = self.options["gbp_location_id"]
        _, rep = _http("GET", "/uploadposts/google-business/reviews", self.cle, params=params)
        out = []
        for r in (rep or {}).get("reviews") or []:
            note = r.get("starRating")
            out.append(Avis(external_id=str(r.get("name")),
                            rating=ETOILES.get(note, note if isinstance(note, int) else 0),
                            text=r.get("comment") or "", author=(r.get("reviewer") or {}).get("displayName", ""),
                            reply=(r.get("reviewReply") or {}).get("comment", "")))
        return out

    def reply_review(self, review_id, text):
        code, rep = _http("PUT", "/uploadposts/google-business/reviews/reply", self.cle,
                          json_={"user": self.profile, "comment": text, "review_name": review_id})
        if code >= 400 or not (rep or {}).get("success", True):
            raise RefusReseau(f"réponse à l'avis refusée : {(rep or {}).get('message', code)}")


def verifier_signature(secret: str, horodatage: str, corps: bytes, signature: str) -> bool:
    """Webhook : HMAC_SHA256(secret, "<horodatage>." + corps brut), en hexadécimal."""
    import hashlib
    import hmac
    if not (secret and horodatage and signature):
        return False
    attendu = hmac.new(secret.encode(), f"{horodatage}.".encode() + corps, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature.removeprefix("sha256="), attendu)


def lien_de_connexion(profil: str, retour: str, titre: str) -> str:
    """Le lien (valable 48 h) que le responsable d'une marque ouvre pour relier
    ses comptes, sans jamais nous confier un mot de passe."""
    cle = config.cle_upload_post()
    if not cle:
        raise NonBranche("UPLOAD_POST_API_KEY absente de l'environnement")
    _http("POST", "/uploadposts/users", cle, json_={"username": profil})        # 409 si déjà là : sans effet
    code, rep = _http("POST", "/uploadposts/users/generate-jwt", cle, json_={
        "username": profil, "redirect_url": retour, "language": "fr", "connect_title": titre,
        "connect_description": "Reliez les comptes de la marque. Aucun mot de passe ne nous est transmis."})
    if code >= 400 or not (rep or {}).get("access_url"):
        raise RefusReseau(f"lien de connexion refusé : {json.dumps(rep)[:200]}")
    return rep["access_url"]


def profil_de(marque_id: str) -> str:
    """Un profil Upload-Post par marque, nommé d'office : rien à inventer, rien à retenir."""
    return f"alma-{marque_id}"


def comptes_relies(profil: str) -> dict:
    """→ {notre réseau: {"nom": @compte, "reauth": bool}} pour les réseaux reliés au profil.
    Lu après la page de liaison, et par la page santé (jeton mort = « reauth »)."""
    cle = config.cle_upload_post()
    if not cle:
        raise NonBranche("UPLOAD_POST_API_KEY absente de l'environnement")
    code, rep = _http("GET", f"/uploadposts/users/{profil}", cle)
    if code == 404:
        return {}
    if code >= 400:
        raise RefusReseau(f"profil {profil} illisible : {code}")
    sociaux = ((rep or {}).get("profile") or rep or {}).get("social_accounts") or {}
    leurs = {v: k for k, v in NOMS.items() if k != "linkedin_perso"}
    out = {}
    for leur, compte in sociaux.items():
        if not compte:
            continue
        notre = leurs.get(leur, leur)
        out[notre] = {"nom": compte.get("handle") or compte.get("display_name") or compte.get("username") or "",
                      "reauth": bool(compte.get("reauth_required"))}
    return out


WEBHOOKS = "https://app.upload-post.com/api/uploadposts/users/notifications"    # hôte app., pas api.


def enregistrer_webhook(url: str) -> str:
    """Branche les notifications du compte sur notre adresse, et rend le secret
    `whsec_…` qui les signe. Appelé par le bouton du PDG : personne n'a à
    recopier ce secret, l'application le range chiffré."""
    cle = config.cle_upload_post()
    if not cle:
        raise NonBranche("UPLOAD_POST_API_KEY absente de l'environnement")
    code, rep = _http("POST", WEBHOOKS, cle, json_={
        "channels": {"webhook": True, "telegram": False}, "webhook_url": url,
        "webhook_events": {"upload_completed": True, "social_account_connected": True,
                           "social_account_disconnected": True, "social_account_reauth_required": True}})
    secret = ((rep or {}).get("notifications") or {}).get("webhook_secret") or ""
    if code >= 400 or not secret:
        raise RefusReseau(f"webhook refusé par Upload-Post ({code})")
    return secret
