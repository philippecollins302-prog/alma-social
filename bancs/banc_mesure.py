"""Banc : la mesure jusqu'au client (jalon 4).

Les cinq portes du client (QR, conversion serveur signée, appel tracé, code
promo, rapport de livraison), le tableau de bord, l'Analyste (statistique,
carnet, emballement, pic de messages), les tests A/B, et la note du lundi
avec ses décisions — dont aucune DÉPENSE ne s'applique seule.

Les publications « réelles » sont posées directement en base avec leurs
mesures : on juge ici le calcul, pas la publication.
"""
import datetime as dt
import hashlib
import hmac
import json
import os
import random

import socle
from socle import egal, verifier

from fastapi.testclient import TestClient
from sqlalchemy import insert, select

from alma_social import (ab, acces, analyste, carnet, conversions, db, graines, journal, mesure, planificateur,
                         rapport)

socle.figer(2026, 12, 7, 9)            # un lundi, SAZÚ ouvert
graines.semer()
import app as appli                    # noqa: E402

X = {"X-Alma": "1"}


def client(code=None):
    c = TestClient(appli.app, base_url="https://social.exemple.test")
    if code:
        assert c.post("/api/connexion", json={"code": code}, headers=X).status_code == 200
    return c


pdg, lucie, anonyme = client("101010"), client("202020"), client()
sazu, rega = acces.marque("sazu"), acces.marque("rega")

print("— 1. Le QR code")
q = conversions.lien_terrain(rega, "Panneau chantier Lattes", "https://rega.exemple/devis", "banc")
verifier(q["qr"].endswith("?q=1"), "le QR porte le lien tracé, marqué ?q=1")
egal(anonyme.get(f"/go/{q['code']}?q=1", follow_redirects=False,
                 headers={"User-Agent": "Mozilla/5.0 (iPhone)"}).status_code, 302, "un scan redirige")
anonyme.get(f"/go/{q['code']}?q=1", follow_redirects=False, headers={"User-Agent": "Mozilla/5.0 (Android) Mobile"})
anonyme.get(f"/go/{q['code']}", follow_redirects=False, headers={"User-Agent": "Mozilla/5.0 (Windows)"})
anonyme.get(f"/go/{q['code']}?q=1", follow_redirects=False, headers={"User-Agent": "facebookexternalhit/1.1"})
t = [x for x in conversions.liens_terrain(["rega"]) if x["code"] == q["code"]][0]
egal(t["scans"], 2, "deux scans comptés (le robot d'aperçu non, le clic simple à part)")
egal(t["support"], "Panneau chantier Lattes", "le support est nommé")
svg = pdg.get(f"/api/qr/{q['code']}.svg")
verifier(svg.status_code == 200 and b"<svg" in svg.content, "le QR se télécharge en SVG (impression)")
png = pdg.get(f"/api/qr/{q['code']}.png")
verifier(png.content[:8] == b"\x89PNG\r\n\x1a\n", "… et en PNG")
egal(lucie.get(f"/api/qr/{q['code']}.svg").status_code, 404, "le QR de REGA n'est pas servi à SAZÚ")
try:
    conversions.lien_terrain(rega, "  ")
    verifier(False, "un support sans nom est refusé")
except ValueError:
    verifier(True, "un support sans nom est refusé")

print("— 2. La conversion côté serveur")
corps = json.dumps({"marque": "rega", "type": "devis", "id": "F-1001", "montant": "12 400,00",
                    "marqueur": q["code"]}).encode()
egal(anonyme.post("/api/conversions", content=corps).status_code, 401, "sans secret posé : porte fermée")
os.environ["SOCIAL_CONVERSIONS_SECRET"] = "une-phrase-de-banc-assez-longue-pour-signer"
sig = conversions.signer(corps, os.environ["SOCIAL_CONVERSIONS_SECRET"])
egal(anonyme.post("/api/conversions", content=corps, headers={"X-Alma-Signature": "sha256=faux"}).status_code, 401,
     "une signature fausse : 401")
