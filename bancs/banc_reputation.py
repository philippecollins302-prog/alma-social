"""Banc : la relation et la réputation (jalon 5).

Commentaire « DEVIS » → lien de conversation ; la conversation qui qualifie
(nom et téléphone d'abord, jamais une question déjà répondue, une
température écrite en règle) ; la fiche au responsable et au webhook ; la
boîte triée par valeur, avec son délai RÉEL ; le mode crise, à la main et
seul ; les demandes d'avis (à tous, sans tri, relances, arrêt) ; la lecture
des avis ; Google Maps (grille, relevé, audit) ; les routes publiques.
Aucun appel sortant : Places et le webhook sont des faux.
"""
import datetime as dt
import hashlib
import hmac
import json
import os

import socle
from socle import egal, verifier

from fastapi.testclient import TestClient
from sqlalchemy import insert, select, update

from alma_social import (acces, alertes, conversions, crise, db, demandes_avis, file, graines, journal,
                         lecture_avis, maps, qualification, rapport, relation)

socle.figer(2026, 12, 2, 9)            # un mercredi, SAZÚ ouvert
graines.semer()
import app as appli                    # noqa: E402

X = {"X-Alma": "1"}
rega, sazu, lms = acces.marque("rega"), acces.marque("sazu"), acces.marque("lms")


def client(code=None):
    c = TestClient(appli.app, base_url="https://social.exemple.test")
    if code:
        assert c.post("/api/connexion", json={"code": code}, headers=X).status_code == 200
    return c


def conv(eid):
    with db.moteur().connect() as c:
        return db.ligne(c.execute(select(db.conversations).where(db.conversations.c.external_id == eid)))


def poser_post(marque, pf, texte, statut="publie", quand=None):
    with db.moteur().begin() as c:
        return c.execute(insert(db.posts).values(
            brand_id=marque, platform=pf, text=texte, status=statut, simulated=False,
            published_at=db.maintenant() if statut == "publie" else None,
            scheduled_at=quand, created_at=db.maintenant())).inserted_primary_key[0]


def derniere_reponse(cid):
    with db.moteur().connect() as c:
        return [j for j in db.lignes(c.execute(select(db.audit_log))) if j["action"] == "reponse"
                and str(j["object_id"]) == str(cid)][-1]


print("— Commentaire « DEVIS » → la conversation")
pid = poser_post("rega", "facebook", "Extension livrée à Lattes : 30 m² de plus pour la famille.")
egal(relation.mot_declencheur(rega, "DEVIS"), "qualifier", "« DEVIS » seul déclenche")
egal(relation.mot_declencheur(rega, "devis svp 🙏"), "qualifier", "en minuscules, avec un emoji aussi")
egal(relation.mot_declencheur(rega, "pas besoin de devis merci"), None, "« pas … devis » ne déclenche pas")
egal(relation.mot_declencheur(rega, "Bonjour, je voudrais un devis pour une extension de ma maison svp"), None,
     "une vraie phrase passe par le tri normal")
egal(relation.mot_declencheur(sazu, "BOWL"), "commander", "SAZÚ : « BOWL » → commander")
alertes.ENVOYES.clear()
relation.recevoir(rega, "facebook", "c-devis-1", "Paul Martin", "DEVIS", post_id=pid)
c = conv("c-devis-1")
egal((c["category"], c["status"], c["replied_by"]), ("devis", "repondu", "ia"), "un prospect, pris en charge seul")
verifier("/go/" in c["reply"] and "Paul" in c["reply"], f"le lien tracé part, au prénom ({c['reply']})")
egal(c["first_reply_s"], 0, "délai de première réponse mesuré : immédiat")
egal(derniere_reponse(c["id"])["after"]["voie"], "prive", "envoyé en message privé (simulé en bac à sable)")
code = c["reply"].split("/go/")[1].split()[0]
with db.moteur().connect() as cx:
    lien = db.ligne(cx.execute(select(db.links).where(db.links.c.code == code)))
