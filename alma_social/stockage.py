"""Les fichiers : l'original intact, les déclinaisons à côté.

Adressage par empreinte : un original se range sous son sha256, il n'est
jamais réécrit ni écrasé, et deux dépôts du même fichier ne coûtent qu'une
copie. Les déclinaisons portent un jeton public aléatoire : c'est l'adresse
que l'agrégateur vient lire pour publier, et elle ne se devine pas.
"""
from __future__ import annotations

import hashlib
import pathlib
import secrets

from . import config


def racine() -> pathlib.Path:
    return config.dossier_fichiers()


def verifier_le_montage(dossier: pathlib.Path | None = None, app: pathlib.Path | None = None,
                        env: dict | None = None) -> str:
    """REFUSER DE DÉMARRER SI LE DISQUE DES PHOTOS N'EST PAS MONTÉ.

    Un FS Bucket qui ne se monte pas ne fait AUCUNE erreur — le dossier existe
    quand même, sur le disque éphémère de l'instance. Ici, les originaux
    déposés y partiraient, l'écran les montrerait, et le déploiement suivant
    les effacerait : une panne de montage devenue perte de photos, en silence.

    On vérifie le MONTAGE, pas la vacuité (un bucket neuf est vide) : un disque
    monté n'a pas le numéro de périphérique de l'application. On ne parle que
    là où il y a un disque à monter (`CC_FS_BUCKET`). Un dossier illisible EST
    la panne. `SOCIAL_DISQUE_SANS_GARDE=1` désarme la garde, sans redéployer.
    → '' si tout va bien, sinon le message (et l'appelant refuse de démarrer)."""
    import os
    env = os.environ if env is None else env
    if (env.get("SOCIAL_DISQUE_SANS_GARDE") or "").strip() == "1" or not (env.get("CC_FS_BUCKET") or "").strip():
        return ""
    dossier, app = dossier or racine(), app or config.RACINE
    try:
        monte = os.stat(dossier).st_dev != os.stat(app).st_dev
    except OSError as e:
        return f"dossier des photos illisible ({dossier}) : {e}"
    if monte:
        return ""
    return (f"le dossier des photos ({dossier}) est sur le disque de l'application, pas sur le FS Bucket : "
            "le montage a échoué ou SOCIAL_FICHIERS ne pointe pas sur CC_FS_BUCKET. Rien ne démarre, pour ne pas "
            "ranger des photos sur un disque que le prochain déploiement effacera.")


def ranger_original(octets: bytes, extension: str) -> tuple:
    """→ (chemin relatif, sha256). Écrit une seule fois."""
    sha = hashlib.sha256(octets).hexdigest()
    ext = (extension or "jpg").lower().lstrip(".")
    if ext not in ("jpg", "jpeg", "png", "heic", "heif", "webp"):
        ext = "jpg"
    rel = pathlib.Path("originaux") / sha[:2] / f"{sha}.{ext}"
    chemin = racine() / rel
    if not chemin.exists():
        chemin.parent.mkdir(parents=True, exist_ok=True)
        tmp = chemin.with_suffix(".tmp")
        tmp.write_bytes(octets)
        tmp.replace(chemin)
    return str(rel), sha


def chemin(rel: str) -> pathlib.Path:
    p = (racine() / rel).resolve()
    if racine().resolve() not in p.parents:
        raise ValueError("chemin hors du stockage")
    return p


def chemin_declinaison(asset_id: int, fmt: str, cle: str, video: bool = False) -> str:
    nom = fmt.replace(":", "x")
    return str(pathlib.Path("declinaisons") / str(asset_id) / f"{nom}-{cle[:12]}.{'mp4' if video else 'jpg'}")


def jeton_public() -> str:
    return secrets.token_urlsafe(18)


def cle_cache(*morceaux) -> str:
    """Ne jamais retraiter deux fois la même image : la clé dit tout ce qui
    change le résultat (original, format, charte, version des traitements, flou)."""
    return hashlib.sha256("|".join(str(m) for m in morceaux).encode()).hexdigest()
