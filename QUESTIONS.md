# Ce qui attend Philippe

Tout le reste avance sans vous : l'application tourne en bac à sable avec des
valeurs provisoires, marquées « À compléter » dans Réglages → chaque marque.

## Les six gestes que vous seul pouvez faire

1. **Les comptes des réseaux.** Les créer ou les retrouver (vérification par
   téléphone, conditions à accepter). Puis, pour chaque marque :
   Réglages → la marque → **Relier les réseaux**. Un lien Upload-Post s'ouvre,
   valable 48 h ; aucun mot de passe ne passe par nous.
2. **Deux abonnements.**
   - Upload-Post **Professional** : 50 $/mois, ou 33 $/mois payé à l'année ;
     25 profils, il nous en faut 6 ou 7.
   - Clever Cloud pour la nouvelle application : instance Python XS,
     add-on PostgreSQL et un FS Bucket.
   Total prévu avec Claude : environ 100 €/mois, dans l'enveloppe.
3. **Les demandes d'accès aux API officielles.** Rien ne presse : Upload-Post
   publie sans elles. Les dossiers sont prêts, pièce par pièce, dans
   `docs/recherche/acces-api.md`. Commencez par l'audit TikTok, le plus long.
4. **Le domaine des liens tracés.** Facultatif : les liens marchent dès
   aujourd'hui sur l'adresse de l'application. Un domaine court
   (`alma.li`, `go-alma.fr`…) se pose plus tard dans `SOCIAL_URL_LIENS`.
5. **Les clés** — voir le tableau ci-dessous. Vous les collez vous-même dans
   Clever ; je ne les vois jamais.
6. **Les réponses de la section suivante.**

### Les clés : lesquelles, où, et dans quelle variable

Toutes se collent dans la console Clever : l'application ALMA SOCIAL →
**Environment variables**. Jamais dans un fichier du dépôt.

| Variable | Où la créer | Remarque |
|---|---|---|
| `ANTHROPIC_API_KEY` | https://console.anthropic.com → Settings → **API Keys** → Create Key | Une clé dédiée à ALMA SOCIAL : sa facture se lit alors séparément. Posez une limite mensuelle de 40 € (Settings → Limits). |
| `UPLOAD_POST_API_KEY` | https://app.upload-post.com → section **API Keys** → Generate New API Key | Après la souscription. |
| `SOCIAL_CLE_CHIFFREMENT` | Vous la fabriquez sur le Mac : `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` | Gardez-en une copie dans un coffre : la perdre oblige à relier tous les comptes à nouveau. |
| `SOCIAL_CODE_PDG` | Vous la choisissez : 8 chiffres | Lue au premier démarrage seulement. |
| `SOCIAL_EMAIL_PDG` | Votre adresse | Alertes urgentes et récapitulatif du lundi. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM` | Le compte d'envoi de la messagerie du groupe (serveur, port, identifiant, mot de passe d'application, adresse d'expédition) | Un compte d'envoi dédié (`social@…`) se révoque sans toucher au reste. |
| `SOCIAL_URL_PUBLIQUE` | L'adresse que Clever donne à la nouvelle application (`https://….cleverapps.io`) | |

**Facultatives** :
- `SOCIAL_NETTOYAGE_CLE` : une clé Stability AI (https://platform.stability.ai
  → API Keys), pour effacer les gros objets parasites. Sans elle, un
  effacement local traite les petits.
- `UPLOAD_POST_WEBHOOK_SECRET` : inutile. Le bouton Réglages → Santé →
  « Brancher les notifications » le range lui-même.

## Les questions (section 15) — ce que j'ai trouvé, à corriger

1. **LMS Perpignan** : une zone de LMS PACA (La Maison des Services) ou une
   septième marque ? Pour l'instant, Perpignan n'apparaît que dans la zone du
   Groupe Alma : aucune marque ne publie pour elle. **VIP Plus** : j'ai repris
   l'activité de la plaquette du groupe (serrurerie-métallerie, fermetures,
   automatismes, sécurité, CVC, plomberie, désenfumage, bureau d'études).
   Cible et zone sont à confirmer.