egal((lien["kind"], lien["post_id"]), ("chat", pid), "le lien est rattaché à la publication")
verifier(lien["target_url"].endswith("/parler/rega"), "il mène à la conversation REGA")
relation.recevoir(rega, "facebook", "c-devis-2", "Anne", "devis", post_id=pid)
verifier(code in conv("c-devis-2")["reply"], "un seul lien par publication et par réseau")
verifier(any("demande de devis" in a["sujet"] for a in alertes.ENVOYES), "le responsable est prévenu")

print("— « BOWL » sans lien de commande : on ne promet rien")
pz = poser_post("sazu", "instagram", "Le Salvador du jour")
relation.recevoir(sazu, "instagram", "c-bowl-1", "lea", "BOWL", post_id=pz)
verifier("/go/" not in (conv("c-bowl-1")["reply"] or ""), "aucun lien inventé")
liens = dict(sazu["links"])
liens["uber_eats"] = "https://www.ubereats.com/fr/store/sazu"
with db.moteur().begin() as cx:
    cx.execute(update(db.brands).where(db.brands.c.id == "sazu").values(links=liens))
sazu = acces.marque("sazu")
cp = conversions.creer_code(sazu, "-10 % sur le premier bowl", post_id=pz, plateforme="instagram")
alertes.ENVOYES.clear()
relation.recevoir(sazu, "instagram", "c-bowl-2", "leo", "BOWL 🔥", post_id=pz)
r = conv("c-bowl-2")["reply"]
verifier("/go/" in r and cp["code"] in r and "-10 %" in r, f"le lien de commande et le code du jour ({r})")
verifier(not alertes.ENVOYES, "une commande en route n'est pas une urgence : pas d'alerte")

print("— La conversation qui qualifie")
socle.figer(2026, 12, 2, 9, 10)
ch = qualification.ouvrir(rega, marqueur=code)
egal((ch["entry_door"], ch["post_id"]), ("commentaire", pid), "porte : le commentaire, publication d'origine gardée")
verifier("nom" in ch["messages"][0]["texte"], "le nom d'abord")
j = ch["token"]
v = qualification.repondre(j, "Paul Martin")
verifier("téléphone" in v["messages"][-1]["texte"], "puis le téléphone")
v = qualification.repondre(j, "pas de numéro")
verifier("réécrire" in v["messages"][-1]["texte"], "un numéro illisible est redemandé")
v = qualification.repondre(j, "06 12 34 56 78")
verifier("projet" in v["messages"][-1]["texte"], "puis le projet, en une phrase")
v = qualification.repondre(j, "Une extension de 30 m2, c'est urgent")
reponses = qualification.chat(j)["answers"]
egal(reponses.get("surface"), "30 m²", "la surface est lue dans la phrase")
verifier(reponses.get("delai"), "le délai aussi")
questions_posees = " ".join(x["texte"] for x in qualification.chat(j)["messages"] if x["de"] == "marque")
egal(reponses.get("travaux"), "extension", "les travaux aussi : « extension » n'est pas redemandé")
for rep in ["Lattes", "autour de 60 000 €"]:
    v = qualification.repondre(j, rep)
    questions_posees += " " + v["messages"][-1]["texte"]
verifier("surface" not in questions_posees.lower() and "pour quand" not in questions_posees.lower()
         and "quels travaux" not in questions_posees.lower(),
         "une question déjà répondue n'est jamais reposée")
alertes.ENVOYES.clear()
v = qualification.repondre(j, "Le matin")
verifier(v["fini"], "conversation terminée")
ch = qualification.chat(j)
egal((ch["status"], ch["temperature"]), ("qualifie", "chaud"), "urgent → chaud")
with db.moteur().connect() as cx:
    lead = db.ligne(cx.execute(select(db.leads).where(db.leads.c.id == ch["lead_id"])))
egal((lead["entry_door"], lead["post_id"], lead["link_id"], lead["temperature"]),
     ("commentaire", pid, lien["id"], "chaud"), "la fiche est un client de cette publication")
