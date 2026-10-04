"""Banc : le publieur Upload-Post, et le webhook qui lui répond.

Rien ne sort : `upload_post._http` est remplacé par un faux qui n'accepte que
ce qu'on lui a appris, et le webhook est appelé par le client de test de
FastAPI, signé comme Upload-Post signe.
"""
import hashlib
import hmac
import json
import os
import time

import socle
from socle import egal, verifier

from sqlalchemy import select, update

from alma_social import acces, alertes, db, file, graines, journal, pipeline, securite
from alma_social.publieurs import upload_post
from alma_social.publieurs.base import NonBranche, PanneTransitoire, PostPrepare, RefusReseau

socle.figer(2026, 10, 5, 6)
graines.semer()
os.environ["UPLOAD_POST_API_KEY"] = "cle-de-banc"
cts = acces.contraintes()
photo = socle.ICI / "photo-banc.jpg"
photo.write_bytes(socle.image("banc", graine=3))


def pub(pf, options=None):
    p = upload_post.UploadPost(pf, cts.get(pf), "alma-rega")
    p.options = dict(options or {})
    return p


def post(pf, texte="Chantier du jour à Montpellier.\nDeuxième ligne.", lien="", titre="", video=False):
    return PostPrepare(post_id=42, brand_id="rega", platform=pf, text=texte, title=titre,
                       media_url="https://social.exemple.test/m/x", media_path=str(photo),
                       is_video=video, link_url=lien)


def leve(f, classe):
    try:
        f()
    except classe as e:
        return str(e) or True
    except Exception as e:                      # une autre classe : c'est un défaut
        return f"MAUVAISE CLASSE {type(e).__name__}"
    return None


print("— Sans clé, sans profil : refus net, rien ne part")
os.environ.pop("UPLOAD_POST_API_KEY")
verifier(leve(lambda: upload_post.UploadPost("facebook", cts["facebook"], "alma-rega"), NonBranche),
         "sans UPLOAD_POST_API_KEY : NonBranche")
os.environ["UPLOAD_POST_API_KEY"] = "cle-de-banc"
verifier(leve(lambda: upload_post.UploadPost("facebook", cts["facebook"], ""), NonBranche),
         "sans profil relié : NonBranche")

print("— Les champs envoyés, réseau par réseau")
f = dict(pub("instagram")._champs(post("instagram")))
egal((f["user"], f["platform[]"], f["media_type"]), ("alma-rega", "instagram", "IMAGE"),
     "Instagram : le profil de la marque, une image")
egal(f["request_id"], "alma-42", "un request_id par post (le renvoi se reconnaît)")
egal(dict(pub("instagram", {"story": True})._champs(post("instagram")))["media_type"], "STORIES",
     "Instagram : l'option story")
egal(dict(pub("instagram")._champs(post("instagram", video=True)))["media_type"], "REELS",
     "Instagram : une vidéo part en Reel")
egal(dict(pub("facebook", {"facebook_page_id": 777})._champs(post("facebook")))["facebook_page_id"], "777",
     "Facebook : la page choisie")
verifier(leve(lambda: pub("linkedin")._champs(post("linkedin")), NonBranche),
         "LinkedIn sans page choisie : refusé (jamais le profil personnel par erreur)")
f = dict(pub("linkedin", {"linkedin_page_id": 9})._champs(post("linkedin")))
egal(f["target_linkedin_page_id"], "9", "LinkedIn : la page de l'entreprise")
f = dict(pub("linkedin_perso")._champs(post("linkedin_perso")))
egal((f["platform[]"], "target_linkedin_page_id" in f), ("linkedin", False),
     "LinkedIn personnel : la plateforme « linkedin », sans page")
f = pub("tiktok")._champs(post("tiktok", texte="A" * 150 + "\nsuite"))
egal(sum(1 for k, _ in f if k == "title"), 1, "TikTok : un seul titre")
egal(len(dict(f)["title"]), 90, "TikTok : titre coupé à 90 caractères")
verifier(dict(f)["tiktok_description"].endswith("suite"), "TikTok : la légende entière en description")
verifier(leve(lambda: pub("pinterest")._champs(post("pinterest")), NonBranche), "Pinterest sans tableau : refusé")
f = dict(pub("pinterest", {"pinterest_board_id": 5})._champs(post("pinterest", lien="https://x.test/go/a")))
egal((f["pinterest_board_id"], f["pinterest_link"]), ("5", "https://x.test/go/a"), "Pinterest : tableau et lien")
f = dict(pub("gbp", {"gbp_location_id": "loc-1"})._champs(post("gbp", lien="https://x.test/go/b")))
egal((f["platform[]"], f["gbp_language_code"], f["gbp_location_id"], f["gbp_cta_url"]),
     ("google_business", "fr", "loc-1", "https://x.test/go/b"), "Google Business : en français, bouton vers le lien tracé")
f = pub("youtube")._champs(post("youtube", video=True, titre="T" * 140))
egal((sum(1 for k, _ in f if k == "title"), len(dict(f)["youtube_title"])), (1, 100),
     "YouTube : un seul titre, coupé à 100")

