# Audit de la v1 — 05/10/2026

Ce qui tient, ce qui ne suffit pas, ce que la v3 a changé.

## Ce qui tient (gardé tel quel)

- **Le dépôt** : file du téléphone (IndexedDB, référence unique), aucune photo perdue, aucun doublon.
- **Les garde-fous de langage** : chiffres sourcés seulement, superlatifs, allégations de santé, prix vérifiés.
- **Le journal** chaîné et non modifiable (la base refuse UPDATE et DELETE).
- **La porte `Publisher`** (bac à sable, Upload-Post, Ayrshare, direct) et le bac à sable par défaut.
- **L'arrêt général, la pause 48 h, le retrait partout, le floutage.**
- **Le déploiement** : une poussée sur `main` = bancs puis mise en ligne vérifiée.

## Ce qui ne suffisait pas

| Défaut v1 | Conséquence | v3 |
|---|---|---|
| Un seul modèle pour tout | trop cher pour le tri, pas assez fort pour juger | un modèle par agent, réglable |
| Aucun coût suivi | dépense invisible | `agent_runs`, coût par agent, plafond mensuel |
| Pas de stratégie de marque | des textes « corrects », interchangeables | plateforme de marque versionnée, lue par tous les agents |
| Le garde-fou disait ce qui est interdit, rien ne disait ce qui est médiocre | publication « correcte » = publiée | le Critique, seuil 80, trois tours, retour banque |
| Gabarit sans modèle ouvrant sur « Aujourd'hui : … » | accroche creuse | ouvre sur ce que montre la photo, ou une accroche de la marque |
| « lien en bio » refusé chez SAZÚ (mot interdit « bio ») | légende Instagram SAZÚ jamais publiée sans modèle | corrigé |
| Les corrections humaines ne servaient à rien | mêmes fautes répétées | la voix apprend (3 corrections = 1 règle) |
| Aucune mémoire | pas d'apprentissage | carnet d'apprentissage avec preuve |
| Le terrain ne pouvait rien dire au dépôt | textes sans contexte | une phrase dictée, transmise au rédacteur |
| Écran : 5 onglets d'outil d'administration | « nul » (Philippe) | 9 écrans, Aujourd'hui, Boîte, Demander, Marques, Santé |

## Ce qui reste à faire (jalons suivants)

Studio SAZÚ (rééclairage, photos → Reel, carrousels), séquence d'ouverture simulée (J2) ;
créneaux 80/20, evergreen, Coach terrain (J3) ; mesure jusqu'au chiffre d'affaires (J4) ;
relation et réputation (J5) ; amplification et MCP (J6).