egal(lead["qualification"]["contact"]["telephone"], "+33612345678", "téléphone normalisé")
fiche = [a for a in alertes.ENVOYES if "prospect" in a["sujet"]]
verifier(fiche and "CHAUD" in fiche[0]["corps"] and "Publication d'origine" in fiche[0]["corps"]
         and "Extension livrée" in fiche[0]["corps"], "la fiche part au responsable, avec la publication")
v2 = qualification.repondre(j, "encore un message")
egal(len(v2["messages"]), len(v["messages"]), "une conversation finie ne bouge plus")

print("— Lire une phrase sans modèle")
lu = qualification._regles(lms, "Du parquet dans le salon et la chambre, 40 m2 sur Castelnau-le-Lez, avec pose")
egal((lu.get("sol"), lu.get("piece"), lu.get("surface"), lu.get("commune"), lu.get("pose")),
     ("parquet", "salon, chambre", "40 m²", "Castelnau-le-Lez", "avec pose"), "cinq cases remplies d'une phrase")
egal(qualification._regles(rega, "à rénover").get("commune"), None, "« à rénover » n'est pas une commune")

print("— La température, une règle écrite")
auj = dt.date(2026, 12, 2)
verifier(qualification._mois_de_delai("dans 2 semaines", auj) < 1, "« dans 2 semaines » < 1 mois")
verifier(1 < qualification._mois_de_delai("en février", auj) < 3, "« en février » : deux mois et demi")
verifier(qualification._mois_de_delai("je me renseigne", auj) >= 12, "« je me renseigne » : loin")
verifier(qualification._mois_de_delai("le 12 décembre", auj) < 1, "« le 12 décembre » : dans dix jours")
egal(qualification._mois_de_delai("bleu", auj), None, "rien de lisible : rien")
egal(qualification.temperature(rega, {"delai": "en février"})[0], "tiede", "trois mois au plus : tiède")
egal(qualification.temperature(rega, {"delai": "je me renseigne", "budget": "je ne sais pas"})[0], "froid",
     "« je ne sais pas » n'est pas un budget")
egal(qualification.temperature(rega, {"delai": "l'an prochain", "budget": "20 000 €"})[0], "tiede",
     "un budget annoncé réchauffe")
egal(qualification.temperature(sazu, {"groupe": "15", "date": "vendredi"})[0], "chaud",
     "SAZÚ : quinze personnes vendredi → chaud")
egal(qualification.temperature(sazu, {"groupe": "3", "date": "vendredi"})[0], "froid", "trois personnes → froid")
egal(qualification.telephone_valide("+33 6 12 34 56 78"), "+33612345678", "format international lu")
egal(qualification.telephone_valide("12"), "", "un faux numéro est refusé")

print("— Interrompue : une fiche quand même, s'il y a un téléphone")
a1 = qualification.ouvrir(lms)["token"]
qualification.repondre(a1, "Mme Roux")
qualification.repondre(a1, "0611223344")
a2 = qualification.ouvrir(lms)["token"]
qualification.repondre(a2, "Quelqu'un")
socle.figer(2026, 12, 2, 12)
egal(qualification.abandons(), 1, "une seule conversation devient une fiche")
egal(qualification.chat(a1)["status"], "abandonne", "celle avec téléphone : close…")
verifier(qualification.chat(a1)["lead_id"], "… et devenue une fiche")
verifier(not qualification.chat(a2)["lead_id"], "sans téléphone : personne à rappeler, pas de fiche")

print("— Le webhook générique et l'export")
envoyes = []
qualification._http_post = lambda url, corps, entetes: (envoyes.append((url, corps, entetes)), 200)[1]
os.environ["SOCIAL_LEADS_WEBHOOK"] = "https://crm.exemple.test/leads"
os.environ["SOCIAL_LEADS_WEBHOOK_SECRET"] = "secret-de-banc"
c3 = qualification.ouvrir(sazu)["token"]
for x in ["Inès", "0700000001", "Un déjeuner d'équipe", "20", "Agence Sud", "le 10 décembre"]:
    qualification.repondre(c3, x)
