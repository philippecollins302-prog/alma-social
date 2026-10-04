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