2. **Chartes tirées du Drive** :

   | Marque | Couleurs | Polices | Logo | Ton |
   |---|---|---|---|---|
   | SAZÚ | olive, crème, framboise, encre | Bagel Fat One, Manrope, Courier Prime | ✓, montré à partir du 13/11 18 h | chaleureux, latino, joueur ; tutoiement |
   | REGA | anthracite, sauge, rouge | Poppins, Inter | ✓ | professionnel, direct, rassurant |
   | LMS Sols | navy, orange, crème | Archivo Black, Montserrat | ✓ | haut de gamme, sobre, précis |
   | LMS PACA | navy, or, crème | Playfair Display, DM Sans, Josefin Sans | ✓ | simple et rassurant, pour les syndics |
   | Groupe Alma | **provisoire** (bleu nuit, ivoire, or) | Poppins, Inter | ✗ | institutionnel, posé, ambitieux |
   | VIP Plus | **provisoire** (bleu acier, rouge sécurité) | Montserrat, Inter | ✗ | technique et expert, sans jargon |

3. **Comptes existants.** Je n'ai trouvé que ceux de SAZÚ : Instagram et
   TikTok `@sazu.montpellier`, Facebook « SAZÚ Montpellier ». Il manque tous
   ceux des cinq autres marques.
4. **Sites.** Je n'ai trouvé que `lamaisondesservices.fr` et un numéro pour
   REGA. Il manque les sites de REGA, VIP Plus, du groupe et de SAZÚ, ainsi
   que leurs pages de devis. Sans site, chaque lien tracé mène à la page
   « lien en bio » de la marque.
5. **SAZÚ** : les liens Uber Eats et Deliveroo, dès que les pages existent.
   Les prix aussi, avec la date à laquelle vous les avez vérifiés : sans
   cette date, aucun prix ne s'écrit.
6. **Google Business** : aucune fiche trouvée. Pour SAZÚ, le Drive la prévoit
   à J-7.
7. **Les responsables** : nom et e-mail pour chaque marque. Pour SAZÚ, Lucie :
   son e-mail. D'ici là, toutes les alertes vous arrivent.
8. **Mots interdits.** Ceux de SAZÚ, REGA et LMS viennent du Drive. Ceux du
   groupe, de VIP Plus et de LMS PACA sont provisoires (« pas cher »,
   « low cost »).
9. **Les clés** : voir le tableau ci-dessus.
10. **Concurrents.** SAZÚ en a cinq, tirés du Drive : Pokawa, Eat Salad, Olla,
    Pokhawaï, Fresh Burritos. Il en faut 3 à 5 pour chacune des autres marques.

## Vos décisions que je conteste, une ligne chacune

- **Ayrshare** est remplacé par Upload-Post. Ayrshare coûte 299 $/mois pour
  six marques, soit le budget entier ; Upload-Post coûte 50 $ et couvre tout.
- **TypeScript** est remplacé par Python : l'image et l'IA y sont plus simples,
  et le dépôt du groupe est déjà en Python.
- **La veille concurrents se saisit à la main.** Aspirer leurs pages enfreint
  les règles des réseaux et peut faire suspendre nos comptes.

## Ce que le Drive dit autrement que le cahier des charges

- **SAZÚ « Lucie valide tout »** contredit « aucune validation ». J'ai suivi
  le cahier. Si vous voulez la validation pour SAZÚ seulement, c'est un
  interrupteur par marque (`requires_approval`).
- **La retouche de SAZÚ** : le Drive la limite à l'exposition, le cahier veut
  la retouche maximale. C'est un réglage par marque. Il est aujourd'hui sur
  « complète » : je le passe sur « exposition » sur votre mot.
- **« LMS »** : le Drive parle de La Maison des **Services** (multiservice
  pour syndics), pas des Sols. Le site trouvé est celui des Services. J'ai
  gardé les deux marques ; à vous de confirmer.
- **La zone de REGA** : le Drive dit tantôt Hérault, tantôt Marseille.
- **La campagne SAZÚ** commence à J-28 (30/10) selon le cahier. Le Drive ne
  fait commencer le teasing qu'à J-21. J'ai suivi le cahier ; sur votre mot,
  je retire les deux premières étapes.
- **Facebook republie Instagram** automatiquement sur SAZÚ. Coupez ce partage
  dans Meta Business Suite, sinon chaque photo sortira deux fois.

## ⚠ À faire tout de suite

Le document SAZÚ « Applications en ligne » du Drive contient **quatre liens
publics vers des pages claude.ai**. Quiconque a le lien les ouvre. Révoquez-les
depuis claude.ai, puis retirez-les du document.