r = anonyme.post("/api/conversions", content=corps, headers={"X-Alma-Signature": f"sha256={sig}"})
egal(r.status_code, 200, "signée : acceptée, SANS l'en-tête X-Alma (une machine l'appelle)")
egal(r.json()["deja"], False, "une nouvelle demande")
lead = db.ligne(db.moteur().connect().execute(select(db.leads).where(db.leads.c.id == r.json()["id"])))
egal((lead["channel"], lead["amount"], lead["link_id"] is not None), ("serveur", 12400.0, True),
     "canal serveur, montant lu à la française, rattachée au QR")
egal(anonyme.post("/api/conversions", content=corps, headers={"X-Alma-Signature": sig}).json()["deja"], True,
     "la même demande renvoyée : comptée une fois")
# Le navigateur l'annonce d'abord, le serveur ensuite : un seul client.
l2 = mesure.creer_lien(rega, None, "instagram", "devis", "https://rega.exemple/devis")
anonyme.post("/api/leads/web", data={"marque": "rega", "marqueur": l2["code"], "type": "devis"})
c2 = json.dumps({"marque": "rega", "type": "devis", "id": "F-1002", "marqueur": l2["code"]}).encode()
r2 = anonyme.post("/api/conversions", content=c2,
                  headers={"X-Alma-Signature": conversions.signer(c2, os.environ["SOCIAL_CONVERSIONS_SECRET"])})
with db.moteur().connect() as c:
    n = len(db.lignes(c.execute(select(db.leads).where(db.leads.c.marker == l2["code"]))))
egal(n, 1, "le formulaire vu par le navigateur PUIS par le serveur : un seul client")
egal(r2.json()["deja"], True, "… la ligne du navigateur est complétée")

print("— 3. Le numéro d'appel tracé")
os.environ.pop("SOCIAL_APPELS_SECRET", None)
egal(anonyme.post("/api/appels/entrant?jeton=x", json={}).status_code, 401, "sans jeton posé : porte fermée")
os.environ["SOCIAL_APPELS_SECRET"] = "jeton-du-fournisseur-de-banc"
J = "jeton-du-fournisseur-de-banc"
egal(pdg.post("/api/terrain/numero", json={"marque": "rega", "numero": "04 67 00 11 22", "source": "google",
                                          "fournisseur": "invox"}, headers=X).status_code, 200, "un numéro posé")
egal(conversions.normaliser_numero("0033 4 67 00 11 22"), "+33467001122", "les écritures d'un numéro se rejoignent")
egal(anonyme.post("/api/appels/entrant?jeton=faux", json={}).status_code, 401, "un jeton faux : 401")
r = anonyme.post(f"/api/appels/entrant?jeton={J}",
                 json={"called_number": "+33467001122", "caller": "06 12 34 56 78", "duration": 95, "call_id": "a1"})
egal(r.json()["compte"], True, "un appel de 95 s sur le numéro « google » : un client")
egal(anonyme.post(f"/api/appels/entrant?jeton={J}", json={"called": "+33467001122", "duration": 95,
                                                          "call_id": "a1"}).json()["compte"], False,
     "le même appel reçu deux fois : compté une fois")
egal(anonyme.post(f"/api/appels/entrant?jeton={J}", json={"to": "+33467001122", "from": "0700000000",
                                                          "duration": 8, "call_id": "a2"}).json()["compte"], False,
     "un appel de 8 s : consigné, pas compté")
egal(anonyme.post(f"/api/appels/entrant?jeton={J}", json={"to": "+33467001122", "from": "+33612345678",
                                                          "duration": 60, "call_id": "a3"}).json()["raison"],
     "le même client rappelle (déjà compté)", "le même client qui rappelle n'est pas un second client")
egal(anonyme.post(f"/api/appels/entrant?jeton={J}", json={"to": "+33499999999", "duration": 60}).json()["raison"],
     "numéro inconnu", "un numéro qui n'est pas à nous : rien")
with db.moteur().connect() as c:
    appels = db.lignes(c.execute(select(db.leads).where(db.leads.c.channel == "telephone")))
egal(len(appels), 1, "un seul client téléphone")
verifier(all("612345678" not in json.dumps(a, default=str) for a in appels), "le numéro de l'appelant n'est gardé nulle part en clair")
egal((appels[0]["type"], appels[0]["source"]), ("appel", "google"), "type appel, source google")

