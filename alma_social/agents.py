"""L'équipe d'agents — qui fait quoi, avec quel modèle, sous quelles consignes.

Chaque agent a un rôle, un NIVEAU de modèle, une version de consignes, et
ses critères de réussite. Le niveau se règle en base, agent par agent
(réglage `agents.modeles`), sans redéployer : le jour où le Critique doit
passer sur un modèle plus fort, c'est un geste dans Réglages, pas un commit.

Les trois niveaux suivent le prompt maître (§ 6) : le plus capable pour ce
qui se lit une fois et engage (Stratège, Critique, Analyste), un modèle
rapide pour le volume (Rédacteurs, Community manager), un petit modèle pour
le tri en masse. Les identifiants ont été relus le 05/10/2026 dans la
documentation du SDK ; ils se changent par l'environnement.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import config

NIVEAUX = {
    "fort": config._env("SOCIAL_MODELE_FORT", config._env("SOCIAL_MODELE", "claude-opus-5-5")),
    "rapide": config._env("SOCIAL_MODELE_RAPIDE", "claude-sonnet-5-5"),
    "tri": config._env("SOCIAL_MODELE_TRI", "claude-haiku-4-5"),
}

# Prix publics en dollars par million de jetons (entrée, sortie), relus le
# 05/10/2026. Lecture du cache ×0,1 ; écriture ×1,25. Un modèle inconnu est
# compté au prix du plus cher : on surestime, on ne sous-estime jamais.
PRIX = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
}
PRIX_INCONNU = (4.0, 20.0)


@dataclass(frozen=True)
class Agent:
    cle: str
    nom: str
    role: str
    niveau: str
    consignes: str          # version des consignes — change = repasser le jeu d'or
    effort: str = "low"     # la constance avant l'inspiration
    reussite: str = ""


EQUIPE = {a.cle: a for a in [
    Agent("stratege", "Le Stratège", "Plateforme de marque, ligne éditoriale, plan du mois", "fort",
          "stratege-v1", "medium", "un plan que Philippe valide sans le réécrire"),
    Agent("da", "Le Directeur artistique", "Format, cadrage, habillage, couverture", "rapide", "da-v1",
          reussite="aucun visuel hors charte"),
    Agent("monteur", "Le Monteur", "Reels, TikTok, Shorts : plans, rythme, sous-titres", "rapide", "monteur-v1",
          reussite="une accroche visuelle dans la première seconde"),
    Agent("redacteur", "Les Rédacteurs", "Un texte par réseau, chacun natif", "rapide", "redaction-v2",
          reussite="note du Critique ≥ 80 au premier tour"),
    Agent("critique", "Le Critique", "Note chaque publication sur 100 avant envoi", "fort", "critique-v1",
          reussite="un taux de refus qui ne tombe pas à zéro"),
    Agent("garde_fou", "Le Garde-fou", "Mots interdits, chiffres, droit, règles des plateformes", "tri",
          "garde-v1", reussite="zéro publication retirée après coup"),
    Agent("lecteur", "Le Lecteur d'images", "Sujet, qualité, texte visible, visages, quarantaine", "rapide",
          "vision-v1"),
    Agent("cm", "Le Community manager", "Classe, répond, qualifie, alerte", "rapide", "relation-v1",
          reussite="première réponse en moins de 5 minutes"),
    Agent("reputation", "Le Gardien de réputation", "Avis : demande, réponse, analyse", "rapide", "avis-v1"),
    Agent("analyste", "L'Analyste", "Résultats, carnet d'apprentissage, note du lundi", "fort", "analyste-v1",
          "medium"),
    Agent("veilleur", "Le Veilleur", "Tendances, actualité locale, concurrents, mentions", "tri", "veille-v1"),
    Agent("media", "Le Média acheteur", "Boosts et pub livraison, dans l'enveloppe", "fort", "media-v1",
          reussite="zéro euro dépensé hors enveloppe"),
    Agent("coach", "Le Coach terrain", "Briefs de prise de vue", "rapide", "coach-v1"),
    Agent("assistant", "Demander", "Répond avec les données et agit en l'annonçant", "fort", "demander-v1",
          "medium"),
]}

# Les anciens usages de la v1 → l'agent qui les porte désormais.
USAGES = {"vision": "lecteur", "redaction": "redacteur", "relation": "cm", "avis": "reputation"}


def agent(cle: str) -> Agent:
    cle = USAGES.get(cle, cle)
    return EQUIPE.get(cle) or Agent(cle or "inconnu", cle or "inconnu", "", "rapide", "v0")


def modele(cle: str) -> str:
    """Le modèle de l'agent : réglage en base d'abord, niveau sinon."""
    from . import journal
    a = agent(cle)
    regle = (journal.lire("agents.modeles") or {}).get(a.cle)
    if regle in NIVEAUX:
        return NIVEAUX[regle]
    if isinstance(regle, str) and regle.startswith("claude-"):
        return regle
    return NIVEAUX.get(a.niveau, NIVEAUX["rapide"])


def cout_usd(modele_id: str, entree: int, sortie: int, cache_lu: int = 0, cache_ecrit: int = 0) -> float:
    pe, ps = next((p for k, p in PRIX.items() if modele_id.startswith(k)), PRIX_INCONNU)
    return round((entree * pe + sortie * ps + cache_lu * pe * 0.1 + cache_ecrit * pe * 1.25) / 1e6, 6)


def tableau() -> list:
    """Pour l'écran Santé et Réglages : l'équipe, son modèle, ses consignes."""
    return [{"cle": a.cle, "nom": a.nom, "role": a.role, "niveau": a.niveau, "modele": modele(a.cle),
             "consignes": a.consignes, "reussite": a.reussite} for a in EQUIPE.values()]
