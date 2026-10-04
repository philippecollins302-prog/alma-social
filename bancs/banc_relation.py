"""Banc : la relation — commentaires triés par gravité, avis Google, veille.

Sans clé de modèle : les règles locales, prudentes (dans le doute, on ne
répond pas). Bac à sable ouvert : les réponses sont simulées, rien ne sort.
"""
import datetime as dt

import socle
from socle import egal, verifier

from sqlalchemy import select

from alma_social import acces, alertes, db, garde_fous, graines, journal, relation

socle.figer(2026, 12, 2, 9)
graines.semer()
sazu, rega = acces.marque("sazu"), acces.marque("rega")
verifier(journal.bac_a_sable(), "bac à sable ouvert : les réponses sont simulées")


def conv(external_id):
    with db.moteur().begin() as c:
        return db.ligne(c.execute(select(db.conversations).where(db.conversations.c.external_id == external_id)))


def avis(external_id):
    with db.moteur().begin() as c:
        return db.ligne(c.execute(select(db.reviews).where(db.reviews.c.external_id == external_id)))


print("— La FAQ vérifiée de la marque")
egal(len(relation._faq(sazu)), 6, "les six réponses vérifiées de SAZÚ sont lues")
verifier("Uber Eats" in relation._reponse_faq(sazu, "Vous livrez à Antigone ?"),
         "« vous livrez ? » → la réponse « commander »")
verifier("VERDE" in relation._reponse_faq(sazu, "Il y a un bowl vegan ?"), "« vegan ? » → le VERDE")
egal(relation._reponse_faq(sazu, "Quel est le nom du chef ?"), "", "aucune réponse vérifiée : rien")

print("— Les commentaires, triés par gravité")
alertes.ENVOYES.clear()
relation.recevoir(sazu, "instagram", "c-q", "manon", "Vous livrez jusqu'à Antigone ?")
c = conv("c-q")
egal((c["category"], c["status"], c["replied_by"]), ("question", "repondu", "ia"),
     "question avec réponse vérifiée : répondue seule")
verifier("Uber Eats" in c["reply"], "par la réponse de la FAQ, pas par une invention")
relation.recevoir(sazu, "instagram", "c-chef", "manon", "C'est quoi le nom du chef ?")
c = conv("c-chef")
verifier(c["category"] == "autre" and not c["reply"], "question sans réponse vérifiée : aucune réponse")
relation.recevoir(sazu, "instagram", "c-merci", "leo", "Trop bon le Salvador, bravo !")
c = conv("c-merci")
egal((c["category"], c["status"]), ("compliment", "repondu"), "compliment : remercié seul")
verifier("vous" not in c["reply"].lower(), "dans la voix de SAZÚ (tutoiement)")
relation.recevoir(rega, "facebook", "c-devis", "M. Durand", "Bonjour, je voudrais un devis pour une extension.")
c = conv("c-devis")
egal((c["category"], c["status"]), ("devis", "repondu"), "devis : une première réponse part")
verifier("vous" in c["reply"], "dans la voix de REGA (vouvoiement)")
verifier(any("demande de devis" in a["sujet"] for a in alertes.ENVOYES), "ET une alerte immédiate")
relation.recevoir(sazu, "instagram", "c-plainte", "julie", "Commande arrivée froide, très déçue.")
c = conv("c-plainte")
egal((c["category"], c["status"], c["reply"] or ""), ("plainte", "alerte", ""),
     "plainte : AUCUNE réponse automatique, alerte")