print("— 4. Les codes promo")
try:
    conversions.creer_code(sazu, "", plateforme="instagram")
    verifier(False, "un code sans offre est refusé")
except ValueError as e:
    verifier("décision" in str(e), "un code sans offre est refusé : l'offre est une décision")
socle.figer(2026, 12, 1, 12)
with db.moteur().begin() as c:
    pid_promo = c.execute(insert(db.posts).values(brand_id="sazu", platform="instagram", text="Le bowl du mardi",
                                                  status="publie", published_at=db.maintenant(), simulated=False,
                                                  created_at=db.maintenant())).inserted_primary_key[0]
socle.figer(2026, 12, 7, 9)
cp = conversions.creer_code(sazu, "-10 % sur le premier bowl", post_id=pid_promo, plateforme="instagram")
verifier(cp["code"].startswith("SAZU"), f"un code lisible ({cp['code']})")
cp2 = conversions.creer_code(sazu, "-10 %", createur="Léa Gourmande")
verifier(cp2["code"] != cp["code"], "chaque code est unique")

print("— 5. Les rapports Uber Eats et Deliveroo")
uber = ("N° de commande;Date de commande;Statut;Ventes (TTC);Code promo\n"
        f"UE-1;01/12/2026 12:31;Livrée;24,50 €;{cp['code']}\n"
        "UE-2;01/12/2026 19:02;Livrée;18,00 €;\n"
        "UE-3;02/12/2026 12:15;Annulée;30,00 €;\n"
        "UE-4;03/12/2026 13:00;Livrée;1 012,40 €;INCONNU9\n").encode("cp1252")
b = conversions.importer_livraisons(sazu, "uber_eats", uber, "banc")
egal((b["importees"], b["annulees"], b["avec_code"], b["rattachees"]), (3, 1, 1, 1),
     "3 commandes, 1 annulée écartée, 1 avec code, rattachée à sa publication")
egal(b["chiffre"], 1054.9, "le chiffre lu à la française (virgule, espace des milliers, €)")
egal(b["codes_inconnus"], ["INCONNU9"], "un code qui n'est pas à nous est signalé")
egal(conversions.importer_livraisons(sazu, "uber_eats", uber, "banc")["deja"], 3,
     "le même fichier importé deux fois : rien ne compte deux fois")
with db.moteur().connect() as c:
    code = db.ligne(c.execute(select(db.promo_codes).where(db.promo_codes.c.code == cp["code"])))
    ue1 = db.ligne(c.execute(select(db.leads).where(db.leads.c.external_id == "UE-1")))
egal((code["utilisations"], code["chiffre"]), (1, 24.5), "le code compte ses utilisations et son chiffre")
egal(ue1["post_id"], pid_promo, "la commande remonte à la publication du code")
egal(ue1["created_at"].date(), dt.date(2026, 12, 1), "à la date de la commande, pas à celle de l'import")
deliveroo = ("Order ID,Order placed at,Order status,Subtotal,Offer\n"
             "D-77,2026-12-02 12:00:00,DELIVERED,15.90,\n").encode()
egal(conversions.importer_livraisons(sazu, "deliveroo", deliveroo, "banc")["importees"], 1,
     "Deliveroo : colonnes anglaises reconnues")
try:
    conversions.importer_livraisons(sazu, "deliveroo", b"nom;prenom\na;b\n")
    verifier(False, "un fichier sans les bonnes colonnes est refusé")
except ValueError as e:
    verifier("colonnes introuvables" in str(e) and "nom" in str(e), "un fichier étranger est refusé, avec ses colonnes lues")
r = pdg.post("/api/livraisons/import", data={"marque": "sazu", "plateforme": "uber_eats"},
             files={"fichier": ("semaine.csv", uber, "text/csv")}, headers=X)
egal(r.json()["deja"], 3, "l'import passe aussi par l'écran")

print("— 6. L'Analyste : la statistique")
verifier(analyste.mann_whitney([1, 2, 3, 4, 5, 6, 7, 8], [1, 2, 3, 4, 5, 6, 7, 8]) > 0.9, "deux groupes identiques : p ≈ 1")
verifier(analyste.mann_whitney([10, 11, 12, 13, 14, 15, 16, 17], [1, 2, 3, 4, 5, 6, 7, 8]) < 0.01,
         "deux groupes séparés : p très petit")
