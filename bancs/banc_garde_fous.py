"""Banc : le garde-fou de langage, la conformité alimentaire, les contraintes des réseaux."""
import datetime as dt

import socle
from socle import egal, verifier

from alma_social import acces, garde_fous, graines

socle.figer(2026, 12, 2, 9)
graines.semer()
sazu, rega, lms = acces.marque("sazu"), acces.marque("rega"), acces.marque("lms")
cts = acces.contraintes()
J = dt.date(2026, 12, 2)


def v(texte, m=sazu, pf="facebook", ctx=None, autres=None):
    return garde_fous.verifier_texte(texte, pf, m, cts.get(pf), ctx, autres, J)


bon = "Chaud devant 🔥 Le MÉXICO sort de la cuisine ce midi, tinga mijotée et salsa verde. Cherche SAZÚ sur Uber Eats ou Deliveroo."
egal(v(bon), [], "un texte SAZÚ correct passe")
verifier(any("restaurant" in x for x in v("Le meilleur restaurant de Boutonnet, c'est ici.")), "SAZÚ : « restaurant » refusé")
verifier(any("superlatif" in x for x in v("Le meilleur bowl de Montpellier, cuisiné ce matin pour toi.")), "superlatif refusé")
verifier(any("fait maison" in x for x in v("Nos salsas fait maison, à découvrir sur l'app, avec ton bowl du jour.")),
         "« fait maison » refusé (mention réglementée)")
verifier(any("santé" in x for x in v("Un bowl sain et équilibré pour bien finir ta journée à Boutonnet.")),
         "allégation de santé refusée pour l'alimentaire")
verifier(any("prix" in x for x in v("Le SALVADOR à 15,50 € sur Uber Eats, cuisiné ce matin.")),
         "prix non vérifié : refusé (pas de prix plutôt qu'un prix faux)")
sazu_prix = dict(sazu, products=[dict(sazu["products"][1], prix_verifie_le="2026-12-01")])
egal(garde_fous.verifier_texte("Le SALVADOR à 15,50 € sur Uber Eats et Deliveroo, cuisiné ce matin.", "facebook",
                               sazu_prix, cts.get("facebook"), None, None, J), [],
     "le même prix, vérifié hier sur les deux apps : accepté")
verifier(any("chiffre" in x for x in v("Déjà 500 bowls servis à Boutonnet cette semaine, merci à toi.")),
         "un chiffre inventé est refusé")
egal(v("Ouverture le vendredi 27 novembre à 11 h 30, cuisine de 20 m² à Boutonnet."), [],
     "les chiffres de la fiche (horaires, 20 m²) sont permis")
verifier(any("français" in x for x in v("Our new bowl is here and we love it, order now for your lunch today.")),
         "un texte en anglais est refusé")
egal(v("¡Ponle sazón! Le VERDE sort ce midi avec sa salsa suave, cherche SAZÚ sur Uber Eats ou Deliveroo."), [],
     "quelques mots d'espagnol dans une phrase française : permis")
verifier(any("certifi" in x for x in v("REGA Construction, entreprise certifiée RGE à votre service.", rega)),
         "REGA : « certifiée RGE » refusé (c'est le réseau d'artisans, pas REGA)")
verifier(any("chiffre" in x or "€" in x for x in v("Parquet stratifié posé à partir de 16 € le m².", lms)),
         "La Maison des Sols : jamais de prix")
verifier(any("identique" in x for x in v(bon, autres={"instagram": bon + " #montpellier"})),
         "deux réseaux, même texte : refusé")
long_ = "Chaud devant. " * (cts["gbp"]["caption_max"] // 14 + 2)   # au-delà de la limite du réseau, quelle qu'elle soit
verifier(any("trop long" in x for x in v(long_, pf="gbp")), "trop long pour Google Business : refusé")
verifier(any("hashtags" in x for x in v("Chaud devant " + " ".join(f"#mot{i}" for i in range(40)), pf="instagram")),
         "trop de hashtags pour Instagram : refusé")

print("— Quarantaine (protection d'image, pas validation)")
verifier(garde_fous.quarantaine({"logos_tiers": ["Pokawa"]}).startswith("logo"), "logo concurrent : quarantaine")
verifier(garde_fous.quarantaine({"document_confidentiel": "un devis lisible"}), "document lisible : quarantaine")
egal(garde_fous.quarantaine({"logos_tiers": [], "document_confidentiel": ""}), "", "photo propre : rien")

print("— Contraintes de média")
egal(garde_fous.verifier_media({"largeur": 1080, "hauteur": 1350, "poids_mo": 1.2, "video": False}, cts["instagram"]),
     [], "4:5 JPEG pour Instagram : accepté")
verifier(garde_fous.verifier_media({"largeur": 1080, "hauteur": 1920, "poids_mo": 1.2, "video": False}, cts["instagram"]),
         "9:16 en image fixe pour Instagram : refusé (ratio)")
socle.fin()
