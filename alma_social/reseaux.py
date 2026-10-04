"""Les réseaux : leurs noms, et la façon d'écrire pour chacun.

Les CONTRAINTES techniques (longueurs, formats, quotas) ne vivent pas ici :
elles sont en base, table `platform_constraints`, avec leur source et leur date
de vérification. Ici, seulement le style — ce qui est un choix éditorial.
"""
from __future__ import annotations

RESEAUX = ["instagram", "facebook", "linkedin", "linkedin_perso", "tiktok",
           "gbp", "youtube", "threads", "pinterest"]

NOMS = {
    "instagram": "Instagram", "facebook": "Facebook", "linkedin": "LinkedIn (page)",
    "linkedin_perso": "LinkedIn (profil)", "tiktok": "TikTok", "gbp": "Google Business",
    "youtube": "YouTube Shorts", "threads": "Threads", "pinterest": "Pinterest",
}

# Le style demandé, réseau par réseau (section 6 du cahier des charges).
STYLE = {
    "instagram": "Court, rythmé, concret. 3 à 8 hashtags utiles et LOCAUX. Le lien n'est pas "
                 "cliquable dans une légende : l'appel à l'action renvoie au lien en bio.",
    "facebook": "Un peu plus long, plus explicatif, ton chaleureux. Le lien est cliquable : "
                "l'appel à l'action finit par {LIEN}. 0 à 3 hashtags.",
    "linkedin": "Professionnel : savoir-faire, méthode, résultat concret. Aucun hashtag décoratif "
                "(0 à 3 hashtags métier au plus). Finit par {LIEN}.",
    "linkedin_perso": "À la première personne, la voix du dirigeant : ce que ce sujet dit du métier "
                      "ou de l'équipe. Sobre, aucun hashtag décoratif. Finit par {LIEN}.",
    "tiktok": "Parlé, direct. La PREMIÈRE LIGNE est une accroche qui arrête le pouce. "
              "Lien non cliquable : appel à l'action vers le lien en bio. 2 à 5 hashtags.",
    "gbp": "Factuel et utile : ce qui est proposé, la zone desservie, les horaires s'ils sont "
           "connus, puis un appel à l'action. Aucun hashtag. Pas de lien dans le texte "
           "(le bouton d'action porte le lien).",
    "youtube": "Un TITRE accrocheur (60 caractères max) et une description courte qui finit par {LIEN}. "
               "2 à 3 hashtags dont #Shorts.",
    "threads": "Une phrase, un ton léger, comme une remarque entre amis. Finit par {LIEN}. "
               "0 ou 1 hashtag.",
    "pinterest": "Descriptif et durable, pensé pour la recherche : les mots qu'on taperait pour "
                 "trouver cette image. Un TITRE (100 caractères max). Pas de hashtag.",
}

# Où le lien va. Sur ces réseaux il n'est pas cliquable dans le texte : l'appel à
# l'action renvoie vers la page « lien en bio » de la marque (/b/<marque>), qui
# liste les liens tracés des dernières publications.
LIEN_EN_BIO = {"instagram", "tiktok"}
LIEN_HORS_TEXTE = {"gbp", "pinterest"}     # le lien part dans un champ à part

# Les réseaux qui n'acceptent que de la vidéo : la photo y part en clip animé 9:16.
VIDEO_SEULEMENT = {"youtube"}

# Le format d'image préféré quand la table des contraintes n'en dit rien.
FORMAT_DEFAUT = {"instagram": "4:5", "facebook": "4:5", "linkedin": "1:1",
                 "linkedin_perso": "1:1", "tiktok": "9:16", "gbp": "4:3",
                 "youtube": "9:16", "threads": "4:5", "pinterest": "2:3"}
