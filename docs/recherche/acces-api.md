# Accès aux API de publication — état au 2026-10-04 et dossiers à préparer

Chaque exigence est tirée d'une page officielle lue le **2026-10-04** (URL citée).
Ce qui n'a pas pu être lu sur une page officielle est marqué **NON CONFIRMÉ**.
Les **délais** sont presque partout absents des docs officielles : ils sont donnés
quand Meta/Google/Pinterest les écrivent, et marqués NON CONFIRMÉ sinon.

---

## Synthèse

| Plateforme | Ce qu'il faut demander | Bloquant tant que non accordé | Délai officiel | Où déposer |
|---|---|---|---|---|
| Instagram | Accès **Advanced** à `instagram_business_content_publish` (Instagram Login) ou `instagram_content_publish` (Facebook Login) + App Review + Business Verification — **sauf** si l'app ne sert que des comptes de l'entreprise propriétaire de l'app (Standard Access suffit, pas de review) | Comptes tiers sans rôle sur l'app | App Review : « decision within a week » ; Business Verification : jusqu'à 14 jours ouvrés **NON CONFIRMÉ** | https://developers.facebook.com/apps/ |
| Facebook Page | Accès Advanced à `pages_manage_posts`, `pages_read_engagement`, `pages_show_list` (+ même règle Standard/Advanced) | idem | idem | idem |
| Threads | App « cas d'usage Threads » ; App Review de `threads_basic` + `threads_content_publish` ; app publiée | Seuls les **testeurs Threads invités** peuvent l'utiliser | non publié (même circuit App Review Meta) | idem |
| LinkedIn profil | Produit **Share on LinkedIn** (`w_member_social`) — **self-service, sans review** | — | immédiat (permission ouverte) | https://www.linkedin.com/developers/apps |
| LinkedIn page | **Community Management API** : tier Development (formulaire) puis tier **Standard** (formulaire + screencast + identifiants de test) | Development : 500 appels/app/24 h, 100/membre/24 h, 12 mois pour finir | non publié (**NON CONFIRMÉ**) | idem, onglet Products |
| TikTok | Revue de l'app (Login Kit + Content Posting API, scope `video.publish`) puis **audit Content Posting API** | Non audité : `SELF_ONLY`, comptes privés, 5 utilisateurs/24 h | non publié (**NON CONFIRMÉ** ; tiers : 2-6 semaines) | https://developers.tiktok.com/application/content-posting-api |
| Google Business Profile | Formulaire « Application for Basic API Access » | Quota à **0 QPM** | non publié (**NON CONFIRMÉ**) | https://support.google.com/business/contact/api_default |
| YouTube | **Audit** « YouTube API Services – Audit and Quota Extension Form » (+ vérification OAuth du scope sensible) | Vidéos forcées en **privé** (projets créés après le 28/07/2020) ; 100 uploads/jour/projet | audit : « as soon as possible » ; vérif. OAuth : 3-5 jours ouvrés | https://support.google.com/youtube/contact/yt_api_form |
| Pinterest | Accès **Trial** (formulaire) puis **Standard** (bouton Upgrade + vidéo) | Trial : épingles visibles **seulement par leur créateur**, 300 écritures/jour/app | Trial : revue « each business day » ; Standard : « reviewed regularly » | https://developers.pinterest.com/apps/ |

---

## 1. Meta — Instagram, Facebook Page (une app Meta)

### Ce qu'il faut savoir avant de déposer quoi que ce soit

- **Deux variantes d'API Instagram** — https://developers.facebook.com/docs/instagram-platform/overview — vérifié le 2026-10-04 :
  - *Instagram API with Instagram Login* : comptes professionnels Instagram **sans Page Facebook** ; permissions `instagram_business_basic` + `instagram_business_content_publish`. Pas de recherche de hashtags, pas de tags produits.
  - *Instagram API with Facebook Login* : compte Instagram **lié à une Page Facebook** ; permissions `instagram_basic`, `instagram_content_publish`, `pages_read_engagement` (+ `ads_management`/`ads_read` si le rôle sur la Page passe par Business Manager) — https://developers.facebook.com/docs/instagram-platform/content-publishing/ — vérifié le 2026-10-04. L'upload reprenable de grosses vidéos n'existe **que** via Facebook Login for Business (même page).
  - **Recommandation** : Facebook Login, puisque l'app publie aussi sur la Page Facebook — un seul consentement couvre IG + FB.
