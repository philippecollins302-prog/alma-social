"""L'unique porte vers le modèle de langue.

Un seul endroit appelle Claude : la lecture d'image, l'écriture des textes,
le tri des commentaires et les réponses aux avis passent tous par `appeler`.
Les bancs remplacent `ia.CLIENT` par un faux — aucun banc ne parle à
l'extérieur.

Sorties structurées (un schéma Pydantic par usage) : le modèle rend du JSON
valide, jamais du texte à déchiffrer. La « température basse » demandée
n'existe plus comme paramètre sur les modèles actuels ; la constance vient
d'un effort bas, du schéma imposé et d'un prompt versionné (DECISIONS.md).
"""
from __future__ import annotations

import base64
import time

from . import config

try:
    import anthropic
except ImportError:                     # pragma: no cover
    anthropic = None


class ErreurIA(Exception):
    pass


class SansCle(ErreurIA):
    """Aucune clé : chaque appelant a un repli déterministe et le dit."""


CLIENT = None          # remplacé par les bancs ; construit à la demande sinon
APPELS = []            # trace des derniers appels (page santé), sans contenu


def _client():
    global CLIENT
    if CLIENT is not None:
        return CLIENT
    if anthropic is None or not config.cle_anthropic():
        raise SansCle("ANTHROPIC_API_KEY absente")
    CLIENT = anthropic.Anthropic(api_key=config.cle_anthropic(), max_retries=2, timeout=120.0)
    return CLIENT


def disponible() -> bool:
    try:
        _client()
        return True
    except SansCle:
        return False


def image_bloc(octets: bytes, media_type: str = "image/jpeg") -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                       "data": base64.standard_b64encode(octets).decode()}}


def appeler(systeme: str, contenu: list, schema, max_tokens: int = 8000, usage: str = ""):
    """→ (objet Pydantic validé, modèle qui a vraiment répondu).

    Le repli côté serveur (`fallbacks: "default"`) laisse l'API relancer la
    même demande sur un autre modèle si le premier décline ; le modèle
    réellement utilisé est donc relu dans la réponse, pas supposé.
    """
    c = _client()
    debut = time.monotonic()
    try:
        rep = c.beta.messages.parse(
            model=config.MODELE,
            max_tokens=max_tokens,
            system=systeme,
            messages=[{"role": "user", "content": contenu}],
            output_format=schema,
            output_config={"effort": config.EFFORT},
            betas=["server-side-fallback-2026-07-01"],
            extra_body={"fallbacks": "default"},
        )
    except Exception as e:      # erreurs réseau / API : la file de travaux réessaiera
        _tracer(usage, debut, "erreur")
        raise ErreurIA(f"{type(e).__name__}: {e}") from e
    if getattr(rep, "stop_reason", None) == "refusal":
        _tracer(usage, debut, "refus")
        raise ErreurIA("le modèle a décliné la demande")
    if getattr(rep, "stop_reason", None) == "max_tokens":
        _tracer(usage, debut, "tronque")
        raise ErreurIA("réponse tronquée (max_tokens)")
    obj = getattr(rep, "parsed_output", None)
    if obj is None:
        _tracer(usage, debut, "vide")
        raise ErreurIA("réponse sans contenu structuré")
    _tracer(usage, debut, "ok")
    return obj, getattr(rep, "model", config.MODELE)


def _tracer(usage, debut, issue):
    APPELS.append({"usage": usage, "secondes": round(time.monotonic() - debut, 2), "issue": issue})
    del APPELS[:-50]