print("— Lire la réponse : un 200 ne prouve rien")
p = pub("facebook")
egal(p._lire_envoi(200, {"results": {"facebook": {"success": True, "post_id": "fb-1", "url": "https://f/1"}}},
                   42).external_id, "fb-1", "succès : l'identifiant du réseau")
r = p._lire_envoi(200, {"results": {"facebook": {"success": True, "post_ids": ["fb-2"],
                                                 "warnings": ["image recadrée"]}}}, 42)
egal((r.external_id, r.raw["warnings"]), ("fb-2", ["image recadrée"]), "un avertissement reste un succès")
verifier(leve(lambda: p._lire_envoi(200, {"results": {"facebook": {"success": False, "error": "x"}}}, 42),
              RefusReseau), "200 mais success=false pour CE réseau : refus")
verifier(leve(lambda: p._lire_envoi(200, {"results": {"facebook": {"skipped": True, "error": "non relié"}}}, 42),
              NonBranche), "skipped : un réglage manquant, pas un refus")
verifier(leve(lambda: p._lire_envoi(429, {"message": "quota"}, 42), PanneTransitoire),
         "429 : trop tôt, la file reprendra (ne compte pas comme refus)")
verifier(leve(lambda: p._lire_envoi(401, {}, 42), NonBranche), "401 : clé ou offre")
verifier(leve(lambda: p._lire_envoi(400, {"invalid_platforms": ["facebook"]}, 42), NonBranche),
         "400 réseau non relié : NonBranche")
verifier(leve(lambda: p._lire_envoi(400, {"message": "caption too long"}, 42), RefusReseau), "400 autre : refus")
r = p._lire_envoi(200, {"request_id": "abc"}, 42)
verifier(r.raw.get("en_attente") and r.external_id == "", "parti en arrière-plan : en attente, pas publié")

print("— Retirer, comptes reliés")
verifier(pub("instagram").delete("ig-1") is False, "Instagram ne se retire pas par API : on le dit")
APPELS = []


def faux(methode, chemin, cle, data=None, files=None, json_=None, params=None, entetes=None):
    APPELS.append((methode, chemin, json_ or params or dict(data or [])))
    if chemin == "/uploadposts/posts/unpublish":
        return 404, {"message": "not found"}
    if chemin == "/uploadposts/users/alma-rega":
        return 200, {"profile": {"social_accounts": {
            "google_business": {"display_name": "REGA Montpellier"},
            "instagram": {"handle": "rega.construction", "reauth_required": True},
            "tiktok": None}}}
    if chemin == "/uploadposts/users/alma-vide":
        return 404, {}
    if chemin == "/upload_photos":
        return 200, {"results": {"facebook": {"success": True, "post_id": "fb-9"}}}
    raise AssertionError(chemin)


upload_post._http = faux
verifier(pub("facebook").delete("fb-1") is True, "déjà parti (404) : le but est atteint")
egal(upload_post.comptes_relies("alma-rega"),
     {"gbp": {"nom": "REGA Montpellier", "reauth": False}, "instagram": {"nom": "rega.construction", "reauth": True}},
     "les comptes reliés, dans nos noms (google_business → gbp), un compte vide ignoré")
egal(upload_post.comptes_relies("alma-vide"), {}, "profil inconnu : aucun compte, pas d'erreur")
egal(upload_post.profil_de("sazu"), "alma-sazu", "un profil par marque, nommé d'office")
r = pub("facebook").publish(post("facebook"))
egal(r.external_id, "fb-9", "publish : un envoi multipart sur /upload_photos")

print("— La signature du webhook")
S = "secret-de-banc"
corps = b'{"event":"upload_completed"}'
sig = hmac.new(S.encode(), b"1700000000." + corps, hashlib.sha256).hexdigest()
verifier(upload_post.verifier_signature(S, "1700000000", corps, "sha256=" + sig), "bonne signature : acceptée")
verifier(not upload_post.verifier_signature(S, "1700000001", corps, "sha256=" + sig), "horodatage changé : refusée")
verifier(not upload_post.verifier_signature(S, "1700000000", corps + b" ", "sha256=" + sig), "corps changé : refusé")
verifier(not upload_post.verifier_signature("", "1700000000", corps, "sha256=" + sig), "sans secret : tout est refusé")

print("— Le webhook, de bout en bout")
from fastapi.testclient import TestClient
import app as appli

client = TestClient(appli.app)
os.environ["UPLOAD_POST_WEBHOOK_SECRET"] = S


def envoyer(ev, ts=None, livraison="", signer=True):
    b = json.dumps(ev).encode()
    ts = str(int(time.time()) if ts is None else ts)
    s = hmac.new(S.encode(), ts.encode() + b"." + b, hashlib.sha256).hexdigest() if signer else "0" * 64
    h = {"x-upload-post-timestamp": ts, "x-upload-post-signature": "sha256=" + s, "content-type": "application/json"}
    if livraison:
        h["x-upload-post-delivery"] = livraison
    return client.post("/webhooks/upload-post", content=b, headers=h).status_code


