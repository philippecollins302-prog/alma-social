"""Banc : l'application web — la porte, le cloisonnement, les routes publiques de la mesure.

Le client de test de FastAPI parle à l'application sans réseau. Deux
personnes : le PDG (il voit tout) et la responsable SAZÚ (elle ne voit que
SAZÚ — une autre marque lui répond 404, on ne lui confirme même pas qu'elle
existe).
"""
import json
import re
import urllib.parse

import socle
from socle import egal, verifier

from fastapi.testclient import TestClient
from sqlalchemy import select

from alma_social import acces, db, file, graines, journal, mesure, pipeline

socle.figer(2026, 12, 2, 9)          # mercredi 2 décembre : SAZÚ est ouvert
graines.semer()
import app as appli                  # noqa: E402

X = {"X-Alma": "1"}


def client(code=None):
    c = TestClient(appli.app, base_url="https://social.exemple.test")
    if code:
        r = c.post("/api/connexion", json={"code": code}, headers=X)
        assert r.status_code == 200, r.text
    return c


print("— La porte")
anonyme = client()
egal(anonyme.get("/sante").text, "ok", "/sante répond sans session (pour l'hébergeur)")
egal(anonyme.get("/api/moi").status_code, 401, "sans session : 401")
egal(anonyme.post("/api/connexion", json={"code": "999999"}, headers=X).status_code, 401, "code inconnu : 401")
egal(anonyme.post("/api/connexion", json={"code": "101010"}).status_code, 403,
     "écriture sans l'en-tête X-Alma (formulaire d'un autre site) : 403")
pdg = client("101010")
verifier(pdg.cookies.get("alma_social"), "connexion : un cookie de session")
moi = pdg.get("/api/moi").json()
egal(moi["utilisateur"]["role"], "pdg", "le PDG est reconnu")
egal(len(moi["marques"]), 6, "le PDG voit les six marques")
verifier(moi["bac_a_sable"], "à l'installation, le bac à sable est OUVERT : rien ne sort")
r = pdg.get("/api/moi")
egal((r.headers.get("x-content-type-options"), r.headers.get("referrer-policy")),
     ("nosniff", "strict-origin-when-cross-origin"), "en-têtes de sécurité posés")

essais = client()
for _ in range(6):
    essais.post("/api/connexion", json={"code": "000000"}, headers={**X, "X-Forwarded-For": "203.0.113.9"})
egal(essais.post("/api/connexion", json={"code": "101010"}, headers={**X, "X-Forwarded-For": "203.0.113.9"})
     .status_code, 429, "six codes faux de la même adresse : la porte se ferme un moment")

print("— Le cloisonnement")
lucie = client("202020")
mm = lucie.get("/api/moi").json()
egal([m["id"] for m in mm["marques"]], ["sazu"], "la responsable SAZÚ ne voit que SAZÚ")
egal(mm["utilisateur"]["role"], "responsable", "et elle est responsable, pas PDG")
egal(lucie.get("/api/photos?marque=rega").status_code, 404, "une autre marque : 404, pas 403")
egal(lucie.get("/logo/rega").status_code, 404, "le logo d'une autre marque : 404")
egal(lucie.post("/api/marque/rega/pause", json={}, headers=X).status_code, 404, "mettre REGA en pause : 404")
egal(lucie.get("/api/tableau?marque=lms").status_code, 404, "le tableau d'une autre marque : 404")
egal(lucie.post("/api/arret", json={"actif": True}, headers=X).status_code, 403, "le STOP général : réservé au PDG")
egal(lucie.post("/api/bac-a-sable", json={"ouvert": False}, headers=X).status_code, 403,
     "ouvrir les vannes : réservé au PDG")
egal(lucie.get("/api/journal/verifier").status_code, 403, "vérifier la chaîne du journal : réservé au PDG")

print("— Le dépôt, depuis le téléphone")
photo = socle.image("bowl", graine=4)
r = lucie.post("/api/depot", data={"marque": "sazu", "refs": "tel-a"},
               files=[("photos", ("bowl.jpg", photo, "image/jpeg"))], headers=X)