file.vider(50)
egal(len(envoyes), 1, "la fiche part une fois")
url, corps, entetes = envoyes[0]
attendue = "sha256=" + hmac.new(b"secret-de-banc", corps, hashlib.sha256).hexdigest()
egal(entetes.get("X-Alma-Signature"), attendue, "signée HMAC-SHA256")
d = json.loads(corps)
egal((d["marque"], d["type"], d["temperature"], d["nom"]), ("sazu", "commande", "chaud", "Inès"),
     "le contenu : marque, type, température, contact")
egal(d["reponses"].get("groupe"), "20", "et les réponses")
qualification._http_post = lambda url, corps, entetes: 503
c4 = qualification.ouvrir(sazu)["token"]
for x in ["Jo", "0700000002", "Un pot", "4", "Moi", "samedi"]:
    qualification.repondre(c4, x)
file.vider(50)
with db.moteur().connect() as cx:
    jw = [j_ for j_ in db.lignes(cx.execute(select(db.jobs))) if j_["kind"] == "webhook_lead" and j_["status"] != "fait"]
verifier(jw, "un webhook en panne est réessayé, pas perdu")
os.environ.pop("SOCIAL_LEADS_WEBHOOK")
csv = qualification.export_csv(["sazu", "rega", "lms"])
verifier("Inès" in csv and "Paul Martin" in csv and "température" in csv, "l'export CSV contient les fiches")

print("— La boîte : valeur, assignation, délai réel")
socle.figer(2026, 12, 2, 14)
relation.recevoir(sazu, "instagram", "c-q", "manon", "Vous livrez jusqu'à Antigone ?")
relation.recevoir(sazu, "instagram", "c-p", "julie", "Commande arrivée froide, très déçue.")
cp_, cq = conv("c-p"), conv("c-q")
egal(cp_["assigned_to"], "Responsable SAZÚ (essai) (copie PDG)", "une plainte : le responsable, PDG en copie")
egal(cq["assigned_to"], "Responsable SAZÚ (essai)", "une question : le responsable")
egal((cq["value"], cp_["value"]), (1, 2), "valeur commerciale notée")
egal(relation.responsable(rega), "PDG", "sans responsable : le PDG")
b = relation.boite(["sazu"])
verifier(b.index(next(x for x in b if x["external_id"] == "c-p")) <
         b.index(next(x for x in b if x["external_id"] == "c-q")), "l'urgence d'abord")
dl = relation.delais(["sazu", "rega"])
verifier(dl["question"]["repondus"] >= 1 and dl["question"]["en_retard"] == 0, "question : répondue dans les temps")
egal(dl["devis"]["mediane_s"], 0, "devis : pris en charge en 0 s")

print("— Le mode crise, à la main")
pf = poser_post("sazu", "instagram", "Demain, le Salvador", statut="programme",
                quand=db.maintenant() + dt.timedelta(hours=5))
alertes.ENVOYES.clear()
r = crise.declencher(sazu, "Philippe", "livraisons froides en série")
sazu = acces.marque("sazu")
verifier(crise.en_crise(sazu) and acces.en_pause(sazu), "en crise : la marque ne publie plus")
egal(r["retenues"], 1, "la publication programmée est retenue")
with db.moteur().connect() as cx:
    egal(cx.execute(select(db.posts.c.status).where(db.posts.c.id == pf)).scalar(), "suspendu", "suspendue, pas effacée")
verifier(r["brouillon"] and "L'équipe SAZÚ" in r["brouillon"], "un brouillon de prise de parole est écrit")
verifier(any("MODE CRISE" in a["sujet"] and r["brouillon"] in a["corps"] for a in alertes.ENVOYES),
         "il est envoyé au PDG — et rien n'est parti en public")
egal(crise.declencher(sazu, "Philippe", "encore")["deja"], True, "deux déclenchements, une seule crise")
relation.recevoir(sazu, "instagram", "c-crise-merci", "tom", "Trop bon le Salvador, bravo !")
c = conv("c-crise-merci")
egal((c["category"], c["reply"] or "", c["status"]), ("compliment", "", "alerte"),
     "en crise, même un merci ne part pas seul : il attend un humain")