- **Standard ou Advanced Access** — même page overview, vérifié le 2026-10-04 :
  - *Standard Access* (par défaut) « suffices for apps serving only your own accounts » ; Advanced Access est « required if your app serves Instagram professional accounts that you don't own or manage », et exige App Review + Business Verification.
  - La page App Review Instagram dit que pour une app qui ne sert qu'**une seule entreprise possédée/gérée**, « App Review [is] Not required » — https://developers.facebook.com/docs/instagram-platform/app-review — vérifié le 2026-10-04.
  - Business Verification n'est pas requise si l'app n'est utilisée que par des personnes ayant un **rôle sur l'app** ou dans le Business qui l'a revendiquée — https://developers.facebook.com/docs/development/release/business-verification — vérifié le 2026-10-04.
  - **⇒ Décision à faire prendre au client** : si l'app ne publie que sur **ses propres** comptes (ceux de son Business Manager), l'app peut être créée **dans son Business**, ses gestionnaires y ont un rôle, et **aucune App Review n'est nécessaire**. Si l'app doit servir des comptes de **tiers** (clients du client), c'est Advanced Access : dossier complet ci-dessous.
- Permissions Page — https://developers.facebook.com/docs/graph-api/reference/page/photos/ et https://developers.facebook.com/docs/video-api/guides/reels-publishing — vérifié le 2026-10-04 : `pages_manage_posts`, `pages_read_engagement`, `pages_show_list` ; jeton de Page d'une personne ayant la tâche `CREATE_CONTENT` ; la page posts cite aussi `pages_manage_engagement`, `pages_read_user_engagement` et `publish_video` pour la vidéo — https://developers.facebook.com/docs/pages-api/posts — vérifié le 2026-10-04.

### Démarches (cas Advanced Access)