verifier(not analyste.comparer([5, 6, 7], [1, 2, 3])["net"], "trois contre trois : jamais net, quoi qu'il arrive")

alea = random.Random(7)


def publier_vrai(marque, pf, quand, fmt, vues, interactions, pilier="", texte="Un texte.", simule=False, clients=0):
    with db.moteur().begin() as c:
        pid = c.execute(insert(db.posts).values(
            brand_id=marque, platform=pf, text=texte, status="publie", published_at=quand, simulated=simule,
            post_format=fmt, pillar=pilier, created_at=quand)).inserted_primary_key[0]
        c.execute(insert(db.metrics).values(post_id=pid, checkpoint="24h", measured_at=quand + dt.timedelta(hours=24),
                                            views=vues, reach=vues, likes=interactions, comments=0, shares=0,
                                            saves=0, clicks=0, simulated=simule))
        for _ in range(clients):
            c.execute(insert(db.leads).values(brand_id=marque, post_id=pid, channel="formulaire", type="devis",
                                              created_at=quand))
    return pid


base = db.maintenant() - dt.timedelta(days=50)
carrousels, images_ = [], []
for i in range(12):
    carrousels.append(publier_vrai("rega", "instagram", base + dt.timedelta(days=i * 4, hours=8), "carrousel", 1000,
                                   alea.randint(70, 95), "renovation", clients=1 if i < 3 else 0))
    images_.append(publier_vrai("rega", "instagram", base + dt.timedelta(days=i * 4 + 2, hours=18), "image", 1000,
                                alea.randint(30, 45), "gros_oeuvre"))
# Du simulé très « performant » : il ne doit RIEN changer.
for i in range(10):
    publier_vrai("rega", "instagram", base + dt.timedelta(days=i), "video", 100, 90, simule=True)
obs = analyste.observations("rega")
egal(len(obs), 24, "24 publications réelles observées (les simulées écartées)")
r = analyste.correler(rega, "banc")
verifier(any("carrousel" in l and "%" in l for l in r["lecons"]), "le carnet apprend : le carrousel fait mieux, chiffré")
lecons = {l["cle"]: l for l in carnet.lecons("rega", 20)}
verifier("format:carrousel" in lecons and lecons["format:carrousel"]["preuve"]["echantillon"] == 24,
         "la leçon porte sa preuve (échantillon, période, p)")
verifier(not any(k.startswith("format:video") for k in lecons), "rien n'est appris du simulé")
verifier(any("renovation" in l or "Rénovation" in l for l in r["lecons"]) or "pilier:renovation" in lecons,
         "le pilier qui marche est vu aussi")
p = analyste.prediction("rega", {"format": "carrousel", "reseau": "instagram"})
verifier(p["score"] and p["score"] > 1, f"prédiction : un carrousel Instagram, au-dessus de la moyenne ({p['phrase']})")
egal(analyste.prediction("lms", {"format": "image"})["score"], None, "sans historique : pas de prédiction inventée")

print("— 7. Les tests A/B")
e = ab.lancer(rega, "accroche", "banc")
egal(e["statut"], "en_cours", "un test lancé, hypothèse écrite d'avance")
verifier(e["hypothese"].startswith("Une première phrase en question"), "l'hypothèse est écrite")
try:
    ab.lancer(rega, "longueur", "banc")
    verifier(False, "un second test simultané est refusé")
except ValueError:
    verifier(True, "un second test simultané est refusé : deux tests se mêlent")
noms = []
for i in range(4):
    a_ = ab.assigner("rega")
    noms.append(a_["nom"])
    ab.enregistrer(a_["experience"], a_["nom"], [10_000 + i])
egal(noms, ["question", "affirmation", "question", "affirmation"], "les variantes alternent créneau après créneau")
egal(ab.assigner("lms"), None, "pas de test : pas de variante")
# On remplace les numéros fictifs par de vraies publications mesurées.
with db.moteur().begin() as c:
    from sqlalchemy import update
    vs = [{"nom": "question", "consigne": "", "post_ids": carrousels[:10]},
          {"nom": "affirmation", "consigne": "", "post_ids": images_[:10]}]
    c.execute(update(db.experiments).where(db.experiments.c.id == e["id"]).values(variantes=vs))
