"""Banc : la répétition générale de l'ouverture SAZÚ — tout voir, rien publier.

Le 5 octobre, on rejoue les douze étapes du 30/10 au 29/11 : chaque visuel,
chaque texte réseau par réseau, chaque heure. On vérifie que la répétition
suit les mêmes règles que l'horloge (logo caché jusqu'au 13/11 à 18 h,
garde-fous, Critique), qu'elle n'écrit AUCUN post et ne touche à AUCUN
créneau, et que ses visuels ne se montrent qu'à qui voit la marque."""
import io
import json

import socle
from socle import egal, verifier

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, insert, select

from alma_social import acces, db, graines, planificateur, repetition, securite, stockage

socle.figer(2026, 10, 5, 7)
graines.semer()
for m in acces.marques():
    planificateur.demarrer(m)
with db.moteur().connect() as c:
    cid = c.execute(select(db.campaigns.c.id)).scalar()
    avant_slots = json.dumps(db.lignes(c.execute(select(db.slots).order_by(db.slots.c.id))), default=str)
    avant_posts = c.execute(select(func.count()).select_from(db.posts)).scalar()

print("— La répétition de l'ouverture")
r = repetition.repeter(cid, "banc")
e = r["etapes"]
egal(len(e), 12, "douze étapes, du 30/10 au 29/11")
egal((e[0]["etiquette"], e[0]["jour"], e[0]["heure"]), ("J-28", "2026-10-30", "18:00"), "la première : J-28, le 30/10 à 18 h")
egal((e[-1]["etiquette"], e[-1]["jour"]), ("J+2", "2026-11-29"), "la dernière : J+2, le 29/11")
jour_j = next(x for x in e if x["etiquette"] == "Jour J")
egal((jour_j["jour"], jour_j["heure"]), ("2026-11-27", "11:30"), "le Jour J : vendredi 27/11 à 11 h 30")
verifier("gbp" in jour_j["reseaux"], "Google entre en jeu le Jour J (l'adresse est publique)")
egal([x["logo"] for x in e if x["jour"] < "2026-11-13"], [False] * 4, "aucun logo avant le 13/11")
egal(next(x for x in e if x["etiquette"] == "J-14")["logo"], True, "J-14 (13/11 à 18 h) : le logo apparaît")
egal(r["resume"]["premiere_etape_avec_logo"], "J-14", "le résumé le dit")
verifier(all(x["visuel"]["source"] == "carte" for x in e), "sans photo déposée, chaque étape part en carte à la charte")
egal(r["resume"]["cartes"], 12, "et le résumé le compte")
img = Image.open(io.BytesIO(stockage.chemin(e[0]["visuel"]["chemin"]).read_bytes()))
egal(img.size, (1080, 1350), "un visuel 4:5 par étape")
verifier(all(x["textes"] and all(t["texte"] for t in x["textes"].values()) for x in e), "un texte par réseau, partout")
verifier(all("{LIEN}" not in t["texte"] for x in e for t in x["textes"].values()), "aucun marqueur {LIEN} oublié")
verifier(all("Nouvelle publication" not in t["texte"] for x in e for t in x["textes"].values()),
         "aucune formule creuse (« Nouvelle publication »)")
verifier(all("Rendez-vous le vendredi 27 novembre 2026 à 11h30" in x["textes"]["instagram"]["texte"]
             for x in e if x["etiquette"].startswith("J-")), "avant l'ouverture, chaque légende Instagram donne le rendez-vous")
verifier(all(t["note"] is not None for x in e for t in x["textes"].values()), "chaque texte a sa note du Critique")
egal(r["resume"]["a_revoir"], [], "aucune étape à revoir")
verifier(all(x["verdict"] == "pret" for x in e), "toutes les étapes sont prêtes")

print("— Rien n'est publié, rien n'est déplacé")
with db.moteur().connect() as c:
    egal(c.execute(select(func.count()).select_from(db.posts)).scalar(), avant_posts, "aucun post créé")
    egal(json.dumps(db.lignes(c.execute(select(db.slots).order_by(db.slots.c.id))), default=str), avant_slots,
         "les créneaux sont exactement ceux d'avant")
    egal(c.execute(select(func.count()).select_from(db.assets)).scalar(), 0, "aucune carte rangée en banque")
egal(repetition.derniere(cid)["id"], r["id"], "la répétition est gardée (la dernière se relit)")

print("— Ce que voit qui")
import app as appli  # noqa: E402
X = {"X-Alma": "1"}
with db.moteur().begin() as c:
    c.execute(insert(db.users).values(name="Responsable REGA", role="responsable", brands=["rega"],
                                      code_hash=securite.hacher_code("303030"), active=True,
                                      created_at=db.maintenant()))


def client(code):
    cl = TestClient(appli.app, base_url="https://social.exemple.test")
    assert cl.post("/api/connexion", json={"code": code}, headers=X).status_code == 200
    return cl


lucie, rega, pdg = client("202020"), client("303030"), client("101010")
j = lucie.get(f"/api/campagnes/{cid}/repetition").json()
egal(len(j["etapes"]), 12, "la responsable SAZÚ relit la répétition")
url = j["etapes"][0]["visuel"]["url"]
verifier("chemin" not in json.dumps(j["etapes"][0]["visuel"]), "aucun chemin disque dans la réponse")
egal(lucie.get(url).headers["content-type"], "image/jpeg", "et voit ses visuels")
egal(rega.get(f"/api/campagnes/{cid}/repetition").status_code, 404, "la responsable REGA ne la voit pas")
egal(rega.get(url).status_code, 404, "ni ses visuels")
egal(pdg.post(f"/api/campagnes/{cid}/repetition", json={}, headers=X).status_code, 200, "le PDG la rejoue")
egal(rega.post("/api/studio", json={"marque": "sazu", "type": "carrousel", "photos": [1]}, headers=X).status_code,
     404, "le studio d'une autre marque : 404")

socle.fin()