1. **Business Verification** — App Dashboard → Settings → Basic → Verification → « Start Verification » → Business Manager — https://developers.facebook.com/docs/development/release/business-verification — vérifié le 2026-10-04.
   - Pièces : documents officiels portant **raison sociale et adresse** (extrait Kbis, statuts…), pas de document auto-rempli sans cachet ni signature, pas de document expiré ; délai « up to 14 business days » — **NON CONFIRMÉ** (page d'aide `facebook.com/business/help/2058515294227817` illisible par l'outil, chiffres vus dans l'extrait du moteur de recherche seulement).
2. **App Review** — guide de soumission : https://developers.facebook.com/docs/resp-plat-initiatives/individual-processes/app-review/submission-guide — vérifié le 2026-10-04 :
   1. choisir permissions et fonctionnalités ;
   2. Business Verification terminée ;
   3. répondre aux questions de traitement des données ;
   4. paramètres : **icône 1024×1024**, **URL de politique de confidentialité**, objectif de l'app (« Yourself or your own business » / « Clients »), catégorie, e-mail de contact accessible ;
   5. **instructions pas à pas** pour que le testeur Meta se connecte, et **identifiants de test** ;
   6. pour **chaque** permission : description de l'usage + **screencast dédié** ;
   7. soumettre. « You should receive a decision within a week. »
   - **Prérequis technique** : « Make at least 1 successful API call using each permission for which you are requesting advanced access. Calls must be made within **30 days** of submitting. »
   - Screencasts : **1080p minimum**, curseur visible, interface en **anglais** si possible ; sinon sous-titres/infobulles qui expliquent chaque bouton (https://developers.facebook.com/docs/instagram-platform/app-review).
   - URL de suppression des données utilisateur : exigée dans les paramètres de l'app — **NON CONFIRMÉ** (non lu sur les pages consultées ce jour ; à vérifier dans le tableau de bord au moment du dépôt).

### Dossier à préparer (Meta)

- [ ] Business Manager du client avec raison sociale exacte, adresse, téléphone, site web sur un domaine à lui
- [ ] Kbis récent (< 3 mois conseillé — **NON CONFIRMÉ**) + justificatif d'adresse au nom de la société
- [ ] Politique de confidentialité publique sur le domaine du client, qui mentionne Instagram/Facebook/Threads et la suppression des données
- [ ] Icône 1024×1024
- [ ] Compte de test (identifiant + mot de passe) avec un compte IG pro et une Page de test déjà reliés
- [ ] Instructions pas à pas en anglais (connexion → choix de la Page/du compte → composition → publication → vérification sur Instagram)
- [ ] Un screencast par permission (1080p, anglais ou sous-titré) : écran de consentement Meta, sélection des comptes, publication réelle, résultat visible sur la plateforme
- [ ] Preuve d'au moins un appel réussi par permission dans les 30 jours précédant le dépôt

---

## 2. Threads (app Meta dédiée)

Source : https://developers.facebook.com/docs/threads/get-started — vérifié le 2026-10-04

- Créer une app Meta avec le **cas d'usage Threads** ; utiliser **l'ID d'app et le secret Threads** (pas l'autre paire affichée).
- Permissions : `threads_basic` (obligatoire partout), `threads_content_publish` ; en option `threads_manage_replies`, `threads_read_replies`, `threads_manage_insights`.
- Avant App Review : « only Threads testers can use your app » — inviter chaque compte depuis le tableau de bord, la personne accepte dans son profil Threads.
- Pour le public : chaque permission validée en App Review **et** app publiée.
- Jetons : court 1 h, long **60 jours** ; consentement valable 90 jours pour un profil public.
- Business Verification pour Threads : **NON CONFIRMÉ** (non mentionnée sur la page). Délai : non publié.
- **Dossier** : identique au dossier Meta ci-dessus, avec un screencast pour `threads_basic` et un pour `threads_content_publish`.
- Si seuls les comptes Threads du client publient, l'ajout comme **testeurs** permet de publier sans App Review (même page) — à confirmer comme usage durable : **NON CONFIRMÉ** (la doc parle de test, pas de production).

---

## 3. LinkedIn

### 3a. Profil personnel — Share on LinkedIn

- `w_member_social` est une **permission ouverte** : « available to all developers, and may be added via self-service through the LinkedIn Developer Portal, under the Products tab » — https://learn.microsoft.com/en-us/linkedin/shared/authentication/getting-access — vérifié le 2026-10-04. **Toujours ouverte aux nouvelles apps.**
- Ajouter aussi « Sign in with LinkedIn using OpenID Connect » (`openid profile email`) pour identifier la personne.
- Plafonds : **150 requêtes/membre/jour**, **100 000/app/jour** — https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin — vérifié le 2026-10-04.
- Prérequis : une **Page LinkedIn** de l'entreprise à associer à l'app (exigé à la création d'app — **NON CONFIRMÉ** sur les pages lues ce jour ; la doc CM le dit pour CM).
- Délai : immédiat. Dossier : aucun.

### 3b. Page entreprise — Community Management API

Sources : https://learn.microsoft.com/en-us/linkedin/marketing/community-management-app-review · https://learn.microsoft.com/en-us/linkedin/marketing/increasing-access · https://learn.microsoft.com/en-us/linkedin/marketing/community-management/community-management-overview — vérifiés le 2026-10-04

- **Créer une app NEUVE** : la demande CM est grisée sur une app qui a déjà d'autres produits (FAQ de l'overview). ⇒ prévoir **deux apps** : une « Share on LinkedIn » (immédiate) et une « Community Management » (qui inclut d'ailleurs `w_member_social`, `w_organization_social`, `r_organization_social`, `rw_organization_admin`…).
- **Tier Development** (formulaire dans Products) — vérifié :
  - réservé aux **organisations légalement enregistrées**, usage **commercial** ;
  - fournir : **raison sociale, adresse du siège, site web, politique de confidentialité**, **e-mail professionnel** (vérifié par lien ; adresses perso refusées) ;
  - un **super admin de la Page LinkedIn** de l'organisation doit **vérifier** l'app ;
  - le nom/logo de l'app ne doit contenir **aucune** partie des noms ou logos LinkedIn/Microsoft ;
  - si refus : **impossible de redemander avec la même app**, il faut une nouvelle app ;
  - tier accordé : 500 appels/app/24 h, 100/membre/24 h, pas de BATCH_GET ni de webhooks ; 12 mois pour terminer l'intégration.
- **Tier Standard** (formulaire dans My Apps → Products, une fois l'intégration finie) — vérifié :
  - présentation de la société et du produit, description du cas d'usage, **identifiants de test** pour les relecteurs ;
  - **screencast** haute résolution, **téléchargeable**, limité aux écrans de l'app, narration recommandée, montrant pour le cas « Page Management » : le parcours OAuth complet, **une publication sur la Page via l'app**, l'affichage d'un **commentaire** d'un membre sur ce post, les **champs de profil** du commentateur affichés, toute autre fonction utilisant des données de membres ; si une fonction n'existe pas dans l'app, **le dire dans la vidéo** ;
  - pour publier sur le profil des dirigeants (cas « Executive Management ») : même chose côté profil ;
  - revue : cas d'usage approuvé, politique de confidentialité valide, conformité termes/sécurité/stockage, vidéo fidèle ;
  - refus : nouvelle app + nouvelle demande Development.
- Délai : « Restricted APIs are evaluated on a case-by-case basis with no fixed timeline » (pour les API restreintes) ; pour CM, **aucun délai publié** — **NON CONFIRMÉ**.

### Dossier à préparer (LinkedIn CM)

- [ ] Page LinkedIn du client + un **super admin** disponible pour valider l'app
- [ ] E-mail professionnel sur le domaine du client
- [ ] Raison sociale, adresse du siège, site web, URL de politique de confidentialité (mentionnant LinkedIn)
- [ ] Nom et logo d'app sans « Linked », « In », ni logo Microsoft
- [ ] Description du cas d'usage : « Page Management » (+ « Executive Management » si profils)
- [ ] Compte de test pour les relecteurs
- [ ] Screencast narré (anglais conseillé) couvrant les 5 points ci-dessus, fichier téléchargeable
- [ ] Viser `Linkedin-Version` ≥ 202609 : 202510 est coupée le 15/10/2026

---

## 4. TikTok — Content Posting API

Sources : https://developers.tiktok.com/doc/app-review-guidelines · https://developers.tiktok.com/doc/getting-started-create-an-app · https://developers.tiktok.com/doc/content-sharing-guidelines · https://developers.tiktok.com/doc/content-posting-api-get-started — vérifiés le 2026-10-04 (pages « Last updated August 4, 2026 »)

### ⚠ Risque de refus à trancher AVANT de déposer

La section « Intended Use » des Content Sharing Guidelines dit, mot pour mot :
- « API Clients must not be limited to test applications and should be intended for a wide audience, not limited to internal groups/private use. **Not acceptable: A utility tool to help upload contents to the account(s) you or your team manages.** ❌ »
- La revue d'app ajoute : « Apps must not be for private or personal use. » et « Apps that are still in development or testing will not be approved. »

⇒ Si l'outil du client sert à publier **sur ses propres comptes**, l'audit Direct Post a de fortes chances d'être **refusé**. Alternatives :
1. **Mode brouillon (`video.upload`, endpoint `/post/publish/inbox/…`)** : la vidéo/les photos arrivent dans la boîte de réception TikTok et la personne termine la publication **dans l'app TikTok** — https://developers.tiktok.com/doc/content-posting-api-get-started-upload-content — vérifié le 2026-10-04. Il faut l'approbation du scope `video.upload` ; la doc ne mentionne **pas** d'audit pour ce mode (exemption **NON CONFIRMÉE**). Plafond : 5 brouillons en attente / 24 h.
2. Présenter honnêtement un produit destiné à un **large public** (si c'est vraiment le cas) — sinon ne pas maquiller : un audit trompeur expose à la coupure de l'app.

### Démarches

1. **Compte développeur** + **organisation** (recommandée) sur developers.tiktok.com ; « Connect an app » sous l'organisation.
2. **Configuration** : nom personnalisé (pas « TikTok », ne décrit pas une fonction), icône **1024×1024 JPEG/PNG ≤ 5 Mo**, catégorie, description visible des utilisateurs, plateforme Web + **URL de redirection**, produits **Login Kit** + **Content Posting API** (Direct Post activé), scopes `video.publish` (et/ou `video.upload`) — vérifiés sur les pages Direct Post / Upload — plus `user.info.basic` pour Login Kit (**NON CONFIRMÉ** ce jour) ; **vérification de domaine / préfixe d'URL** pour `PULL_FROM_URL` (obligatoire pour les photos).
3. **Revue de l'app** (Production) — critères vérifiés :
   - **site web officiel complet** (pas une page de connexion ni une landing) avec liens **Politique de confidentialité** et **Conditions d'utilisation** visibles **sans ouvrir de menu** ;
   - explication détaillée de l'usage de **chaque produit et scope** ;
   - **1 à 5 vidéos de démo, 50 Mo max chacune**, parcours complet de bout en bout ; si l'app n'a jamais été approuvée, la démo se fait dans l'**environnement Sandbox** ; le **domaine visible dans la vidéo = l'URL du site** déclarée ; tout scope non montré doit être retiré.
4. **Audit Content Posting API** (pour sortir de `SELF_ONLY`) — formulaire : https://developers.tiktok.com/application/content-posting-api (connexion requise ; lien donné par la doc « Get started »). Le plafond de créateurs actifs / 24 h est fixé d'après **l'estimation d'usage** que vous y déclarez (Content Sharing Guidelines).
   - La démo doit montrer **toute l'UX obligatoire** (voir `plateformes.md` §4) : pseudo du compte, confidentialité **sans valeur par défaut**, interactions décochées, divulgation commerciale, phrase « Music Usage Confirmation », aperçu, texte modifiable, consentement explicite, suivi du statut.
   - Pièces exactes du formulaire d'audit : **NON CONFIRMÉ** (formulaire derrière connexion).
5. Délai : **non publié** — **NON CONFIRMÉ** (sources tierces : 2 à 6 semaines).

### Dossier à préparer (TikTok)

- [ ] Site public complet du produit + pages Confidentialité et CGU liées en pied de page
- [ ] Icône 1024×1024 ≤ 5 Mo, nom de marque sans « TikTok »
- [ ] Domaine de stockage des médias vérifié dans le portail (préfixe d'URL)
- [ ] Texte : rôle de Login Kit, de `video.publish` / `video.upload`, de chaque écran
- [ ] Vidéo(s) de démo ≤ 50 Mo : connexion TikTok → écran « Publier sur TikTok » conforme → publication → statut ; tournée en Sandbox, sur le domaine déclaré
- [ ] Estimation d'usage (nombre de créateurs / jour, posts / jour) pour l'audit
- [ ] Décision écrite du client sur le risque « outil pour ses propres comptes » et le repli « brouillon »

---

## 5. Google Business Profile

Sources : https://developers.google.com/my-business/content/prereqs · https://developers.google.com/my-business/content/limits — vérifiés le 2026-10-04 (« Last updated 2026-08-28 »)

- **Prérequis** :
  - un compte Google ; un **projet Google Cloud** (noter son **numéro de projet**) ; un **compte Organisation** GBP (via le centre d'aide) ;
  - gérer une fiche GBP **validée et active depuis plus de 60 jours** (la sienne ou celle d'un client) ;
  - un **site web** représentant l'entreprise de la fiche ; fiche complète et à jour recommandée ;
  - déposer avec une adresse e-mail **propriétaire ou gestionnaire** de la fiche.
- **Demande** : formulaire de contact GBP API, option « **Application for Basic API Access** » — https://support.google.com/business/contact/api_default — vérifié le 2026-10-04.
- **Savoir si c'est accordé** : quota de l'API dans la console : **0 QPM = pas encore**, **300 QPM = accordé**. Ne pas demander d'augmentation de quota à 0 : c'est la demande d'accès qui manque.
- Ensuite activer les API Business Profile du projet (« Basic setup »). Les posts (`localPosts`) et les réponses aux avis passent par l'API v4 « Google My Business » — https://developers.google.com/my-business/reference/rest/v4/accounts.locations.localPosts — vérifié le 2026-10-04.
- Délai : **non publié** — **NON CONFIRMÉ**.
- Vérification OAuth Google du scope `business.manage` pour des utilisateurs externes : **NON CONFIRMÉ** (classement du scope non lu ce jour ; la console l'indique au moment de le déclarer). Si exigée : 3-5 jours ouvrés (voir YouTube ci-dessous).

### Dossier à préparer (GBP)

- [ ] Numéro du projet Google Cloud
- [ ] Fiche GBP validée depuis > 60 jours, complète, avec le site web
- [ ] E-mail propriétaire/gestionnaire de la fiche (celui qui dépose)
- [ ] Raison sociale, site web, description de l'usage (publication de posts locaux, réponses aux avis)

---

## 6. YouTube — Data API v3

Sources : https://developers.google.com/youtube/v3/docs/videos/insert · https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits (« Last updated 2026-09-14 ») · https://support.google.com/youtube/contact/yt_api_form · https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification — vérifiés le 2026-10-04

- **Sans audit** : vidéos téléversées par un projet non vérifié créé après le 28/07/2020 → **privées** ; quota par défaut **100 `videos.insert`/jour** + 10 000 unités pour le reste.
- **Audit** (lève le « privé » et ouvre les augmentations de quota) : « YouTube API Services – Audit and Quota Extension Form ». « A member of YouTube's API Services team will contact you as soon as possible » — **aucun délai publié**.
- **Vérification OAuth Google** (écran de consentement, scope `youtube.upload`) : politique de confidentialité **sur le même domaine** que la page d'accueil et liée depuis l'écran de consentement ; page d'accueil publique ; **domaines vérifiés dans Search Console** ; justification par scope ; **vidéo de démo sur YouTube en « Non répertoriée »** montrant comment l'utilisateur accorde l'accès ; « typically takes **3-5 business days** ». Sans elle : plafond d'utilisateurs + écran « app non vérifiée ». (Que `youtube.upload` soit classé « sensible » : **NON CONFIRMÉ** sur la page lue ; la console le dit.)

### Contenu du formulaire d'audit (lu le 2026-10-04)

- Section 1 : motif (audit + extension de quota).
- Section 2 : nom légal du demandeur, **raison sociale exacte** (comme sur les documents officiels), société mère, site (https), **adresse légale**, catégorie, taille, contact principal et contact technique.
- Section 3 : description de l'activité liée à YouTube (100 à 5 000 caractères), public visé, modèle de revenus, contacts Google éventuels.
- Section 4 : **un formulaire par client API** ; nom de l'app (contient-il « YouTube » ?), **URL d'accès**, **URL de politique de confidentialité**, CGU (optionnel), **identifiants d'un compte de démo avec accès complet et données d'exemple**.
- Section 5 (par numéro de projet, jusqu'à 10) : catégorie d'usage (« Video Uploading & Account Management »), volume attendu, endpoints utilisés et **quota demandé séparément pour `videos.insert`**, justification détaillée.
- **Pièces obligatoires par projet** (JPEG/PNG/PDF, **un fichier < 10 Mo**, **≥ 1280×720**, barre d'adresse visible, noms de fichiers explicites) :
  - captures de la **politique de confidentialité** montrant les sections YouTube, le **lien vers la Politique de confidentialité Google**, la politique de suppression ;
  - capture de la **page d'accueil** montrant où est le lien de confidentialité, **avec la marque YouTube visible** ;
  - documentation des **CGU** ;
  - **captures du parcours OAuth** (consentement, scopes, **révocation**) et **captures de l'interface d'upload**.
- Section 6 (facultatif, recommandé) : schéma d'architecture, diagrammes de parcours.
- Section 7 : attestations (Conditions des services API YouTube, Politique de confidentialité Google, Developer Policies…).

### Dossier à préparer (YouTube)

- [ ] Numéro(s) de projet Google Cloud, domaine vérifié dans Search Console
- [ ] Politique de confidentialité avec une section YouTube, le lien https://policies.google.com/privacy, la suppression des données ; CGU qui renvoient aux Conditions d'utilisation YouTube (exigence des Developer Policies — **NON CONFIRMÉ** ce jour)
- [ ] Page d'accueil avec le lien de confidentialité et la marque YouTube visibles
- [ ] Compte de démo complet avec données
- [ ] Captures ≥ 720p : consentement OAuth, scopes, révocation, écran d'upload
- [ ] Vidéo non répertoriée du parcours OAuth (pour la vérification Google)
- [ ] Justification du quota `videos.insert` (nombre de chaînes × Shorts/jour)

---

## 7. Pinterest — API v5

Sources : https://developers.pinterest.com/docs/getting-started/set-up-app/ · https://developers.pinterest.com/docs/key-concepts/access-tiers/ · https://developers.pinterest.com/docs/reference/rate-limits/ · https://developers.pinterest.com/docs/changelog/changelog/ — vérifiés le 2026-10-04

- **Trial** : « Connect app » + formulaire de demande ; « Application requests are reviewed each business day », réponse par e-mail.
  - Refus fréquents : politique de confidentialité inaccessible ou hébergée sur un domaine sans lien clair avec la société ; description de l'app vague.
  - En Trial, **épingles et tableaux créés ne sont visibles que par leur créateur** (« Sandbox entities ») ; `org_write` : 300 requêtes/jour/app.
- **Standard** : My apps → bouton **Upgrade** → revérifier cas d'usage et URL de confidentialité → **téléverser une vidéo de démo** → soumettre ; « reviewed regularly » (délai non chiffré).
  - La vidéo doit montrer **le parcours OAuth** (même si vous êtes le seul utilisateur) et **l'intégration Pinterest réelle** dans l'app (pas de maquette) ; enregistrements de terminal ou de Postman acceptés.
  - Refus si : pas de parcours d'authentification dans la vidéo, authentification par identifiants/cookies au lieu d'OAuth, pas d'intégration réelle visible.
- Scopes pour publier : `boards:read`, `boards:write`, `pins:read`, `pins:write` — https://developers.pinterest.com/docs/api-features/content-overview/ — vérifié le 2026-10-04.
- **Nouveau (14/09/2026)** : une app enregistrée à partir de cette date peut recevoir `403 PINNER_DATA_ACCESS_DENIED` sur « Get board », « List Pins on board », « Get Pin »… pour un utilisateur **non-business** ; il faut alors une approbation Pinterest (via un account manager). ⇒ Connecter un **compte Pinterest Business** ; ne pas boucler sur le 403.

### Dossier à préparer (Pinterest)

- [ ] Compte Pinterest **Business** du client (administrateur de l'app)
- [ ] Politique de confidentialité publique sur le domaine du client
- [ ] Description détaillée de l'app (publication d'épingles de contenus créés par le client)
- [ ] Vidéo : OAuth Pinterest complet → création d'une épingle depuis l'app → épingle visible

---

## Pièces communes à toutes les plateformes

- [ ] Domaine du client avec site public complet (pas une page de connexion seule)
- [ ] Politique de confidentialité et CGU publiques, liées en pied de page, citant chaque réseau
- [ ] Procédure de suppression des données (page ou e-mail dédié)
- [ ] Icône carrée 1024×1024 sans marque de réseau social
- [ ] Un compte de test par plateforme, déjà relié, avec des données d'exemple
- [ ] Vidéos de démo 1080p (720p minimum chez YouTube), interface en anglais ou sous-titrée, parcours OAuth complet + publication réelle + résultat visible
- [ ] Raison sociale, adresse du siège, Kbis, e-mail professionnel sur le domaine
