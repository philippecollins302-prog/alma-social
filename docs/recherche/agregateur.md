# Agrégateur social, API Ayrshare, détourage d'objets : recherche du 2026-10-04

Contexte : application Python qui publie automatiquement pour **6 marques** (un profil par marque).
Budget **total** (hébergement + agrégateur + LLM + IA image) : **100 à 250 €/mois**.
Réseaux visés : Instagram (feed, Reels, Stories, carrousels), page Facebook, LinkedIn (page entreprise
**et** profil personnel), TikTok, Google Business Profile (posts + réponses aux avis), YouTube Shorts,
Threads, Pinterest.

Conventions de ce document :
- chaque fait porte sa source et la mention « vérifié le 2026-10-04 » ; quand un point n'a pas pu être
  lu sur la page officielle, c'est écrit en toutes lettres (« NON VÉRIFIÉ ») ;
- les prix sont en dollars comme sur les pages. La conversion en euros utilise un **taux indicatif
  de 0,85 €/$**, déduit des prix en euros qu'Upload-Post affiche lui-même (50 $ → 42 €, 438 $ → 378 €).
  Ce taux n'est pas un cours du jour.
- Ayrshare publie sa documentation en Markdown brut (`https://www.ayrshare.com/docs/<chemin>.md`) :
  c'est ce texte qui a été lu, pas un résumé.

---

## Partie A : quel agrégateur ?

### A.1 Ayrshare : la vérité sur les prix (page datée « lastModified: 2026-09-30 »)

| Formule | Prix mensuel | Profils | Points clés | Source |
|---|---|---|---|---|
| Premium | 149 $/mois | **1 profil** (« Up to 14 social accounts across 14 networks ») | analytics « Basic », commentaires et messages, un seul utilisateur | https://www.ayrshare.com/pricing.md (vérifié le 2026-10-04) |
| Launch | **299 $/mois** (≈ 254 €) | **jusqu'à 10 profils** | « Webhook integrations », analytics « Advanced », API multi-utilisateurs (lien d'association, profils), essai gratuit de 28 jours | https://www.ayrshare.com/pricing.md ; https://www.ayrshare.com/docs/multiple-users/business-launch-overview.md (vérifié le 2026-10-04) |
| Business | à partir de 599 $/mois | 30 profils inclus, puis 8,99 $/profil (31-100) | identique à Launch, plus de profils | https://www.ayrshare.com/pricing/ (vérifié le 2026-10-04) |
| Max Pack (option) | +300 $/mois (« available at a reduced Launch price » sans chiffre publié) | — | raccourcisseur de liens (`shortenLinks`), `instagramOptions.autoResize`, liens d'association valables plus de 5 min (`expiresIn`), e-mail d'association, mode « connect », IA de génération | https://www.ayrshare.com/docs/additional/maxpack.md ; https://www.ayrshare.com/docs/multiple-users/business-launch-overview.md (vérifié le 2026-10-04) |

