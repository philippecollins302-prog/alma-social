"""Effacer les objets parasites — la seule retouche qui justifie un service d'IA.

Deux nettoyeurs derrière la même porte :
- `NettoyeurLocal` : OpenCV (inpainting), gratuit et instantané, honnête sur les
  PETITS objets (un mégot, un câble, un gobelet) ; il refuse les grands, qu'il
  ferait baver.
- `NettoyeurDistant` : un service d'effacement par masque, si une clé est posée
  (`SOCIAL_NETTOYAGE_CLE`, service choisi dans DECISIONS.md).

Les boîtes viennent de la lecture d'image (`parasites`). Le résultat est mis en
cache par la déclinaison : une image n'est jamais nettoyée deux fois.
"""
from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image

from . import config

AIRE_MAX_LOCALE = 0.035     # au-delà de 3,5 % de l'image, le local bave


def masque(taille, boites, marge=0.12) -> Image.Image:
    W, H = taille
    m = Image.new("L", taille, 0)
    a = np.zeros((H, W), np.uint8)
    for b in boites:
        x0, y0, x1, y1 = b
        mx, my = (x1 - x0) * marge, (y1 - y0) * marge
        a[max(0, int((y0 - my) * H)):min(H, int((y1 + my) * H)),
          max(0, int((x0 - mx) * W)):min(W, int((x1 + mx) * W))] = 255
    m.paste(Image.fromarray(a))
    return m


class NettoyeurLocal:
    nom = "local-opencv"

    def nettoyer(self, img: Image.Image, parasites: list):
        faits, laisses = [], []
        boites = []
        for p in parasites:
            x0, y0, x1, y1 = p["box"]
            if (x1 - x0) * (y1 - y0) <= AIRE_MAX_LOCALE:
                boites.append(p["box"])
                faits.append(p.get("label", "objet"))
            else:
                laisses.append(p.get("label", "objet"))
        if not boites:
            return img, faits, laisses
        m = np.asarray(masque(img.size, boites))
        out = cv2.inpaint(np.asarray(img), m, 7, cv2.INPAINT_TELEA)
        return Image.fromarray(out), faits, laisses


class NettoyeurDistant:
    """Stability AI « Erase » : image + masque (blanc = effacer) → image.
    Choisi pour sa forme simple et synchrone (une requête, une image en
    retour), à 0,05 $ l'image (vérifié le 2026-10-04, docs/recherche/agregateur.md).
    fal.ai (bria/eraser, 0,04 $) est l'alternative moins chère, mais asynchrone."""
    nom = "stability-erase"
    URL = "https://api.stability.ai/v2beta/stable-image/edit/erase"

    def __init__(self, cle: str, url: str = ""):
        self.cle, self.url = cle, url or self.URL

    def nettoyer(self, img: Image.Image, parasites: list):
        import httpx
        if not parasites:
            return img, [], []
        m = masque(img.size, [p["box"] for p in parasites])
        bi, bm = io.BytesIO(), io.BytesIO()
        img.save(bi, "JPEG", quality=95)
        m.save(bm, "PNG")
        r = httpx.post(self.url, timeout=90,
                       headers={"authorization": f"Bearer {self.cle}", "accept": "image/*"},
                       files={"image": ("image.jpg", bi.getvalue(), "image/jpeg"),
                              "mask": ("mask.png", bm.getvalue(), "image/png")},
                       data={"output_format": "jpeg", "grow_mask": "5"})
        r.raise_for_status()
        out = Image.open(io.BytesIO(r.content)).convert("RGB")
        if out.size != img.size:            # le service rend au plus 4 mégapixels
            out = out.resize(img.size, Image.LANCZOS)
        return out, [p.get("label", "objet") for p in parasites], []


def nettoyeur():
    cle = config.cle_nettoyage()
    if cle:
        return NettoyeurDistant(cle, config._env("SOCIAL_NETTOYAGE_URL"))
    return NettoyeurLocal()
