# DECISIONS — un choix par ligne, avec sa raison

Les trois premières lignes répondent à la consigne « si tu préfères autre chose,
argumente en trois lignes » ; les suivantes, à « doute entre deux options : la
plus simple à maintenir ».

## Les choix qui s'écartent du cahier des charges (à confirmer en une ligne)

- **Python + FastAPI au lieu de TypeScript** : l'image (Pillow, OpenCV), le SDK Claude et les bancs vivent mieux en Python ; le dépôt du groupe est déjà en Python, donc un seul langage à faire reprendre.
- **Upload-Post au lieu d'Ayrshare** : Ayrshare exige la formule Launch (299 $/mois, ≈ 254 €) pour six profils, soit au-dessus du budget à lui seul. Upload-Post Professional coûte 50 $/mois (≈ 42 €) pour 25 profils et couvre nos neuf voies, réponses aux avis Google comprises. Ayrshare reste branché en repli (`SOCIAL_AGREGATEUR=ayrshare`) — sources dans `docs/recherche/agregateur.md`.
- **La veille concurrents se saisit à la main** (posts de la semaine, note Google) : aspirer leurs pages enfreint les conditions des réseaux, et un compte suspendu coûte plus que la veille.

## Architecture

- Un dépôt et une application à part, sans lien avec les autres projets du groupe : une panne, une clé ou un déploiement de l'un ne touche jamais l'autre.
- Une seule application web (écran + API + horloge) : pas de Redis ni de second processus à surveiller ; la file de travaux vit en base.
- PostgreSQL en production (add-on Clever), SQLite en développement : SQLAlchemy Core, une définition des tables pour les deux.
- Les photos sur un FS Bucket monté, pas sur un stockage d'objets : fichiers écrits une fois, jamais réécrits, sans frais ni clé supplémentaire.
- L'application refuse de démarrer si le bucket annoncé n'est pas monté : sinon les photos iraient sur un disque que le prochain déploiement efface (un montage raté ne fait aucune erreur visible).
- Une seule instance et `zero-downtime=false` : deux instances auraient deux horloges et publieraient deux fois.
- L'horloge du produit est en UTC en base et en heure de Paris à l'écran ; `db.figer_horloge()` la fige pour les bancs.
- L'interface `Publisher` a trois sortes d'échec (refus, panne passagère, non branché) parce qu'elles n'appellent pas la même réponse.
- Le bac à sable l'emporte sur tout réglage de compte, et il est ouvert au premier démarrage.
- Un profil Upload-Post par marque, nommé d'office `alma-<marque>` : rien à inventer, rien à retenir ; le nom est rangé chiffré.
- Les comptes se relient par le lien de connexion d'Upload-Post (48 h) : aucun mot de passe ne transite par nous.
- Le webhook est facultatif : un envoi long se confirme par l'historique d'Upload-Post toutes les deux minutes ; le bouton « Brancher les notifications » range lui-même le secret, chiffré.
- LinkedIn « page » refuse de partir sans identifiant de page : sans lui, Upload-Post publierait sur le profil personnel.

## Le pipeline

