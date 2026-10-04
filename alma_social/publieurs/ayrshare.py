"""Ayrshare — agrégateur de REPLI (le plus complet, mais hors budget pour six marques).

Gardé branché derrière la même interface : si un jour Upload-Post ne suffit
plus, on bascule `SOCIAL_AGREGATEUR=ayrshare` et rien d'autre ne bouge.
Référence lue le 2026-10-04 : docs/recherche/agregateur.md, partie B
(https://www.ayrshare.com/docs/apis/…).

Un profil Ayrshare = une marque ; sa clé (`Profile-Key`) est stockée chiffrée
sur chaque compte. Chaque publication part réseau par réseau, avec SON texte.
"""
from __future__ import annotations

import httpx

from .. import config
from .base import (Avis, Commentaire, Mesures, NonBranche, PanneTransitoire, Publisher,
                   RefusReseau, Resultat)

BASE = "https://api.ayrshare.com/api"
NOMS = {"gbp": "gmb", "linkedin_perso": "linkedin"}          # nos clés → les leurs
SANS_SUPPRESSION = {"instagram", "tiktok", "threads"}        # pas de retrait par l'API


def _http(methode: str, chemin: str, cle: str, profil: str = "", json=None, params=None):
    """Le seul point de contact réseau — les bancs le remplacent."""
    h = {"Authorization": f"Bearer {cle}", "Content-Type": "application/json"}
    if profil:
        h["Profile-Key"] = profil
    try:
        r = httpx.request(methode, BASE + chemin, headers=h, json=json, params=params, timeout=60)
    except httpx.HTTPError as e:
        raise PanneTransitoire(f"Ayrshare injoignable : {e}") from e
    if r.status_code >= 500 or r.status_code == 429:
        raise PanneTransitoire(f"Ayrshare {r.status_code}")
    try:
        return r.status_code, r.json()
    except ValueError:
        raise PanneTransitoire(f"Ayrshare {r.status_code} : réponse illisible")


def _premier(corps: dict) -> dict:
    """Avec une Profile-Key, la réponse est enveloppée dans `posts[]`."""
    if isinstance(corps, dict) and isinstance(corps.get("posts"), list) and corps["posts"]:
        return corps["posts"][0]
    return corps


def _erreurs(corps: dict) -> list:
    return [e for e in (corps.get("errors") or []) if isinstance(e, dict)]


