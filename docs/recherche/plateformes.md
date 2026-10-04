# Contraintes de publication par plateforme — relevé du 2026-10-04

Règle suivie : chaque chiffre ci-dessous a été **lu le 2026-10-04** sur la page citée
(documentation développeur officielle d'abord, centre d'aide officiel ensuite).
Tout ce qui n'a pas pu être lu sur une page officielle est marqué **NON CONFIRMÉ**.
Une valeur « — » signifie : aucune contrainte publiée trouvée (ce n'est pas « illimité »).

Méthode : pages récupérées et lues en texte intégral (curl + extraction), ou via un
lecteur web pour les pages Meta rendues côté client. Les pages d'aide Facebook
(`facebook.com/business/help/...`) ne se laissent pas lire par l'outil : ce qui n'en
est connu que par un extrait de moteur de recherche est marqué NON CONFIRMÉ.

---

## Ce qui a changé par rapport aux idées reçues (à lire d'abord)

| Idée reçue | Ce que dit la doc officielle le 2026-10-04 | Source |
|---|---|---|
| YouTube : un upload coûte 1 600 unités → ~6 vidéos/jour | **Faux depuis 2025-2026.** 04/12/2025 : coût ramené à ~100 unités. 01/06/2026 : `videos.insert` a **son propre seau de quota : 100 appels/jour, 1 unité/appel**, par **projet** Google Cloud (pas par chaîne). | https://developers.google.com/youtube/v3/revision_history · https://developers.google.com/youtube/v3/determine_quota_cost |
| YouTube : liens cliquables dans la description | **Pas pour les Shorts** : « URLs placed in YouTube Shorts comments and Shorts descriptions are non-clickable ». Pour une vidéo longue, il faut en plus les « fonctionnalités avancées » de la chaîne. | https://support.google.com/youtube/answer/13748639?hl=en |
| Instagram : 25 (ou 50) publications API / 24 h | **Contradiction entre deux pages Meta** : le guide dit **100** / 24 h glissantes, la référence de l'endpoint dit « currently **50** ». Lire `quota_total` à l'exécution. | https://developers.facebook.com/docs/instagram-platform/content-publishing/ · https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/content_publishing_limit |
| TikTok : on peut publier en public dès qu'on a l'API | **Non** : client non audité → `SELF_ONLY` uniquement, comptes **privés** uniquement, **5 utilisateurs / 24 h** max. Et un outil « pour les comptes que vous ou votre équipe gérez » est explicitement **refusé** à l'audit. | https://developers.tiktok.com/doc/content-sharing-guidelines |
| TikTok : images PNG acceptées | **Non** : photos **JPEG ou WebP** seulement, 1080p max, 20 Mo. | https://developers.tiktok.com/doc/content-posting-api-media-transfer-guide |
| Pinterest : l'accès d'essai suffit pour tester en vrai | Les épingles créées en **Trial** ne sont **visibles que par leur créateur** (« Sandbox entities »). Et depuis le **14/09/2026**, une app neuve peut recevoir `403 PINNER_DATA_ACCESS_DENIED` en lisant un tableau / une épingle d'un utilisateur non-business. | https://developers.pinterest.com/docs/key-concepts/access-tiers/ · https://developers.pinterest.com/docs/changelog/changelog/ |
| Threads : 500 caractères | Vrai, mais **les emojis comptent en octets UTF-8**, **5 liens max** (au-delà la publication échoue depuis le 22/12/2025), **1 seul sujet (#tag) par post**. | https://developers.facebook.com/docs/threads/posts |
| LinkedIn : carrousel organique par API | **Non** : « Carousels » = sponsorisé uniquement. En organique, c'est **MultiImage (2 à 20 images)**. | https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api |
| LinkedIn : version d'API stable | La version **202510 est coupée le 15/10/2026** (dans 11 jours). Viser `Linkedin-Version: 202609`. | idem |
| Facebook Reels : comme une vidéo | API Reels : **3 à 90 s**, **30 Reels / 24 h** par Page. | https://developers.facebook.com/docs/video-api/guides/reels-publishing |

---

## 1. Instagram (compte professionnel — Graph API)

Sources :
- [IG-PUB] https://developers.facebook.com/docs/instagram-platform/content-publishing/ — vérifié le 2026-10-04
- [IG-MEDIA] https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media — vérifié le 2026-10-04
- [IG-LIMIT] https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/content_publishing_limit — vérifié le 2026-10-04

**Images (fil)**
- Format : **JPEG uniquement** — « JPEG is the only image format supported. Extended JPEG formats such as MPO and JPS are not supported. » [IG-PUB] — vérifié le 2026-10-04
- Poids max : **8 Mo** [IG-MEDIA] — vérifié le 2026-10-04
- Ratio : **4:5 à 1.91:1** (0,8 à 1,91) [IG-MEDIA] — vérifié le 2026-10-04
- Largeur : min **320 px** (agrandie sinon), max **1440 px** (réduite sinon) ; espace colorimétrique sRGB (converti sinon) [IG-MEDIA] — vérifié le 2026-10-04
- Taille recommandée 1080×1350 (4:5) : **NON CONFIRMÉ** (convention répandue, pas sur la doc ; la doc ne donne que min/max de largeur).
- Les médias doivent être hébergés sur un serveur **public** au moment de l'appel [IG-PUB] — vérifié le 2026-10-04

**Vidéo (Reels via API)** [IG-MEDIA] — vérifié le 2026-10-04
- Conteneur **MOV ou MP4**, pas d'edit list, atome `moov` en tête ; vidéo HEVC ou H.264, progressif, GOP fermé ; audio AAC ≤ 48 kHz, 1 ou 2 canaux, 128 kb/s
- **23 à 60 i/s**, largeur max 1920 px, débit ≤ 25 Mb/s VBR
- Ratio accepté **0.01:1 à 10:1**, recommandé **9:16**
- Durée **3 s à 15 min**, poids max **300 Mo**
- Stories (vidéo) : 3 à 60 s, 100 Mo max ; Stories (image) : JPEG 8 Mo, 9:16 recommandé

**Texte** [IG-MEDIA] — vérifié le 2026-10-04
- Légende **2 200 caractères max, 30 hashtags, 20 @mentions**
- Texte alternatif (image) jusqu'à 1 000 caractères ; non supporté pour Reels et Stories [IG-PUB]

**Limite de publication**
- [IG-PUB] : « Instagram accounts are limited to **100** API-published posts within a 24-hour moving period. Carousels count as a single post. » — vérifié le 2026-10-04
- [IG-LIMIT] : `quota_total` « currently **50** », `quota_duration` 86 400 s — vérifié le 2026-10-04
- → **Contradiction officielle.** Prendre 50 comme plafond prudent et lire `GET /<IG_ID>/content_publishing_limit` avant de publier (c'est la méthode que le guide lui-même recommande).
- Limite d'appels (BUC) : 4 800 × nombre d'impressions / 24 h — https://developers.facebook.com/docs/graph-api/overview/rate-limiting — vérifié le 2026-10-04

**Liens** : liens non cliquables dans la légende — **NON CONFIRMÉ** (aucune page officielle trouvée qui le dise ; comportement constaté communément).

**Carrousel** : **10 éléments max** (images, vidéos ou mélange), compte pour 1 publication ; toutes les images sont recadrées sur la première (1:1 par défaut) [IG-PUB] — vérifié le 2026-10-04

**Non supporté par l'API** : tags shopping, filtres [IG-PUB] — vérifié le 2026-10-04

---

## 2. Facebook (Page)

Sources :
- [FB-POSTS] https://developers.facebook.com/docs/pages-api/posts — vérifié le 2026-10-04
- [FB-PHOTOS] https://developers.facebook.com/docs/graph-api/reference/page/photos/ — vérifié le 2026-10-04
- [FB-PHOTO] https://developers.facebook.com/docs/graph-api/reference/photo/ — vérifié le 2026-10-04
- [FB-REELS] https://developers.facebook.com/docs/video-api/guides/reels-publishing — vérifié le 2026-10-04

**Images**
- Formats : **.jpeg, .bmp, .png, .gif, .tiff** [FB-PHOTOS] — vérifié le 2026-10-04 ; « Animated photos are not supported » [FB-PHOTO]
- Poids max : **10 Mo** ; pour un PNG, Meta recommande **≤ 1 Mo** (« or the image may appear pixelated ») [FB-PHOTOS] — vérifié le 2026-10-04
- Ratio min/max : **aucune contrainte publiée** sur ces pages.
- Taille recommandée : **NON CONFIRMÉ** (rien sur la doc).

**Vidéo (Reels de Page)** [FB-REELS] — vérifié le 2026-10-04
- `.mp4` recommandé ; H.264 / H.265 (VP9, AV1 aussi) ; audio AAC-LC 48 kHz stéréo ≥ 128 kb/s ; GOP fermé 2-5 s ; 4:2:0 ; progressif, i/s fixe
- Ratio **9:16** ; résolution recommandée **1080×1920**, minimum **540×960**
- Durée **3 à 90 s** ; **24 à 60 i/s**
- Poids max : **non publié** sur cette page (**NON CONFIRMÉ**)
- Vidéos de Page hors Reels : aucune limite de durée/poids publiée sur la référence `/page/videos` (vérifié le 2026-10-04) ; upload reprenable via la Resumable Upload API.

**Texte**
- Longueur max d'une publication : **63 206 caractères — NON CONFIRMÉ** (chiffre repris par la presse et des outils tiers ; aucune page Meta officielle trouvée).
- Hashtags : aucune limite publiée.

**Limite de publication**
- Reels : « Reels API is limited to **30** API-published posts within a 24-hour moving period » [FB-REELS] — vérifié le 2026-10-04
- Publications de fil (texte/photo/lien) : **aucun plafond publié** ; seule la limite d'appels BUC des Pages : 4 800 × nombre d'utilisateurs engagés / 24 h — https://developers.facebook.com/docs/graph-api/overview/rate-limiting — vérifié le 2026-10-04
- Programmation native : date de publication entre **10 minutes et 30 jours** après la requête [FB-POSTS] — vérifié le 2026-10-04

**Liens** : cliquables dans le texte — **NON CONFIRMÉ** sur une page officielle (le paramètre `link` du fil existe ; la cliquabilité du texte n'est pas écrite).

**Carrousel / multi-photos** : via `/page-id/feed` + `attached_media[]` (photos téléversées avec `published=false`) [FB-PHOTOS] — vérifié le 2026-10-04. **Nombre max NON CONFIRMÉ** (non publié). Une photo non publiée est gardée ~24 h [FB-PHOTOS].

**Divers** : une app ne peut modifier une publication que si elle l'a créée [FB-POSTS] — vérifié le 2026-10-04

---

## 3. LinkedIn (page entreprise + profil personnel)

Sources :
- [LI-POSTS] https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api — vérifié le 2026-10-04 (version doc par défaut li-lms-2026-09)
- [LI-IMG] https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/images-api — vérifié le 2026-10-04
- [LI-VID] https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/videos-api — vérifié le 2026-10-04
- [LI-MULTI] https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/multiimage-post-api — vérifié le 2026-10-04
- [LI-HELP-POST] https://www.linkedin.com/help/linkedin/answer/a528176 — vérifié le 2026-10-04
- [LI-HELP-PHOTO] https://www.linkedin.com/help/linkedin/answer/100983 — vérifié le 2026-10-04
- [LI-HELP-VIDEO] https://www.linkedin.com/help/linkedin/answer/a7486279 — vérifié le 2026-10-04
- [LI-SHARE] https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin — vérifié le 2026-10-04
- [LI-CM] https://learn.microsoft.com/en-us/linkedin/marketing/increasing-access — vérifié le 2026-10-04

**⚠ Version d'API** : « The Marketing Version 202510 (Marketing October 2025) will be sunset on **October 15, 2026** » [LI-POSTS]. En-têtes obligatoires : `Linkedin-Version: AAAAMM` et `X-Restli-Protocol-Version: 2.0.0`.

**Images**
- API : **JPG, GIF, PNG** ; moins de **36 152 320 pixels** ; GIF ≤ 250 images [LI-IMG] — vérifié le 2026-10-04. L'API ne publie **pas** de poids max ni de ratio.
- Aide LinkedIn (téléversement) : **5 Mo** max ; au moins **552×276 px**, **1080 px de large recommandé** ; ratio **3:1 à 4:5** (largeur:hauteur → 0,8 à 3,0) [LI-HELP-PHOTO] — vérifié le 2026-10-04. (Page d'aide de l'interface ; appliquée par prudence à l'API.)
- Texte alternatif : 4 086 caractères max (120 recommandés) [LI-IMG]

**Vidéo**
- API [LI-VID] — vérifié le 2026-10-04 : **MP4**, **3 s à 30 min**, **75 Ko à 500 Mo** (« high-level specifications », renvoyant aux specs pub) ; mais le champ `fileSizeBytes` dit « Maximum allowed Videos size is **5GB** ». **Contradiction interne** → 500 Mo retenu par prudence.
- Aide LinkedIn (publication organique) [LI-HELP-VIDEO] — vérifié le 2026-10-04 : **75 Ko à 5 Go**, **3 s (desktop) à 15 min**, 256×144 à 4096×2304, ratio **1:2.4 à 2.4:1**, 10 à 60 i/s, 192 kb/s à 30 Mb/s.
- → Retenu : 3 s à **15 min** et **500 Mo** (le plus strict des deux sources).
- Sous-titres : un seul fichier, **anglais uniquement** [LI-VID]

**Texte**
- « The character limit for a post is **3,000 characters** » [LI-HELP-POST] — vérifié le 2026-10-04 (aide officielle ; la doc API ne donne pas le chiffre, seulement l'erreur `FIELD_LENGTH_TOO_LONG` sur `commentary`).
- Format « little text » : caractères réservés à échapper ; mentions `@[Nom](urn:li:organization:…)`, hashtags `{hashtag|\#|mot}` — https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/little-text-format — vérifié le 2026-10-04
- Hashtags max : **aucune limite publiée**.

**Limite de publication** (aucun plafond « posts/jour » publié ; ce sont des plafonds d'**appels**)
- Share on LinkedIn (profil) : **150 requêtes / membre / jour**, **100 000 / application / jour** (UTC) [LI-SHARE] — vérifié le 2026-10-04
- Community Management, tier Development : **500 appels / app / 24 h**, **100 appels / membre / 24 h**, pas de BATCH_GET, pas de webhooks [LI-CM] — vérifié le 2026-10-04
- Tier Standard : « No restrictions » [LI-CM] ; limites réelles « not published in documentation », visibles dans le portail (onglet Analytics) — https://learn.microsoft.com/en-us/linkedin/shared/api-guide/concepts/rate-limits — vérifié le 2026-10-04

**Liens** : cliquables dans le texte — **NON CONFIRMÉ** sur une page officielle. Article : l'API **ne scrape pas** l'URL ; il faut fournir soi-même titre, description et vignette (Images API) [LI-POSTS] — vérifié le 2026-10-04

**Carrousel**
- Organique : **MultiImage, 2 à 20 images**, images seulement [LI-MULTI] ; aide : « maximum of 20 photos » [LI-HELP-PHOTO] — vérifié le 2026-10-04
- « Carousels » : **sponsorisé uniquement** (« Organic carousel is currently not supported ») [LI-POSTS] — vérifié le 2026-10-04
- Documents (PDF) et sondages : possibles en organique [LI-POSTS]

---

## 4. TikTok (Content Posting API — Direct Post)

Sources :
- [TT-MEDIA] https://developers.tiktok.com/doc/content-posting-api-media-transfer-guide — vérifié le 2026-10-04 (page « Last updated August 4, 2026 »)
- [TT-VIDEO] https://developers.tiktok.com/doc/content-posting-api-reference-direct-post — vérifié le 2026-10-04
- [TT-PHOTO] https://developers.tiktok.com/doc/content-posting-api-reference-photo-post — vérifié le 2026-10-04
- [TT-GUIDE] https://developers.tiktok.com/doc/content-sharing-guidelines — vérifié le 2026-10-04 (« Last updated August 4, 2026 »)

**Images (posts photo)** [TT-MEDIA] — vérifié le 2026-10-04
- Formats : **WebP, JPEG** (pas de PNG)
- Taille : **1080p max** ; poids **20 Mo max par image**
- Envoi uniquement en `PULL_FROM_URL` depuis un domaine / préfixe d'URL **vérifié** dans le portail [TT-PHOTO]
- Ratio : **aucune contrainte publiée**.

**Vidéo** [TT-MEDIA] — vérifié le 2026-10-04
- Formats **MP4 (recommandé), WebM, MOV** ; codecs H.264 (recommandé), H.265, VP8, VP9
- **23 à 60 i/s** ; **360 à 4096 px** en hauteur et en largeur
- Durée : « All TikTok creators can post **3-minute** videos, while some have access to post 5-minute or 10-minute videos. The longest video a developer can send via the initialize Upload Video endpoint is **10 minutes**. » → lire `max_video_post_duration_sec` dans `/creator_info/query/` (obligatoire, cf. UX ci-dessous)
- Poids **4 Go max** ; morceaux de 5 à 64 Mo (dernier ≤ 128 Mo), 1 à 1 000 morceaux, envoyés dans l'ordre
- Durée minimale : **non publiée** (NON CONFIRMÉ).

**Texte**
- Vidéo : `title` (= légende) **2 200 « UTF-16 runes »** max ; # et @ reconnus [TT-VIDEO] — vérifié le 2026-10-04
- Photo : `title` **90**, `description` **4 000** UTF-16 runes [TT-PHOTO] — vérifié le 2026-10-04
- Hashtags max : **aucune limite publiée**.

**Limite de publication** [TT-GUIDE] — vérifié le 2026-10-04
- Plafond par créateur : « typically around **15** posts per day / creator account », variable, **partagé entre toutes les apps** qui utilisent Direct Post
- Plafond de créateurs actifs / 24 h par app, fixé d'après l'estimation donnée dans le formulaire d'audit
- Non audité : **5 utilisateurs / 24 h**, comptes **privés**, `SELF_ONLY` uniquement
- **6 requêtes / minute** par jeton utilisateur sur l'endpoint d'init [TT-VIDEO], [TT-PHOTO]
- Brouillons (mode `MEDIA_UPLOAD`) : **5 partages en attente max / 24 h** [TT-PHOTO]
- Erreurs à gérer : `spam_risk_too_many_posts`, `reached_active_user_cap`, `unaudited_client_can_only_post_to_private_accounts` [TT-VIDEO]

**Liens** : non cliquables dans la légende — **NON CONFIRMÉ** (rien sur la doc). ⚠ Interdit en revanche par les règles : ajouter **logo, filigrane, lien ou texte promotionnel** dans le contenu [TT-GUIDE].

**Carrousel (photo)** : jusqu'à **35** images (`photo_images`), une image de couverture désignée [TT-PHOTO] — vérifié le 2026-10-04

**UX OBLIGATOIRE (sinon audit refusé)** [TT-GUIDE] — vérifié le 2026-10-04
- afficher le **pseudo** du compte cible ; bloquer si `creator_info` dit que le compte ne peut plus publier ; vérifier la durée max ;
- confidentialité choisie **manuellement** dans une liste issue de `privacy_level_options`, **sans valeur par défaut** ;
- Commentaires / Duo / Collage : **décochés par défaut**, grisés si désactivés côté créateur (photo : seulement « Commentaires ») ;
- divulgation de contenu commercial (« Votre marque » / « Contenu de marque ») avec les libellés et règles exacts ;
- phrase de consentement avant le bouton : « By posting, you agree to TikTok's Music Usage Confirmation » (+ Branded Content Policy selon le cas) ;
- **aperçu** du contenu, texte et hashtags **modifiables** par l'utilisateur, envoi seulement **après consentement exprès** ;
- prévenir que le traitement prend quelques minutes, et suivre le statut (`publish/status/fetch` ou webhook).

---

## 5. Google Business Profile (posts locaux)

Sources :
- [GBP-REF] https://developers.google.com/my-business/reference/rest/v4/accounts.locations.localPosts — vérifié le 2026-10-04
- [GBP-POSTS] https://developers.google.com/my-business/content/posts-data — vérifié le 2026-10-04 (« Last updated 2026-08-28 »)
- [GBP-MEDIA] https://developers.google.com/my-business/content/upload-photos — vérifié le 2026-10-04
- [GBP-LIMITS] https://developers.google.com/my-business/content/limits — vérifié le 2026-10-04
- [GBP-HELP-PHOTO] https://support.google.com/business/answer/6103862?hl=en — vérifié le 2026-10-04
- [GBP-HELP-POSTS] https://support.google.com/business/answer/7342169?hl=en — vérifié le 2026-10-04

**Images**
- Médias d'un post : **uniquement par URL** (`sourceUrl` est le seul champ pris en charge pour un MediaItem de post) [GBP-REF], [GBP-MEDIA] — vérifié le 2026-10-04
- Aide (photos de la fiche) : **JPG ou PNG**, **10 Ko à 5 Mo**, recommandé **720×720**, minimum **250×250** [GBP-HELP-PHOTO] — vérifié le 2026-10-04. (Appliqué aux posts par prudence ; la doc API ne donne pas de spec propre aux posts.)
- Ratio : **aucune contrainte publiée**.

**Vidéo**
- Aide (vidéos de la fiche) : **≤ 30 s**, **≤ 75 Mo**, **720p ou plus** [GBP-HELP-PHOTO] — vérifié le 2026-10-04
- Vidéo **dans un post via l'API : NON CONFIRMÉ** (les exemples API ne montrent que `PHOTO`).

**Texte**
- `summary` : **aucune longueur max publiée** dans la référence API ni dans l'aide. Le chiffre **1 500 caractères est NON CONFIRMÉ**.
- Types : `STANDARD`, `EVENT`, `OFFER`, `ALERT` [GBP-REF] ; offres et événements exigent un titre et des dates [GBP-HELP-POSTS]
- Un numéro de téléphone dans le texte peut faire rejeter le post [GBP-HELP-POSTS] — vérifié le 2026-10-04
- Les posts de plus de **6 mois sont archivés** sauf plage de dates [GBP-HELP-POSTS] — vérifié le 2026-10-04
- Hôtels : pas de post « offre » [https://support.google.com/business/answer/7213077?hl=en — vérifié le 2026-10-04]

**Limite de publication** [GBP-LIMITS] — vérifié le 2026-10-04
- Aucun plafond « posts/jour » publié.
- **Edits : 10 par minute par fiche** (« cannot be increased ») — qu'un post compte comme « edit » est **NON CONFIRMÉ**.
- Quota par défaut des API : 300 requêtes/min ; **0 QPM = accès pas encore accordé**.

**Liens** : par **bouton d'action** (`callToAction` : URL + type, ex. `ORDER`) ; ignoré pour `OFFER` (l'offre porte `redeemOnlineUrl`) [GBP-REF], [GBP-POSTS] — vérifié le 2026-10-04. Lien cliquable dans le texte : **NON CONFIRMÉ**.

**Carrousel** : `media[]` est une liste, mais **nombre max NON CONFIRMÉ**.

**Avis** : lister, lire, répondre, supprimer une réponse — https://developers.google.com/my-business/content/review-data — vérifié le 2026-10-04 (même accès API).

---

## 6. YouTube (Shorts)

Sources :
- [YT-INSERT] https://developers.google.com/youtube/v3/docs/videos/insert — vérifié le 2026-10-04
- [YT-QUOTA] https://developers.google.com/youtube/v3/determine_quota_cost — vérifié le 2026-10-04
- [YT-REV] https://developers.google.com/youtube/v3/revision_history — vérifié le 2026-10-04
- [YT-VIDEOS] https://developers.google.com/youtube/v3/docs/videos — vérifié le 2026-10-04
- [YT-SHORTS] https://support.google.com/youtube/answer/15424877?hl=en — vérifié le 2026-10-04
- [YT-LINKS] https://support.google.com/youtube/answer/13748639?hl=en — vérifié le 2026-10-04
- [YT-TAGS] https://support.google.com/youtube/answer/6390658?hl=en — vérifié le 2026-10-04
- [YT-FORMATS] https://support.google.com/youtube/troubleshooter/2888402?hl=en — vérifié le 2026-10-04

**Images** : sans objet (les Shorts sont des vidéos).

**Vidéo**
- Short = **carré ou vertical, jusqu'à 3 minutes** (depuis le **15/10/2024** pour les chaînes standard) ; une vidéo plus large (16:9) n'est pas classée Short [YT-SHORTS] — vérifié le 2026-10-04
- API : fichier **256 Go max**, MIME `video/*` ou `application/octet-stream` [YT-INSERT] — vérifié le 2026-10-04
- Formats : .MOV, .MPEG-1, .MPEG-2, .MPEG4, .MP4, .MPG, .AVI, .WMV, .MPEGPS, .FLV, 3GPP, WebM, DNxHR, ProRes, CineForm, HEVC [YT-FORMATS] — vérifié le 2026-10-04
- Durée minimale, résolution recommandée (1080×1920) : **NON CONFIRMÉ**.

**Texte** [YT-VIDEOS] — vérifié le 2026-10-04
- Titre **100 caractères**, description **5 000 octets** (pas caractères), sans `<` ni `>` ; tags 500 caractères au total
- Hashtags : au-delà de **60**, **tous** sont ignorés ; 3 affichés près du titre [YT-TAGS] — vérifié le 2026-10-04

**Limite de publication**
- 01/06/2026 : quotas granulaires ; `videos.insert` a son propre seau [YT-REV] — vérifié le 2026-10-04
- « Projects that enable the YouTube Data API have a default quota allocation of 100 search.list calls, **100 videos.insert calls**, and 10,000 units per day combined for all other endpoints. » [YT-QUOTA] ; `videos.insert` : « 100 calls per day. A call to this method has a quota cost of 1 unit in the Video Uploads quota bucket » [YT-INSERT] — vérifié le 2026-10-04
- ⚠ C'est **par projet Google Cloud**, partagé entre **toutes** les chaînes connectées à l'app, remis à zéro à minuit heure du Pacifique.
- Miniature perso (`thumbnails.set`) : 50 unités dans le seau commun de 10 000 [YT-QUOTA]
- ⚠ La synthèse automatique en tête de [YT-QUOTA] cite encore « 1600 » : elle est périmée, le tableau de la même page dit 100 appels/jour à 1 unité.

**Liens**
- **Shorts : non cliquables** dans la description et les commentaires [YT-LINKS] — vérifié le 2026-10-04
- Vidéo longue : cliquables si la chaîne a les « fonctionnalités avancées » [YT-LINKS], [YT-VIDEOS] — vérifié le 2026-10-04

**Carrousel** : sans objet.

**Confidentialité forcée** : « All videos uploaded via the videos.insert endpoint from **unverified API projects created after 28 July 2020** will be restricted to **private** viewing mode » — audit obligatoire pour lever [YT-INSERT] — vérifié le 2026-10-04

---

## 7. Threads

Sources :
- [TH-OV] https://developers.facebook.com/docs/threads/overview — vérifié le 2026-10-04
- [TH-POSTS] https://developers.facebook.com/docs/threads/posts — vérifié le 2026-10-04
- [TH-TROUBLE] https://developers.facebook.com/docs/threads/troubleshooting — vérifié le 2026-10-04

**Images** [TH-OV], [TH-POSTS] — vérifié le 2026-10-04
- **JPEG et PNG** ; **8 Mo** max ; largeur **320 à 1 440 px** ; ratio « limit **10:1** »
- Interprétation 1:10 → 10:1 (0,1 à 10) : **borne basse NON CONFIRMÉE** (la doc n'écrit que « 10:1 »).

**Vidéo** [TH-OV] — vérifié le 2026-10-04
- MOV ou MP4 ; HEVC ou H.264 ; AAC ; **23 à 60 i/s** ; ratio **0.01:1 à 10:1**
- **300 s (5 min) max** ; **1 Go max**
- Durée minimale : **non publiée**.

**Texte** [TH-POSTS] — vérifié le 2026-10-04
- **500 caractères** ; « Emojis are counted as the number of UTF-8 bytes »
- **1 seul sujet (topic tag) par post** (le premier valide) ; 1 à 50 caractères, sans `.` ni `&`

**Limite de publication** [TH-OV], [TH-TROUBLE] — vérifié le 2026-10-04
- **250 posts / 24 h glissantes** ; 1 000 réponses ; 100 suppressions
- Un conteneur non publié expire au bout de **24 h** ; vérifier son statut 1×/min pendant 5 min max

**Liens** [TH-POSTS] — vérifié le 2026-10-04
- **5 liens max** (URL uniques du texte + `link_attachment` s'il diffère) ; au-delà, échec de la publication depuis le **22/12/2025**
- `link_attachment` (carte d'aperçu) : **posts texte uniquement** ; sans lui, le premier lien du texte devient l'aperçu

**Carrousel** : **2 à 20** éléments (images, vidéos ou mélange) [TH-POSTS] — vérifié le 2026-10-04

---

## 8. Pinterest (API v5)

Sources :
- [PIN-SPEC] https://help.pinterest.com/en/business/article/pinterest-product-specs — vérifié le 2026-10-04
- [PIN-OAS] https://github.com/pinterest/api-description (fichier `v5/openapi.json`, version **5.28.0**, dépôt officiel Pinterest) — vérifié le 2026-10-04 ; référence lisible : https://developers.pinterest.com/docs/api/v5/pins-create
- [PIN-RATE] https://developers.pinterest.com/docs/reference/rate-limits/ — vérifié le 2026-10-04
- [PIN-CONTENT] https://developers.pinterest.com/docs/api-features/content-overview/ — vérifié le 2026-10-04

**Images**
- **.PNG ou .JPEG** ; poids **20 Mo (desktop), 32 Mo (appli)** ; ratio recommandé **2:3 (1000×1500)**, au-delà de 2:3 l'épingle « might get cut off » [PIN-SPEC] — vérifié le 2026-10-04
- API : `content_type` ∈ `image/jpeg`, `image/png` [PIN-OAS] — vérifié le 2026-10-04
- Ratio min/max pour une **image** : **NON CONFIRMÉ** (seule la recommandation 2:3 est écrite) ; le JSON reprend la plage **vidéo** 1:2 → 1.91:1.
- Tout est reconverti en JPEG RGB 8 bits ; Pinterest conseille de téléverser en PNG sRGB [PIN-SPEC]

**Vidéo** [PIN-SPEC] — vérifié le 2026-10-04
- **.MP4, .MOV, .M4V** ; H.264 ou H.265 ; **2 Go max**
- **4 s à 15 min**
- Ratio : entre **1:2 et 1.91:1** ; recommandé 1:1 ou vertical (2:3, 4:5, 9:16)
- API : enregistrement `POST /v5/media`, puis envoi du fichier, puis épingle avec `video_id` [PIN-OAS]

**Texte** [PIN-OAS], [PIN-SPEC] — vérifié le 2026-10-04
- Titre **100**, description **800**, lien **2 048**, texte alternatif **500** caractères
- Hashtags : **aucune limite publiée**

**Limite de publication** [PIN-RATE] — vérifié le 2026-10-04
- Pas de plafond « épingles/jour » publié ; catégorie **`org_write`** (créer/modifier tableaux et épingles) : **Trial 300 requêtes/jour/app** ; **Standard 100 requêtes/min/utilisateur/app**
- Plafonds globaux : Trial 1 000 requêtes/jour ; Standard 100 requêtes/s/utilisateur/app
- Plafonds de compte : 2 000 tableaux, 200 000 épingles [PIN-CONTENT]

**Liens** : lien de destination cliquable via le champ `link` (2 048 car.) [PIN-OAS] — vérifié le 2026-10-04. Lien cliquable dans la description : **NON CONFIRMÉ**.

**Carrousel** : `multiple_image_urls` / `multiple_image_base64` : **2 à 5 images**, chacune avec titre, description et lien propres [PIN-OAS] ; aide : « 2 to 5 images per carousel », ratio 1:1 ou 2:3, 20 Mo/image [PIN-SPEC] — vérifié le 2026-10-04

**Usage** : `POST /pins` est « intended solely for publishing new content created by the user » (pas de curation de contenus tiers) [PIN-OAS] — vérifié le 2026-10-04