verifier(any("PLAINTE" in a["sujet"] for a in alertes.ENVOYES), "l'alerte dit PLAINTE")
relation.recevoir(sazu, "instagram", "c-presse", "Midi Libre", "Bonjour, journaliste, on prépare un reportage.")
egal(conv("c-presse")["category"], "vip", "journaliste : VIP, pas de réponse automatique")
verifier(not conv("c-presse")["reply"], "et rien n'est répondu à sa place")
relation.recevoir(sazu, "instagram", "c-gros", "influence", "Trop bon !", meta={"followers": 52000})
egal(conv("c-gros")["category"], "vip", "un compliment d'un compte à 52 000 abonnés : VIP")
relation.recevoir(sazu, "instagram", "c-spam", "bot", "Gagnez des bitcoin ici")
egal(conv("c-spam")["status"], "masque", "spam : masqué")
ids = [x["external_id"] for x in relation.boite(["sazu"])]
verifier("c-spam" not in ids, "et absent de la boîte")
egal(ids[0], "c-plainte", "la boîte : la plainte en tête (urgence d'abord)")
egal(relation.recevoir(sazu, "instagram", "c-plainte", "julie", "doublon"), 0, "un message déjà vu : ignoré")

print("— Une réponse passe le garde-fou d'une publication")
egal(relation._sure(sazu, "Merci, le meilleur restaurant de Boutonnet te remercie !", "instagram"), "",
     "une réponse avec un mot interdit ne part pas")

print("— Avis Google")
alertes.ENVOYES.clear()
relation.recevoir_avis(sazu, "av-5", 5, "Le bowl Salvador était parfait, livré chaud.", "Camille R.")
a = avis("av-5")
egal(a["status"], "a_repondre", "5 ★ : réponse automatique prévue")
egal(a["reply_due_at"], db.maintenant() + dt.timedelta(hours=3), "dans trois heures (sous 24 h, pas à la seconde)")
verifier("Camille" in a["draft"] and "bowl Salvador" in a["draft"], "personnalisée : le prénom, un détail concret")
verifier(not alertes.ENVOYES, "aucune alerte pour un bon avis")
egal(relation.repondre_aux_avis_dus(), 0, "avant l'heure : rien ne part")
socle.figer(2026, 12, 2, 12, 1)
egal(relation.repondre_aux_avis_dus(), 1, "à l'heure : la réponse part seule")
egal(avis("av-5")["status"], "repondu", "et l'avis est répondu")

relation.recevoir_avis(sazu, "av-resto", 5, "Super, le restaurant est top.", "Paul")
d = avis("av-resto")["draft"]
verifier("restaurant" not in d.lower(), "le détail repris portait un mot interdit (« restaurant ») : écarté")
egal(garde_fous.verifier_texte(d, "gbp", sazu, None), [], "le brouillon passe le garde-fou")

relation.recevoir_avis(sazu, "av-2", 2, "Le bowl est arrivé froid et en retard.", "Marc D.")
a = avis("av-2")
egal(a["status"], "alerte", "2 ★ : aucune réponse automatique")
verifier(any("2 ★" in x["sujet"] for x in alertes.ENVOYES), "une alerte part")
verifier(any(a["draft"] in x["corps"] for x in alertes.ENVOYES), "avec le brouillon prêt à envoyer en un tap")
socle.figer(2026, 12, 3, 12)
relation.repondre_aux_avis_dus()
egal(avis("av-2")["status"], "alerte", "un jour après : toujours rien parti seul")
verifier(relation.envoyer_reponse_avis(a["id"], a["draft"], "Lucie"), "le responsable l'envoie en un tap")
egal(avis("av-2")["status"], "repondu", "répondu, à son initiative")
relation.recevoir_avis(sazu, "av-deja", 4, "Très bon.", "Zoé", reponse_existante="Merci Zoé !")
egal(avis("av-deja")["status"], "repondu", "un avis déjà répondu sur Google : on n'y revient pas")
egal(relation.note_moyenne("sazu"), {"avis": 4, "moyenne": 4.0}, "la note moyenne")

print("— La veille")
v = relation.veille(sazu)
verifier("concurrents suivis" in v["phrase"], "sans relevé : la phrase le dit")
cid = v["concurrents"][0]["id"]
relation.noter_concurrent(cid, posts_7j=4, par="banc")
verifier(relation.veille(sazu)["phrase"].startswith("On décroche"), "eux 4, nous 0 : « on décroche »")

socle.fin()