class Ayrshare(Publisher):
    mode = "agregateur"

    def __init__(self, platform, constraints, profile=""):
        super().__init__(platform, constraints, profile)
        self.cle = config.cle_ayrshare()
        if not self.cle:
            raise NonBranche("AYRSHARE_API_KEY absente de l'environnement")
        self.leur_nom = NOMS.get(platform, platform)

    def _options(self, post) -> dict:
        p, o = self.name, {}
        if p == "youtube":
            o["youTubeOptions"] = {"title": (post.title or post.text[:90])[:100], "shorts": True,
                                   "visibility": "public"}
        elif p == "pinterest":
            o["pinterestOptions"] = {"title": (post.title or "")[:100], "link": post.link_url}
            if post.options.get("board"):
                o["pinterestOptions"]["boardId"] = post.options["board"]
        elif p == "gbp" and post.link_url:
            o["gmbOptions"] = {"callToAction": {"actionType": post.options.get("cta", "learn_more"),
                                                "url": post.link_url}}
        elif p == "tiktok":
            o["tikTokOptions"] = {"visibility": "public"}
        elif p == "instagram" and post.options.get("story"):
            o["instagramOptions"] = {"stories": True}
        return o

    def publish(self, post):
        corps = {"post": post.text, "platforms": [self.leur_nom], "mediaUrls": [post.media_url],
                 "idempotencyKey": f"alma-post-{post.post_id}"}
        if post.is_video:
            corps["isVideo"] = True
        corps.update(self._options(post))
        code, rep = _http("POST", "/post", self.cle, self.profile, json=corps)
        rep = _premier(rep)
        errs = _erreurs(rep)
        if code >= 400 or rep.get("status") == "error" or errs:
            e = errs[0] if errs else {}
            msg = f"Ayrshare {e.get('code', code)} : {e.get('message', rep.get('message', 'refus'))}"
            if e.get("code") in (156,):
                raise NonBranche(msg + " (compte non relié chez l'agrégateur)")
            raise RefusReseau(msg)
        ids = [x for x in rep.get("postIds") or [] if x.get("platform") == self.leur_nom]
        x = ids[0] if ids else {}
        return Resultat(external_id=rep.get("id", ""), permalink=x.get("postUrl", ""),
                        raw={"social_id": x.get("id"), "reponse": rep})

    def metrics(self, external_id):
        if self.name == "gbp":
            return Mesures(raw={"note": "pas d'analytics par post sur Google Business"})
        _, rep = _http("POST", "/analytics/post", self.cle, self.profile,
                       json={"id": external_id, "platforms": [self.leur_nom]})
        a = ((rep or {}).get(self.leur_nom) or {}).get("analytics") or {}
        return _traduire(self.name, a)

    def comments(self, external_id):
        _, rep = _http("GET", f"/comments/{external_id}", self.cle, self.profile)
        out = []
        for c in (rep or {}).get(self.leur_nom) or []:
            out.append(Commentaire(external_id=str(c.get("commentId") or c.get("id")),
                                   author=(c.get("from") or {}).get("username") or (c.get("from") or {}).get("name", ""),
                                   text=c.get("comment", ""), post_external_id=external_id))
        return out

    def reply(self, target_id, text):
        code, rep = _http("POST", f"/comments/reply/{target_id}", self.cle, self.profile,
                          json={"comment": text, "platforms": [self.leur_nom]})
        if code >= 400:
            raise RefusReseau(f"réponse refusée : {rep}")

    def delete(self, external_id):
        if self.name in SANS_SUPPRESSION:
            return False
        code, rep = _http("DELETE", "/post", self.cle, self.profile, json={"id": external_id})
        if code >= 400 and "383" not in str(rep):
            raise RefusReseau(f"retrait refusé : {rep}")
        return True

    def reviews(self):
        if self.name != "gbp":
            return []
        _, rep = _http("GET", "/reviews", self.cle, self.profile, params={"platform": "gmb"})
        etoiles = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}
        out = []
        for r in (rep or {}).get("gmb") or []:
            note = r.get("rating")
            out.append(Avis(external_id=str(r.get("id")), rating=etoiles.get(note, note if isinstance(note, int) else 0),
                            text=r.get("review", ""), author=(r.get("reviewer") or {}).get("name", ""),
                            reply=(r.get("reviewReply") or {}).get("reply", "")))
        return out

    def reply_review(self, review_id, text):
        code, rep = _http("POST", "/reviews", self.cle, self.profile,
                          json={"platform": "gmb", "reviewId": review_id, "reply": text})
        if code >= 400:
            raise RefusReseau(f"réponse à l'avis refusée : {rep}")


# Chaque réseau a ses propres noms de champs : la table de correspondance.
_CHAMPS = {
    "instagram": {"views": ["viewsCount", "playsCount"], "reach": ["reachCount"], "likes": ["likeCount"],
                  "comments": ["commentsCount"], "shares": ["sharesCount"], "saves": ["savedCount"],
                  "followers_gained": ["followsCount"]},
    "facebook": {"views": ["mediaView", "totalVideoViews"], "likes": ["likeCount"], "comments": ["commentsCount"],
                 "shares": ["sharesCount"]},
    "linkedin": {"views": ["impressionCount"], "reach": ["uniqueImpressionsCount"], "likes": ["likeCount"],
                 "comments": ["commentCount"], "shares": ["shareCount"], "clicks": ["clickCount"]},
    "tiktok": {"views": ["videoViews"], "reach": ["reach"], "likes": ["likeCount"], "comments": ["commentsCount"],
               "shares": ["shareCount"]},
    "youtube": {"views": ["views"], "likes": ["likes"], "comments": ["comments"], "followers_gained": ["subscribersGained"]},
    "pinterest": {"views": ["impression"], "clicks": ["outboundClick", "pinClick"], "saves": ["save"],
                  "comments": ["totalComments"], "likes": ["totalReactions"], "followers_gained": ["userFollow"]},
    "threads": {"views": ["views"], "likes": ["likes"], "comments": ["replies"], "shares": ["reposts", "shares", "quotes"]},
}
_CHAMPS["linkedin_perso"] = _CHAMPS["linkedin"]


def _traduire(reseau: str, a: dict) -> Mesures:
    m = Mesures(raw=a)
    for champ, cles in _CHAMPS.get(reseau, {}).items():
        valeurs = [a.get(k) for k in cles if isinstance(a.get(k), (int, float))]
        if valeurs:
            v = sum(valeurs) if champ == "shares" else valeurs[0]
            setattr(m, champ, int(v))
    return m
