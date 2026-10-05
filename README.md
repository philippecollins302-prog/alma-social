# ALMA SOCIAL

**Déposer une photo, toucher la marque : le reste se fait seul.**

L'application publie pour les six marques du Groupe Alma — Groupe Alma, REGA
Construction, VIP Plus, LMS La Maison des Sols, LMS PACA, SAZÚ — sans file de
validation. Une photo déposée depuis le téléphone est lue, retouchée, habillée
à la charte de la marque, déclinée en un texte différent par réseau, placée au
meilleur créneau et publiée. Les commentaires et les avis Google reçoivent une
réponse quand c'est sans risque, et une alerte quand ce ne l'est pas. Le lundi
matin, un récapitulatif dit combien de **clients** chaque marque a gagnés, et
grâce à quelles publications.

Un projet autonome : son dépôt, sa liste de paquets, ses bancs, sa propre
application chez l'hébergeur. Il ne dépend d'aucun autre projet du groupe.

---

## Le cerveau (v3)

Quatorze agents (`alma_social/agents.py`) passent tous par `ia.appeler` : modèle par agent,
contexte de marque en cache, coût inscrit dans `agent_runs`, plafond mensuel. Chaque texte
passe le garde-fou puis le Critique (`critique.py`, seuil 80, trois tours). Les plateformes
de marque (`marque.py`, graines dans `graines/plateformes.json`) sont lues par tous les
agents. Sans clé Claude, chaque agent a un repli déterministe, et l'écran Santé le dit.
L'audit de la v1 : `docs/AUDIT.md`.

