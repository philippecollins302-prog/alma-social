"""Le socle des bancs d'ALMA SOCIAL : une base neuve, une horloge figée, aucun appel sortant.

Chaque banc commence par `import socle` : AVANT toute importation du produit,
il pose un environnement fermé — dossier temporaire, aucune clé, horloge du
processus coupée, courrier en mode essai — puis branche une base SQLite neuve.
Rien ne parle à l'extérieur : le modèle répond « pas de clé » (repli local),
et le transport d'Upload-Post est remplacé par un faux qui refuse tout ce
qu'on ne lui a pas appris.
"""
import datetime as dt
import os
import pathlib
import sys
import tempfile

ICI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent))

_TMP = tempfile.mkdtemp(prefix="alma-social-banc-")
for cle in ("ANTHROPIC_API_KEY", "UPLOAD_POST_API_KEY", "UPLOAD_POST_WEBHOOK_SECRET", "AYRSHARE_API_KEY",
            "SOCIAL_NETTOYAGE_CLE", "SOCIAL_CODE_PDG", "SOCIAL_EMAIL_PDG", "DATABASE_URL", "POSTGRESQL_ADDON_URI",
            "SMTP_HOST", "SOCIAL_CLE_CHIFFREMENT"):
    os.environ.pop(cle, None)
os.environ.update(SOCIAL_DONNEES=_TMP, SOCIAL_FICHIERS=f"{_TMP}/fichiers", SOCIAL_HORLOGE="0",
                  MAIL_TEST_MODE="1", SOCIAL_URL_PUBLIQUE="https://social.exemple.test")

from alma_social import db  # noqa: E402
from alma_social.publieurs import upload_post  # noqa: E402

db.brancher(f"sqlite:///{_TMP}/banc.db")


def _transport_interdit(*a, **k):
    raise AssertionError(f"appel réseau Upload-Post non prévu par le banc : {a[:2]}")


upload_post._http = _transport_interdit

IMAGES = ICI / "images"
_ok, _ko = [], []


def verifier(condition, message: str):
    (_ok if condition else _ko).append(message)
    print(("  ✅ " if condition else "  ❌ ") + message)


def egal(obtenu, attendu, message: str):
    verifier(obtenu == attendu, f"{message} (obtenu : {obtenu!r}" + ("" if obtenu == attendu else f", attendu : {attendu!r}") + ")")


def figer(*morceaux):
    """`figer(2026, 10, 5, 7)` : l'horloge du produit (UTC) s'arrête là."""
    db.figer_horloge(dt.datetime(*morceaux))


def image(nom: str = "chantier", largeur: int = 1600, hauteur: int = 1200, graine: int = 1) -> bytes:
    """Une photo de synthèse nette et bien exposée (des formes, du bruit léger) —
    jamais deux identiques pour deux graines différentes."""
    import io
    import random
    from PIL import Image, ImageDraw, ImageFilter
    r = random.Random(f"{nom}{graine}")
    img = Image.new("RGB", (largeur, hauteur), tuple(r.randint(90, 170) for _ in range(3)))
    d = ImageDraw.Draw(img)
    for _ in range(40):
        x, y = r.randint(0, largeur), r.randint(0, hauteur)
        w, h = r.randint(40, largeur // 3), r.randint(40, hauteur // 3)
        coul = tuple(r.randint(20, 235) for _ in range(3))
        (d.rectangle if r.random() < .5 else d.ellipse)([x, y, x + w, y + h], fill=coul, outline=(10, 10, 10), width=3)
    img = img.filter(ImageFilter.SMOOTH)
    tampon = io.BytesIO()
    img.save(tampon, "JPEG", quality=92)
    return tampon.getvalue()


def fin():
    print(f"\n{len(_ok)} contrôles verts, {len(_ko)} rouges.")
    if _ko:
        print("ROUGES :\n  - " + "\n  - ".join(_ko))
        sys.exit(1)