egal(r.status_code, 200, "dépôt SAZÚ : 200")
res = r.json()["resultats"][0]
verifier(res["ok"] and not res["deja"], "la photo est reçue")
r = lucie.post("/api/depot", data={"marque": "sazu", "refs": "tel-a"},
               files=[("photos", ("bowl.jpg", photo, "image/jpeg"))], headers=X)
egal((r.json()["resultats"][0]["id"], r.json()["resultats"][0]["deja"]), (res["id"], True),
     "renvoyée par la file du téléphone : la même, rien de créé")
egal(lucie.post("/api/depot", data={"marque": "rega"}, files=[("photos", ("x.jpg", photo, "image/jpeg"))],
                headers=X).status_code, 404, "déposer pour une autre marque : 404")
r = lucie.post("/api/depot", data={"marque": "sazu"}, files=[("photos", ("x.jpg", b"pas une image", "image/jpeg"))],
               headers=X)
verifier(r.status_code == 200 and not r.json()["resultats"][0]["ok"], "un fichier illisible : refusé, dit en clair")
file.vider(500)
ph = lucie.get("/api/photos").json()["photos"]
egal(ph[0]["id"], res["id"], "« Mes photos » : la dernière déposée en tête")
verifier(ph[0]["publications"], "et ce qu'elle devient, réseau par réseau")
egal(lucie.get(ph[0]["vignette"]).headers["content-type"], "image/jpeg", "sa vignette")
egal(client("101010").get(f"/api/photo/{res['id']}/vignette").status_code, 200, "le PDG la voit aussi")

print("— Les liens tracés et la mesure")
sazu = acces.marque("sazu")
principal = mesure.liens_de_publication(sazu, None, "instagram")
r = anonyme.get(f"/c/{principal['code']}", follow_redirects=False)
egal(r.status_code, 200, "/c/ : la page de choix SAZÚ s'ouvre sans session")
verifier("Uber Eats" in r.text and "Deliveroo" in r.text, "avec un bouton par application")
codes = [urllib.parse.unquote(x.split('"')[0]) for x in r.text.split('href="/go/')[1:]]
egal(len(set(codes)), 2, "deux liens tracés distincts (chaque application se mesure à part)")
r = anonyme.get(f"/go/{codes[0]}", follow_redirects=False)
egal(r.status_code, 302, "/go/ : une redirection")
q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(r.headers["location"]).query))
egal((q.get("am"), q.get("utm_medium")), (codes[0], "social"), "la cible porte le marqueur am et les UTM")
with db.moteur().begin() as c:
    egal(c.execute(select(db.links.c.clicks).where(db.links.c.code == codes[0])).scalar_one(), 1, "le clic est compté")
egal(anonyme.get("/go/inexistant", follow_redirects=False).status_code, 404, "un code inconnu : 404, page lisible")
egal(anonyme.get("/b/sazu").status_code, 200, "/b/ : la page « lien en bio »")
egal(anonyme.get("/b/inconnue").status_code, 404, "/b/ d'une marque inconnue : 404")
js = anonyme.get("/s/marqueur.js")
verifier(js.status_code == 200 and "alma_marqueur" in js.text and "/api/leads/web" in js.text,
         "/s/marqueur.js : le marqueur qui suit le formulaire du site")
lien_rega = mesure.creer_lien(acces.marque("rega"), None, "facebook", "devis", "https://rega.exemple/devis")
egal(anonyme.post("/api/leads/web", data={"marque": "rega", "marqueur": lien_rega["code"], "type": "devis"})
     .status_code, 204, "un formulaire du site REGA : accepté sans session ni X-Alma")
egal(anonyme.post("/api/leads/web", data={"marque": "rega", "marqueur": codes[0]}).status_code, 204,
     "un marqueur d'une autre marque : accepté…")
with db.moteur().begin() as c:
    leads = db.lignes(c.execute(select(db.leads).where(db.leads.c.brand_id == "rega").order_by(db.leads.c.id)))
egal([l["link_id"] is not None for l in leads], [True, False], "…mais il ne rattache rien (pas de vol de mérite)")
t = client("101010").get("/api/tableau?marque=rega").json()["marques"][0]["chiffre"]
egal(t["clients"], 2, "le tableau de REGA compte les deux demandes")
egal(client("101010").post("/api/leads", json={"marque": "rega", "type": "appel", "canal": "telephone",
                                                "note": "vu sur Instagram"}, headers=X).status_code, 200,
     "« il nous a vus sur Instagram » : la saisie à la main")