- Facturation annuelle : −17 %, soit environ 248 $/mois pour Launch. Ce chiffre vient de l'affichage « Yearly »
  de la page de prix, relevé par l'outil de lecture et pas dans le Markdown. Il est donc à reconfirmer au moment
  de payer (https://www.ayrshare.com/pricing/, vérifié le 2026-10-04).
- **Un profil Ayrshare associe UN compte par réseau.** « Independent brands or locations = separate profiles »
  (https://www.ayrshare.com/pricing.md, vérifié le 2026-10-04). Six marques avec chacune leur Instagram exigent
  donc six profils, et **Premium (1 profil) est exclu** : il faut au minimum **Launch à 299 $**.
- **LinkedIn : page entreprise OU profil personnel, pas les deux dans un même profil.** « You may link either a
  company page or a personal LinkedIn account » (https://www.ayrshare.com/docs/apis/post/social-networks/linkedin.md),
  et à l'association : « You may either choose a LinkedIn company page or your personal LinkedIn account »
  (https://www.ayrshare.com/docs/dashboard/connect-social-accounts/linkedin.md) (vérifié le 2026-10-04).
  Conséquence : 6 profils de marque, plus 1 profil si le profil personnel est celui d'une seule personne (7 au
  total, ça tient dans Launch). Si chaque marque a son propre profil personnel, il en faut 12 : on dépasse le
  plafond de 10 et on bascule sur **Business à 599 $**.
- La couverture fonctionnelle est complète :
  - publication sur les 13 réseaux de `/post`, dont `gmb`, `threads` et `pinterest` ;
  - avis Google Business et Facebook : lecture, réponse, suppression de la réponse ;
  - commentaires : lecture et réponse ;
  - analytics par publication et par compte ;
  - webhooks ;
  - messages privés (inclus dans Launch et Business).

  Sources : https://www.ayrshare.com/docs/apis/overview.md et https://www.ayrshare.com/docs/apis/reviews/get-reviews.md
  (vérifié le 2026-10-04).
- Incohérence relevée entre deux pages. La page de prix classe « Webhook integrations » dans Launch, alors que la
  documentation de `POST /hook/webhook` l'indique disponible dès Premium (`PlansAvailable plans={["premium"]}`)
  (https://www.ayrshare.com/docs/apis/webhooks/register.md, vérifié le 2026-10-04). Sans conséquence ici,
  puisque Launch est de toute façon obligatoire.

**Verdict budget.** Launch coûte à lui seul ≈ 254 €/mois en mensuel, ou ≈ 211 €/mois en annuel. **C'est au-delà
du plafond de 250 € pour l'ensemble des outils**, ou bien ça ne laisse presque rien pour l'hébergement, le LLM et
l'image. Ayrshare est hors budget pour 6 marques.

### A.2 Les alternatives (pages officielles lues le 2026-10-04)

| | **Upload-Post** | **bundle.social** | **Zernio** (ex-Late / getlate.dev) | Outstand (écarté) |
|---|---|---|---|---|
| Modèle de prix | formules à nombre de profils ; 1 profil = 1 compte par réseau | prix par organisation ; comptes et équipes illimités | prix par compte connecté, dégressif | prix par organisation et volume de posts |
| **Prix pour 6 marques** | **Professional : 50 $/mois (42 €)**, ou 33 $/mois (28 €) en annuel, avec 25 profils. Basic (24 $) n'a que 5 profils et pas de marque blanche | **Pro : 100 $/mois** (≈ 85 €), ou 90 $/mois en annuel | 54 comptes (6 × 9, dont 6 LinkedIn personnels) = 0 + 8×6 $ + 44×3 $ = **180 $/mois** (≈ 153 €). Avec 49 comptes (un seul LinkedIn personnel) : **165 $/mois** | 19 $/mois (formule « Pay as you go ») |
| Instagram feed / Reels / Stories / carrousel | oui (`media_type=REELS`, Stories, `photos[]` en carrousel) | oui (`POST`, `REEL`, `STORY`) | oui | oui |
| Page Facebook | oui | oui | oui | oui |
| LinkedIn page **et** profil personnel | **oui, avec UNE seule connexion** : personnel par défaut, page via `target_linkedin_page_id` | oui, mais 1 équipe = 1 LinkedIn : il faut 2 équipes par marque (gratuit en formule payante) | oui (« personal profiles and organization pages ») | oui |
| TikTok | oui (à partir de Basic) | oui | oui | oui |
| Google Business : posts | oui (actualités, offres, événements) | oui (`STANDARD`, `EVENT`, `OFFER`, `ALERT`) | oui | **seulement avec vos propres identifiants Google (BYOK)** |
| Google Business : **réponses aux avis** | **oui** (lister, répondre, supprimer la réponse) | **oui** (import puis réponse ; 200 avis importés par compte et par mois) | **oui** (lister, répondre, supprimer) | non mentionné |
| YouTube Shorts / Threads / Pinterest | oui / oui / oui | oui (`SHORT`) / oui / oui | oui / oui / oui | oui / oui / oui |
| API commentaires | oui : IG, FB, YouTube, TikTok, Threads, LinkedIn (posts de page) | oui (`/comment`, 5 000 créations par mois en Pro) | oui (« comments + reviews ») | répondre aux commentaires de ses propres posts |
| API analytics | oui (par post, par profil, impressions totales) | oui (formule Pro et au-dessus) | oui | oui |
| Webhooks | `upload_completed`, `social_account_connected/disconnected/reauth_required`. **Pas d'événement commentaire** | `post.published`, `comment.received`, `social-account.*`, `conversation.*` (5 webhooks max) | statut des posts, messages, commentaires | NON VÉRIFIÉ |
| Association des comptes par le client (marque blanche) | profils + lien d'association JWT, à partir de Professional | lien de portail (`/social-account/create-portal-link`) | profils | — |
| Limites notables | plafonds quotidiens par compte : IG 50, TikTok 15, LinkedIn 150, YouTube 10, FB 25, Threads 50, Pinterest 20 | plafonds Pro par compte et par jour : LinkedIn **18**, TikTok 10, YouTube 10, GBP 20, IG 50 ; 10 000 posts/mois | facture qui grimpe avec chaque réseau ajouté ; pas de remise annuelle affichée | Google Business en BYOK, alors que l'accès à l'API GBP passe par une validation de Google |
| Sources (vérifié le 2026-10-04) | https://www.upload-post.com/llms-full.txt ; http://docs.upload-post.com/resources/pricing-and-limits/ ; http://docs.upload-post.com/guides/post-to-linkedin-api/ ; http://docs.upload-post.com/api/google-business-reviews/ ; http://docs.upload-post.com/api/webhooks/ ; http://docs.upload-post.com/api/comments/ | https://bundle.social/pricing.md ; https://bundle.social/llms-full.txt ; https://api.bundle.social/swagger-json | https://zernio.com/pricing.md ; https://docs.zernio.com/llms.txt | https://outstand.so/pricing.md ; https://www.outstand.so/llms.txt |

Détails vérifiés à retenir :
- **Upload-Post.** Authentification `Authorization: Apikey <clé>`, base `https://api.upload-post.com/api`.
  Endpoints de publication : `POST /api/upload` (vidéo), `/api/upload_photos`, `/api/upload_text`.
  Le profil est désigné par le champ `user`, et LinkedIn page par `target_linkedin_page_id`.
  Avis Google : `GET /api/uploadposts/google-business/reviews?user=…` puis `PUT /api/uploadposts/google-business/reviews/reply`
  avec `{user, review_name, comment}`.
  Webhooks signés `X-Upload-Post-Signature: sha256=…`, calculée comme HMAC(secret, "<timestamp>.<corps>").
  Instagram et TikTok n'ont pas d'API de suppression ; elle existe pour Facebook, YouTube, LinkedIn et Pinterest.
  Sources : pages Upload-Post citées dans le tableau, plus http://docs.upload-post.com/api/unpublish-post/ (vérifié le 2026-10-04).
- **bundle.social.** Base `https://api.bundle.social/api/v1`, en-tête `x-api-key`. Limites : 100 requêtes/s,
  500 par 10 s, 2 000 par minute. Une « équipe » (« social set ») contient au plus un compte par réseau.
  Sources : https://bundle.social/llms.txt et https://bundle.social/pricing.md (vérifié le 2026-10-04).
- **Zernio.** Base `https://zernio.com/api/v1`, authentification `Authorization: Bearer`. Grille par compte connecté :
  comptes 1-2 gratuits, 3-10 à 6 $, 11-100 à 3 $. Sources : https://zernio.com/pricing.md et https://docs.zernio.com/llms.txt
  (vérifié le 2026-10-04).
- **Écartés sans étude poussée** : Publer (pas de `llms.txt`, non lu), Buffer et Postiz (Postiz se présente
  aujourd'hui comme une surface MCP et CLI, https://postiz.com/llms.txt, vérifié le 2026-10-04). Pour ces trois,
  NON VÉRIFIÉ.

### A.3 Coût total estimé (6 marques, 150 à 300 images détourées par mois)

| Poste | Upload-Post Professional | bundle.social Pro | Ayrshare Launch |
|---|---|---|---|
| Agrégateur | 42 €/mois (28 € en annuel) | ≈ 85 € | ≈ 254 € |
| IA image (300 × 0,04 $, cf. partie C) | ≈ 10 € | ≈ 10 € | ≈ 10 € |
| Reste pour l'hébergement et le LLM (plafond 250 €) | **≈ 198 €** | ≈ 155 € | **< 0 €** |

### A.4 Recommandation (3 lignes)
1. **Upload-Post Professional, à 50 $/mois (42 €).** Il couvre les 8 réseaux, y compris la page LinkedIn et le profil personnel sur une seule connexion, ainsi que les posts et les réponses aux avis Google Business. Il laisse environ 200 € pour le reste.
2. **bundle.social Pro (100 $/mois) en repli.** C'est le choix si l'on veut des webhooks `comment.received` et des comptes illimités sans calcul. Zernio (≈ 165-180 $) n'est rentable qu'avec peu de réseaux par marque.
3. **Ayrshare est le plus complet, mais hors budget** : Launch à 299 $ minimum, et Business à 599 $ s'il faut 12 profils pour LinkedIn. Écrire un adaptateur `Agregateur` dans le code permet de changer de fournisseur sans réécrire l'application.

---

## Partie B : référence de l'API Ayrshare (documentation officielle, lue le 2026-10-04)

> Toute la documentation lue ici vient de `https://www.ayrshare.com/docs/…md`. Le site `docs.ayrshare.com`
> n'a pas été utilisé : la documentation vit désormais sous `www.ayrshare.com/docs/`, et l'index complet est
> https://www.ayrshare.com/docs/_llms/en/documentation.md (vérifié le 2026-10-04).

### B.1 Authentification et URL de base
- **Base : `https://api.ayrshare.com/api`**
  (https://www.ayrshare.com/docs/apis/overview.md, vérifié le 2026-10-04).
- `Authorization: Bearer <API_KEY>` : la clé du profil primaire, **toujours présente**
  (même source, vérifié le 2026-10-04).
- `Profile-Key: <PROFILE_KEY>` : pour agir au nom d'un sous-profil (formules Launch, Business, Enterprise). Il
  s'**ajoute** à l'`Authorization` et ne le remplace jamais : mettre la Profile-Key à la place de l'API key
  provoque une erreur (même source, vérifié le 2026-10-04).
- `Content-Type: application/json` ; compression facultative avec `Accept-Encoding: deflate, gzip, br`
  (même source, vérifié le 2026-10-04).
- Dates au format **UTC ISO 8601**, `YYYY-MM-DDThh:mm:ssZ` (même source, vérifié le 2026-10-04).
- Deux identifiants à ne pas confondre :
  - l'**ID Ayrshare du post**, champ `id` au premier niveau de la réponse. Il sert pour la suppression, les
    analytics et les commentaires ;
  - les **ID sociaux**, dans `postIds[].id`.

  Source : https://www.ayrshare.com/docs/apis/overview.md (vérifié le 2026-10-04).

### B.2 `POST /api/post`
Source principale : https://www.ayrshare.com/docs/apis/post/post.md (vérifié le 2026-10-04).

**Champs du corps :**
- `post` (string, **requis**, `""` accepté) ;
- `platforms` (array, **requis**) : valeurs exactes `bluesky`, `facebook`, `gmb`, `instagram`, `linkedin`,
  `pinterest`, `reddit`, `snapchat`, `telegram`, `threads`, `tiktok`, `twitter`, `youtube`, ou `all`.
  `facebook` désigne la page Facebook et `gmb` Google Business Profile. **Les identifiants que vous aviez écrits
  sont les bons.**
- `mediaUrls` (array d'URL en `https://`) ;
- `isVideo` (bool), pour une URL sans extension vidéo connue ;
- `scheduleDate` (string UTC) ;
- `validateScheduled` (bool, `true` par défaut) ;
- `shortenLinks` (bool) : **exige le Max Pack** ;
- `firstComment` (objet), `disableComments` (bool : Instagram, LinkedIn et TikTok seulement) ;
- `autoSchedule`, `autoRepost`, `autoHashtag`, `requiresApproval`, `notes` ;
- **`idempotencyKey`** (string unique par profil : une clé déjà vue est refusée, quel que soit l'état du post) ;
- les objets d'options par réseau, détaillés ci-dessous.

**Noms exacts des objets d'options** (attention à la casse, ils diffèrent de ce que vous aviez écrit) :

| Votre nom | **Nom réel** |
|---|---|
| instagramOptions | `instagramOptions` |
| faceBookOptions | `faceBookOptions` (B majuscule) |
| linkedInOptions | `linkedInOptions` |
| tiktokOptions | **`tikTokOptions`** (T majuscule à « Tok ») |
| gmbOptions | `gmbOptions` |
| youTubeOptions | `youTubeOptions` |
| pinterestOptions | `pinterestOptions` |
| threadsOptions | `threadsOptions` |

**`instagramOptions`**
Source : https://www.ayrshare.com/docs/apis/post/social-networks/instagram.md (vérifié le 2026-10-04).
- **Stories** : `"stories": true`. Une seule image ou vidéo ; le texte est ignoré ; réservé aux comptes Business
  (pas aux comptes Creator).
- **Reels** : une vidéo est **détectée automatiquement comme Reel**. `reels: true` est accepté mais pas
  nécessaire. Options : `shareReelsFeed` (bool, simple indication du flux souhaité), `thumbNail` (URL),
  `thumbNailOffset` (ms), `audioName`, `audioConfiguration{audioId, audioVolume, videoVolume}`,
  `trialParams{graduationStrategy: "MANUAL"|"SS_PERFORMANCE"}`.
- **Carrousel** : plusieurs `mediaUrls`, jusqu'à 10. Il n'y a **pas de flag** dédié. `isVideo` n'est pas supporté
  en carrousel.
- Autres options : `altText[]`, `locationId`, `userTags[{username,x,y}]`, `collaborators[]` (3 au plus),
  `isAIGenerated`, `autoResize` (Max Pack).
- Limites : **50 posts par 24 h glissantes** (champ `usedQuota` dans la réponse), 5 hashtags, 3 mentions,
  2 200 caractères. **Pas de suppression par l'API.**

**`faceBookOptions`**
Source : https://www.ayrshare.com/docs/apis/post/social-networks/facebook.md (vérifié le 2026-10-04).
- Champs : `reels: true` (obligatoire pour un Reel ; 30 Reels par page et par 24 h), `stories: true`, `title`,
  `thumbNail`, `altText[]`, `mediaCaptions[]`, `locationId`, `link` (aperçu de lien), `draft`,
  `scheduledPublishDate`, `targeting`, `carousel{link, items[{name, link, picture}]}`.
- Piège des Reels Facebook : une erreur 108 peut arriver alors que le Reel est publié. La réponse contient alors
  `detailsData.verifyReelsUrl` et `verifyReelsIn` pour vérifier.

**`linkedInOptions`**
Source : https://www.ayrshare.com/docs/apis/post/social-networks/linkedin.md (vérifié le 2026-10-04).
- Champs : `altText[]`, `disableShare`, `targeting{countries, seniorities, …}` (300 abonnés minimum dans l'audience
  ciblée), `thumbNail`, `title` (documents PDF, PPT ou DOC), `titles[]`, `visibility` (`public`, `connections`
  ou `loggedin`).
- Limites : 3 000 caractères, 150 posts par jour et par compte ; **ré-association obligatoire tous les 365 jours**
  (un webhook `social` de type `refresh` prévient 15 jours avant).
- La réponse porte `owner` (par exemple `urn:li:organization:…`).

**`tikTokOptions`**
Source : https://www.ayrshare.com/docs/apis/post/social-networks/tiktok.md (vérifié le 2026-10-04).
- Champs : `autoAddMusic`, `disableComments`, `disableDuet`, `disableStitch`, `draft`, `isAIGenerated`,
  `isBrandedContent`, `isBrandOrganic`, `imageCoverIndex`, `title`, `thumbNailOffset`, `thumbNail`,
  `visibility` (`public`, `private`, `followers` ou `friends`).
- **La réponse renvoie `"id": "pending"` avec un `idShare`.** Le vrai identifiant arrive par le webhook
  `scheduled` avec `subAction: "tikTokPublished"`, ou par `/history`, en 1 à 2 minutes.
- Limites : 6 publications par minute et 15 par jour par l'API.

**`gmbOptions`** : il n'y a **pas de champ « type »**. Le type se déduit de l'objet fourni.
Source : https://www.ayrshare.com/docs/apis/post/social-networks/google.md (vérifié le 2026-10-04).
- **Standard (« What's New »)** : rien de spécial. Image facultative, **pas de vidéo**, `callToAction` facultatif.
- **Photo ou vidéo** : `"isPhotoVideo": true` et `category` facultative (`cover`, `profile`, `logo`, `exterior`,
  `interior`, `product`, `at_work`, `food_and_drink`, `menu`, `common_area`, `rooms`, `teams`). Un seul média ;
  pas de CTA.
- **Événement** : `event{title, startDate, endDate}`, tous requis. CTA permis, pas de vidéo.
- **Offre** : `offer{title, startDate, endDate, couponCode (58 caractères max), redeemOnlineUrl, termsConditions}`,
  tous marqués requis. Pas de CTA.
- **CTA** : `callToAction{actionType, url}`, avec `actionType` parmi `book`, `order`, `shop`, `learn_more`,
  `sign_up`, `call` (`url` facultatif pour `call`).
- **Pièges** : les posts de type « Produit » ne sont pas supportés. **Google rejette tout post qui contient un
  numéro de téléphone.** La fiche doit être revendiquée et vérifiée.

**`youTubeOptions`**
Source : https://www.ayrshare.com/docs/apis/post/social-networks/youtube.md (vérifié le 2026-10-04).
- Champs : `title` (**requis**, 100 caractères max), `visibility` (`public`, `unlisted` ou `private`, **`private`
  par défaut**), `shorts: true` (3 min max, ajoute #shorts ; **pas de miniature possible pour un Short**),
  `thumbNail`, `playListId`, `tags[]`, `madeForKids`, `notifySubscribers`, `categoryId`,
  `containsSyntheticMedia`, `publishAt`, `subTitleUrl`.
- Une seule vidéo par post ; `post` sert de description (5 000 caractères).

**`pinterestOptions`**
Source : https://www.ayrshare.com/docs/apis/post/social-networks/pinterest.md (vérifié le 2026-10-04).
- Champs : `title` (100 caractères max), `link` (2 048 max), `boardId` (sinon le tableau par défaut ; la liste
  vient de `/user/details`), `altText[]`, `note`, `thumbNail` (**requis pour une épingle vidéo**),
  `carouselOptions[{title, link, description}]`.
- `post` est limité à 500 caractères.

**`threadsOptions`**
Source : https://www.ayrshare.com/docs/apis/post/social-networks/threads.md (vérifié le 2026-10-04).
- Champs : `allowCountries[]` (seulement si Meta l'a activé sur le compte, sinon erreur 101), `thread`,
  `threadNumber`, `mediaUrls` (un média par fil).
- Limites : 500 caractères, **1 hashtag**, carrousel de 20 médias, 250 posts par 24 h. **Pas de suppression par
  l'API.**

**Réponse en cas de succès** (https://www.ayrshare.com/docs/apis/post/post.md, vérifié le 2026-10-04) :
```json
{ "status": "success", "errors": [],
  "postIds": [ { "status": "success", "id": "<id social>", "postUrl": "https://…", "platform": "instagram", "usedQuota": 12 },
               { "status": "success", "id": "pending", "idShare": "…", "isVideo": true, "platform": "tiktok" },
               { "status": "success", "id": "urn:li:share:…", "postUrl": "…", "owner": "urn:li:organization:…", "platform": "linkedin" },
               { "status": "success", "id": "…", "postUrl": "…", "type": "localPosts", "platform": "gmb" } ],
  "id": "RhrbDtYh7hdSMc67zC8H", "refId": "…", "post": "…" }
```
- **Post programmé** : `{"status": "scheduled", "scheduleDate": "…", "id": "…", "refId": "…", "post": "…"}`.
- **Avec `Profile-Key`, la réponse est ENVELOPPÉE** dans `{"status": "...", "posts": [ { …objet ci-dessus…, "profileTitle": "…" } ]}`.
  Il faut lire `posts[0]` (exemples « Success with Profile Key » de la même page, vérifié le 2026-10-04).
- **Erreur** (HTTP 400 ou 500) :
  `{"status": "error", "errors": [{"action": "post", "status": "error", "code": 156, "message": "…", "platform": "youtube"}], "postIds": [], "id": "…"}`.
  Avec Profile-Key, la même chose sous `posts[]`.
- Des avertissements non bloquants peuvent apparaître dans `postIds[].warnings[]`, par exemple le code 518
  (https://www.ayrshare.com/docs/apis/post/social-networks/instagram.md, vérifié le 2026-10-04).

### B.3 `DELETE /api/post`
Source : https://www.ayrshare.com/docs/apis/post/delete-post.md (vérifié le 2026-10-04).
- **Corps JSON** : `{"id": "<ID Ayrshare>"}`. Variantes : `{"bulk": ["id1", "id2"]}`,
  `{"deleteAllScheduled": true}`, ou `{"id": …, "markManualDeleted": true}` (marque le post supprimé sans toucher
  au réseau).
- **Réponse** : `{"twitter": {"action": "delete", "status": "success", "id": "…"}, "facebook": {…}, "status": "success"}`.
- **Erreurs** : 114 (identifiant inconnu), 383 (déjà supprimé), 382 (`markManualDeleted` alors que le post existe
  encore).
- **Limites** : on ne peut **pas supprimer un post publié sur Instagram ni sur TikTok**, ni une Story image
  Facebook. La page Threads indique la même chose pour Threads
  (https://www.ayrshare.com/docs/apis/post/social-networks/threads.md, vérifié le 2026-10-04). Les posts
  programmés se suppriment sur tous les réseaux.

### B.4 Analytics d'une publication : c'est un **POST**, pas un GET
Source : https://www.ayrshare.com/docs/apis/analytics/post.md (vérifié le 2026-10-04).
- Appel : `POST /api/analytics/post` avec le corps `{"id": "<ID Ayrshare>", "platforms": ["instagram", "facebook", …]}`.
  `platforms` est facultatif.
- **Google Business n'est PAS couvert** par l'analytics par post. Réseaux couverts : Bluesky, Facebook,
  Instagram, LinkedIn, Pinterest, Reddit, Snapchat, Threads, TikTok, X, YouTube.
- Forme de la réponse :
  `{"<réseau>": {"id": "…", "postUrl": "…", "analytics": {…}, "lastUpdated": "…", "nextUpdate": "…"}, "status": "success"|"partial"|"error", "errors": [ … ]}`.
  **Toujours tester la présence de `errors[]`** : un échec partiel renvoie HTTP 200 avec `status: "partial"`.
- Noms exacts des champs `analytics` par réseau (relevés dans l'exemple de réponse de la même page) :

| Réseau | Champs |
|---|---|
| Instagram | `likeCount`, `commentsCount`, `reachCount`, `viewsCount`, `savedCount`, `sharesCount`, `engagementCount`, `profileVisitsCount`, `profileActivityCount`, `followsCount`. Reels : `playsCount`, `igReelsAggregatedAllPlaysCount`, `igReelsAvgWatchTimeCount`. Stories : `navigationCount`, `repliesCount`, `tapForwardCount`, `tapBackCount`, `tapExitCount`, `swipeForwardCount` |
| Facebook | `likeCount`, `commentsCount`, `sharesCount`, `mediaView`, `reactions{like, love, haha, wow, sorry, anger, total}`, `blueReelsPlayCount`, `totalVideoViews`, `totalVideoAvgTimeWatched`… |
| LinkedIn | `impressionCount`, `uniqueImpressionsCount`, `likeCount`, `commentCount`, `shareCount`, `clickCount`, `engagement`, `reactions{…}`, `videoViews`, `videoViewers`, `videoWatchTimeMs` |
| TikTok | `videoViews`, `likeCount`, `commentsCount`, `shareCount`, `reach`, `averageTimeWatched`, `fullVideoWatchedRate`, `impressionSources`, `audienceCountries`… |
| YouTube | `views`, `likes`, `dislikes`, `comments`, `averageViewDuration`, `averageViewPercentage`, `estimatedMinutesWatched`, `engagedViews`, `subscribersGained`, `subscribersLost` |
| Pinterest | `impression`, `pinClick`, `outboundClick`, `save`, `saveRate`, `totalComments`, `totalReactions`, `profileVisit`, `userFollow`, `videoStart`… |
| Threads | `views`, `likes`, `replies`, `reposts`, `shares`, `quotes` |

- Il n'existe pas de nom commun du type `impressions` ou `clicks` pour tous les réseaux. Chaque réseau a ses
  propres noms, et un champ « clics » n'existe que sur LinkedIn (`clickCount`) et Pinterest (`pinClick`,
  `outboundClick`). **Il faut une table de correspondance par réseau dans notre code.**
- Délais de disponibilité : TikTok et YouTube 24 à 48 h, Pinterest 24 à 72 h. Les insights de Story Instagram ne
  sont disponibles que 24 h.
- Pour **Google Business**, il faut l'analytics de compte :
  `POST /api/analytics/social` avec `{"platforms": ["gmb"]}`. Champs `businessImpressionsDesktopSearch`,
  `businessImpressionsMobileSearch`, `businessImpressionsDesktopMaps`, `businessImpressionsMobileMaps`,
  `callClicks`, `websiteClicks`, `businessDirectionRequests`, `businessBookings`, `businessConversations`
  (https://www.ayrshare.com/docs/apis/analytics/social.md, vérifié le 2026-10-04).

### B.5 Commentaires et messages privés
- **Lire** : `GET /api/comments/:id`, où `:id` est l'ID Ayrshare du post. Pour un ID social, ajouter
  `?searchPlatformId=true&platform=instagram`, plus `commentId=true` pour un ID de commentaire.
  Réponse : `{"instagram": [{"comment", "commentId", "created", "from": {"id", "username"}, "hidden", "likeCount", "platform", "postId", "replies": […]}], "facebook": […], "status", "lastUpdated", "nextUpdate"}`.
  Données rafraîchies toutes les 10 minutes ; Facebook et Instagram limités aux 1 000 derniers commentaires.
  Réseaux couverts : Bluesky, Facebook, Instagram, LinkedIn, Reddit, Threads, TikTok, X, YouTube. **Pas Google
  Business ni Pinterest.**
  Sources : https://www.ayrshare.com/docs/apis/comments/get-comments.md et https://www.ayrshare.com/docs/apis/comments/overview.md
  (vérifié le 2026-10-04).
- **Commenter son propre post** : `POST /api/comments` avec `{"id": "<ID Ayrshare>", "comment": "…", "platforms": [ … ]}`
  (https://www.ayrshare.com/docs/apis/comments/post-comment.md, vérifié le 2026-10-04).
- **Répondre à un commentaire : la forme que vous aviez est la bonne.** `POST /api/comments/reply/:commentId` avec
  `{"comment": "…", "platforms": ["instagram"], "searchPlatformId": true}`. Pour LinkedIn, ajouter `commentUrn` ;
  pour TikTok, `videoId`.
  Réponse : `{"<réseau>": {"status", "commentId", "sourceCommentId", "comment", "platform"}, "status", "id"}`.
  Réseaux couverts : Bluesky, Facebook, Instagram, LinkedIn, TikTok, X, YouTube. **Threads n'y figure pas.**
  Source : https://www.ayrshare.com/docs/apis/comments/reply-to-comment.md (vérifié le 2026-10-04).
- **Messages privés : oui, `/api/messages`.**
  - Lire : `GET /api/messages/:platform`, avec les paramètres `status`, `conversationId`, `conversationsOnly`,
    `limit`, `next`.
  - Envoyer : `POST /api/messages/:platform` avec `{"recipientId", "message", "mediaUrls"}`.
  - Réseaux : Facebook Messenger, Instagram Direct, X, et WhatsApp en bêta privée.
  - Inclus dans Launch et Business (option payante sur Premium). Il faut l'activer sur le compte, puis par
    profil (`messagingActive`), puis **ré-associer Facebook et Instagram**. Codes d'erreur : 361 (non activé),
    362 (ré-association nécessaire).

  Sources : https://www.ayrshare.com/docs/apis/messages/overview.md, https://www.ayrshare.com/docs/apis/messages/get-messages.md,
  https://www.ayrshare.com/docs/apis/messages/send-message.md (vérifié le 2026-10-04).

### B.6 Avis
- **Lire** : `GET /api/reviews?platform=gmb` (ou `facebook`).
  Réponse : `{"gmb": [{"id", "rating": "FIVE", "review", "reviewReply": {"reply", "updated"}, "reviewer": {"name", "profile"}, "created", "updated"}], "averageRating", "totalReviewCount", "lastUpdated", "nextUpdate"}`.
  Sur Facebook, `rating` vaut `positive` ou `negative`. Erreur 350 s'il n'y a pas d'avis.
  Source : https://www.ayrshare.com/docs/apis/reviews/get-reviews.md (vérifié le 2026-10-04).
- **Répondre** : `POST /api/reviews` avec `{"platform": "gmb", "reviewId": "…", "reply": "…"}`.
  Réponse : `{"gmb": {"action": "reply", "status": "success", "id", "reply", "platform"}}`. Erreur 349 si l'avis
  n'existe plus.
  Source : https://www.ayrshare.com/docs/apis/reviews/reply-review.md (vérifié le 2026-10-04).
- **Supprimer sa réponse** : `DELETE /api/reviews` avec `{platform, reviewId}`
  (https://www.ayrshare.com/docs/apis/reviews/delete-review-reply.md, vérifié le 2026-10-04).
- Disponible dès Premium. Réseaux : Google Business et Facebook uniquement (mêmes sources).

### B.7 Profils (une marque = un profil) et association des comptes
- **Créer un profil** : `POST /api/profiles`, avec **l'API key seule (sans Profile-Key)**.
  - Corps : `title` (**requis, unique**), `messagingActive`, `disableSocial[]`, `hideTopHeader`, `topHeader`,
    `subHeader`, `tags[]`, `team`, `email`.
  - Réponse : `{"status": "success", "title", "refId", "profileKey", "messagingActive"}`.
  - **La `profileKey` n'est renvoyée QU'UNE fois** : il faut la stocker chiffrée. Erreur 146 si le titre existe
    déjà.

  Source : https://www.ayrshare.com/docs/apis/profiles/create-profile.md (vérifié le 2026-10-04).
- **Lien d'association : `generateJWT` est déprécié** (toujours fonctionnel, sans date de retrait). La méthode
  recommandée est **`POST /api/profiles/link-sessions`**.
  - En-têtes : `Authorization` et **`Profile-Key` obligatoire** (pas de `profileKey` dans le corps).
  - Corps : `mode` (`grid` par défaut, ou `connect`), `redirect`, `allowedSocial[]`, `network`,
    `instagramLinkMethod`, `origin`, `domain`, `logout`, `expiresIn` (Max Pack), `email` (Max Pack).
  - Réponse : `{"status", "sessionId", "url", "expiresAt", "emailSent", "title"}`.
  - **L'URL vit 5 minutes par défaut.** Au-delà, il faut `expiresIn` (jusqu'à 2 880 min), qui exige le Max Pack.

  Source : https://www.ayrshare.com/docs/apis/profiles/create-link-session.md (vérifié le 2026-10-04).
- **`generateJWT`, forme ancienne** : `POST /api/profiles/generateJWT` avec `{"profileKey", "domain"?, "redirect"?, "allowedSocial"?, "expiresIn"?}`.
  Réponse : `{"status", "title", "token": "ayr_ls_…", "url", "emailSent", "expiresIn"}`. `privateKey` n'est plus
  lu. Source : https://www.ayrshare.com/docs/apis/profiles/generate-jwt.md (vérifié le 2026-10-04).
- **Parcours du propriétaire de la marque :**
  1. Notre app crée le profil et stocke la `profileKey`.
  2. Le propriétaire clique sur « Connecter mes réseaux ». Notre serveur appelle `link-sessions` **à ce
     moment-là**, à cause de la validité de 5 minutes.
  3. Le navigateur ouvre l'`url` sur `profile.ayrshare.com`, une page en marque blanche.
  4. Le propriétaire s'authentifie sur chaque réseau en OAuth. Pour LinkedIn, il choisit « Company page » ou
     « Personal ».
  5. Notre app est prévenue par le webhook `social` (`type: "link"`), ou en lisant `GET /api/user`
     (`activeSocialAccounts`, `refreshDaysRemaining`).

  Le tableau de bord Ayrshare est réservé à notre équipe et ne doit jamais être donné aux clients.
  Sources : https://www.ayrshare.com/docs/multiple-users/business-plan-overview.md et https://www.ayrshare.com/docs/apis/user/profile-details.md
  (vérifié le 2026-10-04).

### B.8 Webhooks
- **Inscription** : `POST /api/hook/webhook` avec `{"action": "…", "url": "https://…", "secret": "…"}`.
  - Réponse : `{"status", "action", "url", "refId"}`.
  - Actions : `feed`, `social`, `scheduled`, `batch`, `messages`, `mentions`, `comments`, `automations`,
    `suspended`.
  - Un webhook s'inscrit **par profil** (avec Profile-Key) ou sur le profil primaire, dont les profils
    héritent. Il s'inscrit aussi depuis le tableau de bord.

  Sources : https://www.ayrshare.com/docs/apis/webhooks/register.md et https://www.ayrshare.com/docs/apis/webhooks/overview.md
  (vérifié le 2026-10-04).
- **Événements utiles** (https://www.ayrshare.com/docs/apis/webhooks/actions.md, vérifié le 2026-10-04) :
  - `social` : association ou dissociation d'un compte, `type` valant `link`, `unlink` ou `refresh`, avec
    `platform`, `refId`, `source` (`system` ou `user`) et `refreshBy` ;
  - `scheduled` : résultat d'un **post programmé** (`status`, `id`, `postIds[]`, `errors[]`), plus
    `subAction: "tikTokPublished"`. **Aucun webhook n'est envoyé pour un post immédiat** : la réponse HTTP
    fait foi ;
  - `comments` : nouveau commentaire, **Instagram et Facebook seulement**. Contient `postId` (l'ID Ayrshare),
    `id`, `text`, `from`, `media` ;
  - `messages` : messages privés, avec `subAction` `messageCreated`, `messageRead`, `reactionCreated` ou
    `messageEdited`.
- **Contrat de réception** (https://www.ayrshare.com/docs/apis/webhooks/overview.md, vérifié le 2026-10-04) :
  - répondre **200 en moins de 15 s**, puis traiter en asynchrone ;
  - les réponses 429, 408, 425, les 5xx et les délais dépassés sont **retentés** (jusqu'à 9 envois sur environ
    1 h, puis à cadence décroissante) ; **les autres 4xx ne le sont jamais** ;
  - la livraison est « au moins une fois » : **dédupliquer sur `hookId`**, sur au moins 24 h ;
  - en-têtes de signature : `X-Authorization-Timestamp`, `X-Authorization-Content-SHA256` (HMAC-SHA256 du corps
    avec le secret), et `X-Authorization-Content-SHA256-V2` pendant une rotation du secret ;
  - en-têtes de livraison : `X-Ayrshare-Delivery-Id`, `X-Ayrshare-Delivery-Attempt`.

### B.9 Limites et codes d'erreur à gérer
- **Débit** : **300 requêtes par 5 minutes et par profil**. En-têtes `x-ratelimit-max` et `x-ratelimit-count`.
  **1 000 réponses 429 en 24 h suspendent le profil.**
  Source : https://www.ayrshare.com/docs/errors/errors-http.md (vérifié le 2026-10-04).
- **Quand y a-t-il erreur ?** Quand le code HTTP n'est pas 200 **ou** quand `status` vaut `"error"`. Si
  `retryAvailable: true` est présent, on peut retenter avec le même contenu (ou par `/post/retry`). **Si `postIds`
  n'est pas vide, ne pas tout renvoyer** : il ne faut retenter que les réseaux en échec, sous peine de doublon.
  Source : https://www.ayrshare.com/docs/errors/errors-ayrshare.md (vérifié le 2026-10-04).
- Codes relevés (mêmes sources et pages de post, vérifié le 2026-10-04) :

| Code | Sens | Geste |
|---|---|---|
| **137** | **Doublon Ayrshare** : contenu identique ou quasi identique dans une fenêtre de 48 h **centrée sur `scheduleDate`**, par profil et par réseau. Pinterest, Reddit et Telegram ne sont pas contrôlés | varier le texte, sans retenter tel quel |
| 110 | doublon X/Twitter (« Status is a duplicate ») | idem |
| 107 | Facebook : statut identique au précédent | idem |
| 156 | réseau non associé au profil | demander l'association |
| 161 | autorisation Facebook perdue | faire ré-associer |
| 138 | erreur Instagram (format ou ratio d'image…) | corriger le média |
| 479 | Meta n'arrive pas à télécharger le média (robots.txt, WAF), non retentable | servir le média depuis un hôte accessible |
| 108 | Reel Facebook incertain | vérifier `verifyReelsUrl` |
| 288 | TikTok encore en traitement (commentaires) | attendre `tikTokPublished` |
| 485 | Story expirée (analytics ou commentaires) | ignorer |
| 114 / 383 / 382 | suppression : identifiant inconnu / déjà supprimé / `markManualDeleted` refusé | — |
| 146 | titre de profil déjà pris | — |
| 349 / 350 | avis introuvable / aucun avis | — |
| 361 / 362 | messagerie non activée / ré-association nécessaire | — |
| 501 / 502 / 503 | lien d'association révoqué / introuvable / expiré | régénérer le lien |
| 429 (HTTP) | quota de débit | attente exponentielle |

- **Limites propres aux réseaux** (pages réseau Ayrshare, vérifié le 2026-10-04) :
  - Instagram : 50 posts par 24 h ;
  - Reels Facebook : 30 par 24 h et par page ;
  - LinkedIn : 150 par jour ;
  - TikTok : 15 par jour (6 par minute) ;
  - Threads : 250 par 24 h ;
  - YouTube : plafond quotidien fixé par la chaîne.

---

## Partie C : IA de nettoyage d'image (effacer une poubelle, un cône, un câble à partir d'un masque)

| Service | Prix par image | Forme de l'API | Masque | Sortie | Qualité / remarques | Disponibilité UE | Source (vérifié le 2026-10-04) |
|---|---|---|---|---|---|---|---|
| **fal.ai : Bria Eraser** (`fal-ai/bria/eraser`) | **0,04 $** | `POST https://fal.run/fal-ai/bria/eraser` (ou `queue.fal.run/…` en asynchrone), en JSON. En-tête `Authorization: Key <FAL_KEY>` (nom confirmé pour le modèle FLUX Fill sur la même plateforme) | `mask_url` en binaire, `mask_type` `manual` ou `automatic`. Requis : `image_url` et `mask_url` (URL ou data URI). Options `preserve_alpha`, `sync_mode` | `{"image": {"url", "content_type"}}` | modèle dédié à l'effacement, sans prompt, « trained exclusively on licensed data for safe commercial use » | société américaine ; région de calcul non documentée dans les pages lues (NON VÉRIFIÉ) | https://fal.ai/models/fal-ai/bria/eraser/api |
| **fal.ai : Object Removal par masque** (`fal-ai/object-removal/mask`) | **0,006 à 0,024 $** selon `model` (`low_quality` → `best_quality`) | même forme et même authentification que fal ci-dessus | `mask_url` : pixels **blancs (255) = zone à effacer**. Option `mask_expansion` (0-50, 15 par défaut) | `{"images": [{"url", "width", "height", …}]}` | le moins cher ; modèle sous-jacent non nommé | idem | https://fal.ai/models/fal-ai/object-removal/mask/api |
| **Stability AI : Erase** | **5 crédits = 0,05 $** (1 crédit = 0,01 $) | `POST https://api.stability.ai/v2beta/stable-image/edit/erase`, en `multipart/form-data`. En-têtes `authorization: Bearer sk-…` et `accept: image/*` (octets) ou `application/json` (base64) | champ `mask` : **blanc = effacer, noir = garder** (ou canal alpha de l'image). `grow_mask` 0-20 (5 par défaut), `seed`, `output_format` (`png`, `jpeg` ou `webp`) | l'image elle-même, **sortie annoncée à 4 mégapixels** | entrée de 4 096 à 9 437 184 pixels, au moins 64 px de côté ; un échec n'est pas facturé. Le schéma OpenAPI liste à tort `prompt` comme requis, le texte de la doc non | société britannique ; région d'hébergement non documentée (NON VÉRIFIÉ) | https://api.stability.ai/v2alpha/openapi (endpoint, crédits) ; prix du crédit relevé sur https://platform.stability.ai/pricing (« 1 credit = $0.01 ») |
| **Clipdrop Cleanup** (Jasper) | **plus de prix publié** : la page de prix renvoie vers un formulaire de contact Jasper | `POST https://clipdrop-api.co/cleanup/v1`, en-tête `x-api-key`, champs `image_file` et `mask_file`, `mode` (`fast` ou `quality`) | PNG de même taille, **255 = nettoyer** | PNG | historiquement excellent ; page : « Clipdrop is part of Jasper now… contact Jasper's team » ; 60 requêtes par minute | NON VÉRIFIÉ | https://clipdrop.co/apis/docs/cleanup |
| Photoroom | — | **pas d'effacement par masque** : « We don't currently offer mask or region based object removal » (équipe Photoroom, 11/02/2026) | — | — | écarté | — | https://photoroom.discourse.group/t/object-removal-via-api-editor-based/377 |
| Picsart, Claid.ai | NON VÉRIFIÉ | documentation de l'endpoint et prix par appel introuvables dans le temps imparti | — | — | — | — | — |

**Coût pour 150 à 300 images par mois :**

| Service | 150 images | 300 images |
|---|---|---|
| Bria Eraser | 6 $ | 12 $ |
| Stability Erase | 7,50 $ | 15 $ |
| Object Removal (« best_quality ») | 3,60 $ | 7,20 $ |

Dans tous les cas, c'est négligeable dans le budget (moins de 13 €).

**Recommandation.** **fal.ai, modèle `fal-ai/bria/eraser` à 0,04 $ par image.** Il est conçu pour l'effacement
sans prompt et entraîné sur des données sous licence, ce qui est plus sûr pour des visuels de marque publiés. Il
prend des **URL** en entrée, alors que nos images sont de toute façon hébergées publiquement pour l'agrégateur. Il
renvoie une URL, et la même clé fal donne accès à l'option moins chère `object-removal/mask` si la qualité suffit.
Stability Erase sert de second fournisseur, derrière le même adaptateur.

**Avant de figer le choix**, passer les deux fournisseurs sur une vingtaine de vraies photos (poubelle, cône,
câble), pour moins de 2 $ au total : aucune mesure de qualité indépendante n'a été trouvée.

**Point non tranché** : aucun de ces services n'affiche d'hébergement garanti dans l'UE dans les pages lues. Si
les photos sont sensibles au sens RGPD (des personnes reconnaissables), c'est une question à poser par écrit au
fournisseur avant la mise en production.