res = ab.conclure(ab.actif("rega"), "banc")
egal(res["statut"], "nette", "dix contre dix, écart net : conclu")
verifier("question" in res["conclusion"] and "p =" in res["conclusion"], f"la conclusion dit qui gagne, et p ({res['conclusion']})")
verifier("ab:accroche" in {l["cle"] for l in carnet.lecons("rega", 30)}, "… et entre au carnet")
e2 = ab.lancer(rega, "longueur", "banc")
with db.moteur().begin() as c:
    vs = [{"nom": "court", "consigne": "", "post_ids": carrousels[:5] + images_[:5]},
          {"nom": "long", "consigne": "", "post_ids": carrousels[5:10] + images_[5:10]}]
    c.execute(update(db.experiments).where(db.experiments.c.id == e2["id"]).values(variantes=vs))
egal(ab.conclure(ab.actif("rega"), "banc")["statut"], "pas_nette", "deux groupes mêlés : « pas net », rien au carnet")
verifier("ab:longueur" not in {l["cle"] for l in carnet.lecons("rega", 30)}, "un résultat pas net n'entre pas au carnet")
egal(pdg.post("/api/ab", json={"marque": "rega", "variable": "format"}, headers=X).status_code, 200,
     "un test se lance depuis l'écran")
egal(pdg.post("/api/ab", json={"marque": "rega", "variable": "format"}, headers=X).status_code, 409, "… une fois")
egal(ab.assigner("rega", peut_monter=False), None, "test de format : un créneau sans montage n'y entre pas")

print("— 8. Les alertes qui s'expliquent")
socle.figer(2026, 12, 7, 10)
virale = publier_vrai("rega", "instagram", db.maintenant() - dt.timedelta(hours=1), "carrousel", 1000, 900)
r = analyste.emballement(virale)
verifier(r and r["sens"] == "bien", "une publication à 10× la médiane : alerte « s'emballe »")
with db.moteur().connect() as c:
    al = db.ligne(c.execute(select(db.alerts).where(db.alerts.c.kind == "emballement")))
verifier("fois la médiane" in al["body"] and "commentaires" in al["body"], "l'alerte donne les chiffres et le pourquoi")
egal(analyste.emballement(virale), r, "même résultat au second relevé…")
with db.moteur().connect() as c:
    egal(len(db.lignes(c.execute(select(db.alerts).where(db.alerts.c.kind == "emballement")))), 1, "… mais une seule alerte")
sim = publier_vrai("rega", "instagram", db.maintenant(), "image", 10, 900, simule=True)
egal(analyste.emballement(sim), None, "le simulé ne déclenche rien")
for i in range(14):
    with db.moteur().begin() as c:
        c.execute(insert(db.conversations).values(
            brand_id="rega", platform="instagram", kind="commentaire", external_id=f"pic-{i}", post_id=virale,
            author="@voisin_curieux" if i < 4 else f"@client{i}", text="C'est où ce chantier ?",
            category="plainte" if i < 2 else "question", received_at=db.maintenant() - dt.timedelta(minutes=i * 5)))
pic = analyste.pic_de_mentions(rega)
verifier(pic and pic["n"] == 14, "14 messages en deux heures : un pic")
verifier("sous la publication du" in pic["corps"] and "@voisin_curieux" in pic["corps"],
         f"l'alerte dit d'où ils viennent ({pic['corps'][:120]}…)")
egal(analyste.pic_de_mentions(sazu), None, "pas de pic chez SAZÚ")

print("— 9. Le tableau : ce que ça rapporte, ce que ça coûte")
with db.moteur().begin() as c:
    c.execute(insert(db.agent_runs).values(agent="redacteur", brand_id="rega", cout_usd=1.5, created_at=db.maintenant()))