egal(envoyer({"event": "x"}, signer=False), 401, "signature fausse : 401")
egal(envoyer({"event": "x"}, ts=int(time.time()) - 3600), 401, "signée il y a une heure (rejeu) : 401")
egal(envoyer({"event": "x", "profile_username": "inconnu"}), 200, "événement d'un profil étranger : ignoré")

# REGA, Facebook relié par l'agrégateur ; un post part, la confirmation vient du webhook.
journal.ecrire("bac_a_sable", False, par="banc")
with db.moteur().begin() as c:
    c.execute(update(db.accounts).where(db.accounts.c.brand_id == "rega").values(
        status="actif", external_profile_enc=securite.chiffrer("alma-rega"),
        options={"linkedin_page_id": "1", "pinterest_board_id": "2"}))
a = pipeline.recevoir("rega", socle.image("toiture", graine=8), "toiture.jpg")
file.vider(500)
with db.moteur().begin() as c:
    fb = db.ligne(c.execute(select(db.posts).where(db.posts.c.asset_id == a["id"], db.posts.c.platform == "facebook")))
    c.execute(update(db.posts).where(db.posts.c.id == fb["id"]).values(status="envoi"))
ev = {"event": "upload_completed", "profile_username": "alma-rega", "platform": "facebook",
      "result": {"success": True, "post_id": "fb-webhook", "url": "https://facebook.test/p"}}
egal(envoyer(ev, livraison="d-1"), 200, "confirmation de publication : 200")
with db.moteur().begin() as c:
    fb = db.ligne(c.execute(select(db.posts).where(db.posts.c.id == fb["id"])))
egal((fb["status"], fb["external_id"]), ("publie", "fb-webhook"), "le post passe à « publié » avec son identifiant")
egal(envoyer(ev, livraison="d-1"), 200, "la même livraison rejouée : 200, sans effet")

alertes.ENVOYES.clear()
egal(envoyer({"event": "social_account_reauth_required", "profile_username": "alma-rega",
              "platform": "instagram", "reason": "token expired"}, livraison="d-2"), 200, "compte à reconnecter : 200")
egal(acces.compte("rega", "instagram")["status"], "erreur", "Instagram de REGA : en erreur, plus rien n'y part")
verifier(any("à reconnecter" in x["sujet"] for x in alertes.ENVOYES), "et une alerte nomme le réseau à reconnecter")
egal(envoyer({"event": "social_account_connected", "profile_username": "alma-rega", "platform": "instagram",
              "account_name": "rega.construction"}, livraison="d-3"), 200, "reconnecté : 200")
egal(acces.compte("rega", "instagram")["status"], "actif", "Instagram de REGA : de nouveau actif")

print("— Brancher les notifications : un bouton, aucun secret recopié à la main")
os.environ.pop("UPLOAD_POST_WEBHOOK_SECRET")
appli._LIVRAISONS_VUES.clear()
NOUVEAU = "secret-range-par-l-application"


def faux_webhook(methode, chemin, cle, data=None, files=None, json_=None, params=None, entetes=None):
    APPELS.append((methode, chemin, json_))
    if chemin == upload_post.WEBHOOKS:
        return 200, {"success": True, "notifications": {"webhook_secret": NOUVEAU}}
    raise AssertionError(chemin)


upload_post._http = faux_webhook
pdg = TestClient(appli.app, base_url="https://social.exemple.test")
pdg.post("/api/connexion", json={"code": "101010"}, headers={"X-Alma": "1"})
egal(pdg.post("/api/webhook/brancher", json={}, headers={"X-Alma": "1"}).status_code, 200, "le PDG branche les notifications")
m, chemin, corps = APPELS[-1]
egal(chemin, "https://app.upload-post.com/api/uploadposts/users/notifications", "sur l'hôte app. (et non api.)")
egal(corps["webhook_url"], "https://social.exemple.test/webhooks/upload-post", "vers notre adresse publique")
verifier(NOUVEAU not in json.dumps(journal.lire("webhook_upload_post")), "le secret est rangé chiffré, pas en clair")
verifier(not any(NOUVEAU in json.dumps(l["after"] or {}) for l in db.lignes(
    db.moteur().connect().execute(select(db.audit_log)))), "et n'apparaît pas au journal")
S = NOUVEAU
egal(envoyer({"event": "x", "profile_username": "inconnu"}, livraison="d-9"), 200,
     "une notification signée avec ce secret est acceptée")
egal(pdg.get("/api/sante").json()["cles"]["webhook"], True, "la santé le dit branché")
lucie = TestClient(appli.app, base_url="https://social.exemple.test")
lucie.post("/api/connexion", json={"code": "202020"}, headers={"X-Alma": "1"})
egal(lucie.post("/api/webhook/brancher", json={}, headers={"X-Alma": "1"}).status_code, 403, "réservé au PDG")

photo.unlink()
socle.fin()
