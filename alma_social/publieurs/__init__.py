"""Choisir le bon Publisher pour un compte — le seul endroit qui sache qu'il y en a plusieurs."""
from __future__ import annotations

import os

from .. import journal, securite
from .bac_a_sable import BacASable
from .base import Contraintes, NonBranche, Publisher  # noqa: F401
from .direct import DIRECTS, DirectNonBranche


def agregateur() -> str:
    return (os.getenv("SOCIAL_AGREGATEUR") or "upload_post").strip().lower()


def pour(compte: dict, contraintes: Contraintes, forcer_reel: bool = False) -> Publisher:
    """Le bac à sable l'emporte sur tout : quand il est ouvert, rien ne sort,
    quel que soit le réglage du compte."""
    plateforme = compte["platform"]
    if journal.bac_a_sable() and not forcer_reel:
        return BacASable(plateforme, contraintes)
    if compte.get("mode") == "direct":
        cls = DIRECTS.get(plateforme, DirectNonBranche)
        return cls(plateforme, contraintes, securite.dechiffrer(compte.get("tokens_enc", "")))
    profil = securite.dechiffrer(compte.get("external_profile_enc", ""))
    if agregateur() == "ayrshare":
        from .ayrshare import Ayrshare
        pub = Ayrshare(plateforme, contraintes, profil)
    else:
        from .upload_post import UploadPost
        pub = UploadPost(plateforme, contraintes, profil)
    pub.options = dict(compte.get("options") or {})
    return pub