relation.recevoir(sazu, "instagram", "c-crise-bowl", "zoe", "BOWL", post_id=pz)
egal(conv("c-crise-bowl")["reply"] or "", "", "et le mot « BOWL » ne déclenche plus rien")
relation.recevoir_avis(sazu, "g-crise", 5, "Le bowl Salvador est parfait", "Nina R.")
socle.figer(2026, 12, 2, 20)
relation.repondre_aux_avis_dus()
with db.moteur().connect() as cx:
    egal(cx.execute(select(db.reviews.c.status).where(db.reviews.c.external_id == "g-crise")).scalar(), "a_repondre",
         "un avis 5 ★ attend : aucune réponse automatique en crise")
relation.recevoir(rega, "facebook", "c-rega-merci", "Luc", "Bravo pour le chantier, super travail")
egal(conv("c-rega-merci")["status"], "repondu", "les autres marques continuent")
r = crise.lever(sazu, "Philippe")
sazu = acces.marque("sazu")
verifier(not crise.en_crise(sazu) and r["repris"] == 1, "crise levée : ce qui était retenu repart")
with db.moteur().begin() as cx:                 # la publication du banc n'a pas d'image : on la retire
    cx.execute(update(db.posts).where(db.posts.c.id == pf).values(status="annule"))

print("— Le mode crise, seul")
socle.figer(2026, 12, 3, 19)
for i in range(4):
    relation.recevoir(lms, "facebook", f"c-lms-{i}", f"client{i}", "Chantier bâclé, malfaçon partout, inadmissible")
verifier(not crise.en_crise(acces.marque("lms")), "quatre plaintes : pas une crise")
alertes.ENVOYES.clear()
relation.recevoir(lms, "facebook", "c-lms-4", "client4", "Plainte : retard de trois semaines, honteux")
lm = acces.marque("lms")
verifier(crise.en_crise(lm), "la cinquième en deux heures : le Veilleur déclenche la crise")
verifier("messages négatifs en deux heures" in lm["crisis_reason"], f"et dit pourquoi ({lm['crisis_reason']})")
verifier(any("déclenché automatiquement" in a["sujet"] for a in alertes.ENVOYES), "le PDG est prévenu")
crise.lever(lm, "Philippe")
socle.figer(2026, 12, 4, 19)
for i in range(5):
    relation.recevoir(rega, "facebook", f"c-rega-bruit-{i}", f"x{i}", "Super chantier bravo merci")
for i in range(5):
    relation.recevoir(rega, "facebook", f"c-rega-p-{i}", f"y{i}", "Malfaçon, inadmissible")
verifier(crise.en_crise(acces.marque("rega")), "cinq plaintes, la moitié des messages : crise aussi chez REGA")
egal(crise.surveiller(acces.marque("rega")), None, "déjà en crise : rien de plus")

print("— Demander un avis : à tous, sans tri")
crise.lever(acces.marque("rega"), "Philippe")
rega = acces.marque("rega")
socle.figer(2026, 12, 5, 17, 30)        # un samedi, 18 h 30 à Paris
alertes.ENVOYES.clear()
dmd = demandes_avis.demander(rega, "pv_chantier", "Claire Dubois", "claire@exemple.test", "", "PV-2026-118", "Kevin")
egal(dmd["channel"], "email", "par e-mail")
egal(demandes_avis.demander(rega, "pv_chantier", "Claire", "claire@exemple.test", "", "PV-2026-118")["deja"], True,
     "le même PV deux fois : une seule demande")
with db.moteur().connect() as cx:
    jobs = sorted([j_ for j_ in db.lignes(cx.execute(select(db.jobs))) if j_["kind"] == "demande_avis"
                   and j_["payload"]["id"] == dmd["id"]], key=lambda j_: j_["payload"]["rang"])
