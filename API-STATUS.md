# API-STATUS — réseau par réseau

**Dernière vérification de toutes les pages citées : 2026-10-04.** Les
contraintes de chaque réseau (formats, ratios, longueurs, hashtags, plafonds
par jour) vivent en base, dans `platform_constraints`, chacune avec sa date de
vérification ; leur source est `graines/contraintes.json`, et une graine plus
récente met la base à jour au démarrage.

## Phase 1 — par l'agrégateur (ce qui publiera dès la première semaine)

Upload-Post publie avec **ses propres applications**, déjà validées par chaque
réseau. Il n'y a donc aucune demande d'accès à déposer pour la phase 1 : il
suffit de souscrire et de relier les comptes.

| | État au 2026-10-04 | Ce qui débloque |
|---|---|---|
| Abonnement Upload-Post (Professional, 50 $/mois, 25 profils) | **non souscrit** | Philippe : souscrire, puis créer la clé d'API |
| `UPLOAD_POST_API_KEY` | **absente** — l'application tourne en bac à sable | Philippe : la coller dans Clever |
| Profils `alma-<marque>` | créés d'office au premier « Relier les réseaux » | — |
| Comptes reliés | **aucun** | chaque responsable : Réglages → la marque → Relier les réseaux |
| Webhook | non branché (facultatif) | PDG : Réglages → Santé → Brancher les notifications |

Documentation consultée : https://docs.upload-post.com/llms-full.txt, https://docs.upload-post.com/api/webhooks,
https://docs.upload-post.com/api/google-business-reviews, https://docs.upload-post.com/guides/post-to-linkedin-api
— notes complètes dans `docs/recherche/upload-post-api.md`.

Formats envoyés par le studio : carrousel = plusieurs `photos[]` sur `/upload_photos`, dans
l'ordre (Instagram 10 vues au plus, LinkedIn 20) ; Reel = `/upload` avec `video` et, pour
Instagram, `media_type=REELS`. Les publieurs Ayrshare et Direct n'envoient encore que la
première vue d'un carrousel.

| Réseau | Par Upload-Post | Réglage à poser une fois (Réglages → Comptes) | Limite connue |
|---|---|---|---|
| Instagram (feed, Reels, Stories) | oui | — | 50 publications/jour/compte ; pas de retrait par API |
| Facebook (page) | oui | identifiant de la page | 25/jour ; **couper le partage automatique Instagram → Facebook**, sinon chaque photo sort deux fois |
| LinkedIn page | oui | identifiant de la page (**obligatoire** : sinon refus, plutôt que de publier sur un profil personnel) | 150/jour |
| LinkedIn profil personnel | oui | — | celui de qui ? (question ouverte) |
| TikTok | oui | — | 15/jour ; pas de retrait par API |
| Google Business Profile | oui (posts, réponses aux avis) | identifiant de l'établissement | pas de statistiques par publication |
| YouTube Shorts | oui | — | 10/jour |
| Threads | oui | — | pas de retrait par API ; aucune marque ne l'a activé |
| Pinterest | oui | identifiant du tableau (**obligatoire**) | 20/jour |

## Phase 2 — les API officielles (en tâche de fond, derrière la même interface)

**Aucune demande n'est déposée** : chacune se fait au nom de l'entreprise, avec
l'identité de Philippe. Les dossiers complets (pièces, textes, captures à
tourner) sont prêts dans `docs/recherche/acces-api.md`. La bascule d'un
réseau se fait par un réglage en base (`accounts.mode = 'direct'`), sans
toucher au reste.

| Réseau | Ce qu'il faut demander | État | Bloquant tant que non accordé | Documentation officielle (lue le 2026-10-04) |
|---|---|---|---|---|
| Instagram | Accès standard suffisant **si l'app est créée dans le Business Manager du groupe** et ne sert que ses comptes ; sinon Advanced Access + App Review + Business Verification | **non déposé** | comptes tiers | https://developers.facebook.com/docs/instagram-platform/overview · https://developers.facebook.com/docs/instagram-platform/app-review |
| Facebook (page) | `pages_manage_posts`, `pages_read_engagement`, `pages_show_list` — même règle | **non déposé** | idem | https://developers.facebook.com/docs/pages-api/posts |
| Threads | cas d'usage Threads, App Review de `threads_basic` + `threads_content_publish` | **non déposé** (dernier : aucune marque ne l'utilise) | seuls des testeurs invités | https://developers.facebook.com/docs/threads/get-started |
| LinkedIn profil | Share on LinkedIn (`w_member_social`) — **libre-service, sans revue** | **non déposé** | — | https://learn.microsoft.com/en-us/linkedin/shared/authentication/getting-access |
| LinkedIn page | Community Management API : palier Development, puis Standard (démo vidéo) | **non déposé** | 500 appels/app/jour en Development | https://learn.microsoft.com/en-us/linkedin/marketing/community-management-app-review |
| TikTok | revue de l'app puis **audit** Content Posting API | **non déposé** | publications en `SELF_ONLY` (invisibles) avant l'audit | https://developers.tiktok.com/doc/content-posting-api-get-started |
| Google Business Profile | « Application for Basic API Access » | **non déposé** | quota à 0 | https://developers.google.com/my-business/content/prereqs · https://support.google.com/business/contact/api_default |
| YouTube | audit et extension de quota ; vérification OAuth du scope sensible | **non déposé** | vidéos forcées en privé ; 100 envois/jour/projet | https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits |
| Pinterest | accès Trial, puis Standard (vidéo) | **non déposé** | en Trial, épingles visibles par leur seul créateur | https://developers.pinterest.com/docs/key-concepts/access-tiers/ |

**Ordre conseillé** (du plus long au plus court) : TikTok (audit), LinkedIn
page (Community Management), Google Business Profile, Meta, YouTube,
Pinterest, Threads. Tant que l'agrégateur publie, aucun de ces délais ne
retarde la mise en service.
