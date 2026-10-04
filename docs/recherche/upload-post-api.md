# Upload-Post : référence d'implémentation (offre Professional)

Tout ce qui suit a été lu le 2026-10-04 dans la documentation officielle :
`https://docs.upload-post.com/llms-full.txt`, qui concatène toutes les pages avec
leur ligne `URL:`, et la spécification OpenAPI publiée. Chaque section donne
l'URL de la page d'origine et porte la mention « vérifié le 2026-10-04 ».

Les noms de champs sont recopiés **tels quels**. La mention **NON CONFIRMÉ**
signale ce qu'aucune page officielle n'établit, ou ce sur quoi deux pages
officielles se contredisent.

---

## 0. Ce qu'il faut savoir avant d'écrire une ligne

- **L'offre Professional** coûte $50/mois, ou $33/mois en annuel. Elle comprend :
  - **25 profils** ;
  - des envois illimités ;
  - la marque blanche (« Whitelabel integration : Yes ») ;
  - 2 sièges.
  - Source : https://docs.upload-post.com/resources/pricing-and-limits — vérifié le 2026-10-04.
- **Un profil (`user`) connecte un compte par plateforme.** On crée donc un
  profil par marque, soit 6 profils.
  - Source : même page — vérifié le 2026-10-04.
- **Le texte du post s'appelle `title`**, et non `caption`. Le champ
  `description` n'est lu que par certaines plateformes (voir §2.4).
- **Une réponse HTTP 200 ne prouve pas la publication.** Chaque plateforme a son
  propre `results.<plateforme>.success`, et l'échec d'une plateforme n'arrête
  pas les autres.
  - Source : https://docs.upload-post.com/guides/error-handling — vérifié le 2026-10-04.
- **Les recommandations officielles** :
  - toujours envoyer `async_upload=true` et un en-tête `Idempotency-Key` ;
  - remplacer l'interrogation périodique par les webhooks.
  - Source : https://docs.upload-post.com/guides/rate-limits — vérifié le 2026-10-04.

---

## 1. Authentification, URL de base, profils, liaison des comptes

Sources :
- https://docs.upload-post.com/guides/authentication
- https://docs.upload-post.com/api/user-profiles
- https://docs.upload-post.com/guides/user-profile-integration
- https://docs.upload-post.com/api/connect-api

Toutes vérifiées le 2026-10-04.

### 1.1 Base et en-tête

- **URL de base** : `https://api.upload-post.com/api`, par exemple
  `POST https://api.upload-post.com/api/upload`.
- **En-tête d'authentification** : `Authorization: Apikey <CLE_API>`. Le mot
  `Apikey` est littéral. Certaines pages écrivent `ApiKey` : le serveur accepte
  les deux graphies dans les exemples officiels.
- **Le JWT de profil** (§1.3) s'envoie en `Authorization: Bearer <JWT>`. Il ne
  sert qu'à `validate-jwt` et à l'API Connect côté navigateur.
- **Un 401** renvoie `{"success": false, "message": "Invalid or expired token"}`.
  Autres messages possibles : `"Authorization header required"`,
  `"Invalid API key"`, `"API key expired"`.

### 1.2 Créer, lire et supprimer un profil (une marque)

**Créer un profil** : `POST /api/uploadposts/users`, en JSON.

```json
{ "username": "marque-01" }
```

- `username` est obligatoire et unique.
- Réponse 201 :

  ```json
  {"success": true, "profile": {"username", "created_at", "social_accounts": {...}}}
  ```

- Erreurs :
  - `400` : `username` absent ;
  - `401` ;
  - `403` avec `error_code: PROFILE_LIMIT_REACHED` ;
  - `409` : le profil existe déjà.

**Lister les profils** : `GET /api/uploadposts/users`.

- Réponse : `{success, plan, limit, profiles: [...]}`.
- Chaque profil porte `social_accounts.<plateforme>` avec les champs :
  - `username` : identifiant stable du compte ;
  - `display_name` ;
  - `social_images` ;
  - `handle` : le @nom ;
  - `capabilities` : liste ouverte, à tester par appartenance ;
  - `reauth_required` : vaut `true` quand le jeton est mort.
- Une plateforme non connectée vaut `null`.

**Lire un profil** : `GET /api/uploadposts/users/{username}`. Renvoie 404 avec
`"Profile not found"` si le profil n'existe pas.

**Supprimer un profil** : `DELETE /api/uploadposts/users`, corps JSON
`{"username": "..."}`.

**Capacités TikTok** (`capabilities`) :
- `music`, `location`, `cover_image`, `cover_timestamp`, `draft` ;
- `photo_privacy`, `video_privacy`, `inbox_fallback` ;
- `comments` et `trend_search` : accordées **seulement après une reconnexion** ;
- `profile_analytics`.

### 1.3 Lien de connexion en marque blanche (le propriétaire de la marque relie ses comptes)

**Générer le lien** : `POST /api/uploadposts/users/generate-jwt`, en JSON.

| Champ | Type | Rôle |
|---|---|---|
| `username` | String | **obligatoire** : le profil visé |
| `redirect_url` | String | URL de retour après liaison |
| `logo_image` | String (URL) | logo affiché sur la page |
| `redirect_button_text` | String | défaut « Logout connection » |
| `connect_title` | String | titre de la page |
| `connect_description` | String | texte de la page |
| `platforms` | Array | filtre des plateformes proposées, toutes par défaut (voir réserve ci-dessous) |
| `show_calendar` | Boolean | défaut `true` |
| `readonly_calendar` | Boolean | calendrier en lecture seule, défaut `false` |
| `language` | String | `en`, `es`, `de`, `fr`, `pt`, `pl` ou `tr` |
| `ui_labels` | Object | surcharges de libellés : 100 entrées au plus, 300 caractères par valeur |
| `connect_theme` | String | `light`, `dark` ou `auto` |

**Réponse 200** :

```json
{"success": true, "access_url": "https://app.upload-post.com/connect?token=…", "duration": "48h"}
```

- **Le lien est valide 48 heures.** La page User Profiles le décrit comme
  « single-use ».
- Erreurs :
  - `400` ;
  - `401` ;
  - `403` avec `PROFILE_BLOCKED` ;
  - `404` avec `PROFILE_NOT_FOUND`.

**Réserve sur `platforms` — NON CONFIRMÉ pour Pinterest et Google Business :**
- la page User Profiles liste `tiktok`, `instagram`, `linkedin`, `youtube`,
  `facebook`, `x`, `threads` et `google_business` ;
