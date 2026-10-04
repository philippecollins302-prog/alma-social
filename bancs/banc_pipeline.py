"""Banc : d'une photo déposée aux publications — et tous les garde-fous de la section 10."""
import datetime as dt
import io
import os

import socle
from socle import egal, verifier

from sqlalchemy import select, update

from alma_social import acces, alertes, db, file, garde_fous, graines, horloge, journal, pipeline, planificateur
from alma_social.publieurs import upload_post


def posts_de(asset_id):
    with db.moteur().begin() as c:
        return db.lignes(c.execute(select(db.posts).where(db.posts.c.asset_id == asset_id).order_by(db.posts.c.id)))


def avancer(heures, tours=3):
    """L'horloge avance ; la file traite ce qui est dû."""
    t = db.maintenant()
    for _ in range(tours):
        t += dt.timedelta(hours=heures / tours)
        db.figer_horloge(t)
        file.vider(500)


socle.figer(2026, 10, 5, 6)          # lundi 5 octobre, 8 h à Paris
graines.semer()
for m in acces.marques():
    planificateur.demarrer(m)

print("— Dépôt : idempotent, original intact")
photo = socle.image("chantier", graine=1)
a = pipeline.recevoir("rega", photo, "chantier.jpg", client_ref="tel-1")
egal(a["status"], "recu", "la photo est reçue")
egal(pipeline.recevoir("rega", photo, "chantier.jpg", client_ref="tel-1")["id"], a["id"],
     "renvoyée par la file du téléphone (même référence) : rien de nouveau")
egal(pipeline.recevoir("rega", photo, "copie.jpg", client_ref="tel-2").get("deja"), True,
     "la même photo redéposée : reconnue, rien de nouveau")
from alma_social import stockage
egal(stockage.chemin(a["original_path"]).read_bytes(), photo, "l'original est rangé octet pour octet")

print("— Lecture, placement, préparation (sans clé de modèle : repli local)")
file.vider(500)
a = pipeline.asset(a["id"])
egal(a["status"], "programme", "la photo est programmée sans que personne valide")
ps = posts_de(a["id"])
egal(sorted(p["platform"] for p in ps), sorted(acces.marque("rega")["active_platforms"]),
     "un post par réseau actif de REGA")
verifier(all(p["status"] == "programme" for p in ps), "tous programmés")
textes = {p["platform"]: p["text"] for p in ps}
verifier(all(garde_fous.similarite(x, y) <= 0.82 for i, x in enumerate(textes.values())
             for j, y in enumerate(textes.values()) if i < j), "aucun texte identique d'un réseau à l'autre")
verifier("/go/" not in textes["instagram"] and "lien en bio" in textes["instagram"],
         "Instagram : pas d'adresse dans la légende, « lien en bio »")
verifier("https://social.exemple.test/go/" in textes["facebook"], "Facebook : un lien tracé cliquable")
heures = sorted(p["scheduled_at"] for p in ps)
verifier(all((b - a_).total_seconds() >= 25 * 60 for a_, b in zip(heures, heures[1:])),
         "les réseaux d'une même photo sont décalés d'au moins 25 minutes")
with db.moteur().begin() as c:
    toks = [r["public_token"] for r in db.lignes(c.execute(select(db.renditions)))]
verifier(toks and all(len(t) >= 24 for t in toks), "chaque image publique a un jeton imprévisible")

print("— Publication dans le bac à sable")
n_alertes = len(alertes.ENVOYES)
avancer(48)
ps = posts_de(a["id"])
egal({p["status"] for p in ps}, {"simule"}, "tout est « simulé » : rien n'est sorti pour de vrai")
with db.moteur().begin() as c:
    pub = db.lignes(c.execute(select(db.audit_log).where(db.audit_log.c.action == "publication_simulee")))
verifier(len(pub) == len(ps) and all(l["after"]["texte"] and l["after"]["image_sha256"] for l in pub),
         "chaque publication au journal : texte exact et empreinte de l'image")
egal(len(alertes.ENVOYES), n_alertes, "aucune notification par publication")

print("— Refus technique : banque, journal, AUCUNE alerte")
petite = socle.image("petite", 500, 400, graine=2)
b = pipeline.recevoir("rega", petite, "petite.jpg")
n_alertes = len(alertes.ENVOYES)
file.vider(500)
b = pipeline.asset(b["id"])
egal(b["status"], "refuse", "photo trop petite écartée")
egal(len(alertes.ENVOYES), n_alertes, "pas d'alerte pour un refus technique")

print("— Anti-doublon visuel : la même photo réexportée")
from PIL import Image
im = Image.open(io.BytesIO(photo)).resize((1500, 1125))
t = io.BytesIO()
im.save(t, "JPEG", quality=70)
d = pipeline.recevoir("rega", t.getvalue(), "reexport.jpg")
file.vider(500)
d = pipeline.asset(d["id"])
egal(d["status"], "refuse", f"réexport reconnu à l'empreinte visuelle ({d['refusal_reason']})")

