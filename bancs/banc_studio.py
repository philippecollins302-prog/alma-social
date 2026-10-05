"""Banc : le studio — une prise, plusieurs contenus, et la règle d'honnêteté.

On fabrique pour de vrai (ffmpeg, OpenCV) : un Reel, un carrousel, un
avant/après, un rideau. Et on vérifie que le studio REFUSE le fond studio à
une marque qui montre des réalisations — un chantier montré est ce
chantier-là."""
import io

import socle
from socle import egal, verifier

import numpy as np
from PIL import Image
from sqlalchemy import select

from alma_social import acces, db, graines, images, marque as marque_, pipeline, stockage, studio

socle.figer(2026, 10, 5, 6)
graines.semer()


def deposer(marque, n, nom):
    return [pipeline.recevoir(marque, socle.image(nom, graine=i + 1), f"{nom}{i}.jpg")["id"] for i in range(n)]


sazu = deposer("sazu", 3, "bowl")
rega = deposer("rega", 2, "chantier")

print("— La règle d'honnêteté")
egal(marque_.mise_en_scene(acces.marque("sazu")), "studio_permis", "SAZÚ (produit) : fond studio permis")
egal(marque_.mise_en_scene(acces.marque("rega")), "decor_reel", "REGA (réalisations) : décor réel")
try:
    studio.fond_studio(Image.new("RGB", (400, 300)), acces.marque("rega"))
    verifier(False, "fond studio refusé à REGA")
except studio.RegleHonnetete:
    verifier(True, "fond studio refusé à REGA")
try:
    studio.fabriquer("carrousel", "rega", rega, {"studio": True})
    verifier(False, "un carrousel « studio » de REGA est refusé")
except studio.RegleHonnetete:
    verifier(True, "un carrousel « studio » de REGA est refusé")

print("— Retouche culinaire et fond studio (SAZÚ)")
photo = images.ouvrir(stockage.chemin(pipeline.asset(sazu[0])["original_path"]))
ret, faits = studio.retouche_culinaire(photo)
egal(ret.size, photo.size, "la retouche garde la taille")
verifier("rééclairage doux" in faits and "chaleur" in faits, "la retouche dit ce qu'elle a fait")
# Un plat simple au centre d'une table : le fond doit changer, le plat non.
plat = Image.new("RGB", (800, 800), (70, 70, 80))
from PIL import ImageDraw
ImageDraw.Draw(plat).ellipse((250, 250, 550, 550), fill=(200, 120, 40))
out, f2 = studio.fond_studio(plat, acces.marque("sazu"), (0.28, 0.28, 0.72, 0.72))
a, b = np.asarray(plat).astype(int), np.asarray(out).astype(int)
verifier(np.abs(a[400, 400] - b[400, 400]).max() <= 6, "le centre du plat n'est pas repeint")
verifier(np.abs(a[20, 20] - b[20, 20]).max() > 60, "le coin (la table) devient fond studio")
verifier("plat d'origine intact (non repeint)" in f2, "le traitement le déclare")

print("— Le Reel")
j = studio.fabriquer("reel", "sazu", sazu, {"accroche": "Le bowl qui cale vraiment",
                                            "phrases": ["Riz, saumon, avocat", "prêt en dix minutes"],
                                            "cta": "Cherche SAZÚ sur Uber Eats"})
egal(j["statut"], "fait", "le travail est fait")
egal(j["sortie"]["params"]["avec_logo"], False, "le 5 octobre, le Reel SAZÚ est fabriqué SANS logo (révélation le 13/11)")
egal(len(j["fichiers"]), 1, "un fichier")
verifier(j["fichiers"][0]["video"] and j["fichiers"][0]["url"].endswith(".mp4"), "c'est une vidéo servie en .mp4")
with db.moteur().connect() as c:
    r = db.ligne(c.execute(select(db.renditions).where(db.renditions.c.id == j["fichiers"][0]["rendition_id"])))
octets = stockage.chemin(r["path"]).read_bytes()
verifier(len(octets) > 50_000 and octets[4:8] == b"ftyp", "un MP4 réel est écrit")
import imageio_ffmpeg
n, duree = imageio_ffmpeg.count_frames_and_secs(str(stockage.chemin(r["path"])))
verifier(abs(duree - (3 * 2.4 + 2)) < 0.3, f"durée attendue ({duree:.1f} s pour 3 photos + fin)")
verifier(stockage.chemin(r["path"]).with_suffix(".jpg").exists(), "une couverture JPEG l'accompagne")
verifier(any("aucune musique" in t for t in j["traitements"]), "aucune musique incrustée, et c'est écrit")
verifier(r["format"].endswith("v"), "le format de la déclinaison dit « vidéo »")

print("— Le carrousel")
j = studio.fabriquer("carrousel", "sazu", sazu, {"titre": "Trois bowls, trois humeurs",
                                                 "legendes": ["Le doux", "Le piquant"], "studio": True})
