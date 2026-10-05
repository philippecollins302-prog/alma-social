"""Réglages lus dans l'environnement — et nulle part ailleurs.

Aucune clé, aucun jeton, aucun identifiant n'est écrit dans le code ni dans le
dépôt : tout arrive par des variables d'environnement (voir `.env.example`,
qui n'a que des noms, jamais de valeurs). Une valeur vide vaut une valeur
absente : un `ANTHROPIC_API_KEY=` collé sans rien derrière ne doit pas faire
croire qu'une clé existe.
"""
from __future__ import annotations

import os
import pathlib

RACINE = pathlib.Path(__file__).resolve().parent.parent      # la racine du projet
STATIQUES = RACINE / "static"
GRAINES = RACINE / "graines"


def _env(nom: str, defaut: str = "") -> str:
    v = os.getenv(nom, "")
    return v.strip() if v and v.strip() else defaut


def _env_bool(nom: str, defaut: bool) -> bool:
    v = _env(nom)
    if not v:
        return defaut
    return v.lower() in ("1", "oui", "true", "yes", "on")


def url_base_de_donnees() -> str:
    """PostgreSQL en production (add-on Clever), SQLite sur un poste.

    Clever pose `POSTGRESQL_ADDON_URI` sous la forme `postgresql://…` ;
    SQLAlchemy veut savoir quel pilote prendre : on lui dit psycopg (v3).
    """
    url = _env("DATABASE_URL") or _env("POSTGRESQL_ADDON_URI")
    if not url:
        dossier = pathlib.Path(_env("SOCIAL_DONNEES", str(RACINE / "donnees")))
        dossier.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{dossier / 'social.db'}"
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def dossier_fichiers() -> pathlib.Path:
    """Les originaux et les déclinaisons. En production : un FS Bucket monté.

    Des fichiers écrits une fois et jamais réécrits — le disque réseau ne pose
    pas ici le problème qu'il pose à une base SQLite (un seul écrivain, aucun
    verrou à traverser le réseau).
    """
    d = pathlib.Path(_env("SOCIAL_FICHIERS", str(RACINE / "donnees" / "fichiers")))
    if not d.is_absolute():
        d = RACINE / d          # relatif à la racine du projet, quel que soit le dossier de lancement
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Le modèle de langue ──────────────────────────────────────────────────
# Un seul réglage, lisible dans l'environnement. Les textes générés sont
# stockés avec le modèle ET la version du prompt qui les ont produits.
MODELE = _env("SOCIAL_MODELE", "claude-opus-5-5")     # le niveau « fort » (agents.py)
EFFORT = _env("SOCIAL_EFFORT", "low")          # la constance avant l'inspiration


def cle_anthropic() -> str:
    return _env("ANTHROPIC_API_KEY")


def cle_upload_post() -> str:
    """L'agrégateur retenu (voir DECISIONS.md) : une clé pour les six marques,
    un profil Upload-Post par marque."""
    return _env("UPLOAD_POST_API_KEY")


def secret_webhook_upload_post() -> str:
    """Le secret `whsec_…` qui signe les notifications d'Upload-Post."""
    return _env("UPLOAD_POST_WEBHOOK_SECRET")


def cle_ayrshare() -> str:
    return _env("AYRSHARE_API_KEY")


def cle_nettoyage() -> str:
    """Le service d'effacement d'objets parasites (seule étape d'IA payante
    de la retouche). Absent : nettoyage local pour les petits objets."""
    return _env("SOCIAL_NETTOYAGE_CLE")


def cle_chiffrement() -> str:
    """Chiffre au repos les jetons des réseaux (Fernet)."""
    return _env("SOCIAL_CLE_CHIFFREMENT")


def code_pdg_initial() -> str:
    return _env("SOCIAL_CODE_PDG")


def email_pdg() -> str:
    """Où partent le récapitulatif du lundi et les alertes urgentes du PDG.
    Dans l'environnement, jamais dans le dépôt."""
    return _env("SOCIAL_EMAIL_PDG")


def url_publique() -> str:
    """L'adresse où l'application répond — sert aux liens tracés et aux
    images que l'agrégateur vient chercher. TODO : le domaine définitif."""
    return _env("SOCIAL_URL_PUBLIQUE", "http://127.0.0.1:8002").rstrip("/")


def url_liens() -> str:
    """Le domaine du raccourcisseur (`go.<domaine>`). Tant qu'il n'est pas
    acheté, les liens passent par l'application elle-même, sous /go/."""
    v = _env("SOCIAL_URL_LIENS")
    return v.rstrip("/") if v else url_publique() + "/go"


def horloge_active() -> bool:
    """La file de travaux et le planificateur tournent dans le processus web.
    0 dans les bancs, qui appellent les fonctions eux-mêmes."""
    return _env_bool("SOCIAL_HORLOGE", True)


def heberge() -> bool:
    """Sur un hébergeur : Clever Cloud pose `INSTANCE_ID` et `APP_ID` sur chaque
    instance ; `SOCIAL_PRODUCTION=1` le déclare ailleurs."""
    return bool(_env("INSTANCE_ID") or _env("APP_ID")) or _env_bool("SOCIAL_PRODUCTION", False)


def env_dev() -> bool:
    """Le poste de développement : une base SQLite ET aucun hébergeur. La base
    seule ne suffit pas — une production lancée sans PostgreSQL recevrait
    sinon les codes d'essai et une clé de chiffrement de secours."""
    return url_base_de_donnees().startswith("sqlite") and not heberge()


SMTP = {
    "hote": _env("SMTP_HOST"),
    "port": int(_env("SMTP_PORT", "587")),
    "utilisateur": _env("SMTP_USER"),
    "mot_de_passe": _env("SMTP_PASS"),
    "expediteur": _env("SMTP_FROM", "ALMA SOCIAL <noreply@example.invalid>"),  # TODO
}


def courrier_en_test() -> bool:
    """Tant que ce n'est pas explicitement 0, aucun courrier ne part."""
    return _env_bool("MAIL_TEST_MODE", True)


FUSEAU = "Europe/Paris"