egal(len(jobs), 3, "un envoi et deux relances")
from alma_social import creneaux  # noqa: E402
p0 = creneaux.paris(jobs[0]["run_at"])
egal((p0.weekday(), p0.hour), (0, 9), "samedi soir → lundi 9 h : jamais le dimanche, jamais la nuit")
socle.figer(2026, 12, 7, 8, 30)
file.vider(50)
mails = [a for a in alertes.ENVOYES if a["a"] == ["claire@exemple.test"]]
egal(len(mails), 1, "le premier courrier part")
corps = mails[0]["corps"]
verifier("/avis/" in corps and "/stop" in corps, "le lien d'avis, et le lien pour ne plus recevoir")
verifier("satisf" not in corps.lower() and "content" not in corps.lower(),
         "aucune question de satisfaction avant le lien : pas de tri")
verifier("Claire" in corps and "chantier est terminé" in corps, "au prénom, sur l'événement")
jeton = corps.split("/avis/")[1].split()[0]
cl = client()
r = cl.get(f"/avis/{jeton}", follow_redirects=False)
egal(r.status_code, 200, "sans place ID : une page d'attente, pas une erreur")
liens = dict(rega["links"])
liens["google_place_id"] = "ChIJ_banc_rega_123"
with db.moteur().begin() as cx:
    cx.execute(update(db.brands).where(db.brands.c.id == "rega").values(links=liens))
rega = acces.marque("rega")
r = cl.get(f"/avis/{jeton}", follow_redirects=False)
egal((r.status_code, r.headers["location"]),
     (302, "https://search.google.com/local/writereview?placeid=ChIJ_banc_rega_123"),
     "le lien mène droit à la fenêtre d'avis Google")
egal(demandes_avis._une(dmd["id"])["status"], "clique", "le clic est noté")
socle.figer(2026, 12, 12, 12)
file.vider(50)
egal(len([a for a in alertes.ENVOYES if a["a"] == ["claire@exemple.test"]]), 1, "il a cliqué : aucune relance")
d2 = demandes_avis.demander(rega, "facture_payee", "Marc", "marc@exemple.test", "", "F-77")
socle.figer(2026, 12, 20, 12)
file.vider(50)
egal(len([a for a in alertes.ENVOYES if a["a"] == ["marc@exemple.test"]]), 3, "sans clic : J+3 et J+5")
d3 = demandes_avis.demander(rega, "pv_chantier", "Sam", "sam@exemple.test")
socle.figer(2026, 12, 21, 12)
file.vider(50)
jeton3 = [a for a in alertes.ENVOYES if a["a"] == ["sam@exemple.test"]][0]["corps"].split("/avis/")[1].split()[0]
egal(cl.get(f"/avis/{jeton3}/stop").status_code, 200, "« ne plus recevoir »")
socle.figer(2026, 12, 30, 12)
file.vider(50)
egal(len([a for a in alertes.ENVOYES if a["a"] == ["sam@exemple.test"]]), 1, "arrêté : plus rien")
d4 = demandes_avis.demander(rega, "pv_chantier", "Tel", "", "06 00 00 00 01")
socle.figer(2026, 12, 31, 12)
file.vider(50)
d4 = demandes_avis._une(d4["id"])
verifier(d4["status"] == "echec" and "fournisseur" in d4["sends"][0]["erreur"],
         "un téléphone seul : pas de SMS sans fournisseur, et c'est dit")
try:
    demandes_avis.demander(rega, "pv_chantier", "Personne")
    verifier(False, "sans contact : refusé")
except ValueError:
    verifier(True, "sans e-mail ni téléphone : refusé")
egal(demandes_avis.bilan("rega", 60)["ouvertes"], 1, "le bilan compte les ouvertures")
r = cl.get("/avis/m/rega", follow_redirects=False)
egal(r.status_code, 302, "le lien du QR et de la puce NFC mène à Google")

print("— L'événement envoyé par un outil, signé")
os.environ["SOCIAL_CONVERSIONS_SECRET"] = "cle-banc"
corps_ev = json.dumps({"marque": "lms", "evenement": "facture_payee", "id": "FAC-9", "nom": "Hugo",
                       "email": "hugo@exemple.test"}).encode()