## Démarrer en cinq minutes (poste de développement)

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn app:app --port 8002
```

Ouvrez http://127.0.0.1:8002 et tapez **101010** (le PDG, toutes les marques)
ou **202020** (une responsable SAZÚ d'essai, SAZÚ seulement). Ces deux codes
n'existent qu'en développement : sur un hébergeur, ils ne sont jamais créés
(`banc_secrets.py` le vérifie).

Sans aucune clé, **tout fonctionne en simulé** : la lecture d'image et les
textes passent par un repli local, et le **bac à sable**, ouvert d'office au
premier démarrage, fait tourner tout le pipeline sans rien publier. Une
semaine de publications simulées se regarde avant d'ouvrir les vannes
(Réglages → « Ouvrir les vannes », réservé au PDG, et inscrit au journal).

## Les bancs — verts avant toute poussée

```bash
sh bancs/tous.sh        # s'arrête au premier rouge
```

Sept bancs, environ 300 contrôles, une quarantaine de secondes. Aucun ne parle à
l'extérieur : chaque banc part d'une base neuve, l'horloge du produit est
figée, et le transport d'Upload-Post est remplacé par un faux qui refuse tout
appel non prévu. La CI (`.github/workflows/bancs.yml`) les relance à chaque
poussée et chaque pull request.

| Banc | Ce qu'il tient |
|---|---|
| `banc_pipeline` | d'une photo aux publications : idempotence, textes distincts, refus technique → banque, anti-doublon, STOP général, pause 48 h, trois refus → réseau en pause, retirer partout, journal |
| `banc_planificateur` | créneaux, cadence, séries, campagne d'ouverture SAZÚ, calendrier du 25 / veille / 1er, alerte de stock |
| `banc_garde_fous` | mots interdits, superlatifs, allégations, prix non vérifiés, chiffres inventés, français seulement, contraintes de réseau |
| `banc_upload_post` | champs envoyés par réseau, lecture des réponses, signature et événements du webhook |
| `banc_app` | la porte, le cloisonnement (404 hors de sa marque), CSRF, dépôt, liens tracés, journal CSV, PWA |
| `banc_relation` | tri des commentaires par gravité, FAQ vérifiée, avis 4–5 ★ / ≤ 3 ★, veille |
| `banc_secrets` | aucune clé dans le dépôt, `.env.example` complet et vide, aucun code d'essai en production, jetons chiffrés |

## Comment c'est construit

```
alma-social/
├── app.py                 l'application web : écran, API, liens tracés, webhook
├── alma_social/
│   ├── pipeline.py        d'une photo aux publications (lire → retoucher → écrire → placer → publier)
│   ├── vision.py          lire l'image (Claude) ; repli local sans clé
│   ├── images.py          retouche locale, recadrages par réseau, habillage, cartes
│   ├── nettoyage.py       effacer les objets parasites (Stability AI, sinon OpenCV)
│   ├── redaction.py       un texte par réseau, dans la voix de la marque
│   ├── garde_fous.py      les refus mécaniques : rien n'attend jamais une validation
│   ├── planificateur.py   calendrier mensuel, séries, banque de contenu, stock
│   ├── creneaux.py        le choix de l'heure, appris sur les vrais chiffres
│   ├── campagnes.py       le coup de pub (dont l'ouverture SAZÚ du 27/11)
│   ├── mesure.py          liens tracés, relevés, attribution jusqu'au client
│   ├── relation.py        commentaires, avis Google, veille concurrents
│   ├── alertes.py         urgences seulement ; rapport.py : le lundi matin
│   ├── file.py            file de travaux en base, reprise automatique
│   ├── horloge.py         ce qui tourne seul, dans le processus web
│   ├── journal.py         journal intégral, chaîné, non modifiable ; réglages
│   ├── securite.py        codes, sessions, chiffrement des jetons
│   ├── db.py              le modèle de données (PostgreSQL en production, SQLite en local)
│   └── publieurs/         L'INTERFACE PUBLISHER et ses implémentations
├── static/                l'écran du téléphone (PWA, HTML + JS sans bibliothèque)
├── graines/               les 6 marques, les contraintes des réseaux, la campagne SAZÚ
├── bancs/                 les tests
└── docs/recherche/        ce qui a été lu chez les fournisseurs, daté et sourcé
```

### La règle d'architecture : l'interface `Publisher`

Tout le reste de l'application ne parle qu'à `publieurs/base.py`. Derrière :

- `BacASable` : rien ne sort, tout est journalisé (il l'emporte sur tout réglage) ;
- `UploadPost` : l'agrégateur retenu, un **profil par marque** (`alma-<marque>`) ;
- `Ayrshare` : le repli, prêt, choisi par `SOCIAL_AGREGATEUR=ayrshare` ;
- `Direct*` : les API officielles, réseau par réseau, au rythme des validations.

On bascule **un réseau d'une marque** d'une implémentation à l'autre par un
réglage en base (`accounts.mode`), sans toucher au code. Trois sortes d'échec,
qui n'appellent pas la même réponse : `RefusReseau` (compte pour la panne :
trois d'affilée → réseau en pause + alerte), `PanneTransitoire` (on réessaie),
`NonBranche` (réglage manquant : le réseau échoue proprement, les autres partent).

### Le pipeline

1. **Recevoir** : l'original est rangé intact ; une même photo redéposée est
   reconnue (empreinte), un renvoi du téléphone aussi (référence unique).
2. **Lire** : sujet, pilier, défauts, visages, plaques, logos tiers, documents
   lisibles. Un logo concurrent ou un devis lisible → **quarantaine** + alerte.
3. **Retoucher** : exposition, balance, redressement, netteté ; nettoyage des
   objets parasites ; un recadrage par format de réseau ; habillage à la charte.
4. **Écrire** : un texte par réseau, jamais deux identiques (similarité > 0,82
   refusée), passé aux garde-fous ; le texte est stocké avec le modèle et la
   version de consigne qui l'ont produit.
5. **Placer** : le créneau du calendrier, sinon le prochain libre ; 25 minutes
   d'écart entre deux réseaux de la même photo.
6. **Publier** : sans validation. Un refus technique renvoie la photo en
   banque, sans alerte ; le journal le dit.

### L'horloge

Un fil dans le processus web, toutes les 5 secondes : la file de travaux ;
chaque minute, les avis à répondre et les fins de pause ; à 6 h le tour du
matin (remplir les créneaux, calendrier du 25, rappel de la veille, bascule du
1er, alerte de stock) ; le lundi à 8 h le récapitulatif ; les commentaires
toutes les 30 minutes, les avis toutes les heures. **Une seule instance** :
deux instances auraient deux horloges.

## Mettre en ligne (Clever Cloud)

**Une poussée sur `main` déploie toute seule** (`.github/workflows/deployer.yml`) :
les bancs d'abord, et seulement s'ils sont verts, la mise en ligne. La première
fois, le workflow fabrique l'application, la base PostgreSQL, le FS Bucket et
les variables ci-dessous ; la clé de chiffrement est tirée au hasard sur place
et n'est jamais affichée. Il faut d'abord poser trois secrets dans le dépôt
(Settings → Secrets and variables → Actions) : `CLEVER_TOKEN`, `CLEVER_SECRET`
et `SOCIAL_CODE_PDG` — plus la variable `CLEVER_ORG` si le compte Clever a
plusieurs organisations. Le déploiement n'est jugé réussi que si `clever
activity` dit OK sur le commit ET si `/sante` répond `ok`.

Ce que le workflow règle :

| Réglage | Valeur |
|---|---|
| Type | Python |
| `CC_PYTHON_VERSION` | `3.13` (la version des bancs en CI) |
| `CC_RUN_COMMAND` | `uvicorn app:app --host 0.0.0.0 --port 9000` (le port de Clever est **9000**) |
| Add-on | PostgreSQL (pose `POSTGRESQL_ADDON_URI` d'office) |
| Add-on | FS Bucket : `CC_FS_BUCKET=/fichiers:bucket-…` et `SOCIAL_FICHIERS=fichiers` (les photos) |
| Instances | **une seule**, sans mise à l'échelle |
| `zero-downtime` | **`false`** — deux instances auraient deux horloges |

**Si le bucket ne se monte pas, l'application refuse de démarrer** : sinon les
photos partiraient sur le disque éphémère de l'instance, que le déploiement
suivant efface, sans aucune erreur visible. Le message dit
lequel des deux réglages est faux ; `SOCIAL_DISQUE_SANS_GARDE=1` désarme la
garde si son hypothèse se révélait fausse chez l'hébergeur.

Les variables d'environnement sont listées dans `.env.example`, **sans
valeurs**. Les valeurs se posent dans la console de Clever, jamais dans le
dépôt. `SOCIAL_CLE_CHIFFREMENT` est **obligatoire** en production : sans elle,
l'application refuse de stocker un jeton plutôt que de le stocker en clair.

Après le premier démarrage :

1. Connexion avec `SOCIAL_CODE_PDG` ;
2. Réglages → chaque marque → **Relier les réseaux** : un lien Upload-Post
   (valable 48 h) où le responsable relie ses comptes — aucun mot de passe ne
   transite par nous ;
3. Réglages → Santé → **Brancher les notifications** (facultatif) ;
4. une semaine en bac à sable, puis **Ouvrir les vannes**.

## Les gestes qui comptent

| Geste | Où | Qui |
|---|---|---|
| **STOP général** — plus rien ne part, nulle part | Réglages | PDG |
| **Pause 48 h** d'une marque — rien ne repart sans une action | Réglages → la marque | responsable, PDG |
| **Retirer partout** une photo | Photos → la photo | responsable, PDG |
| **Flouter** visages et plaques | Photos → la photo | responsable, PDG |
| Ouvrir / refermer les vannes (bac à sable) | Réglages | PDG |
| Exporter le journal (CSV, chaîné) | Réglages → Journal | tous (sa marque) |

Instagram, TikTok et Threads n'ont pas d'API de suppression : « retirer
partout » le dit, et donne le lien de chaque publication à retirer à la main.

## Le studio et la répétition générale

**Plus → Studio.** Trois photos SAZÚ déposées d'un coup deviennent seules un
Reel (accroche, mouvements, sous-titres, fin sur l'appel) et un carrousel
(couverture, vues numérotées, appel à l'action) : le Reel part sur Instagram et
TikTok, le carrousel sur Facebook. « Fabriquer un montage » en demande d'autres
— un avant/après de chantier, par exemple. Le fond studio n'existe que pour
SAZÚ : un chantier garde son décor.

**La répétition** rejoue toute une campagne avant qu'elle parte : l'ouverture
SAZÚ (30/10 → 29/11), douze étapes, chaque visuel, chaque texte réseau par
réseau, chaque heure, le logo caché jusqu'au 13/11 à 18 h. Rien n'est publié.
Une étape sans photo du bon sujet part en carte à la charte : déposer une
photo la remplace.

## Filmer, et laisser faire

**Une vidéo se dépose comme une photo.** Une visite de chantier de quatre
minutes donne jusqu'à cinq clips de 8 à 15 secondes, choisis sur la netteté,
la lumière, le mouvement et le son, calés sur les changements de plan, au
format 9:16, avec la phrase dictée en accroche. Chaque clip est noté sur son
potentiel (Plus → Studio) et son image la plus nette entre en banque : c'est
elle qui porte le clip vers Instagram, TikTok et YouTube. Pas de sous-titres
— la parole n'est pas transcrite, et c'est écrit sur chaque clip.

**Avant de filmer**, le brief du coach (écran Déposer) dit ce qui manque à
chaque marque ; le **viseur guidé** pose la grille et dit en direct « plus de
lumière », « tenez le téléphone droit », « ne bougez plus ».

**Une photo, tous les formats** : Studio → Fabriquer → « Tous les formats »
rend carré, portrait, story, LinkedIn, miniature YouTube et fiche Google.

**Calendrier → « Quand publier, et avec quoi »** : les sept meilleurs moments
de chaque réseau, la réserve de la banque (secondes chances, gagnants,
intemporels) et les temps forts à venir.

## Mesurer jusqu'au client

**Résultats** montre d'abord les clients, par marque et par source, ce qu'ils
rapportent quand le montant est connu, et ce que ça coûte (IA + publicité).
Sous chaque marque : les décisions de la semaine (Oui / Non), ce que le carnet
a appris, le test A/B en cours, et le **terrain** :

- **QR codes** — un par support (panneau de chantier, camion, flyer, sac de
  livraison), à télécharger en SVG pour l'imprimeur. Chaque scan est compté.
- **Codes promo** — un par réseau ou par créateur ; l'offre est la vôtre.
- **Rapports de livraison** (SAZÚ) — l'export CSV de la semaine, depuis
  l'espace restaurant Uber Eats ou Deliveroo, importé tel quel.

**Brancher le site d'une marque, côté serveur** (à l'abri des bloqueurs) :
poser `SOCIAL_CONVERSIONS_SECRET` chez l'hébergeur, donner la même valeur au
développeur du site, qui envoie à chaque demande :

    POST <adresse de l'application>/api/conversions
    X-Alma-Signature: sha256=<HMAC-SHA256 du corps avec le secret>
    {"marque": "rega", "type": "devis", "id": "<id de la demande>",
     "marqueur": "<valeur du champ alma_marqueur>", "montant": 12400}

**Brancher les numéros tracés** : choisir un fournisseur qui délivre des
numéros français et prévient par webhook à la fin de chaque appel (par
exemple Invox ou Wannaspeak), poser `SOCIAL_APPELS_SECRET`, et lui donner
l'adresse `<application>/api/appels/entrant?jeton=<le secret>`. Chaque
numéro se déclare ensuite avec sa source (google, panneau, camion…).

**Le lundi à 8 h**, la note arrive par courriel ; ses décisions s'appliquent à
midi sauf « Non ». Une dépense n'est jamais appliquée seule.

## Pour aller plus loin

- `DECISIONS.md` — chaque choix technique, en une ligne, avec sa raison ;
- `API-STATUS.md` — réseau par réseau : l'état de l'accès, la date de
  vérification, la documentation officielle consultée ;
- `QUESTIONS.md` — ce qui attend une réponse ou un geste de Philippe ;
- `docs/recherche/` — les pages des fournisseurs lues le 2026-10-04, sourcées.