- l'OpenAPI liste `tiktok`, `instagram`, `linkedin`, `youtube`, `facebook`, `x`,
  `threads`, `discord` et `telegram`, **sans `google_business`** ;
- **aucune des deux sources ne cite `pinterest`.**

Recommandation : **ne pas envoyer `platforms`**. Par défaut, la page propose
toutes les plateformes.

**Valider un jeton (facultatif)** : `GET /api/uploadposts/users/validate-jwt`
avec `Authorization: Bearer <JWT>`.
- Jeton valide : renvoie `{success, profile: {social_accounts, username, ui_labels}}`.
- Jeton invalide : 200 avec `{"isValid": false, "reason": "..."}`.

**Après la liaison**, vérifier côté serveur avec `GET /api/uploadposts/users`, en
lisant `social_accounts`. On peut aussi écouter le webhook
`social_account_connected` (§10).

### 1.4 Alternative : construire sa propre page de connexion (Connect API)

**Démarrer une connexion** : `POST /api/uploadposts/oauth/{platform}/start`.

- Plateformes acceptées : `tiktok`, `instagram`, `facebook`, `linkedin`,
  `youtube`, `x`, `threads`, `pinterest`, `google-business` (**avec un tiret
  ici**, contre `google_business` partout ailleurs) et `snapchat`.
- Corps : `profile`, obligatoire seulement si l'on s'authentifie par clé API,
  et `redirect_url`.
- Réponse : `{success, platform, authorize_url, state, expires_in: 900}`.
  Le `state` est à usage unique et vit 15 minutes.

**Au retour**, l'utilisateur arrive sur
`redirect_url?connect_status=success|cancelled|error&platform=…`, avec en plus
`error_code` dans les cas `cancelled` et `error`. Valeurs de `error_code` :
`ACCESS_DENIED`, `PROVIDER_ERROR`, `INVALID_STATE`, `CONNECTION_FAILED`.

### 1.5 Épingler une page ou un établissement par profil

**Page LinkedIn** : `GET`/`POST`/`DELETE /api/uploadposts/users/linkedin-page`.
- Champs : `profile_username` et `linkedin_page_id`. Ce dernier accepte l'URN
  `urn:li:organization:123` ou l'identifiant numérique.
- **Une page épinglée l'emporte sur `target_linkedin_page_id`.** Tant qu'elle
  est épinglée, on ne peut plus publier sur le profil personnel de ce profil :
  il faut d'abord la désépingler.
- Source : https://docs.upload-post.com/api/linkedin-page — vérifié le 2026-10-04.

**Établissement Google Business** :
`GET`/`POST`/`DELETE /api/uploadposts/users/google-business-location`.
- Champs : `profile_username` et `gbp_location_id`.
- Source : https://docs.upload-post.com/api/google-business-location — vérifié le 2026-10-04.

**Page Facebook** : il existe un équivalent,
`/api/uploadposts/users/facebook-page`.
- Source : https://docs.upload-post.com/api/facebook-page — vérifié le 2026-10-04.

### 1.6 Listes d'identifiants à présenter dans l'interface

| Liste | Requête | Réponse | Valeur à reprendre |
|---|---|---|---|
| Pages Facebook | `GET /api/uploadposts/facebook/pages?profile=` | `{pages: [{page_id, page_name, profile}]}` | `page_id` |
| Pages LinkedIn | `GET /api/uploadposts/linkedin/pages?profile=` | `{pages: [{id: "urn:li:organization:…", name, picture, account_id, followers}]}` | `id`, en `target_linkedin_page_id` |
| Tableaux Pinterest | `GET /api/uploadposts/pinterest/boards?profile=` | `{boards: [{id, name}], pinterest_account_used}` | `id`, en `pinterest_board_id` |
| Établissements Google Business | `GET /api/uploadposts/google-business/locations?profile=` | `{locations: [{name: "accounts/…/locations/…", title, account_id}]}` | `name`, en `gbp_location_id` |

**Format de `target_linkedin_page_id` :** la page « Get LinkedIn Pages » dit de
passer l'`id` (une URN), alors que les exemples d'envoi montrent un numérique
(`"107579166"`). Passer exactement l'`id` renvoyé par la liste.

Sources, toutes vérifiées le 2026-10-04 :
- https://docs.upload-post.com/api/get-facebook-pages
- https://docs.upload-post.com/api/get-linkedin-pages
- https://docs.upload-post.com/api/get-pinterest-boards
- https://docs.upload-post.com/api/get-google-business-locations

---

## 2. `POST /api/upload_photos` (image, carrousel, story)

Sources, vérifiées le 2026-10-04 :
- https://docs.upload-post.com/api/upload-photo
- l'OpenAPI, dont le corps est déclaré en `multipart/form-data`.

### 2.1 Forme de la requête

- **Type de contenu : `multipart/form-data`.** Pas de JSON sur ce point d'entrée.
- **En-têtes :**
  - `Authorization: Apikey …` ;
  - en option, `Idempotency-Key`, ou ses alias `X-Idempotency-Key` et
    `X-Request-Id`. Si un travail correspondant existe déjà, l'API le renvoie au
    lieu d'en créer un doublon.