- Claude (`claude-opus-5-5`, effort bas) lit l'image et écrit les textes en sortie structurée ; sans clé, un repli local garde l'application vivante.
- Chaque texte est stocké avec le modèle et la version de consigne qui l'ont produit, pour comprendre une dérive.
- La retouche est locale (Pillow, OpenCV) : gratuite, instantanée, reproductible ; seul le nettoyage des objets parasites appelle un service (Stability AI « Erase », 0,05 $ l'image, synchrone).
- La retouche est réglable par marque (`kit.retouche`), pas imposée : le Drive limite SAZÚ à l'exposition.
- L'original n'est jamais modifié : rangé sous son empreinte, les déclinaisons à côté, mises en cache.
- L'anti-doublon compare une empreinte visuelle (pHash) sur 90 jours : un recadrage ou un réexport est reconnu.
- Pas deux textes semblables d'un réseau à l'autre (similarité > 0,82 refusée) : un gabarit distinct par réseau même sans modèle.
- Instagram ne reçoit jamais d'adresse dans la légende (« lien en bio ») : la page `/b/<marque>` liste les dernières publications, chacune tracée.
- 25 minutes d'écart entre deux réseaux de la même photo : un même sujet ne sature pas le fil de l'abonné.
- Un refus technique renvoie la photo en banque, au journal, sans alerte ; trois refus d'affilée sur un réseau le mettent en pause, avec alerte.

## Les garde-fous

- Ce sont des refus mécaniques, jamais une file d'attente : `requires_approval` existe par marque, éteint partout.
- Le garde-fou de langue compte les mots outils français contre l'anglais, l'espagnol et l'allemand : « ¡Ponle sazón! » passe, un paragraphe anglais non.
- Un prix ne s'écrit que s'il est identique sur toutes les apps et vérifié depuis moins de 8 jours : pas de prix plutôt qu'un prix faux (une réclamation sur une app de livraison).
- Un chiffre absent de la fiche de la marque est refusé : le modèle n'invente ni délai, ni nombre de clients.
- Une photo avec un logo concurrent ou un document lisible part en quarantaine, avec alerte : c'est une protection d'image, pas une validation.
- Le journal est chaîné (chaque ligne porte l'empreinte de la précédente) et des déclencheurs interdisent de le modifier ou d'en effacer une ligne.

## Le planificateur

- Les créneaux partent du bon sens du secteur, puis apprennent sur les vrais chiffres de la marque (poids recalculés le 1er de chaque mois).
- La cadence vise le milieu de la fourchette de la marque (3–5 → 4 par semaine).
- Pas de week-end pour le B2B ; deux jours consécutifs seulement si la semaine ne se remplit pas autrement.
- Le calendrier du mois est proposé le 25, rappelé la veille, appliqué le 1er même sans validation.
- La banque recycle une photo publiée après 90 jours, avec un nouveau texte et un nouveau cadrage.
- L'alerte de stock dit précisément ce qui manque (« 3 photos de plats et 1 photo d'équipe avant vendredi »), une fois par semaine.
- Une étape de campagne sans photo devient une carte à la charte : une campagne ne rate jamais son rendez-vous.
- SAZÚ ne publie rien avant le 27/11/2026 (`links.calendrier_des`) hors campagne d'ouverture, et rien le lundi (fermé).

## La mesure et la relation

- Un raccourcisseur maison (`/go/<code>`), un code par publication et par réseau : chaque clic se rattache à sa publication.
- Le marqueur `am` suit le visiteur jusqu'au formulaire du site (`/s/marqueur.js`, 30 jours) : la demande de devis se rattache à la publication qui l'a déclenchée.
- SAZÚ : un seul lien dans la publication, puis une page de choix Uber Eats / Deliveroo, chaque bouton tracé à part.
- Les commentaires se relèvent toutes les 30 minutes sur 14 jours : Upload-Post n'a pas d'événement « commentaire ».
- Le tri des commentaires est prudent : plainte, VIP, indésirable et « autre » ne reçoivent jamais de réponse automatique.
- Un compte de 10 000 abonnés et plus passe en VIP, quel que soit son message.
- Une réponse automatique repasse le même garde-fou qu'une publication ; si elle échoue, rien ne part.
- Avis Google 4–5 ★ : réponse automatique trois heures après la réception (« sous 24 h » sans sentir la machine) ; ≤ 3 ★ : alerte et brouillon, rien ne part seul.
- Les alertes sont dédoublonnées et réservées aux urgences ; aucune notification par publication.

## La sécurité

- Un code personnel par personne (6 caractères et plus, haché), six essais faux par quart d'heure et par adresse.
- Un responsable ne voit que sa marque ; une autre lui répond 404, pas 403.
- Les écritures de l'API exigent l'en-tête `X-Alma` (protection CSRF) ; seuls les formulaires des sites (`/api/leads/web`) en sont dispensés.
- Les jetons et profils des réseaux sont chiffrés en base (Fernet) ; sans `SOCIAL_CLE_CHIFFREMENT` en production, l'application refuse de stocker.
- Les codes d'essai (101010, 202020) n'existent qu'en développement : base SQLite ET aucun hébergeur détecté.
- Les images publiques (`/m/<jeton>`) portent un jeton de 32 caractères aléatoires, qui ne dit rien de la marque.

## L'écran

- Une PWA sans bibliothèque ni étape de construction : elle s'ouvre depuis un lien et s'ajoute à l'écran d'accueil.
- Les photos attendent dans le téléphone (IndexedDB) jusqu'à l'accusé de réception, avec une référence unique : un sous-sol sans réseau ne perd rien, un renvoi ne crée rien deux fois.

## v3 — le cerveau (jalon 1, 05/10/2026)

- Une équipe de 14 agents (`alma_social/agents.py`), chacun avec son niveau de modèle : le plus capable (Opus 5.5) pour le Stratège, le Critique, l'Analyste, le Média acheteur et Demander ; le rapide (Sonnet 5.5) pour le volume ; le petit (Haiku 4.5) pour le tri. Le niveau se règle agent par agent dans Réglages, sans redéployer.
- Tous les appels passent par `ia.appeler` et sont inscrits dans `agent_runs` : agent, marque, objet, modèle qui a VRAIMENT répondu, version des consignes, entrées, sortie, jetons, coût, durée.
- Le contexte de marque part en cache côté modèle : identique d'un appel à l'autre, il coûte dix fois moins cher relu.
- Plafond IA mensuel (150 $ par défaut, réglable) : au-delà, chaque agent passe sur son repli et UNE alerte part. Une dépense non décidée n'a pas lieu.
- La plateforme de marque est versionnée ; une preuve ne peut citer qu'un fait de la base ; la mise en scène suit le secteur et le modèle ne peut pas la changer (SAZÚ : fond studio permis ; chantiers et sols : décor réel).
- Le Critique note sur 100 (9 critères pondérés) ; sous 80, réécriture avec les remarques, trois tours, puis retour à la banque. Sans clé, une grille locale ne juge que la forme : seuil 60, et chaque note porte le nom de son juge — sinon plus rien ne sortirait du bac à sable sans clé.
- La voix apprend des corrections par des règles lisibles (mot retiré, plus court, emoji, tutoiement), pas par un modèle : on sait toujours pourquoi elle a bougé. Trois corrections du même genre font une règle.
- Une leçon n'entre au carnet qu'avec au moins six publications et sa période ; une nouvelle mesure sur la même clé remplace l'ancienne (« contredite », gardée lisible).
- « Demander » répond avec un instantané calculé par le code ; ses actions sont une liste fermée (pause, reprise) exécutée avec les droits de la personne.
- Le copilote = l'ancien « validation requise », désactivé partout ; il n'a pas d'écran « approuver / rejeter », seulement « Laisser partir » dans Aujourd'hui.
- La base de production reçoit les colonnes nouvelles par une migration douce (ajout seulement, jamais de retrait).
- Interface : nuit d'encre par défaut, or du groupe en accent, Archivo Black + DM Sans servies localement, 9 écrans (5 onglets + « Plus »).
- « lien en bio » n'est plus pris pour le mot interdit « bio » de SAZÚ (faux positif qui refusait toute légende Instagram).

## v3 — le studio et la répétition générale (jalon 2, 05/10/2026)

- Le studio (`alma_social/studio.py`) fabrique en local, sans service extérieur : retouche culinaire (lumière de fenêtre plutôt que néon, chaleur, éclat sans saturation criarde), Reel 9:16 à partir de photos, carrousel 4:5, avant/après en image et en rideau vidéo. Gratuit, instantané, aucune photo ne sort de la maison pour être montée.
- Le fond studio est refusé PAR LE CODE à toute marque qui montre des réalisations (`RegleHonnetete`) : un chantier montré est ce chantier-là. Pour SAZÚ, le plat est détouré et posé sur le fond de la marque, ses pixels ne sont jamais repeints — et le traitement le déclare.
- Reel : l'accroche est lisible dès la première image (on décide en une seconde de rester), sous-titres mot à mot dans une pastille lisible au soleil, barre de progression, fin de deux secondes sur l'appel à l'action. Aucune musique incrustée : le réseau ajoute un titre de SA bibliothèque commerciale ; on n'embarque jamais un titre protégé.
- L'accent de la marque n'est employé sur fond sombre que s'il s'y lit (la framboise de SAZÚ sur l'olive ne se lit pas) ; sinon un beurre chaud.
- Une rafale (3 photos SAZÚ en trois heures) devient seule un Reel ET un carrousel. La marque produit attend dix minutes avant de placer une photo, le temps que la rafale arrive entière. La 1re photo porte les montages au calendrier ; les autres passent « studio » et ne repartent pas seules la même semaine.
- Quel montage pour quel réseau : Reel sur Instagram, TikTok, YouTube (la vidéo courte y porte) ; carrousel sur Facebook et LinkedIn (on y lit). Upload-Post reçoit plusieurs `photos[]` dans l'ordre pour un carrousel, `video` + `media_type=REELS` pour un Reel.
- Le logo du montage suit la règle de l'heure : fabriqué avant le 13/11 18 h, un montage SAZÚ est SANS logo ; une publication après la révélation peut le porter.
- Les bornes de ratio des fiches réseau valent pour les IMAGES du fil ; une vidéo n'est bornée que là où la fiche est verticale (YouTube Shorts). Un Reel 9:16 sur Instagram n'est pas une faute.
- La vraie durée d'une vidéo du studio est gardée (`renditions.duration_s`) : le garde-fou des durées juge la vidéo réelle, pas une valeur par défaut.
- La répétition générale (`alma_social/repetition.py`) rejoue une campagne comme l'horloge le fera — mêmes textes, garde-fous, Critique, logo à l'heure de l'étape — sans écrire un post, sans toucher un créneau, sans ranger une carte en banque. Ses visuels ne se servent qu'à qui voit la marque.
- La première répétition de l'ouverture SAZÚ a trouvé trois défauts du texte de secours (sans clé IA) qui seraient partis le 30/10 : « Nouvelle publication » sur TikTok et Google, la fiche interne (« dark kitchen… ») recopiée dans Facebook, et un TikTok identique à l'Instagram le Jour J. Corrigés : la tête courte vient de l'accroche de l'étape, Facebook parle avec la PROMESSE de la plateforme de marque, chaque réseau garde sa construction.
- Le texte de secours n'utilise une accroche de la plateforme que pour une marque produit : « Ce mur porte désormais trois étages » serait une affirmation sur CE chantier, que rien ne vérifie. Et jamais une accroche chiffrée (« Jour 1 → livraison » était refusée par le garde-fou des chiffres).

## v3 — l'étendue (jalon 3, 05/10/2026)

- **Les sept meilleurs créneaux** par marque et par réseau (`creneaux.sept_meilleurs`), notés sur 100, au plus deux par jour et à trois heures d'écart : sept fois le même lundi midi n'apprendrait rien. Tant que la marque n'a pas assez de mesures, ce sont les repères du secteur, et l'écran le dit.
- **20 % d'exploration** : une publication sur cinq part sur une heure moins sûre, pour apprendre. Tirage déterministe (la même publication rejouée garde son heure) ; jamais une heure imposée, jamais une seconde chance. Le rapport de garde dit `exploration` ou `meilleur`.
- **La banque se trie seule chaque matin** (`recyclage.classer`) : une publication sous 60 % de la médiane de la marque mais jugée bonne (≥ 75) par le Critique a droit à UNE seconde chance, trois semaines plus tard, recadrée plus serré et avec un texte neuf ; un gagnant (≥ 150 % de la médiane) entre dans les intemporels et ressort après 45 jours sur un pilier evergreen. Moins de cinq publications comparables : on ne juge pas.
- **Publication conditionnelle** (`conditions.py`) : « ne sors celle-ci que si celle-là dépasse tel engagement ». On attend jusqu'à 48 h la mesure ; une condition décidée « non » garde sa raison et annule la publication, au journal.
- **Les temps forts** (`graines/temps_forts.json`) posent leurs créneaux trois semaines avant, marque par marque, avec une consigne. Une date incertaine n'est PAS écrite : les salons attendent leurs dates officielles (`a_confirmer`), affichées à l'écran comme telles.
- **Le coach** (`coach.py`) dit, avant d'aller filmer, ce qui manque à la banque de chaque marque — trois plans précis, un exemple, un style — et le **viseur guidé** (`static/js/viseur.js`) accompagne la prise : grille des tiers, conseils en direct (lumière, bougé, horizon, netteté), mesurés dans le téléphone, rien n'est envoyé avant le dépôt.
- **Vidéo longue → clips** (`clips.py`) : une vidéo déposée est rangée telle quelle et ne part JAMAIS entière. ffmpeg la lit à 2 images/s (netteté, lumière, mouvement en cloche, son) et repère les changements de plan ; jusqu'à cinq fenêtres de 8 à 15 s, les mieux notées, sans chevauchement, calées sur une coupe à moins d'une seconde. Cinq est un plafond, pas un objectif : un passage mort (noir, flou, immobile et muet) ne devient pas un clip pour faire le compte.
- Chaque clip : 9:16 1080×1920, H.264 + AAC, recadrage au centre, l'accroche (la phrase dictée au dépôt, sinon la signature de marque — jamais une phrase inventée sur un chantier réel) sur les deux premières secondes, la marque en coin si son logo est permis à cette date. **Aucun sous-titre** : rien ne transcrit la parole aujourd'hui, et un sous-titre inventé serait pire que pas de sous-titre. Chaque clip le déclare.
- L'image la plus nette de chaque clip entre en banque comme une photo déposée (`client_ref video:<id>:still<n>`) : c'est elle que le planificateur place, et elle porte son clip vers Instagram, TikTok et YouTube (et Facebook, LinkedIn quand il n'y a pas de carrousel). Google reste en photo. Les images fixes d'une vidéo n'entrent jamais dans une rafale du studio.
- Le clip est le seul montage permis à une marque de réalisations : ce sont des images réelles, coupées, jamais retouchées. Les autres montages restent aux produits.
- Plafonds : 200 Mo et 20 minutes par vidéo (au-delà, le message dit le geste : filmer en 1080p, couper avant). Un découpage interrompu reprend sans refaire les clips déjà faits.
- **La déclinaison totale** (studio, type `declinaison`) : une prise → carré, portrait 4:5, story 9:16, LinkedIn 1200×627, miniature YouTube 1280×720 (le titre en grand : c'est elle qu'on clique), fiche Google 1200×900. Chaque format est recadré sur le sujet, jamais étiré, habillé à la charte. Le fond studio y reste interdit aux réalisations.
- L'écran **Calendrier → « Quand publier, et avec quoi »** montre les sept créneaux par réseau relié, la réserve (gagnants, secondes chances, intemporels) et les temps forts des deux mois.