print("— Le pilotage et le journal")
p = client("101010")
egal(p.post("/api/arret", json={"actif": True}, headers=X).json()["arret_general"], True, "STOP général : activé")
verifier(journal.arret_general(), "et l'état le dit")
egal(p.post("/api/arret", json={"actif": False}, headers=X).json()["arret_general"], False, "STOP levé")
r = lucie.post("/api/marque/sazu/pause", json={}, headers=X)
egal(r.status_code, 200, "la responsable met SA marque en pause")
verifier(acces.en_pause(acces.marque("sazu")), "SAZÚ est en pause")
egal(lucie.post("/api/marque/sazu/reprendre", json={}, headers=X).status_code, 200, "et la reprend (son geste)")
csv_ = p.get("/api/journal?format=csv")
verifier(csv_.headers["content-type"].startswith("text/csv") and "attachment" in csv_.headers["content-disposition"],
         "le journal s'exporte en CSV")
lignes = csv_.text.lstrip("﻿").splitlines()
verifier(lignes[0].startswith("id;") and len(lignes) > 10, "avec un en-tête et toutes les lignes")
verifier(any("arret_general" in l for l in lignes), "le STOP y figure")
egal(p.get("/api/journal/verifier").json().get("intact"), True, "la chaîne du journal est intègre")
lj = lucie.get("/api/journal").json()["lignes"]
verifier(lj and all(l["brand_id"] == "sazu" for l in lj), "la responsable ne lit que les lignes de sa marque")
s = p.get("/api/sante").json()
verifier("modele" in json.dumps(s) or "cles" in json.dumps(s), "/api/sante détaille l'état pour le PDG")
verifier("cle-" not in json.dumps(s) and "sk-" not in json.dumps(s), "et n'affiche aucune valeur de clé")
egal(p.post("/api/deconnexion", headers=X).status_code, 200, "déconnexion")
egal(p.get("/api/moi").status_code, 401, "après la déconnexion : 401")

print("— Le disque des photos : un montage raté refuse de démarrer")
from alma_social import config, stockage  # noqa: E402
egal(stockage.verifier_le_montage(env={}), "", "sans CC_FS_BUCKET (poste, bancs) : la garde se tait")
panne = stockage.verifier_le_montage(config.RACINE / "static", config.RACINE, env={"CC_FS_BUCKET": "/f:bucket"})
verifier("FS Bucket" in panne, "bucket annoncé mais dossier sur le disque de l'application : refus de démarrer")
egal(stockage.verifier_le_montage(config.RACINE / "static", config.RACINE,
                                  env={"CC_FS_BUCKET": "/f:bucket", "SOCIAL_DISQUE_SANS_GARDE": "1"}), "",
     "SOCIAL_DISQUE_SANS_GARDE=1 la désarme")
egal(stockage.verifier_le_montage(__import__("pathlib").Path("/proc"), config.RACINE, env={"CC_FS_BUCKET": "/f:b"}),
     "", "un dossier sur un autre périphérique (monté) : accepté")
verifier("illisible" in stockage.verifier_le_montage(config.RACINE / "nulle-part", config.RACINE,
                                                     env={"CC_FS_BUCKET": "/f:b"}),
         "un dossier illisible : c'est la panne")

print("— L'écran")
egal(anonyme.get("/").status_code, 200, "/ sert l'écran")
egal(anonyme.get("/sw.js").headers.get("service-worker-allowed"), "/", "le service worker couvre tout le site")
egal(anonyme.get("/manifest.webmanifest").json()["lang"], "fr", "le manifeste est en français")
page, sw = anonyme.get("/").text, anonyme.get("/sw.js").text
refs = re.findall(r'(?:href|src)="(/static/[^"]+\?v=\d+)"', page)
manquent = [r for r in refs if f'"{r}"' not in sw]
verifier(len(refs) >= 3 and not manquent,
         f"chaque fichier chargé par la page est dans le SHELL du service worker, même version {manquent or ''}")
verifier(all(anonyme.get(r).status_code == 200 for r in refs), "et chacun existe sur le disque")

socle.fin()
