"""Le studio — une prise, plusieurs contenus (§ 9).

Ce que le studio fabrique seul, en local (gratuit, instantané, aucune donnée
qui sort) :

- la RETOUCHE CULINAIRE : rééclairage doux (on aplatit l'éclairage dur d'un
  néon, on rend une lumière de fenêtre), chaleur, éclat, relief ;
- le FOND STUDIO — pour un PRODUIT seulement (SAZÚ) : le plat est détouré et
  posé sur un fond aux couleurs de la marque, avec son ombre. Les pixels du
  plat ne sont jamais repeints. Pour une réalisation (chantier, sol posé),
  le studio REFUSE : un chantier montré est ce chantier-là ;
- le REEL à partir de photos : accroche écrite dès la première image, lents
  mouvements de caméra, fondus, sous-titres animés mot à mot aux couleurs
  de la marque, fin sur l'appel à l'action ;
- le CARROUSEL raconté : une couverture qui arrête le pouce, des vues
  numérotées, une dernière vue d'appel à l'action ;
- l'AVANT / APRÈS : en image (l'un sur l'autre) et en vidéo (un rideau).

Musique : aucune n'est incrustée. Le réseau ajoute un titre de SA
bibliothèque commerciale au moment de publier ; on n'embarque jamais un
titre protégé (§ 9.3).

Chaque fabrication est une ligne de `media_jobs` avec la liste exacte de ses
traitements ; chaque fichier produit est une déclinaison servie par un jeton
public, comme les photos.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import pathlib

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from sqlalchemy import insert, select, update

from . import db, images, journal, marque as marque_, stockage

IPS = 24
W9, H9 = 1080, 1920
VERSION = "studio-1"


class RegleHonnetete(ValueError):
    """Un traitement interdit pour cette marque (décor d'une réalisation)."""


# ── Retouche culinaire ───────────────────────────────────────────────────
def retouche_culinaire(img: Image.Image) -> tuple:
    """→ (image, traitements). Après la correction de base (`images.corriger`) :
    une lumière de fenêtre plutôt qu'un néon, et un plat qui donne faim —
    sans saturation criarde (un plat fluo ne donne pas faim non plus)."""
    img, faits = images.corriger(img)
    a = np.asarray(img).astype(np.float32) / 255.0
    lab = cv2.cvtColor(a, cv2.COLOR_RGB2LAB)
    L = lab[..., 0]
    # 1. Rééclairage : l'éclairage « de grande échelle » (le néon, la tache de
    #    lumière) est estimé par un flou très large et aplati à moitié, puis une
    #    lumière douce venue du haut à gauche est reconstruite.
    h, w = L.shape
    sigma = max(h, w) / 8
    grand = cv2.GaussianBlur(L, (0, 0), sigma)
    moyenne = float(L.mean())
    L = L - 0.5 * (grand - moyenne)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    lumiere = 1.0 - 0.5 * ((xx / w) * 0.6 + (yy / h) * 0.4)
    L = L + 6.0 * (lumiere - lumiere.mean())
    # 2. Relief local (CLAHE sur la luminance seulement : les couleurs ne bavent pas).
    L8 = np.clip(L * 255 / 100, 0, 255).astype(np.uint8)
    L = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(8, 8)).apply(L8).astype(np.float32) * 100 / 255
    lab[..., 0] = np.clip(L, 0, 100)
    # 3. Chaleur : un léger glissement vers le jaune-rouge (b*, a*).
    lab[..., 1] += 1.5
    lab[..., 2] += 4.0
    out = np.clip(cv2.cvtColor(lab, cv2.COLOR_LAB2RGB), 0, 1)
    # 4. Éclat : la saturation monte surtout là où elle est faible (vibrance).
    hsv = cv2.cvtColor((out * 255).astype(np.uint8), cv2.COLOR_RGB2HSV).astype(np.float32)
    s = hsv[..., 1] / 255.0
    hsv[..., 1] = np.clip((s + 0.22 * s * (1 - s) * 2) * 255, 0, 255)
    out = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB)
    # 5. Un vignettage à peine visible ramène l'œil au centre.
    d = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    vign = np.clip(1 - 0.12 * np.clip(d - 0.55, 0, None) ** 1.5, 0.82, 1)[..., None]
    out = np.clip(out.astype(np.float32) * vign, 0, 255).astype(np.uint8)
    return Image.fromarray(out), faits + ["rééclairage doux", "relief local", "chaleur", "éclat des couleurs",
                                          "vignettage léger"]