egal(len(j["fichiers"]), 4, "3 photos → couverture + 2 vues + vue d'appel = 4")
verifier(not any(f["video"] for f in j["fichiers"]), "que des images")
with db.moteur().connect() as c:
    rs = db.lignes(c.execute(select(db.renditions).where(
        db.renditions.c.id.in_([f["rendition_id"] for f in j["fichiers"]]))))
tailles = {Image.open(io.BytesIO(stockage.chemin(x["path"]).read_bytes())).size for x in rs}
egal(tailles, {images.FORMATS["4:5"]}, "toutes les vues en 4:5")
verifier(any("fond studio" in t for t in j["traitements"]), "le fond studio est tracé")
verifier(j["score"] and 50 <= j["score"] <= 95, "un potentiel estimé, borné")

print("— Avant / après (REGA, décor réel)")
j = studio.fabriquer("avant_apres", "rega", rega)
egal(len(j["fichiers"]), 1, "une image avant/après")
verifier(not any("fond studio" in t for t in j["traitements"]), "aucun fond studio sur un chantier")
j = studio.fabriquer("rideau", "rega", rega)
verifier(j["fichiers"][0]["video"], "le rideau est une vidéo")
try:
    studio.fabriquer("rideau", "rega", rega[:1])
    verifier(False, "un avant/après à une photo est refusé")
except ValueError:
    verifier(True, "un avant/après à une photo est refusé")
with db.moteur().connect() as c:
    echecs = db.lignes(c.execute(select(db.media_jobs).where(db.media_jobs.c.statut == "echec")))
egal(len(echecs), 1, "le refus laisse une trace « echec » avec sa raison")
verifier("deux photos" in (echecs[0]["erreur"] or ""), "la raison est écrite")

print("— Cloisonnement")
try:
    studio.fabriquer("carrousel", "sazu", rega)
    verifier(False, "les photos de REGA ne servent pas à SAZÚ")
except ValueError:
    verifier(True, "les photos de REGA ne servent pas à SAZÚ")
egal({t["brand_id"] for t in studio.travaux(["rega"])}, {"rega"}, "travaux() ne rend que les marques demandées")

print("— La rafale : trois photos SAZÚ → un Reel et un carrousel, puis le calendrier")
import datetime as dt
import os
from alma_social import file, planificateur
for m in acces.marques():
    planificateur.demarrer(m)
# Avant l'ouverture, une photo SAZÚ attend en banque : on se place après le 13/11.
# Les photos des essais ci-dessus sortent du jeu (elles prendraient les créneaux).
from sqlalchemy import update
with db.moteur().begin() as c:
    c.execute(update(db.assets).values(status="retire"))
    c.execute(update(db.jobs).where(db.jobs.c.status == "attente").values(status="fait"))
socle.figer(2026, 11, 16, 7)
ids = [pipeline.recevoir("sazu", socle.image("plat", graine=40 + i), f"plat{i}.jpg",
                         note=["Bowl saumon avocat", "Le piquant du chef", "Dessert maison"][i])["id"]
       for i in range(3)]
file.vider(500)
egal([pipeline.asset(i)["status"] for i in ids], ["banque"] * 3, "lues, en banque : le placement attend la rafale")
socle.figer(2026, 11, 16, 7, 12)
file.vider(500)
mt = studio.montages_de(ids[0])
egal(sorted(mt), ["carrousel", "reel"], "la 1re photo porte un Reel et un carrousel")
egal(sorted(mt["reel"]["asset_ids"]), sorted(ids), "le montage prend les trois photos")
egal(mt["reel"]["sortie"]["params"]["avec_logo"], True, "le 16 novembre, le logo est révélé : il signe le Reel")
egal([pipeline.asset(i)["status"] for i in ids[1:]], ["studio", "studio"], "les deux autres vivent dans le montage")
egal(pipeline.asset(ids[0])["status"], "programme", "la 1re photo est placée au calendrier")
with db.moteur().connect() as c:
    ps = db.lignes(c.execute(select(db.posts).where(db.posts.c.asset_id == ids[0])))
par_pf = {p["platform"]: p for p in ps if p["status"] in ("programme", "a_valider")}
verifier(par_pf, f"des publications préparées ({sorted(par_pf)})")
quand = max(p["scheduled_at"] for p in par_pf.values())
verifier("instagram" in par_pf and "facebook" in par_pf, "Instagram et Facebook sont dans le lot")
egal(par_pf.get("instagram", {}).get("post_format"), "reel", "Instagram : le Reel")
egal(par_pf.get("instagram", {}).get("media_job_id"), mt["reel"]["id"], "relié à son montage")
egal(par_pf.get("facebook", {}).get("post_format"), "carrousel", "Facebook : le carrousel")
egal(len(par_pf.get("facebook", {}).get("extra_renditions") or []), 3, "les vues 2 à 4 suivent la couverture")
egal(studio.rafale("sazu")["fait"], False, "relancer la rafale ne refait rien (photos déjà montées)")
egal(studio.rafale("rega")["fait"], False, "REGA : pas de montage automatique (décor réel)")