- **Champs obligatoires :** `user`, `platform[]` et `photos[]`.
- **`photos[]`** reçoit des fichiers **ou des URL HTTPS publiques**, avec un
  champ `photos[]` par URL.
  - Des vidéos ne sont admises dans `photos[]` que pour les carrousels mixtes
    d'Instagram et de Threads.
  - Carrousel Instagram : 10 éléments au plus (source :
    https://docs.upload-post.com/guides/post-to-instagram-api — vérifié le 2026-10-04).
  - Google Business : une seule photo par post via l'API (source :
    https://docs.upload-post.com/resources/character-limits — vérifié le 2026-10-04).

### 2.2 Valeurs exactes de `platform[]` pour les photos

`tiktok`, `instagram`, `linkedin`, `facebook`, `x`, `threads`, `pinterest`,
`bluesky`, `reddit`, `discord`, `telegram`, `google_business`, `mastodon`,
`lemmy`, `wordpress`.

- **Pas de `youtube` pour les photos.**
- `reddit` renvoie actuellement un 503 `reddit_unavailable`.

### 2.3 Champs communs

| Champ | Rôle |
|---|---|
| `title` | **texte par défaut du post**, ou légende |
| `description` | texte long, lu **seulement** par la description photo TikTok, le commentaire LinkedIn, la description Facebook, la note Pinterest et le corps Reddit ; **ignoré ailleurs**, dont Instagram, Threads, X et Google Business |
| `scheduled_date` | ISO-8601, dans le futur, à 365 jours au plus ; renvoie **202** avec `job_id` |
| `timezone` | IANA, par exemple `Europe/Paris` ; UTC par défaut ; sert à lire `scheduled_date` |
| `async_upload` | booléen ; renvoie immédiatement un `request_id` |
| `request_id` | identifiant choisi par le client, également accepté en en-tête `X-Request-Id` |
| `external_id` | notre identifiant, 255 caractères au plus, également en en-tête `X-External-Id` ; une simple étiquette, ce n'est **pas** un anti-doublon |
| `add_to_queue` | booléen ; incompatible avec `scheduled_date` |
| `max_posts_per_slot` | entier, utilisé avec `add_to_queue` |
| `first_comment` | premier commentaire : Instagram, Facebook, Threads, Bluesky, X, YouTube, LinkedIn, TikTok |

### 2.4 Texte par plateforme

**Surcharges de légende :** `instagram_title`, `facebook_title`, `tiktok_title`,
`linkedin_title`, `x_title`, `pinterest_title`, `threads_title`,
`bluesky_title`, `reddit_title`. Sans surcharge, chaque plateforme reprend
`title`.

**Texte d'un post Google Business :** c'est `title`. La page Character Limits
le nomme « Post summary (title) – 1 500 caractères ».
- **Aucun `google_business_title` n'est documenté — NON CONFIRMÉ** ; ne pas
  l'utiliser.
- Source : https://docs.upload-post.com/resources/character-limits — vérifié le 2026-10-04.

**Premier commentaire par plateforme :** `instagram_first_comment`,
`facebook_first_comment`, `x_first_comment`, `threads_first_comment`,
`bluesky_first_comment`, `linkedin_first_comment`, `tiktok_first_comment`,
`reddit_first_comment`.
- Un premier commentaire **ne fait jamais échouer la publication**.
- Un échec revient dans `warnings`, une liste de chaînes, et `success` reste
  `true`.
- Sur TikTok, il faut la capacité `comments`.

### 2.5 Champs propres à chaque plateforme pour les photos

**Instagram**
- `instagram_title`.
- **`media_type`** : `IMAGE` (valeur par défaut) ou `STORIES`. Le carrousel est
  automatique dès qu'il y a plusieurs `photos[]`.
- `collaborators` : liste séparée par des virgules.
- `user_tags` : une chaîne JSON avec des coordonnées `x`/`y` pour les photos.
  Sans coordonnées, l'étiquette est ignorée sans erreur.
- `location_id` : numérique.
- `is_ai_generated`.
- `instagram_alt_text`.

**Facebook**
- `facebook_title`.
- **`facebook_page_id`** :
  - à passer à chaque envoi ;
  - si une seule page est connectée, on peut l'omettre ;
  - s'il y en a plusieurs, la réponse renvoie `available_pages`.
- `facebook_media_type` : `POSTS` ou `STORIES`.
- `facebook_alt_text`, `facebook_place_id`.
- La légende ne s'applique qu'à la première photo.

**LinkedIn**
- `linkedin_title`.
- `linkedin_description`, ou à défaut `description`, pour le commentaire.
- **`target_linkedin_page_id`** : sans lui, la publication part sur le **profil
  personnel**.
- `visibility` : `PUBLIC`, `CONNECTIONS`, `LOGGED_IN` ou `CONTAINER`. Alias
  `linkedin_visibility` et `linkedinVisibility`. Valeur par défaut : `PUBLIC`.
- `linkedin_alt_text`.
- `linkedin_disable_reshare`.

**TikTok (photos)**
- `tiktok_title` : 90 caractères au plus en photo.
- `tiktok_description`.
- `privacy_level` : `PUBLIC_TO_EVERYONE`, `MUTUAL_FOLLOW_FRIENDS`,
  `FOLLOWER_OF_CREATOR` ou `SELF_ONLY`. Une valeur que le compte n'a pas est
  refusée avec `tiktok_privacy_unavailable`.
- `post_mode` : `DIRECT_POST` ou `MEDIA_UPLOAD` (brouillon).
- `auto_add_music`, `disable_comment`, `brand_content_toggle`,
  `brand_organic_toggle`, `photo_cover_index`, `disable_inbox_fallback`.

**Threads**
- `threads_title`.
- `threads_topic_tag`, `threads_alt_text`, `threads_reply_control`.
- `threads_thread_media_layout`.
- 20 médias au plus.

**Pinterest**
- `pinterest_title` : 100 caractères au plus.
- `pinterest_description`, ou à défaut `description`.
- **`pinterest_board_id`**, obligatoire.
- `pinterest_link` : 2 048 caractères au plus.
- `pinterest_alt_text`, `pinterest_board_section_id`.
- Carrousel :
  - `pinterest_carousel_titles[]` ;
  - `pinterest_carousel_descriptions[]` ;
  - `pinterest_carousel_links[]` ;
  - de 2 à 5 photos.

**Google Business**

| Champ | Rôle |
|---|---|
| `gbp_location_id` | automatique s'il n'y a qu'un établissement ; sinon l'API demande de choisir |
| `gbp_topic_type` | `STANDARD` (défaut), `EVENT` ou `OFFER` |
| `gbp_cta_type` | `BOOK`, `ORDER`, `SHOP`, `LEARN_MORE`, `SIGN_UP` ou `CALL` ; alias `cta_type` ; une valeur inconnue renvoie 400 |
| `gbp_cta_url` | obligatoire sauf pour `CALL` (qui ne doit pas porter d'URL) ; alias `cta_url` |
| Événement | `gbp_event_title` (obligatoire, 58 caractères), `gbp_event_start_date` (`YYYY-MM-DD`, obligatoire), `gbp_event_start_time` (`HH:MM`), `gbp_event_end_date` (obligatoire), `gbp_event_end_time` |
| Offre | `gbp_coupon_code` (alias `gbp_offer_coupon`), `gbp_redeem_url` (alias `gbp_offer_redeem_url`), `gbp_terms` (alias `gbp_offer_terms`) |
| `gbp_language_code` | défaut `"en"` : **mettre `"fr"`** |
| Galerie au lieu d'un post | `gbp_post_type` = `MEDIA`, `PHOTO` ou `GALLERY`, ou `gbp_upload_to_gallery=true` |
| `gbp_media_category` | `COVER`, `PROFILE`, `LOGO`, `EXTERIOR`, `INTERIOR`, `PRODUCT`, `AT_WORK`, `FOOD_AND_DRINK`, `MENU`, `COMMON_AREA`, `ROOMS`, `TEAMS` ou `ADDITIONAL` (défaut) |

- Erreurs : `MEDIA_REQUIRED`, `INVALID_MEDIA_CATEGORY`.
- Les produits ne sont pas publiables via l'API.

---

## 3. `POST /api/upload` (vidéo) : ce qui diffère

Sources, vérifiées le 2026-10-04 :
- https://docs.upload-post.com/api/upload-video
- https://docs.upload-post.com/guides/post-to-youtube-api, section « YouTube Shorts »
- la FAQ.

### 3.1 Forme de la requête

- **Type de contenu :** `multipart/form-data`.
- **Champ média :** `video`, qui accepte un **fichier ou une URL**.
- **`platform[]`** admet en plus `youtube`.
- **`title` est obligatoire pour YouTube** (et pour Reddit).
- **`description`** n'est lue que par LinkedIn, Facebook, YouTube et Pinterest.
- Les autres champs communs sont ceux du §2.3.

### 3.2 YouTube Shorts

- **Il n'y a pas de champ « Short ».** YouTube classe automatiquement en Short
  une vidéo de **180 secondes au plus**, au format **vertical 9:16 ou carré 1:1**.
- Les miniatures personnalisées **ne s'appliquent pas aux Shorts**.

| Champ | Valeurs |
|---|---|
| `youtube_title` | 100 caractères ; défaut `title` |
| `youtube_description`, ou `description` | défaut `title` |
| **`privacyStatus`** | `public` (défaut), `unlisted` ou `private` |
| `tags` (`tags[]` dans les exemples) | défaut `[]` |
| `categoryId` | défaut `"22"` |
| `selfDeclaredMadeForKids` | défaut `false` |
| `containsSyntheticMedia` | contenu IA ; défaut `false` |
| `hasPaidProductPlacement` | |
| `defaultLanguage`, `defaultAudioLanguage` | codes BCP-47 |
| `license` | `youtube` ou `creativeCommon` |
| `embeddable`, `publicStatsViewable` | |
| `youtube_notify_subscribers` | |
| `youtube_publish_at` | RFC3339 ; **force `privacyStatus=private`** |
| `youtube_playlist_id` | |
| `youtube_first_comment` | |
| `thumbnail`, ou `thumbnail_url` | |
| Sous-titres | `youtube_subtitle_file`, `_language`, `_name`, et leurs variantes indexées `_{N}` |

### 3.3 TikTok vidéo

**Confidentialité :**
- **`privacy_level`** : `PUBLIC_TO_EVERYONE`, `MUTUAL_FOLLOW_FRIENDS`,
  `FOLLOWER_OF_CREATOR` ou `SELF_ONLY`.
- Sans ce champ, le réglage par défaut du compte s'applique.
- Les valeurs permises pour un compte se lisent dans
  `GET /api/uploadposts/tiktok/settings`, champ `privacy_level_options`.
- Une connexion qui n'a pas la capacité `video_privacy` publie toujours en
  public.

**Publication directe ou brouillon :**
- `post_mode` : `DIRECT_POST` (défaut) ou `MEDIA_UPLOAD`. Alias de ce dernier :
  `tiktok_upload_to_draft=true`.
- **En `MEDIA_UPLOAD`, la légende ne suit pas la vidéo** jusqu'au brouillon.

**Couverture :** `cover_timestamp` (en ms), `tiktok_cover_image_url`,
`tiktok_cover_image`.

**Musique :** `tiktok_music_id`, `tiktok_music_volume`, `tiktok_music_start`,
`tiktok_music_end`, `tiktok_original_sound_volume`.

**Lieu :** `tiktok_location_id` et `tiktok_location_name`.

**Divers :** `is_aigc` (alias `tiktok_is_ai_generated`), `disable_inbox_fallback`.

**La description globale (`description`) est ignorée par TikTok.**

### 3.4 Instagram Reels

- **`media_type`** : `REELS` (défaut en vidéo) ou `STORIES`.
- `share_to_feed` : défaut `true`.
- `share_mode` : `CUSTOM` (défaut), ou les Trial Reels
  `TRIAL_REELS_SHARE_TO_FOLLOWERS_IF_LIKED` et
  `TRIAL_REELS_DONT_SHARE_TO_FOLLOWERS`.
- `cover_url`, ou `cover_image` (fichier).
- `thumb_offset` : en ms.
- `collaborators`.
- `user_tags` : une liste séparée par des virgules suffit, pas de coordonnées
  en vidéo.
- `audio_name`.
- `description` est ignorée.

### 3.5 Facebook vidéo

- `facebook_media_type` : `REELS` (défaut), `STORIES` ou `VIDEO`.
- Une story ignore le titre et la description.
- La miniature (`facebook_thumbnail` ou `thumbnail_url`) n'est prise en compte
  qu'avec `VIDEO`.

### 3.6 Google Business vidéo

- 30 secondes au plus.
- 28 Mo au plus après réencodage ; sinon erreur `MEDIA_LIMITS`.

---

## 4. `POST /api/upload_text`

Source : https://docs.upload-post.com/api/upload-text — vérifié le 2026-10-04.

- **Type de contenu :** `multipart/form-data`, selon l'OpenAPI.
- **Champs obligatoires :** `user`, `platform[]` et `title`. Ici, `title` est le
  texte.
- **Plateformes admises :** `linkedin`, `x`, `facebook`, `threads`, `reddit`,
  `bluesky`, `discord`, `telegram`, `google_business`, `slack`, `mastodon`,
  `nostr`, `lemmy`, `devto`, `hashnode`, `wordpress`, `whop`, `listmonk`.
- **Pas d'Instagram, de TikTok, de YouTube ni de Pinterest** en texte seul.

**Champs utiles pour nous :**

| Champ | Rôle |
|---|---|
| `link_url` | carte d'aperçu sur LinkedIn, Bluesky et Facebook |
| `linkedin_link_url` | prioritaire sur `link_url` pour LinkedIn |
| `facebook_link_url` | prioritaire sur `link_url` pour Facebook |
| `target_linkedin_page_id` | page LinkedIn visée |
| `linkedin_visibility` | |
| Sondage LinkedIn | `linkedin_poll_question`, `linkedin_poll_options[]`, `linkedin_poll_duration` |
| `facebook_page_id` | **obligatoire**, auto-détecté s'il n'y a qu'une page |
| Threads | `threads_long_text_as_post` (au-delà de 500 caractères, Threads crée un fil), `threads_topic_tag`, `threads_link_attachment` |
| Google Business | les mêmes `gbp_*` qu'au §2.5 ; un post sans photo est accepté, sauf si l'on choisit la galerie (`MEDIA_REQUIRED`) |

Les champs communs restent les mêmes : `scheduled_date`, `timezone`,
`async_upload`, `request_id`, `external_id`, `add_to_queue`, `first_comment` et
les `*_first_comment`.

---

## 5. Réponses : synchrone, asynchrone, statut, historique

Sources, vérifiées le 2026-10-04 :
- https://docs.upload-post.com/api/upload-video, section « Responses »
- https://docs.upload-post.com/guides/error-handling
- https://docs.upload-post.com/api/upload-status
- https://docs.upload-post.com/api/upload-history

### 5.1 Réponse synchrone (200)

```json
{"success": true,
 "results": {
   "instagram": {"success": true, "url": "https://instagram.com/p/...", "container_id": "..."},
   "linkedin":  {"success": false, "error": "Expired access token"}},
 "usage": {"count": 12, "limit": 100, "last_reset": "..."}}
```

**Champs possibles pour chaque plateforme :** `url`, `publish_id`,
`container_id`, `post_id`, `post_ids`, `video_urn`, `video_reel_id`,
`video_id`, `image_urns`, `video_was_transcoded`, `changes`,
`prevalidation_metadata`, `error`, `warnings`, `fallback_to_inbox` (TikTok).

**Plateforme non connectée au profil :**

```json
"linkedin": {"success": false, "skipped": true,
  "skip_reason": "profile_platform_not_configured",
  "error": "Profile creator has no Linkedin account configured",
  "error_code": "profile_platform_mapping_invalid",
  "failure_stage": "profile_platform_validation"}
```

Si **aucune** plateforme demandée n'est connectée, l'API répond 400 avec
`invalid_platforms: {plateforme: message}`.

### 5.2 Envoi asynchrone et envoi programmé

**Envoi asynchrone (200)** :

```json
{"success": true, "message": "Upload initiated successfully in background.", "request_id": "…", "total_platforms": 3}
```

- **Au-delà de 59 secondes, l'API passe d'elle-même en asynchrone.**
- Si le client HTTP expire, **ne pas renvoyer la requête** : fournir son propre
  `request_id` dès le départ.

**Envoi programmé (202)** :

```json
{"success": true, "job_id": "…", "scheduled_date": "…"}
```

### 5.3 Codes d'erreur globaux

Le corps vaut `{"success": false, "message": "..."}`, sauf pour le 500 qui
porte `"error"`.

| Code | Sens |
|---|---|
| 400 | champ manquant, `"Invalid platforms: …"`, `"Username not associated with any profile"` |
| 401 | authentification refusée |
| 403 | restriction de l'offre |
| 404 | `"User not found"` |
| 429 | quota mensuel (avec `usage`), plafond quotidien d'un compte, ou limite de requêtes |
| 500 | `{"success": false, "error": "..."}` |
| 503 | `reddit_unavailable` |

### 5.4 Interroger le statut

**Requête :** `GET /api/uploadposts/status?request_id=…`, ou `?job_id=…` pour un
envoi programmé.

**Réponse :**

```json
{"request_id": "...", "external_id": "...", "status": "in_progress",
 "completed": 1, "total": 2,
 "results": [{"platform": "x", "success": true, "message": "...", "upload_timestamp": "..."}],
 "last_update": "..."}
```

**`status` global :**
- `pending`, `queued`, `processing`, `in_progress` : en cours ;
- `completed` : terminé ;
- `failed` : tout a échoué, ou aucune activité depuis plus d'une heure ;
- `not_found` : identifiant inconnu (HTTP 404).

**Statut par plateforme :** `queued`, `processing`, `completed`, `failed`,
`retryable`, `skipped`.

**Cadence d'interrogation :**
- attendre 5 s avant le premier appel ;
- puis interroger toutes les 10 s environ ;
- s'arrêter sur `completed` ou `failed`.

**Où trouver l'URL et l'identifiant du post :** les exemples de `status` ne
montrent ni `post_url` ni `platform_post_id` (**NON CONFIRMÉ qu'ils y
figurent**). Il faut lire l'historique :
`GET /api/uploadposts/history?request_id=…`, ou `?job_id=` ou `?external_id=`.

**Champs d'une ligne d'historique, une par plateforme :**
- `platform` ;
- `success` ;
- **`platform_post_id`** : une chaîne, un tableau ou null ;
- **`post_url`** ;
- `error_message` ;
- `media_type` ;
- `upload_timestamp` ;
- `request_id`, `job_id`, `external_id` ;
- `fallback_to_inbox`.

**Paramètres de l'historique :**
- `page`, et `limit` qui vaut 10, 20, 50 ou 100 ;
- `platform`, `status` (`success` ou `failed`), `profile_username` ;
- `start` et `end` : deux mois d'écart au plus.

### 5.5 Autres actions sur un envoi

**Relancer un échec** : `POST /api/uploadposts/posts/retry`, en JSON
`{request_id}` ou `{job_id}`.
- Seules les plateformes en échec sont relancées.
- Renvoie 409 s'il n'y a rien à relancer.
- Source : https://docs.upload-post.com/api/retry-post — vérifié le 2026-10-04.

**Annuler un envoi programmé** : `DELETE /api/uploadposts/schedule/{job_id}`.
- La réponse contient `credits_refunded`.
- `PATCH` sur la même route permet de modifier l'envoi.
- `GET /api/uploadposts/schedule` liste les envois programmés.
- Source : https://docs.upload-post.com/api/schedule-posts — vérifié le 2026-10-04.

---

## 6. Dépublier ou supprimer un post

Source : https://docs.upload-post.com/api/unpublish-post — vérifié le 2026-10-04.

**Requête :** `POST /api/uploadposts/posts/unpublish`, en JSON.

```json
{"platform": "youtube", "user": "marque-01", "post_id": "<id natif>"}
```

- **Réponse 200 :** `{"success": true, "message": "Post deleted successfully"}`.
- **Erreurs :**
  - 400 : plateforme non prise en charge ;
  - 403 : non autorisé ;
  - 404 : post introuvable ;
  - 500.

| Plateforme | Suppression via l'API |
|---|---|
| Facebook, YouTube, X, LinkedIn, Pinterest, Bluesky, Google Business, Discord, Telegram, Mastodon, WordPress | oui |
| Instagram | **non** |
| TikTok | **non** |
| Threads | **non** (400 `platform_not_supported`) |

Pour Google Business, `post_id` est le nom complet
`accounts/{a}/locations/{l}/localPosts/{p}` renvoyé lors de l'envoi.

---

## 7. Statistiques

Source : https://docs.upload-post.com/api/get-analytics — vérifié le 2026-10-04.

### 7.1 Par profil

**Requête :** `GET /api/analytics/{profile_username}?platforms=instagram,tiktok,...`.

| Paramètre | Portée |
|---|---|
| `platforms` | obligatoire, séparées par des virgules |
| `page_id` | Facebook, obligatoire |
| `days` | Facebook, de 1 à 365, défaut 30 |
| `page_urn` | LinkedIn : **uniquement les pages d'entreprise, jamais le profil personnel** |

**Plateformes couvertes :** `instagram`, `tiktok`, `linkedin`, `facebook`, `x`,
`youtube`, `threads`, `pinterest`, `reddit`, `bluesky`, `google_business`.

**Champs, par plateforme :**
- `followers`, `reach`, `views`, `impressions`, `profileViews` ;
- `likes`, `comments`, `shares`, `saves` ;
- `reach_timeseries: [{date, value}]` ;
- `metric_type` : `reach`, `views`, `impressions` ou `score` ;
- `primary_impressions_field`, `available_metrics`, `metric_labels`.

**Champs propres à certaines plateformes :**
- YouTube : `watch_time_minutes`, `average_view_duration_seconds` ;
- Pinterest : `pin_clicks`, `outbound_clicks` ;
- Instagram : `follower_demographics`, `engaged_audience_demographics` ;
- Facebook : `impressions_timeseries`, `period_days`.

**Le détail des champs renvoyés pour `google_business` n'est pas documenté —
NON CONFIRMÉ.**

**Total consolidé :**
`GET /api/uploadposts/total-impressions/{profile_username}`.
- Paramètres : `date`, `start_date`, `end_date`.
- `period` : `last_day`, `last_week`, `last_month`, `last_3months` ou
  `last_year`.
- `platform`, `breakdown=true`, `metrics`.

### 7.2 Par post

**Pour un envoi fait par l'API :**
`GET /api/uploadposts/post-analytics/{request_id}`, avec `?platform=` en option.
- Réponse : `{success, post: {request_id, profile_username, post_title, post_caption, media_type, upload_timestamp}, platforms: {...}}`.
- Chaque entrée de `platforms` porte `success`, `platform_post_id`, `post_url`,
  `post_metrics` (`views`, `likes`, `comments`, `shares`…),
  `post_metrics_source`, `post_metrics_error`,
  `profile_snapshot_at_post_date`, `profile_snapshot_latest` et
  `profile_snapshot_latest_date`.

**Pour n'importe quel post, y compris publié à la main :**
`GET /api/uploadposts/post-analytics?platform_post_id=…&platform=…&user=…`.
- Interrogation en direct, **limitée à 100 requêtes par tranche de 5 minutes**.
- `post.source` vaut `organic` ou `api_uploaded`.
- Plateformes : `youtube`, `tiktok`, `instagram`, `facebook`, `linkedin`, `x`,
  `threads`, `pinterest`, `reddit`.
- **Google Business n'est pas listé.**

**Lecture en cache, paginée :**
`GET /api/uploadposts/post-analytics/cached?user=…`.
- Paramètres : `platform`, `limit` (50 par défaut, 200 au plus), `cursor`,
  `since`, `until`.
- Champs d'une ligne : `post_id`, `platform`, `profile_username`, `date`,
  `captured_at`, `metrics`, `post_url`, `media_type`, `upload_timestamp`.
- La réponse fournit `next_cursor` pour la page suivante.

---

## 8. Commentaires et messages privés

Sources, vérifiées le 2026-10-04 :
- https://docs.upload-post.com/api/comments
- https://docs.upload-post.com/api/instagram-comments
- https://docs.upload-post.com/api/instagram-dms

### 8.1 Lister

**Requête :** `GET /api/uploadposts/comments`.

**Paramètres :**
- `platform` : défaut `instagram` ;
- `user` : obligatoire ;
- `post_id` **ou** `post_url` ;
- `limit` : de 1 à 50 sur Instagram ;
- `after` : curseur ;
- `comment_id` : sur TikTok, liste les réponses à ce commentaire.

**Réponse :**

```json
{"success": true, "comments": [{"id", "text", "timestamp", "user": {"id", "username"}}],
 "pagination": {"next_cursor", "has_next"}}
```

La forme exacte des commentaires varie selon la plateforme.

**Forme de `post_id` selon la plateforme :**
- YouTube : l'identifiant de la vidéo ;
- TikTok : l'identifiant de la vidéo ;
- LinkedIn : l'URN `urn:li:ugcPost:…` ;
- Instagram : l'identifiant numérique du média ;
- Bluesky : l'URI `at://`.

**Couverture :**

| Plateforme | Lister | Créer | Supprimer |
|---|---|---|---|
| Instagram | oui | oui, **réponse seulement** (exige `comment_id`) | oui |
| Facebook | oui | oui | oui |
| YouTube | oui | oui | oui |
| LinkedIn | oui, **pages d'entreprise seulement** | oui | oui |
| TikTok | oui, après reconnexion | oui | oui |
| X | oui | oui | oui |
| Threads | partiel | oui | non |
| Bluesky | oui | oui | oui |

**Google Business et Pinterest ne figurent pas dans cette API.** Pour Google
Business, les avis se traitent au §9.

### 8.2 Répondre ou commenter

**Requête :** `POST /api/uploadposts/comments/create`, en JSON.

| Champ | Rôle |
|---|---|
| `platform` | obligatoire |
| `user` | obligatoire |
| **`message`** | obligatoire : le texte |
| `comment_id` | répond à ce commentaire |
| `post_id`, ou `post_url` | commentaire de premier niveau |
| `attachment_url`, `attachment_share_url` | Facebook seulement |

- Donner **exactement un** de `comment_id`, `post_id` et `post_url`.
- **Exception TikTok :** `post_id` est toujours obligatoire, et on y ajoute
  `comment_id` pour répondre.
- Réponse : `{"success": true, "id": "...", "message": "Comment created successfully"}`.

**Réponse publique Instagram, autre route :**
`POST /api/uploadposts/comments/public-reply`, avec
`{platform, user, comment_id, message}`.

### 8.3 Supprimer et modérer

**Supprimer :** `DELETE` (ou `POST`) sur `/api/uploadposts/comments/delete`.
- Corps : `{platform, user, comment_id}`.
- Ajouter `post_id` pour LinkedIn.

**Modérer :** `POST /api/uploadposts/comments/action`.
- Corps : `{platform, user, comment_id, action, post_id?, message?, ban_author?}`.
- `action` vaut `hide`, `unhide`, `like`, `unlike`, `pin`, `unpin`, `edit`
  (Facebook), `hold` (YouTube), `enable_comments` ou `disable_comments`
  (Instagram).

### 8.4 Messages privés (Instagram seulement)

- **Réponse privée à un commentaire :** `POST /api/uploadposts/comments/reply`,
  avec `{platform: "instagram", user, comment_id, message, buttons?}`.
  - La fenêtre est de 7 jours.
  - Une seule réponse privée par commentaire.
- **Envoyer un message :** `POST /api/uploadposts/dms/send`, avec
  `{platform: "instagram", user, recipient_id, message, buttons?, attachments?, quick_replies?, reply_to?}`.
- **Lister les conversations :**
  `GET /api/uploadposts/dms/conversations?platform=instagram&user=…`.

Points communs :
- dans l'OpenAPI, l'énumération de `platform` vaut `["instagram"]` ;
- un plafond quotidien renvoie 429 `"Daily DM limit exceeded."`.

---

## 9. Avis Google Business

Source : https://docs.upload-post.com/api/google-business-reviews — vérifié le 2026-10-04.

### 9.1 Lister les avis

**Requête :** `GET /api/uploadposts/google-business/reviews`.

**Paramètres :**
- `user` : obligatoire ;
- `location_id` : `locations/…` ou le chemin complet ;
- `pageSize`, `pageToken` ;
- `orderBy` : par exemple `updateTime desc` ou `rating desc`.

**Réponse :**

```json
{"success": true,
 "reviews": [{"name": "accounts/…/locations/…/reviews/…", "reviewer": {"displayName"},
   "starRating": "FIVE", "comment", "createTime", "updateTime",
   "reviewReply": {"comment", "updateTime"}}],
 "averageRating": 4.7, "totalReviewCount": 128, "nextPageToken": "..."}
```

### 9.2 Répondre à un avis

**Requête :** `PUT` (ou `POST`) sur
`/api/uploadposts/google-business/reviews/reply`, en JSON.

```json
{"user": "...", "comment": "texte public", "review_name": "accounts/…/reviews/…"}
```

- À la place de `review_name`, on peut envoyer `review_id` avec `location_id`.
- La même requête crée la réponse ou la met à jour.
- Réponse : `{success, reply: {comment, updateTime}}`.

### 9.3 Supprimer une réponse, lire en lot, limites

- **Supprimer la réponse :** `DELETE` sur la même route, avec les mêmes
  identifiants.
- **Lecture en lot :** `GET`/`POST /api/uploadposts/google-business/reviews/batch`.
- **Établissements vérifiés seulement.**
- On ne peut ni supprimer un avis ni modifier sa note.

---

## 10. Webhooks

Source : https://docs.upload-post.com/api/webhooks — vérifié le 2026-10-04.

### 10.1 Enregistrer

**Au niveau du compte :**
`POST https://app.upload-post.com/api/uploadposts/users/notifications`.
- **Attention à l'hôte : `app.`**, et non `api.`.
- `GET` sur la même route relit la configuration et le `webhook_secret`.
- `DELETE` la supprime.

Corps :

```json
{"channels": {"webhook": true, "telegram": false},
 "webhook_url": "https://…",
 "webhook_events": {"upload_completed": true, "social_account_connected": true,
   "social_account_disconnected": true, "social_account_reauth_required": true}}
```

La réponse renvoie `notifications.webhook_secret`, sous la forme `whsec_…`.

**Par profil (marque) :** `GET`/`POST`/`DELETE`
`/api/uploadposts/users/profile-webhook`.
- Corps : `{profile_username, webhook_url, webhook_events?}`.
- Il s'ajoute au webhook du compte.
- Il est signé avec le **même** secret.

**Rotation du secret :** `POST /api/uploadposts/users/webhook-secret`.
- Effet immédiat.
- Pendant la bascule, accepter les deux secrets.

### 10.2 Événements

- `upload_completed` : se déclenche **une fois par plateforme et par envoi**,
  en succès comme en échec.
- `social_account_connected`
- `social_account_disconnected`
- `social_account_reauth_required`

### 10.3 Contenu des notifications

**`upload_completed` :**

```json
{"event": "upload_completed", "job_id": "…", "user_email": "…",
 "profile_username": "…", "platform": "instagram", "media_type": "video",
 "title": "…", "caption": "…",
 "result": {"success": true, "url": "…", "publish_id": "…", "post_id": "…", "error": null},
 "created_at": "2024-03-15T14:30:00.000000"}
```

**Rapprocher une notification de l'envoi d'origine — NON CONFIRMÉ.** Le corps
ne documente **pas** de `request_id`, et `job_id` n'y figure que s'il existait
un `job_id`. Pour retrouver l'envoi, rapprocher par `profile_username`,
`platform` et `result.post_id`, ou relire l'historique (§5.4).

**Événements de connexion :** `{event, user_email, platform, account_name,
status, profile_username, reason?, created_at}`.
- `status` vaut `connected`, `disconnected` ou `reauth_required`.
- `reason` vaut par exemple `manual_disconnect`, `account_blocked`,
  `token_refresh_threshold_exceeded` ou `max_auth_strikes`.

### 10.4 Vérifier la signature

**En-têtes reçus :**
- `X-Upload-Post-Signature: sha256=<hex>` ;
- `X-Upload-Post-Timestamp` : en secondes Unix ;
- `X-Upload-Post-Event` ;
- `X-Upload-Post-Delivery` : identifiant unique, pour dédoublonner ;
- `User-Agent: Upload-Post-Webhooks/1.0`.

**Calcul exact :** `HMAC_SHA256(webhook_secret, "<timestamp>." + corps_brut)`,
encodé en hexadécimal.
- Calculer sur les **octets bruts** du corps, sans relire puis resérialiser le
  JSON.
- Refuser au-delà de 300 secondes d'écart.
- Comparer en temps constant.

Exemple officiel en Python :

```python
expected = hmac.new(SECRET.encode(), f"{ts}.".encode() + request.get_data(), hashlib.sha256).hexdigest()
ok = hmac.compare_digest(sig_sans_prefixe, expected)
```

**Coupe-circuit :** après 5 échecs de livraison consécutifs, le canal est mis en
pause 30 minutes.

---

## 11. Limites, plafonds, format d'erreur, codes notables

Sources, vérifiées le 2026-10-04 :
- https://docs.upload-post.com/guides/rate-limits
- https://docs.upload-post.com/guides/limit-of-uploads
- https://docs.upload-post.com/resources/common-errors
- https://docs.upload-post.com/resources/pricing-and-limits

### 11.1 Limites de requêtes

**Offre Professional :**
- **100 requêtes par minute et 500 par tranche de 10 minutes** ;
- plus 2 par minute et 10 par tranche de 10 minutes **pour chaque profil**.

**En-têtes de suivi :** `X-RateLimit-Limit`, `X-RateLimit-Remaining`,
`X-RateLimit-Reset`.

**Dépassement :** HTTP 429.

**Protection contre les clés invalides :** 10 essais de clé invalide bloquent
l'adresse IP 5 minutes.

### 11.2 Plafonds quotidiens

Plafonds par **compte social**, sur 24 heures glissantes. Leur dépassement
renvoie 429.

| Instagram | TikTok | LinkedIn | YouTube | Facebook | Threads | Pinterest | X (Professional) |
|---|---|---|---|---|---|---|---|
| 50 | 15 | 150 | 10 | 25 | 50 | 20 | 20 |

- Les plafonds sont revérifiés au moment où part un envoi programmé.
- **Contradiction :** la page Common Errors donne Pinterest à 25 et YouTube à
  30. Les deux pages « Limit of uploads » et « Pricing & Limits » donnent 20 et
  10, et ce sont elles qui décrivent le plafond **appliqué**.

**Corps renvoyé quand le plafond est atteint (429) :**

```json
{"success": false, "message": "Post verification failed",
 "violations": [{"platform": "instagram", "type": "hard_cap",
   "message": "Daily cap reached for instagram: 50/50 in last 24h", "used_last_24h": 50, "cap": 50}]}
```

**Quota Instagram en direct :**
`GET /api/uploadposts/instagram/publishing_limit?profile=…`.
- Réponse : `quota_usage`, `quota_total`, `remaining`, `limit_reached`.
- À l'épuisement, l'erreur vaut `instagram_publishing_limit_reached`.

### 11.3 Format d'erreur

- **Erreur globale :** `{"success": false, "message": "..."}`. Le 500 porte
  `"error"`, et certaines routes ajoutent `"error_code"`.
- **Erreur d'une plateforme dans une réponse 200 :**
  `results.<p>.error`, en texte libre, plus parfois `error_code` et
  `failure_stage`.

### 11.4 Codes notables

**Contenu en double — NON CONFIRMÉ.**
- Le vérificateur contrôle le « contenu identique ou similaire sous 48 h, par
  compte et par réseau ».
- Un envoi identique (même `user`, même plateforme, même empreinte) dans une
  fenêtre courte **renvoie la requête existante** au lieu d'une erreur.
- **Aucun `error_code` ni `type` de violation n'est documenté pour un refus pour
  doublon.** Seul `hard_cap` l'est.

**Compte non connecté :**
- `skip_reason: "profile_platform_not_configured"` ;
- `error_code: "profile_platform_mapping_invalid"` ;
- 400 avec `invalid_platforms` si plus rien n'est publiable.

**Jeton expiré :**
- **Pour une publication**, l'erreur est un texte libre dans
  `results.<p>.error`, par exemple `"Expired access token"`,
  `"Your LinkedIn session has expired…"` ou `"Token expired and refresh
  failed"`. **Aucun `error_code` stable n'est documenté pour ce cas — NON
  CONFIRMÉ.**
- Signaux fiables :
  - `social_accounts.<p>.reauth_required: true` dans `GET /api/uploadposts/users` ;
  - le webhook `social_account_reauth_required` ;
  - sur Instagram, Facebook et Threads, après un « checkpoint » Meta (code
    `account_checkpoint_required`), les envois suivants sont refusés avant
    départ avec `error_code: "account_reauth_required"` et
    `failure_stage: "precheck"`, sans consommer de crédit ;
  - sur les commentaires TikTok, un 409 avec `"reauth_required": true`.

**Autres codes :**
- `account_restricted` : refus avant départ, avec `restricted_until` ;
- `tiktok_reconnect_required` : 400, le jeton est valide mais la permission
  manque ;
- `tiktok_privacy_unavailable` ;
- `reached_active_user_cap` : TikTok, sinon repli automatique en brouillon avec
  `fallback_to_inbox: true` ;
- `platform_not_supported` ;
- `MEDIA_REQUIRED`, `MEDIA_LIMITS`, `INVALID_MEDIA_CATEGORY` ;
- `PROFILE_LIMIT_REACHED`, `PROFILE_BLOCKED`, `PROFILE_NOT_FOUND` ;
- `reddit_unavailable` : 503.

---

## 12. Décisions d'implémentation qui découlent de ce qui précède

1. **Un profil Upload-Post par marque (6).** On le lie par
   `generate-jwt` → `access_url`, valable 48 h, avec `language: "fr"` et sans
   `platforms`.
2. **LinkedIn : ne pas épingler de page** si la marque publie aussi sur un
   profil personnel. Passer plutôt `target_linkedin_page_id` à chaque envoi qui
   vise la page.
3. **Toujours envoyer :**
   - un `Idempotency-Key` ;
   - un `request_id` à nous ;
   - un `external_id` (notre identifiant de post) ;
   - `async_upload=true`.

   Puis attendre le webhook `upload_completed`, et relire
   `history?request_id=` pour obtenir `platform_post_id` et `post_url`.
4. **Envoyer `facebook_page_id` à chaque envoi Facebook**, et
   `pinterest_board_id` à chaque envoi Pinterest.
5. **Google Business :**
   - `gbp_language_code=fr` ;
   - le texte va dans `title`, 1 500 caractères au plus ;
   - une photo au plus.
6. **Ne jamais proposer « supprimer »** pour Instagram, TikTok et Threads.
7. **Traiter `warnings` comme un succès avec réserve**, jamais comme un échec :
   sinon on republie le post.