# ── Détourage et fond studio (PRODUIT seulement) ─────────────────────────
def detourer(img: Image.Image, sujet=None) -> np.ndarray:
    """→ masque 0–1 (float32) du sujet principal. GrabCut amorcé par la boîte
    du sujet (lecture d'image) ou, à défaut, par la fenêtre la plus saillante."""
    petit = images.reduire(img, 900)
    a = np.asarray(petit)
    h, w = a.shape[:2]
    if sujet:
        x0, y0, x1, y1 = [float(v) for v in sujet]
        rect = (int(x0 * w), int(y0 * h), max(2, int((x1 - x0) * w)), max(2, int((y1 - y0) * h)))
    else:
        bx = images.fenetre(petit, 1.0)
        cote = int(min(bx[2] - bx[0], bx[3] - bx[1]) * 0.9)
        cx, cy = (bx[0] + bx[2]) // 2, (bx[1] + bx[3]) // 2
        rect = (max(1, cx - cote // 2), max(1, cy - cote // 2), min(cote, w - 2), min(cote, h - 2))
    masque = np.zeros((h, w), np.uint8)
    bg, fg = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(cv2.cvtColor(a, cv2.COLOR_RGB2BGR), masque, rect, bg, fg, 4, cv2.GC_INIT_WITH_RECT)
        m = np.where((masque == cv2.GC_FGD) | (masque == cv2.GC_PR_FGD), 1.0, 0.0).astype(np.float32)
    except cv2.error:
        m = np.zeros((h, w), np.float32)
        x, y, rw, rh = rect
        cv2.ellipse(m, (x + rw // 2, y + rh // 2), (rw // 2, rh // 2), 0, 0, 360, 1.0, -1)
    # On garde la plus grande composante (le plat), on bouche ses trous, on adoucit le bord.
    n, lab, stats, _ = cv2.connectedComponentsWithStats((m > 0.5).astype(np.uint8))
    if n > 1:
        k = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        m = (lab == k).astype(np.float32)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    m = cv2.GaussianBlur(m, (0, 0), 2.2)
    return cv2.resize(m, img.size, interpolation=cv2.INTER_LINEAR)


def fond_studio(img: Image.Image, m: dict, sujet=None) -> tuple:
    """→ (image, traitements). Refuse tout ce qui n'est pas un produit."""
    if marque_.mise_en_scene(m) != "studio_permis":
        raise RegleHonnetete(f"{m['name']} montre des réalisations : on améliore l'image, "
                             "on ne remplace jamais le décor")
    masque = detourer(img, sujet)
    if masque.mean() < 0.04 or masque.mean() > 0.92:
        return img, ["fond d'origine gardé (sujet introuvable)"]
    c = images.couleurs(m.get("kit") or {})
    W, H = img.size
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    clair = np.array(c["fond"], np.float32)
    sombre = clair * 0.86
    t = np.clip(np.sqrt(((xx - W / 2) / W) ** 2 + ((yy - H * 0.42) / H) ** 2) * 1.6, 0, 1)[..., None]
    fond = clair * (1 - t) + sombre * t
    # L'ombre : le masque décalé vers le bas, très flou, sous le plat.
    ys, xs = np.nonzero(masque > 0.5)
    ombre = np.zeros_like(masque)
    if len(ys):
        dy = int((ys.max() - ys.min()) * 0.06)
        ombre[dy:, :] = masque[:H - dy, :] if dy else masque
        ombre = cv2.GaussianBlur(ombre, (0, 0), max(W, H) / 45)
    fond = fond * (1 - 0.35 * ombre[..., None])
    a = np.asarray(img.convert("RGB")).astype(np.float32)
    out = a * masque[..., None] + fond * (1 - masque[..., None])
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)), ["fond studio aux couleurs de la marque",
                                                                     "ombre reconstruite",
                                                                     "plat d'origine intact (non repeint)"]


# ── Écrire sur l'image ───────────────────────────────────────────────────
def _accent_lisible(c: dict) -> tuple:
    """L'accent de la marque s'il se lit sur fond sombre ; sinon un beurre
    chaud (la framboise de SAZÚ sur l'encre olive ne se lit pas au soleil)."""
    r, g, b = c["accent"][:3]
    return tuple(c["accent"][:3]) if (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 > 0.55 else (240, 214, 126)


def _polices(m: dict):
    f = (m.get("kit") or {}).get("fonts") or {}
    return f.get("title", "Manrope"), f.get("text", "Manrope"), f.get("detail", "CourierPrime-Regular")


def _texte_centre(d, texte, police, y, W, couleur, marge, interligne=1.08, contour=None):
    for ligne in images._lignes(texte, police, W - 2 * marge):
        l, t, r, b = police.getbbox(ligne)
        kw = dict(stroke_width=contour[0], stroke_fill=contour[1]) if contour else {}
        d.text(((W - (r - l)) / 2 - l, y - t), ligne, font=police, fill=couleur, **kw)
        y += int((b - t) * interligne) + 8
    return y


def sous_titre(calque: Image.Image, mots: list, actif: int, m: dict, y_centre: int):
    """Sous-titres animés : 3 à 5 mots à la fois, le mot dit EN COULEUR
    (l'accent de la marque), dans une pastille lisible au soleil. Hors des
    zones que l'interface d'Instagram et de TikTok recouvre."""
    if not mots:
        return
    c = images.couleurs(m.get("kit") or {})
    _, texte, _ = _polices(m)
    p = images._police(texte, 68, 800)
    groupe_debut = (actif // 4) * 4
    groupe = mots[groupe_debut:groupe_debut + 4]
    d = ImageDraw.Draw(calque)
    largeurs = [p.getlength(w_ + " ") for w_ in groupe]
    total = sum(largeurs)
    W = calque.width
    x = (W - total) / 2
    pad = 22
    d.rounded_rectangle((x - pad, y_centre - 52, x + total + pad - p.getlength(" "), y_centre + 52), radius=26,
                        fill=c["encre"] + (215,))
    for i, w_ in enumerate(groupe):
        couleur = (_accent_lisible(c) if (groupe_debut + i) == actif else (250, 248, 240)) + (255,)
        l, t, r, b = p.getbbox(w_)
        d.text((x, y_centre - (b - t) / 2 - t), w_, font=p, fill=couleur)
        x += largeurs[i]


# ── Le Reel ──────────────────────────────────────────────────────────────
def _base_9x16(img: Image.Image, sujet=None, marge: float = 1.14) -> Image.Image:
    """Le cadre 9:16 du sujet, un peu plus grand que l'écran pour bouger dedans."""
    cadre = images.recadrer(img, "9:16", sujet)
    return cadre.resize((round(W9 * marge), round(H9 * marge)), Image.LANCZOS)


def _plan(base, t: float, sens: int) -> Image.Image:
    """Un mouvement de caméra lent : zoom avant ou arrière, léger glissement.
    Une seule transformation affine (OpenCV) : recadrage et mise à l'échelle
    au sous-pixel près — le mouvement ne « saute » pas d'un pixel à l'autre,
    et c'est huit fois plus rapide qu'un recadrage puis un redimensionnement."""
    a = base if isinstance(base, np.ndarray) else np.asarray(base.convert("RGB"))
    bh, bw = a.shape[:2]
    z = 1.0 + 0.10 * (t if sens > 0 else 1 - t)
    cw, ch = bw / z, bh / z
    gx = (bw - cw) * (0.5 + 0.25 * sens * (t - 0.5))
    gy = (bh - ch) * 0.45
    sx, sy = W9 / cw, H9 / ch
    M = np.float32([[sx, 0, -gx * sx], [0, sy, -gy * sy]])
    return Image.fromarray(cv2.warpAffine(a, M, (W9, H9), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT))


def reel(photos: list, m: dict, accroche: str, phrases: list, sortie: pathlib.Path, cta: str = "",
         avec_logo: bool = True, sujets: list | None = None, par_photo: float = 2.4) -> dict:
    """Des photos (déjà retouchées) → un Reel 9:16 H.264.

    Structure d'agence : l'accroche est LISIBLE dès la première image (on
    décide en une seconde de rester), chaque photo vit 2,4 s avec son
    mouvement, fondus de 0,3 s, sous-titres mot à mot, barre de progression,
    et une fin de 2 s sur l'appel à l'action et la marque.
    """
    import imageio_ffmpeg
    if not photos:
        raise ValueError("aucune photo")
    kit = m.get("kit") or {}
    c = images.couleurs(kit)
    titre_p, texte_p, _ = _polices(m)
    bases = [np.asarray(_base_9x16(p, (sujets or [None] * len(photos))[i]).convert("RGB"))
             for i, p in enumerate(photos)]
    n_photo = round(par_photo * IPS)
    fondu = round(0.3 * IPS)
    n_fin = 2 * IPS
    total = n_photo * len(bases) + n_fin
    mots = " ".join(phrases).split()
    # Les mots se répartissent sur la partie photos (pas sur la fin).
    par_mot = max(1, (n_photo * len(bases) - IPS) // max(1, len(mots)))
    fin = _image_fin(m, cta, avec_logo)
    pa = images._police(titre_p, 104, 800)
    sortie.parent.mkdir(parents=True, exist_ok=True)
    gen = imageio_ffmpeg.write_frames(str(sortie), (W9, H9), fps=IPS, codec="libx264", pix_fmt_out="yuv420p",
                                      quality=6, macro_block_size=8, output_params=["-movflags", "+faststart"])
    gen.send(None)
    try:
        for i in range(total):
            k = min(i // n_photo, len(bases) - 1)
            if i < n_photo * len(bases):
                t = (i - k * n_photo) / n_photo
                cadre = _plan(bases[k], t, 1 if k % 2 == 0 else -1)
                if k + 1 < len(bases) and (i - k * n_photo) >= n_photo - fondu:
                    a = ((i - k * n_photo) - (n_photo - fondu)) / fondu
                    cadre = Image.blend(cadre, _plan(bases[k + 1], 0.0, 1 if (k + 1) % 2 == 0 else -1), a)
            else:
                a = min(1.0, (i - n_photo * len(bases)) / fondu)
                cadre = Image.blend(_plan(bases[-1], 1.0, 1), fin, a) if a < 1 else fin
            calque = Image.new("RGBA", (W9, H9), (0, 0, 0, 0))
            d = ImageDraw.Draw(calque)
            # Barre de progression : le spectateur sait que c'est court.
            d.rectangle((0, 0, round(W9 * (i + 1) / total), 10), fill=c["accent"] + (255,))
            if i < round(1.6 * IPS) and accroche:
                _texte_centre(d, accroche, pa, round(H9 * 0.33), W9, (255, 255, 255, 255), 80,
                              contour=(6, c["encre"] + (255,)))
            elif i < n_photo * len(bases) and mots:
                actif = min(len(mots) - 1, max(0, (i - round(1.6 * IPS)) // par_mot))
                sous_titre(calque, mots, actif, m, round(H9 * 0.68))
            image = Image.alpha_composite(cadre.convert("RGBA"), calque).convert("RGB")
            gen.send(np.ascontiguousarray(np.asarray(image)))
    finally:
        gen.close()
    return {"duree": round(total / IPS, 1), "traitements": [
        f"Reel de {len(bases)} photos ({total / IPS:.1f} s)", "accroche lisible dès la première image",
        "mouvements de caméra et fondus", "sous-titres animés mot à mot aux couleurs de la marque",
        "barre de progression", "fin sur l'appel à l'action", "aucune musique incrustée (bibliothèque du réseau)"]}


def _image_fin(m: dict, cta: str, avec_logo: bool) -> Image.Image:
    kit = m.get("kit") or {}
    titre = cta or kit.get("band_text") or m["name"]
    return images.carte(dict(kit, band=False), m["name"], titre, "", "", "9:16", avec_logo).convert("RGB")


# ── Le carrousel ─────────────────────────────────────────────────────────
def carrousel(photos: list, m: dict, titre: str, legendes: list, cta: str = "", avec_logo: bool = True,
              sujets: list | None = None) -> list:
    """→ liste d'images 4:5. Couverture (titre fort sur la meilleure photo,
    invitation à glisser), vues numérotées avec une ligne chacune, dernière
    vue à la charte avec l'appel à l'action. 3 à 10 vues."""
    if not photos:
        raise ValueError("aucune photo")
    photos = photos[:8]
    kit = m.get("kit") or {}
    c = images.couleurs(kit)
    titre_p, texte_p, detail_p = _polices(m)
    W, H = images.FORMATS["4:5"]
    n = len(photos) + 1                # couverture (1re photo) + vues + appel à l'action
    vues = []
    # Couverture
    cov = images.recadrer(photos[0], "4:5", (sujets or [None])[0]).convert("RGBA")
    voile = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dv = ImageDraw.Draw(voile)
    for y in range(H // 2, H):
        alpha = int(200 * ((y - H / 2) / (H / 2)) ** 1.4)
        dv.line([(0, y), (W, y)], fill=c["encre"] + (alpha,))
    cov = Image.alpha_composite(cov, voile)
    d = ImageDraw.Draw(cov)
    pt = images._police(titre_p, 96 if len(titre) < 28 else 76, 800)
    lignes = images._lignes(titre, pt, W - 140)
    y = H - 170 - len(lignes) * 104
    for ligne in lignes:
        d.text((70, y), ligne, font=pt, fill=(255, 255, 255))
        y += 104
    pd = images._police(texte_p, 34, 700)
    d.text((70, H - 110), "Glisse →" if (kit and (m.get("voice") or {}).get("address") == "tu") else "Faites glisser →",
           font=pd, fill=_accent_lisible(c))
    vues.append(cov.convert("RGB"))
    # Vues intérieures
    for i, p in enumerate(photos[1:] if len(photos) > 1 else []):
        v = images.recadrer(p, "4:5", (sujets or [None] * len(photos))[i + 1]).convert("RGBA")
        d = ImageDraw.Draw(v)
        leg = legendes[i] if i < len(legendes) else ""
        num = f"{i + 2}/{n}"
        pn = images._police(detail_p, 30)
        d.rounded_rectangle((W - 150, 40, W - 40, 92), radius=26, fill=c["encre"] + (190,))
        l, t, r, b = pn.getbbox(num)
        d.text((W - 95 - (r - l) / 2 - l, 66 - (b - t) / 2 - t), num, font=pn, fill=(255, 255, 255))
        if leg:
            pl = images._police(texte_p, 40, 700)
            lignes = images._lignes(leg, pl, W - 160)[:3]
            hauteur = 60 * len(lignes) + 40
            d.rounded_rectangle((50, H - 70 - hauteur, W - 50, H - 70), radius=28, fill=c["fond"] + (235,))
            yy = H - 70 - hauteur + 22
            for ligne in lignes:
                d.text((80, yy), ligne, font=pl, fill=c["encre"])
                yy += 60
        vues.append(v.convert("RGB"))
    # Dernière vue : l'appel à l'action
    vues.append(images.carte(dict(kit, band=False), m["name"], cta or kit.get("band_text") or m["name"],
                             "", f"{n}/{n}", "4:5", avec_logo))
    return vues


# ── Avant / après ────────────────────────────────────────────────────────
def avant_apres(avant: Image.Image, apres: Image.Image, m: dict) -> Image.Image:
    """Les deux états du MÊME lieu, l'un au-dessus de l'autre, étiquetés.
    Aucune retouche de décor : c'est la preuve du travail."""
    W, H = images.FORMATS["4:5"]
    c = images.couleurs(m.get("kit") or {})
    out = Image.new("RGB", (W, H), c["fond"])
    demi = (W, H // 2 - 4)
    for k, (img, nom) in enumerate(((avant, "AVANT"), (apres, "APRÈS"))):
        cadre = img.crop(images.fenetre(img, demi[0] / demi[1])).resize(demi, Image.LANCZOS)
        out.paste(cadre, (0, k * (H // 2 + 4)))
        d = ImageDraw.Draw(out)
        p = images._police(_polices(m)[0], 46, 800)
        l, t, r, b = p.getbbox(nom)
        y = k * (H // 2 + 4) + 30
        d.rounded_rectangle((30, y, 30 + (r - l) + 44, y + (b - t) + 30), radius=18,
                            fill=(c["accent"] if k else c["encre"]))
        d.text((52 - l, y + 15 - t), nom, font=p, fill=(255, 255, 255))
    return out


def rideau(avant: Image.Image, apres: Image.Image, m: dict, sortie: pathlib.Path) -> dict:
    """Vidéo 9:16 : un rideau balaie l'avant pour révéler l'après (5 s)."""
    import imageio_ffmpeg
    a, b = _base_9x16(avant, marge=1.0).resize((W9, H9)), _base_9x16(apres, marge=1.0).resize((W9, H9))
    c = images.couleurs(m.get("kit") or {})
    sortie.parent.mkdir(parents=True, exist_ok=True)
    gen = imageio_ffmpeg.write_frames(str(sortie), (W9, H9), fps=IPS, codec="libx264", pix_fmt_out="yuv420p",
                                      quality=6, macro_block_size=8, output_params=["-movflags", "+faststart"])
    gen.send(None)
    n = 5 * IPS
    p = images._police(_polices(m)[0], 72, 800)
    try:
        for i in range(n):
            t = min(1.0, max(0.0, (i - IPS) / (2.5 * IPS)))
            t = 0.5 - 0.5 * math.cos(math.pi * t)
            x = round(W9 * (1 - t))
            img = b.copy()
            img.paste(a.crop((0, 0, x, H9)), (0, 0))
            d = ImageDraw.Draw(img)
            d.rectangle((x - 5, 0, x + 5, H9), fill=c["accent"])
            d.text((60, 140), "AVANT" if t < 0.5 else "APRÈS", font=p, fill=(255, 255, 255),
                   stroke_width=5, stroke_fill=c["encre"])
            gen.send(np.ascontiguousarray(np.asarray(img)))
    finally:
        gen.close()
    return {"duree": 5.0, "traitements": ["avant/après en rideau (5 s)", "décor d'origine, non retouché"]}


# ── La fabrique : un travail, ses fichiers, sa trace ─────────────────────
def _ranger(job_id: int, asset_id: int, rang: int, octets: bytes, chemin_rel: str, video: bool, faits: list,
            duree: float | None = None) -> int:
    fmt = (f"r{job_id % 10000}v" if video else f"s{job_id % 10000}-{rang}")[:10]
    cle = hashlib.sha256(f"{VERSION}:{job_id}:{rang}:{video}".encode()).hexdigest()
    with db.moteur().begin() as c:
        return c.execute(insert(db.renditions).values(
            asset_id=asset_id, format=fmt, path=chemin_rel, public_token=stockage.jeton_public(),
            treatments=faits, cache_key=cle, sha256=hashlib.sha256(octets).hexdigest(), duration_s=duree,
            created_at=db.maintenant())).inserted_primary_key[0]


def _photos(asset_ids: list, m: dict, studio: bool) -> tuple:
    """Les photos du travail, retouchées (et sur fond studio si permis et demandé)."""
    from . import pipeline
    out, sujets, faits = [], [], []
    for aid in asset_ids:
        a = pipeline.asset(aid)
        if not a or a["brand_id"] != m["id"]:
            raise ValueError(f"photo {aid} inconnue pour cette marque")
        if a["kind"] == "carte":
            img = images.carte(m.get("kit") or {}, m["name"], ((a["vision"] or {}).get("carte") or {}).get("titre", ""))
            f = ["carte à la charte"]
        else:
            img = images.ouvrir(stockage.chemin(a["blurred_path"] or a["original_path"]))
            if m.get("sector") == "food":
                img, f = retouche_culinaire(img)
            else:
                img, f = images.corriger(img)
            if studio:
                img, f2 = fond_studio(img, m, (a["vision"] or {}).get("sujet_boite"))
                f = f + f2
        out.append(img)
        sujets.append((a["vision"] or {}).get("sujet_boite"))
        faits.append(f)
    return out, sujets, faits


def fabriquer(type_: str, marque_id: str, asset_ids: list, params: dict | None = None, par: str = "studio") -> dict:
    """→ le travail (media_jobs) avec ses fichiers. Types : reel, carrousel,
    avant_apres, rideau. `params` : accroche, phrases, titre, legendes, cta,
    studio (fond studio : PRODUIT seulement), avec_logo."""
    from . import acces
    m = acces.marque(marque_id)
    p = params or {}
    if p.get("studio") and marque_.mise_en_scene(m) != "studio_permis":
        raise RegleHonnetete(f"{m['name']} : fond studio interdit (réalisation réelle)")
    with db.moteur().begin() as c:
        jid = c.execute(insert(db.media_jobs).values(brand_id=m["id"], asset_ids=list(asset_ids), type=type_,
                                                     statut="attente", created_at=db.maintenant())).inserted_primary_key[0]
    dossier = f"studio/{m['id']}/{jid}"
    racine = stockage.racine()
    try:
        photos, sujets, faits_photos = _photos(asset_ids, m, bool(p.get("studio")))
        tous_faits = sorted({f for fs in faits_photos for f in fs})
        # Le logo n'apparaît que s'il est déjà permis (SAZÚ le révèle le 13/11 à 18 h).
        avec_logo = bool(p.get("avec_logo", True)) and acces.logo_permis(m)
        p["avec_logo"] = avec_logo
        fichiers = []
        if type_ == "reel":
            rel = f"{dossier}/reel.mp4"
            info = reel(photos, m, p.get("accroche", ""), p.get("phrases") or [], racine / rel, p.get("cta", ""),
                        avec_logo, sujets)
            couverture = _base_9x16(photos[0], sujets[0], 1.0)
            images.enregistrer_jpeg(couverture, (racine / rel).with_suffix(".jpg"), 88)
            faits = tous_faits + info["traitements"]
            rid = _ranger(jid, asset_ids[0], 0, (racine / rel).read_bytes(), rel, True, faits, info["duree"])
            fichiers.append({"rendition_id": rid, "video": True, "duree": info["duree"]})
        elif type_ == "carrousel":
            vues = carrousel(photos, m, p.get("titre", ""), p.get("legendes") or [], p.get("cta", ""), avec_logo,
                             sujets)
            faits = tous_faits + [f"carrousel de {len(vues)} vues", "couverture titrée", "vues numérotées",
                                  "dernière vue : appel à l'action"]
            for i, v in enumerate(vues):
                rel = f"{dossier}/vue-{i + 1:02d}.jpg"
                octets = images.enregistrer_jpeg(v, racine / rel, 90)
                fichiers.append({"rendition_id": _ranger(jid, asset_ids[0], i + 1, octets, rel, False, faits),
                                 "video": False})
        elif type_ in ("avant_apres", "rideau"):
            if len(photos) != 2:
                raise ValueError("un avant/après demande exactement deux photos")
            if type_ == "avant_apres":
                rel = f"{dossier}/avant-apres.jpg"
                octets = images.enregistrer_jpeg(avant_apres(photos[0], photos[1], m), racine / rel, 90)
                faits = tous_faits + ["avant/après superposés, étiquetés", "décor d'origine"]
                fichiers.append({"rendition_id": _ranger(jid, asset_ids[0], 1, octets, rel, False, faits),
                                 "video": False})
            else:
                rel = f"{dossier}/rideau.mp4"
                info = rideau(photos[0], photos[1], m, racine / rel)
                faits = tous_faits + info["traitements"]
                fichiers.append({"rendition_id": _ranger(jid, asset_ids[0], 0, (racine / rel).read_bytes(), rel,
                                                         True, faits, info["duree"]),
                                 "video": True, "duree": info["duree"]})
        elif type_ == "declinaison":
            if len(photos) != 1:
                raise ValueError("une déclinaison part d'une seule photo")
            faits = list(tous_faits)
            for i, (cle, nom, taille, fmt_h, img) in enumerate(declinaison_totale(
                    photos[0], m, p.get("titre") or p.get("accroche") or "", avec_logo, sujets[0]), 1):
                rel = f"{dossier}/{cle}.jpg"
                octets = images.enregistrer_jpeg(img, racine / rel, 90)
                fichiers.append({"rendition_id": _ranger(jid, asset_ids[0], i, octets, rel, False, faits),
                                 "video": False, "cle": cle, "nom": nom, "taille": f"{taille[0]}×{taille[1]}"})
            faits += [f"{len(fichiers)} formats d'une seule prise", "recadrage sur le sujet à chaque format",
                      "habillage à la charte par format"]
        else:
            raise ValueError(f"type inconnu : {type_}")
        with db.moteur().begin() as c:
            c.execute(update(db.media_jobs).where(db.media_jobs.c.id == jid).values(
                statut="fait", sortie={"fichiers": fichiers, "params": json.loads(json.dumps(p, default=str))},
                traitements=faits, score=potentiel(type_, len(photos), p)))
        journal.noter(par, "studio", "media_job", jid, m["id"], apres={"type": type_, "photos": asset_ids,
                                                                        "fichiers": len(fichiers)})
    except Exception as e:
        with db.moteur().begin() as c:
            c.execute(update(db.media_jobs).where(db.media_jobs.c.id == jid).values(statut="echec",
                                                                                   erreur=str(e)[:500]))
        raise
    return travail(jid)


# ── La déclinaison totale : une prise, tous les formats ─────────────────
# (clé, nom lisible, taille en pixels, format d'habillage le plus proche)
DECLINAISONS = [
    ("carre", "Carré — Instagram, Facebook", (1080, 1080), "1:1"),
    ("portrait", "Portrait 4:5 — fil Instagram", (1080, 1350), "4:5"),
    ("story", "Story 9:16 — Instagram, Facebook, WhatsApp", (1080, 1920), "9:16"),
    ("linkedin", "LinkedIn — lien et fil", (1200, 627), "16:9"),
    ("miniature", "Miniature YouTube", (1280, 720), "16:9"),
    ("google", "Fiche Google — publication", (1200, 900), "4:3"),
]


def declinaison_totale(photo: Image.Image, m: dict, titre: str = "", avec_logo: bool = True, sujet=None) -> list:
    """→ [(clé, nom, taille, format, image)] : chaque format recadré sur le
    sujet (jamais un étirement), habillé à la charte. La miniature YouTube
    porte le titre en grand — c'est elle qu'on clique ; les autres non, le
    texte vit dans la légende."""
    kit = m.get("kit") or {}
    out = []
    for cle, nom, (tw, th), fmt in DECLINAISONS:
        img = photo.crop(images.fenetre(photo, tw / th, sujet)).resize((tw, th), Image.LANCZOS)
        if cle == "miniature" and titre:
            img = _titre_miniature(img, m, titre)
        img, _ = images.habiller(img, kit, m["name"], fmt, avec_logo)
        out.append((cle, nom, (tw, th), fmt, img))
    return out


def _titre_miniature(img: Image.Image, m: dict, titre: str) -> Image.Image:
    c = images.couleurs(m.get("kit") or {})
    W, H = img.size
    voile = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dv = ImageDraw.Draw(voile)
    for x in range(round(W * 0.62)):
        dv.line([(x, 0), (x, H)], fill=c["encre"] + (int(185 * (1 - x / (W * 0.62)) ** 1.2),))
    img = Image.alpha_composite(img.convert("RGBA"), voile)
    d = ImageDraw.Draw(img)
    titre_p, _, _ = _polices(m)
    pt = images._police(titre_p, 92 if len(titre) < 24 else 72, 800)
    lignes = images._lignes(titre, pt, round(W * 0.55))[:3]
    y = (H - len(lignes) * 100) // 2
    for ligne in lignes:
        d.text((56, y), ligne, font=pt, fill=(255, 255, 255), stroke_width=4, stroke_fill=c["encre"])
        y += 100
    return img.convert("RGB")


def potentiel(type_: str, n: int, p: dict) -> int:
    """Une estimation grossière et ASSUMÉE comme telle, en attendant les
    mesures de la marque (§ 11.2) : elle sert à départager, jamais à bloquer."""
    base = {"reel": 70, "carrousel": 64, "rideau": 72, "avant_apres": 66, "declinaison": 55}.get(type_, 50)
    base += 6 if p.get("accroche") or p.get("titre") else 0
    base += min(8, 2 * max(0, n - 2))
    return min(95, base)


def travail(jid: int) -> dict:
    with db.moteur().connect() as c:
        j = db.ligne(c.execute(select(db.media_jobs).where(db.media_jobs.c.id == jid)))
        ids = [f["rendition_id"] for f in (j["sortie"] or {}).get("fichiers", [])]
        rs = {r["id"]: r for r in db.lignes(c.execute(select(db.renditions).where(db.renditions.c.id.in_(ids))))} \
            if ids else {}
    j["fichiers"] = [{"rendition_id": i, "url": f"/m/{rs[i]['public_token']}.{'mp4' if rs[i]['format'].endswith('v') else 'jpg'}",
                      "video": rs[i]["format"].endswith("v")} for i in ids if i in rs]
    return j


def travail_par_ref(ref: str) -> dict | None:
    """Un travail réussi déjà fait sous cette référence (`video:12:clip3`) — la
    reprise d'un découpage interrompu ne refait pas ce qui est fait."""
    with db.moteur().connect() as c:
        for j in db.lignes(c.execute(select(db.media_jobs).where(db.media_jobs.c.type == "clip",
                                                                 db.media_jobs.c.statut == "fait"))):
            if (j["sortie"] or {}).get("ref") == ref:
                return j
    return None


def travaux(marque_ids: list, limite: int = 30) -> list:
    with db.moteur().connect() as c:
        ids = [r[0] for r in c.execute(select(db.media_jobs.c.id).where(db.media_jobs.c.brand_id.in_(marque_ids))
                                       .order_by(db.media_jobs.c.id.desc()).limit(limite))]
    return [travail(i) for i in ids]


# ── Le montage automatique : une rafale devient un Reel et un carrousel ──
RAFALE_MIN = 3                    # photos d'un même moment
RAFALE_FENETRE_H = 3              # reçues dans ces heures-là
# Quel montage pour quel réseau : le Reel là où la vidéo courte porte (et
# Instagram pousse les Reels hors des abonnés), le carrousel là où on lit.
MONTAGE_PAR_RESEAU = {"instagram": "reel", "tiktok": "reel", "youtube": "reel",
                      "facebook": "carrousel", "linkedin": "carrousel"}
# Un clip tiré d'une vraie vidéo passe avant un Reel fabriqué de photos là où
# la vidéo porte ; Facebook et LinkedIn le prennent s'il n'y a pas de carrousel.
PREFERENCES = {"instagram": ("clip", "reel"), "tiktok": ("clip", "reel"), "youtube": ("clip", "reel"),
               "facebook": ("carrousel", "clip"), "linkedin": ("carrousel", "clip")}


def montage_pour(plateforme: str, montages: dict) -> dict | None:
    for t in PREFERENCES.get(plateforme, ()):
        if t in montages:
            return montages[t]
    return None


def _vrai_sujet(a: dict) -> str:
    v = a.get("vision") or {}
    if v.get("simule"):
        return ""
    return (v.get("sujet") or "").strip()


def _accroche(m: dict, graine: int) -> str:
    p = (marque_.courante(m["id"]) or {}).get("plateforme") or {}
    acc = [x for x in (p.get("accroches") or []) if 6 <= len(x) <= 60]
    return acc[graine % len(acc)] if acc else (m.get("kit") or {}).get("band_text") or m["name"]


def rafale(marque_id: str, par: str = "studio") -> dict:
    """Les photos d'une marque PRODUIT reçues ensemble deviennent un Reel et un
    carrousel. La première photo porte les montages et part dans le
    calendrier comme d'habitude ; les autres sont rangées « studio » : elles
    vivent dans le montage, elles ne repartent pas seules la même semaine."""
    from . import acces
    m = acces.marque(marque_id)
    if not m or marque_.mise_en_scene(m) != "studio_permis":
        return {"fait": False, "raison": "montage automatique réservé aux marques produit"}
    depuis = db.maintenant() - dt.timedelta(hours=RAFALE_FENETRE_H)
    with db.moteur().connect() as c:
        photos = db.lignes(c.execute(select(db.assets).where(
            db.assets.c.brand_id == m["id"], db.assets.c.kind == "photo", db.assets.c.status == "banque",
            db.assets.c.created_at >= depuis).order_by(db.assets.c.usability.desc(), db.assets.c.id)))
    deja = {i for j in travaux([m["id"]], 60) for i in (j["asset_ids"] or [])}
    photos = [a for a in photos if a["id"] not in deja and not (a.get("client_ref") or "").startswith("video:")][:6]
    if len(photos) < RAFALE_MIN:
        return {"fait": False, "raison": f"{len(photos)} photo(s) : il en faut {RAFALE_MIN}"}
    ids = [a["id"] for a in photos]
    notes = [a.get("note") or _vrai_sujet(a) for a in photos]
    phrases = [n for n in notes if n][:4]
    kit = m.get("kit") or {}
    cta = kit.get("band_text") or ""
    accroche = _accroche(m, ids[0])
    r = fabriquer("reel", m["id"], ids, {"accroche": accroche, "phrases": phrases, "cta": cta,
                                         "auto": True}, par)
    k = fabriquer("carrousel", m["id"], ids, {"titre": accroche, "legendes": notes[1:], "cta": cta, "auto": True},
                  par)
    with db.moteur().begin() as c:
        c.execute(update(db.assets).where(db.assets.c.id.in_(ids[1:])).values(status="studio"))
    journal.noter(par, "montage_auto", "asset", ids[0], m["id"],
                  apres={"photos": ids, "reel": r["id"], "carrousel": k["id"]})
    return {"fait": True, "reel": r["id"], "carrousel": k["id"], "photos": ids}


def montages_de(asset_id: int) -> dict:
    """{type: travail} — les montages réussis que porte cette photo (la 1re de la rafale)."""
    with db.moteur().connect() as c:
        a = db.ligne(c.execute(select(db.assets.c.brand_id).where(db.assets.c.id == asset_id)))
    if not a:
        return {}
    out = {}
    for j in travaux([a["brand_id"]], 60):
        if j["statut"] == "fait" and (j["asset_ids"] or [None])[0] == asset_id and j["type"] not in out:
            out[j["type"]] = j
    return out