print("— Publication simulée du lot (bac à sable)")
socle.figer(*quand.timetuple()[:5])
file.vider(500)
socle.figer(*(quand + dt.timedelta(minutes=5)).timetuple()[:5])
file.vider(500)
with db.moteur().connect() as c:
    ps = db.lignes(c.execute(select(db.posts).where(db.posts.c.asset_id == ids[0])))
verifier(ps and all(p["status"] in ("simule", "publie") for p in ps if p["platform"] in ("instagram", "facebook")),
         f"Reel et carrousel partent (simulés) : {[(p['platform'], p['status']) for p in ps]}")

print("— L'envoi chez Upload-Post")
from alma_social.publieurs import upload_post
from alma_social.publieurs.base import PostPrepare
os.environ["UPLOAD_POST_API_KEY"] = "cle-de-banc"
envois = []


def faux_http(methode, chemin, cle, data=None, files=None, **k):
    envois.append((chemin, [f[0] for f in files or []], [f[1][0] for f in files or []], dict(data or [])))
    return 200, {"results": {"instagram": {"success": True, "post_id": "x", "url": "u"},
                             "facebook": {"success": True, "post_id": "y", "url": "u"}}}


upload_post._http = faux_http
cts = acces.contraintes()
fb = par_pf["facebook"]
r0 = pipeline._info_rendu(pipeline._un(db.renditions, fb["rendition_id"]))
extras = [pipeline._info_rendu(pipeline._un(db.renditions, x))["chemin"] for x in fb["extra_renditions"]]
upload_post.UploadPost("facebook", cts["facebook"], "alma-sazu").publish(PostPrepare(
    post_id=7, brand_id="sazu", platform="facebook", text="t", title="", media_url="", media_path=r0["chemin"],
    is_video=False, extra_paths=extras))
egal(envois[-1][0], "/upload_photos", "carrousel : /upload_photos")
egal(envois[-1][1], ["photos[]"] * 4, "quatre photos[] dans un seul envoi")
egal(envois[-1][2], [f"vue-0{i}.jpg" for i in range(1, 5)], "dans l'ordre : couverture d'abord, appel à l'action en dernier")
ig = par_pf["instagram"]
r1 = pipeline._info_rendu(pipeline._un(db.renditions, ig["rendition_id"]))
upload_post.UploadPost("instagram", cts["instagram"], "alma-sazu").publish(PostPrepare(
    post_id=8, brand_id="sazu", platform="instagram", text="t", title="", media_url="", media_path=r1["chemin"],
    is_video=r1["video"]))
egal((envois[-1][0], envois[-1][1]), ("/upload", ["video"]), "Reel : /upload avec la vidéo")
egal(envois[-1][3].get("media_type"), "REELS", "Instagram : media_type REELS")
verifier(abs(r1["duree"] - 9.2) < 0.2, f"la vraie durée du Reel est connue ({r1['duree']} s)")

print("— La déclinaison totale : une prise, tous les formats")
with db.moteur().begin() as c:
    c.execute(update(db.assets).where(db.assets.c.id == rega[0]).values(status="banque"))
j = studio.fabriquer("declinaison", "rega", [rega[0]], {"titre": "Un sol posé en deux jours"})
egal(j["statut"], "fait", "fabriquée")
tailles = {}
for f, s_ in zip(j["fichiers"], j["sortie"]["fichiers"]):
    r = pipeline._info_rendu(pipeline._un(db.renditions, f["rendition_id"]))
    tailles[s_["cle"]] = (r["largeur"], r["hauteur"])
egal(tailles, {"carre": (1080, 1080), "portrait": (1080, 1350), "story": (1080, 1920), "linkedin": (1200, 627),
               "miniature": (1280, 720), "google": (1200, 900)}, "six formats, aux tailles des réseaux")
verifier(all(s_["nom"] for s_ in j["sortie"]["fichiers"]), "chaque format dit à quoi il sert")
mini = images.ouvrir(stockage.chemin(pipeline._un(db.renditions, j["fichiers"][4]["rendition_id"])["path"]))
lin = images.ouvrir(stockage.chemin(pipeline._un(db.renditions, j["fichiers"][3]["rendition_id"])["path"]))
gauche = np.asarray(mini.crop((40, 200, 600, 520))).std()
verifier(gauche > 20, "la miniature YouTube porte son titre (zone de gauche contrastée)")
try:
    studio.fabriquer("declinaison", "rega", rega[:2], {})
    verifier(False, "deux photos : refusé")
except ValueError:
    verifier(True, "une déclinaison part d'une seule photo")
try:
    studio.fabriquer("declinaison", "rega", [rega[0]], {"studio": True})
    verifier(False, "fond studio refusé à REGA, même en déclinaison")
except studio.RegleHonnetete:
    verifier(True, "fond studio refusé à REGA, même en déclinaison")

socle.fin()