egal(cl.post("/api/avis/evenement", content=corps_ev).status_code, 401, "sans signature : refusé")
sig = "sha256=" + conversions.signer(corps_ev, "cle-banc")
r = cl.post("/api/avis/evenement", content=corps_ev, headers={"X-Alma-Signature": sig})
egal(r.status_code, 200, "signé : accepté")
egal(cl.post("/api/avis/evenement", content=corps_ev, headers={"X-Alma-Signature": sig}).json()["deja"], True,
     "renvoyé : pas de doublon")

print("— Lire les avis")
socle.figer(2026, 12, 31, 13)
for i, (n, t) in enumerate([(5, "Équipe très professionnelle, chantier propre"), (5, "Travail soigné, équipe sympa"),
                            (2, "Retard de deux semaines sur le planning"), (1, "Énorme retard, jamais à l'heure"),
                            (4, "Bonne finition, chantier laissé propre")]):
    relation.recevoir_avis(rega, f"g-rega-{i}", n, t, f"Client {i}")
with db.moteur().begin() as cx:
    kid = cx.execute(insert(db.competitors).values(brand_id="rega", name="Concurrent BTP (banc)")).inserted_primary_key[0]
k = {"id": kid}
for t in ["Très ponctuels, délais tenus", "Rapides et à l'heure", "Délais tenus"]:
    lecture_avis.ajouter_concurrent(k["id"], 5, t)
egal(lecture_avis.ajouter_concurrent(k["id"], 5, "Délais tenus"), False, "le même avis collé deux fois : une fois")
lec = lecture_avis.lecture(rega)
verifier("équipe" in lec["aiment"] and "propreté" in lec["aiment"], f"ils aiment l'équipe et la propreté ({lec['aiment']})")
egal(lec["agacent"], ["délais"], "ce qui agace : les délais")
egal(lec["eux_mieux"], ["délais"], "les concurrents sont loués sur les délais")
verifier(lec["idees"] and "jour par jour" in lec["idees"][0], "une idée de contenu qui répond à l'objection")
egal(lecture_avis.themes_de("bonjour", "food"), [], "« bonjour » n'est pas « bon »")

print("— Google Maps")
pts = maps.grille(43.64, 3.90, 3)
egal(len(set(pts)), 9, "3 × 3 points distincts")
egal(pts[4], (43.64, 3.9), "le centre est l'adresse")
verifier(abs(pts[0][0] - 43.64) > 0.008, "espacés d'environ un kilomètre")
egal(maps.audit(lms)[0]["gravite"], "bloquant", "sans place ID : l'audit le dit d'abord")
egal(maps.releve(rega), 0, "sans clé Places : rien ne part (dépense non décidée)")
appels = []


def faux_places(methode, chemin, champs, json_=None):
    appels.append(chemin)
    if chemin.startswith("/places/"):
        return {"displayName": {"text": "REGA Construction"}, "formattedAddress": "430 Av. Blaise Pascal, 34170 Castelnau-le-Lez",
                "nationalPhoneNumber": "04 99 99 99 99", "photos": [{}] * 4, "types": ["general_contractor"],
                "location": {"latitude": 43.64, "longitude": 3.90}, "businessStatus": "OPERATIONAL"}
    pos = 2 if json_["locationBias"]["circle"]["center"]["latitude"] >= 43.64 else 8
    autres = [{"id": f"autre{i}"} for i in range(10)]
    return {"places": autres[:pos - 1] + [{"id": "ChIJ_banc_rega_123"}] + autres[pos - 1:]}


maps._http = faux_places
os.environ["GOOGLE_PLACES_API_KEY"] = "cle-banc"
n = maps.tour()
egal(n, 2 * 9, "deux requêtes × neuf points relevés")
egal(maps.releve(acces.marque("rega")), 0, "une seule fois par semaine")
rega = acces.marque("rega")
res = maps.resume(rega)
verifier(res["requetes"] and res["requetes"][0]["top3"] == 6 and res["requetes"][0]["points"] == 9,
         f"top 3 sur six points sur neuf ({res['requetes'][0]})")