v = analyste.valeur(rega)
egal(v["clients"], 3, "REGA : 3 clients en 30 jours (QR, conversion, appel ; les plus anciens hors période)")
verifier(any(k.startswith("QR « ") for k in v["par_reseau"]), "un client venu d'un QR est nommé par son support")
verifier(v["cout_par_client"] and v["cout_par_client"] > 0, f"coût par client calculé ({v['cout_par_client']})")
verifier("Instagram" in v["par_reseau"] and "téléphone" in v["par_reseau"], f"par source : {v['par_reseau']}")
t = pdg.get("/api/tableau?marque=rega").json()["marques"][0]
verifier("valeur" in t and t["lecons"], "le tableau porte la valeur et les leçons du carnet")
verifier(t["test"] and t["test"]["variable"] == "format", "… et le test en cours")
te = lucie.get("/api/terrain").json()
verifier(all(x["marque"] == "sazu" for x in te["qr"] + te["numeros"]) and te["codes"],
         "Terrain : la responsable SAZÚ ne voit que SAZÚ")
egal(te["branche"], {"conversions": True, "appels": True}, "l'écran dit ce qui est branché")

print("— 10. La note du lundi, et ses décisions")
egal(pdg.post("/api/marque/rega/objectif", json={"clients": 12}, headers=X).json()["objectif"], 12, "un objectif posé")
egal(lucie.post("/api/marque/sazu/objectif", json={"clients": 3}, headers=X).status_code, 403, "… par le PDG seul")
# Une grosse banque pour que la cadence puisse monter.
from alma_social import pipeline
for i in range(25):
    pipeline.recevoir("rega", socle.image("chantier", graine=300 + i), f"b{i}.jpg")
with db.moteur().begin() as c:
    from sqlalchemy import update as upd
    c.execute(upd(db.assets).where(db.assets.c.brand_id == "rega").values(status="banque"))
titre, corps, html_, fiches = rapport.composer(["rega", "sazu"])
for mot in ("LE CHIFFRE", "objectif 12", "VICTOIRES", "PROBLÈMES", "DÉCISIONS PROPOSÉES", "Concurrents",
            "Avis", "Google Maps", "Stock", "Dépenses"):
    verifier(mot in corps, f"la note contient « {mot} »")
print("\n".join("    | " + x for x in corps.splitlines()[:30]))
ds = analyste.lister("rega", "2026-12-07")
verifier(1 <= len(ds) <= 3, f"{len(ds)} décision(s) proposée(s), trois au plus")
verifier(any(d["type"] == "budget" and not d["auto"] and d["statut"] == "a_decider" for d in ds),
         "le boost est proposé « à décider » : une dépense ne part jamais seule")
rapport.composer(["rega"])
egal(len(analyste.lister("rega", "2026-12-07")), len(ds), "recomposer la note ne double pas les décisions")
pil = next((d for d in ds if d["type"] == "pilier"), None)
cad = next((d for d in ds if d["type"] == "cadence"), None)
verifier(pil is not None, "une décision sur le pilier qui marche")
budget = next(d for d in ds if d["type"] == "budget")
egal(lucie.post(f"/api/decisions/{budget['id']}", json={"oui": True}, headers=X).status_code, 404,
     "une décision de REGA n'existe pas pour SAZÚ")
if cad:
    egal(pdg.post(f"/api/decisions/{cad['id']}", json={"oui": False}, headers=X).json()["statut"], "refusee",
         "« non » avant midi : la décision ne s'applique pas")
socle.figer(2026, 12, 7, 12, 5)
avant_cad = acces.marque("rega")["cadence_max"]
n = analyste.appliquer_decisions_dues("banc")
verifier(n >= 1, f"midi : {n} décision(s) non refusée(s) appliquée(s)")
egal(acces.marque("rega")["cadence_max"], avant_cad, "la cadence refusée n'a pas bougé")
parts = {p_["key"]: p_["share"] for p_ in acces.marque("rega")["pillars"] if not p_.get("hors_rotation")}
verifier(abs(sum(parts.values()) - 100) < 1.5, f"les parts des piliers font toujours 100 ({sum(parts.values()):.1f})")
verifier(parts[pil["parametres"]["pilier"]] == max(parts.values()), "le pilier qui marche a la plus grande part")
egal(next(d for d in analyste.lister("rega", "2026-12-07") if d["id"] == budget["id"])["statut"], "a_decider",
     "le boost, lui, attend toujours une personne")
egal(pdg.post(f"/api/decisions/{pil['id']}", json={"oui": True}, headers=X).status_code, 409,
     "une décision appliquée ne se tranche pas deux fois")

socle.fin()