print("— Arrêt général : plus rien ne part ; à la levée, ça repart étalé")
e = pipeline.recevoir("lms-paca", socle.image("paca", graine=3), "paca.jpg")
file.vider(500)
journal.ecrire("arret_general", True, par="banc")
avancer(72)
ps = posts_de(e["id"])
egal({p["status"] for p in ps}, {"suspendu"}, "arrêt général : tout est suspendu")
journal.ecrire("arret_general", False, par="banc")
repris = pipeline.reprendre("banc")
egal(repris, len(ps), "à la levée : chaque publication repart")
heures = sorted(p["scheduled_at"] for p in posts_de(e["id"]))
verifier(len(set(heures)) == len(heures), "jamais toutes à la même minute")
avancer(24)
egal({p["status"] for p in posts_de(e["id"])}, {"simule"}, "puis elles sortent")

print("— Pause 48 h : rien ne repart sans action")
vip = acces.marque("vipplus")
f_ = pipeline.recevoir("vipplus", socle.image("vip", graine=4), "vip.jpg")
file.vider(500)
with db.moteur().begin() as c:
    c.execute(update(db.brands).where(db.brands.c.id == "vipplus").values(
        paused_until=db.maintenant() + dt.timedelta(hours=48), paused_reason="banc"))
avancer(60)
egal({p["status"] for p in posts_de(f_["id"])}, {"suspendu"}, "marque en pause : suspendu")
alertes.ENVOYES.clear()
horloge.echeances_de_pause()
horloge.echeances_de_pause()
egal(sum("pause de 48 h" in x["sujet"] for x in alertes.ENVOYES), 1, "à l'échéance : un rappel, un seul")
verifier(acces.en_pause(acces.marque("vipplus")), "et la marque reste en pause")

print("— Vrai envoi : 3 refus du même réseau → réseau en pause + alerte")
os.environ["UPLOAD_POST_API_KEY"] = "cle-de-banc"
journal.ecrire("bac_a_sable", False, par="banc")
from alma_social import securite
with db.moteur().begin() as c:
    c.execute(update(db.accounts).where(db.accounts.c.brand_id == "lms").values(
        status="actif", external_profile_enc=securite.chiffrer("alma-lms"),
        options={"linkedin_page_id": "123", "pinterest_board_id": "456"}))
APPELS = []


def faux_http(methode, chemin, cle, data=None, files=None, json_=None, params=None, entetes=None):
    champs = dict(data or [])
    APPELS.append((methode, chemin, champs.get("platform[]") or (json_ or {}).get("platform")))
    if chemin == "/upload_photos":
        pf = champs["platform[]"]
        if pf == "instagram":
            return 200, {"success": True, "results": {"instagram": {"success": False, "error": "media rejected"}}}
        return 200, {"success": True, "results": {pf: {"success": True, "post_id": f"{pf}-1", "url": f"https://{pf}.test/1"}}}
    if chemin == "/uploadposts/posts/unpublish":
        return 200, {"success": True}
    if chemin == "/uploadposts/post-analytics":
        return 200, {"platforms": {params["platform"]: {"post_metrics": {"views": 120, "likes": 9, "comments": 1}}}}
    raise AssertionError(chemin)


upload_post._http = faux_http
g = pipeline.recevoir("lms", socle.image("sol", graine=5), "sol.jpg")
file.vider(500)
alertes.ENVOYES.clear()
avancer(96, tours=12)
ps = {p["platform"]: p for p in posts_de(g["id"])}
egal(ps["instagram"]["status"], "echec", "Instagram : échec après trois refus")
egal(acces.compte("lms", "instagram")["status"], "pause", "Instagram mis en pause pour LMS")
verifier(any("Instagram mis en pause" in x["sujet"] for x in alertes.ENVOYES), "et une alerte part")
egal(ps["facebook"]["status"], "publie", "les autres réseaux, eux, sont publiés")
egal(ps["facebook"]["external_id"], "facebook-1", "avec l'identifiant externe du réseau")
egal(sum(1 for x in APPELS if x[1] == "/upload_photos" and x[2] == "instagram"), 3,
     "exactement trois essais sur le réseau qui refuse")

with db.moteur().begin() as c:
    vues = db.lignes(c.execute(select(db.metrics).where(db.metrics.c.post_id == ps["facebook"]["id"])))
verifier(vues and vues[0]["views"] == 120 and not vues[0]["simulated"], "les relevés réels sont enregistrés (+1 h, +24 h…)")

print("— Retirer partout")
rap = pipeline.retirer_partout(g["id"], "banc")
verifier("Facebook" in rap["retires"], "Facebook : retiré par l'API")
verifier(not any(x["reseau"] == "Instagram" for x in rap["a_la_main"]),
         "Instagram n'était pas sorti : rien à retirer à la main")
egal(pipeline.asset(g["id"])["status"], "retire", "la photo est marquée retirée")

print("— Journal")
try:
    with db.moteur().begin() as c:
        c.execute(update(db.audit_log).values(actor="pirate"))
    verifier(False, "la base refuse de modifier le journal")
except Exception:
    verifier(True, "la base refuse de modifier le journal")
egal(journal.verifier_chaine()["intact"], True, "chaîne intacte")
socle.fin()