verifier("top 3 sur 6/9 points" in res["phrase"], f"une phrase lisible ({res['phrase']})")
au = " ".join(a["phrase"] for a in maps.audit(rega))
verifier("4 photo(s)" in au and "Horaires absents" in au, "l'audit voit les photos et les horaires qui manquent")
verifier("Téléphone différent" in au, "et le téléphone qui ne colle pas avec celui des autres supports")
verifier("Adresse différente" not in au, "« avenue » et « Av. » : la même adresse")
socle.figer(2027, 1, 4, 9)
maps.saisir(rega, maps.requetes(rega)[0], 1, "Kevin")
verifier("place" in maps.resume(rega)["phrase"], "la semaine suivante dit si on monte ou on descend")
os.environ.pop("GOOGLE_PLACES_API_KEY")

print("— Les routes publiques et l'écran")
cl = client()
r = cl.get("/parler/rega")
verifier(r.status_code == 200 and "REGA" in r.text and "/api/chat/ouvrir" in r.text, "la page de conversation")
egal(cl.post("/api/chat/ouvrir", json={"marque": "rega"}).status_code, 403, "sans l'en-tête de l'app : refusé")
r = cl.post("/api/chat/ouvrir", json={"marque": "rega", "source": "site"}, headers=X)
jt = r.json()["jeton"]
egal(cl.post(f"/api/chat/{jt}", json={"texte": "Bob"}, headers=X).json()["messages"][-1]["de"], "marque",
     "la marque répond")
egal(cl.get("/api/chat/inconnu").status_code, 404, "une conversation inconnue : 404")
for _ in range(25):
    r = cl.post("/api/chat/ouvrir", json={"marque": "rega"}, headers=X)
egal(r.status_code, 429, "ouvrir en boucle : freiné")
verifier("/parler/sazu" in cl.get("/s/chat.js?marque=sazu").text, "le bouton du site mène à la conversation")
egal(cl.get("/api/boite").status_code, 401, "la boîte exige une session")
pdg = client("101010")
bo = pdg.get("/api/boite").json()
verifier(bo["prospects"] and "delais" in bo and "crises" in bo, "la boîte sert prospects, délais, crises")
egal(pdg.get("/api/prospects.csv").status_code, 200, "l'export CSV")
rep = pdg.get("/api/reputation?marque=rega").json()
verifier(rep["lien_avis"].endswith("ChIJ_banc_rega_123") and rep["maps"]["requetes"], "la réputation d'une marque")
resp = client("202020")
egal(resp.get("/api/reputation?marque=rega").status_code, 404, "un responsable ne voit pas une autre marque")
egal(resp.post("/api/marque/rega/crise", json={}, headers=X).status_code, 404, "ni ne la met en crise")
r = resp.post("/api/marque/sazu/crise", json={"raison": "essai"}, headers=X)
verifier(r.status_code == 200 and r.json()["crise"], "sa propre marque, oui")
verifier(resp.get("/api/moi").json()["marques"][0]["crise"], "l'écran le sait")
egal(resp.post("/api/marque/sazu/crise/lever", json={}, headers=X).json()["crise"], False, "et la lève")
egal(pdg.post("/api/marque/rega/google", json={"place_id": "pas bon !"}, headers=X).status_code, 400,
     "un place ID fantaisiste est refusé")

print("— La note du lundi")
relation.recevoir(acces.marque("rega"), "facebook", "c-devis-lundi", "Eva", "DEVIS", post_id=pid)
cj = qualification.ouvrir(acces.marque("rega"))["token"]
for x in ["Eva", "0600000009", "Rénover une salle de bains de 8 m2 à Montpellier en mars", "15 000 €",
          "l'après-midi"]:
    qualification.repondre(cj, x)
t = rapport._texte(rapport.fiche(acces.marque("rega")))
verifier("Prospects qualifiés" in t, "les prospects, par température")
verifier("Google Maps : « " in t, "la position Google Maps")
verifier("Délai de réponse" in t, "le délai réel de réponse")
verifier("ce qui agace : délais" in t and "jour par jour" in t, "ce que disent les avis, et l'idée qui y répond")

socle.fin()
