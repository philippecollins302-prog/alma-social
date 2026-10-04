"""La retouche locale : gratuite, instantanée, et reproductible.

Tout ce qui ne demande pas d'intelligence se fait ici, avec Pillow, numpy et
OpenCV : lecture EXIF, empreinte visuelle, mesures de qualité, corrections de
lumière, recadrage qui garde le sujet, habillage à la charte, floutage, cartes
typographiques. Seul l'effacement des objets parasites peut appeler un service
d'IA (voir nettoyage.py) — c'est la seule étape qui le justifie.

L'original n'est JAMAIS modifié : chaque fonction rend une nouvelle image.
"""
from __future__ import annotations

import datetime as dt
import io
import math
import pathlib

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from . import config

try:                                    # photos HEIC des iPhone
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:                     # pragma: no cover
    pass

# Monter ce numéro = toutes les déclinaisons se refont (le cache en dépend).
VERSION_TRAITEMENTS = "3"
COTE_TRAVAIL = 2160                     # assez pour 1080×1920, et rapide

FORMATS = {"1:1": (1080, 1080), "4:5": (1080, 1350), "9:16": (1080, 1920), "16:9": (1920, 1080),
           "4:3": (1200, 900), "2:3": (1000, 1500)}
POLICES = config.STATIQUES / "fonts"


# ── Lecture ──────────────────────────────────────────────────────────────
def ouvrir(source) -> Image.Image:
    """Chemin ou octets → image RGB redressée selon l'EXIF (une photo de
    téléphone tenue en portrait arrive souvent couchée sans ça)."""
    img = Image.open(io.BytesIO(source) if isinstance(source, (bytes, bytearray)) else source)
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        fond = Image.new("RGB", img.size, (255, 255, 255))
        img = img.convert("RGBA")
        fond.paste(img, mask=img.split()[-1])
        return fond
    return img.convert("RGB")


def _rationnel(v):
    try:
        return float(v[0]) / float(v[1]) if isinstance(v, tuple) else float(v)
    except (TypeError, ZeroDivisionError, ValueError):
        return None


def lire_exif(source) -> dict:
    """Date de prise de vue, appareil, position — ce qui sert au journal et au
    lieu probable. Rien de tout ça ne part sur les réseaux : les déclinaisons
    sont enregistrées SANS EXIF (une position GPS de chantier ou de domicile
    n'a rien à faire sur Instagram)."""
    try:
        img = Image.open(io.BytesIO(source) if isinstance(source, (bytes, bytearray)) else source)
        ex = img.getexif()
    except Exception:
        return {}
    out = {}
    base = {0x010F: "marque", 0x0110: "modele"}
    for tag, nom in base.items():
        if ex.get(tag):
            out[nom] = str(ex.get(tag)).strip("\x00 ")
    try:
        sub = ex.get_ifd(0x8769)
        if sub.get(36867):
            out["prise_le"] = str(sub.get(36867))
    except Exception:
        pass
    try:
        gps = ex.get_ifd(0x8825)
        if gps and 2 in gps and 4 in gps:
            def deg(v):
                d, m, s = (_rationnel(x) for x in v)
                return d + m / 60 + s / 3600
            lat, lon = deg(gps[2]), deg(gps[4])
            if gps.get(1) == "S":
                lat = -lat
            if gps.get(3) == "W":
                lon = -lon
            out["gps"] = {"lat": round(lat, 6), "lon": round(lon, 6)}
    except Exception:
        pass
    return out


def date_prise(exif: dict):
    v = exif.get("prise_le")
    if not v:
        return None
    try:
        return dt.datetime.strptime(v[:19], "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


def reduire(img: Image.Image, cote: int = COTE_TRAVAIL) -> Image.Image:
    if max(img.size) <= cote:
        return img.copy()
    r = cote / max(img.size)
    return img.resize((round(img.width * r), round(img.height * r)), Image.LANCZOS)


# ── Empreinte visuelle (anti-doublon) ────────────────────────────────────
def empreinte(img: Image.Image) -> str:
    """pHash 64 bits : la même photo recadrée, réexportée ou légèrement
    retouchée garde une empreinte voisine. Le nom du fichier n'y est pour rien."""
    g = np.asarray(img.convert("L").resize((32, 32), Image.LANCZOS), dtype=np.float32)
    d = cv2.dct(g)[:8, :8]
    med = np.median(d.flatten()[1:])
    bits = (d > med).flatten()
    return "%016x" % int("".join("1" if b else "0" for b in bits), 2)


def distance(a: str, b: str) -> int:
    if not a or not b:
        return 64
    return bin(int(a, 16) ^ int(b, 16)).count("1")


# ── Qualité technique ────────────────────────────────────────────────────
def mesurer(img: Image.Image) -> dict:
    """Mesures locales, sans IA. La netteté est celle de la ZONE LA PLUS NETTE :
    un bowl net sur un fond flou (photo de plat typique) n'est pas une photo
    floue."""
    petit = reduire(img, 1024)
    g = np.asarray(petit.convert("L"), dtype=np.float32)
    lap = cv2.Laplacian(g, cv2.CV_32F)
    h, w = g.shape
    blocs = []
    for i in range(6):
        for j in range(6):
            b = lap[i * h // 6:(i + 1) * h // 6, j * w // 6:(j + 1) * w // 6]
            if b.size:
                blocs.append(float(b.var()))
    blocs.sort()
    nettete = float(np.mean(blocs[-3:])) if blocs else 0.0
    bruit = float(np.median(np.abs(g - cv2.GaussianBlur(g, (3, 3), 0))) * 1.4826)
    return {
        "nettete": round(nettete, 1),
        "luminosite": round(float(g.mean()), 1),
        "ecretage_noir": round(float((g < 8).mean()), 3),
        "ecretage_blanc": round(float((g > 247).mean()), 3),
        "bruit": round(bruit, 2),
        "largeur": img.width,
        "hauteur": img.height,
    }


SEUILS = {"cote_min": 640, "nettete_min": 60.0, "lum_min": 38.0, "lum_max": 232.0,
          "ecretage_max": 0.35, "utilisabilite_min": 45}


def refus_technique(m: dict, utilisabilite=None) -> str:
    """'' si la photo est publiable, sinon la raison (pour le journal)."""
    if min(m["largeur"], m["hauteur"]) < SEUILS["cote_min"]:
        return f"trop petite ({m['largeur']}×{m['hauteur']} px, minimum {SEUILS['cote_min']} px de côté)"
    # L'exposition AVANT la netteté : une photo noire n'a pas de contours, et
    # la dire « floue » enverrait le photographe régler la mauvaise chose.
    if m["luminosite"] < SEUILS["lum_min"] or m["ecretage_noir"] > SEUILS["ecretage_max"]:
        return f"sous-exposée (luminosité {m['luminosite']:.0f}/255)"
    if m["luminosite"] > SEUILS["lum_max"] or m["ecretage_blanc"] > SEUILS["ecretage_max"]:
        return f"surexposée (luminosité {m['luminosite']:.0f}/255)"
    if m["nettete"] < SEUILS["nettete_min"]:
        return f"floue (netteté {m['nettete']:.0f}, minimum {SEUILS['nettete_min']:.0f})"
    if utilisabilite is not None and utilisabilite < SEUILS["utilisabilite_min"]:
        return f"note d'utilisabilité trop basse ({utilisabilite}/100)"
    return ""


# ── Corrections de base ──────────────────────────────────────────────────
def corriger(img: Image.Image, m: dict | None = None, lumiere_seulement: bool = False):
    """Balance des blancs, exposition, contraste, bruit, netteté — dosés
    pour rester naturels : un plat qui a l'air retouché ne donne pas faim.
    `lumiere_seulement` : une marque dont la charte limite la retouche à la
    lumière (réglage `kit.retouche = "lumiere"`) — ni débruitage ni netteté."""
    m = m or mesurer(img)
    img = reduire(img)
    a = np.asarray(img).astype(np.float32)
    faits = []

    # Balance des blancs sur les seuls pixels PRESQUE NEUTRES (murs, assiette,
    # ciel couvert). Le « monde gris » classique refroidit un plat — tout un
    # bowl orangé passe pour une dominante — et un plat bleuté ne donne pas faim.
    # Pas assez de neutres (gros plan d'un plat) : on ne touche pas.
    px = a.reshape(-1, 3)
    mx, mn = px.max(1), px.min(1)
    neutres = px[(mx > 90) & (mx < 245) & ((mx - mn) < 0.12 * mx)]
    if len(neutres) > 0.03 * len(px):
        moy = neutres.mean(0)
        gains = np.clip(moy.mean() / np.maximum(moy, 1), 0.93, 1.07)
        if np.abs(gains - 1).max() > 0.015:
            a *= gains
            faits.append("balance des blancs")

    lum = a.mean(2)
    bas, haut = np.percentile(lum, 0.6), np.percentile(lum, 99.4)
    if haut - bas > 30 and (bas > 6 or haut < 249):
        a = (a - bas) * (255.0 / (haut - bas))
        faits.append("contraste")
    a = np.clip(a, 0, 255)

    med = float(np.median(a.mean(2))) / 255.0
    if med < 0.36 or med > 0.66:
        cible = 0.45 if med < 0.36 else 0.56
        gamma = math.log(cible) / math.log(max(min(med, 0.98), 0.02))
        gamma = min(max(gamma, 0.6), 1.6)
        a = 255.0 * (a / 255.0) ** gamma
        faits.append("exposition")

    out = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    if lumiere_seulement:
        return out, faits
    if m.get("bruit", 0) > 3.2:
        arr = cv2.fastNlMeansDenoisingColored(np.asarray(out), None, 4, 4, 7, 21)
        out = Image.fromarray(arr)
        faits.append("réduction du bruit")
    out = out.filter(ImageFilter.UnsharpMask(radius=1.4, percent=55, threshold=3))
    faits.append("netteté")
    return out, faits


# ── Recadrage qui garde le sujet ─────────────────────────────────────────
def saillance(img: Image.Image) -> np.ndarray:
    """Résidu spectral (Hou & Zhang, 2007) : où l'œil va d'abord. Une carte
    128 px de large, normalisée 0–1, avec un léger biais vers le centre."""
    w = 128
    h = max(8, round(img.height * w / img.width))
    g = np.asarray(img.convert("L").resize((w, h), Image.BILINEAR), dtype=np.float32)
    f = np.fft.fft2(g)
    amp = np.log(np.abs(f) + 1e-6)
    res = amp - cv2.blur(amp, (3, 3))
    s = np.abs(np.fft.ifft2(np.exp(res + 1j * np.angle(f)))) ** 2
    s = cv2.GaussianBlur(s.astype(np.float32), (0, 0), 3)
    s = (s - s.min()) / (s.max() - s.min() + 1e-9)
    yy, xx = np.mgrid[0:h, 0:w]
    centre = np.exp(-(((xx - w / 2) / (0.6 * w)) ** 2 + ((yy - h / 2) / (0.6 * h)) ** 2))
    return s * (0.75 + 0.25 * centre)


def fenetre(img: Image.Image, ratio: float, sujet=None):
    """La meilleure fenêtre (x0, y0, x1, y1) en pixels au ratio voulu.
    `sujet` = boîte normalisée [x0, y0, x1, y1] donnée par la lecture
    d'image : la couper coûte très cher dans le score."""
    W, H = img.size
    if W / H > ratio:
        cw, ch = round(H * ratio), H
    else:
        cw, ch = W, round(W / ratio)
    if cw >= W and ch >= H:
        return (0, 0, W, H)
    s = saillance(img)
    sh, sw = s.shape
    if sujet:
        x0, y0, x1, y1 = [min(max(float(v), 0.0), 1.0) for v in sujet]
        s[int(y0 * sh):max(int(y1 * sh), int(y0 * sh) + 1),
          int(x0 * sw):max(int(x1 * sw), int(x0 * sw) + 1)] += 1.5
    integ = np.pad(s.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    fw, fh = cw * sw / W, ch * sh / H
    meilleur, pos = -1.0, (0, 0)
    pas = max(1, round(max(sw, sh) / 64))
    for py in range(0, max(1, int(sh - fh) + 1), pas):
        for px in range(0, max(1, int(sw - fw) + 1), pas):
            x1, y1 = min(sw, int(px + fw)), min(sh, int(py + fh))
            v = integ[y1, x1] - integ[py, x1] - integ[y1, px] + integ[py, px]
            if sujet:
                sx0, sy0, sx1, sy1 = sujet
                ox = max(0.0, min(sx1 * sw, x1) - max(sx0 * sw, px))
                oy = max(0.0, min(sy1 * sh, y1) - max(sy0 * sh, py))
                aire = max((sx1 - sx0) * sw * (sy1 - sy0) * sh, 1e-6)
                v -= 4.0 * (1 - ox * oy / aire) * integ[-1, -1] / 10
            if v > meilleur:
                meilleur, pos = v, (px, py)
    x0 = min(round(pos[0] * W / sw), W - cw)
    y0 = min(round(pos[1] * H / sh), H - ch)
    return (x0, y0, x0 + cw, y0 + ch)


def recadrer(img: Image.Image, fmt: str, sujet=None) -> Image.Image:
    tw, th = FORMATS[fmt]
    box = fenetre(img, tw / th, sujet)
    return img.crop(box).resize((tw, th), Image.LANCZOS)


# ── Habillage à la charte ────────────────────────────────────────────────
def _hex(c: str, defaut=(40, 40, 40)):
    try:
        c = c.lstrip("#")
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, AttributeError):
        return defaut


def _police(nom: str, taille: int, graisse: int | None = None):
    for f in (POLICES / f"{nom}.ttf", POLICES / nom):
        if f.exists():
            p = ImageFont.truetype(str(f), taille)
            _graisse(p, graisse or 400)
            return p
    for repli in ("Manrope.ttf",):
        if (POLICES / repli).exists():
            return ImageFont.truetype(str(POLICES / repli), taille)
    return ImageFont.load_default()


def _graisse(p, graisse: int):
    """Une police variable se règle axe par axe : le poids sur l'axe « Weight »,
    les autres (taille optique…) à leur défaut. Sans ce réglage, Manrope ou
    Montserrat sortent à leur poids par défaut — le plus maigre."""
    try:
        axes = p.get_variation_axes()
    except Exception:
        return
    valeurs = []
    for a in axes:
        nom = a["name"].decode() if isinstance(a["name"], bytes) else str(a["name"])
        if nom.lower() == "weight":
            valeurs.append(min(max(graisse, a["minimum"]), a["maximum"]))
        else:
            valeurs.append(a["default"])
    try:
        p.set_variation_by_axes(valeurs)
    except Exception:
        pass


def _lisible_sur(fond) -> tuple:
    r, g, b = fond
    return (20, 20, 20) if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else (250, 248, 240)


def couleurs(kit: dict) -> dict:
    """Les rôles de la charte : fond de bandeau, encre, accent."""
    roles = kit.get("roles") or {}
    noms = {c["name"]: c["hex"] for c in kit.get("colors", []) if c.get("hex")}
    def role(cle, defaut):
        v = roles.get(cle)
        return _hex(noms.get(v, v) if v else defaut)
    return {"primaire": role("primaire", "#333333"), "encre": role("encre", "#111111"),
            "fond": role("fond", "#F5F5F0"), "accent": role("accent", "#C0A060")}


def _logo(kit: dict):
    chemin = kit.get("logo")
    if not chemin:
        return None
    p = pathlib.Path(chemin)
    if not p.is_absolute():
        p = config.GRAINES / chemin
    if not p.exists():
        return None
    try:
        return Image.open(p).convert("RGBA")
    except Exception:
        return None


def _marque_texte(kit: dict, nom: str, hauteur: int):
    """Sans fichier de logo : le nom de la marque dans sa police de titre, sur
    une pastille à sa couleur — on n'invente jamais un logo."""
    c = couleurs(kit)
    police = _police(kit.get("fonts", {}).get("title", "Manrope"), hauteur, 800)
    l, t, r, b = police.getbbox(nom)
    pad = hauteur // 3
    im = Image.new("RGBA", (r - l + 2 * pad, b - t + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius=pad, fill=c["primaire"] + (235,))
    d.text((pad - l, pad - t), nom, font=police, fill=_lisible_sur(c["primaire"]))
    return im


def habiller(img: Image.Image, kit: dict, nom_marque: str, fmt: str, avec_logo: bool = True):
    """Logo discret au bon coin, filigrane, bandeau ou liseré aux couleurs de
    la marque, police de la marque. Les zones que l'interface d'Instagram ou
    de TikTok recouvre (bas des formats verticaux) restent libres.

    `avec_logo=False` : la marque n'a pas encore révélé son logo (SAZÚ, avant
    le 13/11/2026). Et une marque dont le logo « ne se retape jamais au
    clavier » (`logo_texte: false`) n'a pas de pastille de remplacement :
    sans fichier, pas de logo du tout."""
    img = img.convert("RGBA")
    W, H = img.size
    c = couleurs(kit)
    d = ImageDraw.Draw(img)
    faits = []
    vertical = fmt == "9:16"

    bandeau_h = 0
    texte_bandeau = kit.get("band_text", "")
    if kit.get("band", True) and not vertical:
        bandeau_h = round(H * 0.065)
        d.rectangle((0, H - bandeau_h, W, H), fill=c["primaire"] + (255,))
        if texte_bandeau:
            p = _police(kit.get("fonts", {}).get("text", "Manrope"), round(bandeau_h * 0.42), 700)
            l, t, r, b = p.getbbox(texte_bandeau)
            d.text(((W - (r - l)) / 2 - l, H - bandeau_h + (bandeau_h - (b - t)) / 2 - t),
                   texte_bandeau, font=p, fill=_lisible_sur(c["primaire"]))
        faits.append("bandeau charte")
    if kit.get("frame"):
        ep = max(4, round(W * 0.012))
        d.rectangle((ep // 2, ep // 2, W - ep // 2, H - bandeau_h - ep // 2),
                    outline=c["accent"] + (255,), width=ep)
        faits.append("liseré")

    logo = _logo(kit) if avec_logo else None
    if logo is None and avec_logo and kit.get("logo_texte", True):
        logo = _marque_texte(kit, nom_marque, round(W * 0.045))
    if logo is None:
        return _filigrane(img, kit, W, H, bandeau_h, vertical, faits, W)
    largeur = round(W * (0.16 if not vertical else 0.22))
    r = largeur / logo.width
    logo = logo.resize((largeur, max(1, round(logo.height * r))), Image.LANCZOS)
    marge = round(W * 0.035)
    coin = kit.get("logo_corner", "haut_droite" if vertical else "bas_droite")
    x = W - logo.width - marge if coin.endswith("droite") else marge
    if coin.startswith("haut"):
        y = round(H * 0.07) if vertical else marge
    else:
        y = H - bandeau_h - logo.height - marge
    img.alpha_composite(logo, (x, y))
    faits.append("logo")
    return _filigrane(img, kit, W, H, bandeau_h, vertical, faits, x)


def _filigrane(img, kit, W, H, bandeau_h, vertical, faits, x_logo):
    filigrane = kit.get("watermark", "")
    if filigrane:
        marge = round(W * 0.035)
        calque = Image.new("RGBA", img.size, (0, 0, 0, 0))
        dc = ImageDraw.Draw(calque)
        p = _police(kit.get("fonts", {}).get("detail", "CourierPrime-Regular"), round(W * 0.024))
        l, t, rr, b = p.getbbox(filigrane)
        fx = marge if x_logo > W / 2 else W - (rr - l) - marge
        fy = (H - bandeau_h - (b - t) - marge) if not vertical else round(H * 0.07)
        dc.text((fx - l, fy - t), filigrane, font=p, fill=(255, 255, 255, 150),
                stroke_width=1, stroke_fill=(0, 0, 0, 90))
        img = Image.alpha_composite(img, calque)
        faits.append("filigrane")
    return img.convert("RGB"), faits


# ── Floutage manuel (bouton « flouter », jamais automatique) ─────────────
def visages(img: Image.Image) -> list:
    """Visages et plaques repérés par OpenCV, en boîtes normalisées. Ne sert
    QUE quand quelqu'un appuie sur « flouter » : le choix est de ne rien
    flouter d'office."""
    petit = reduire(img, 1600)
    g = cv2.cvtColor(np.asarray(petit), cv2.COLOR_RGB2GRAY)
    boites = []
    for fichier in ("haarcascade_frontalface_default.xml", "haarcascade_profileface.xml",
                    "haarcascade_russian_plate_number.xml"):
        casc = cv2.CascadeClassifier(cv2.data.haarcascades + fichier)
        if casc.empty():
            continue
        for (x, y, w, h) in casc.detectMultiScale(g, 1.1, 5, minSize=(24, 24)):
            b = [round(float(v), 4) for v in (x / petit.width, y / petit.height,
                                              (x + w) / petit.width, (y + h) / petit.height)]
            if not any(_recouvre(b, autre) for autre in boites):
                boites.append(b)
    return boites


def _recouvre(a, b) -> bool:
    ox = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    oy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    petite = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return petite > 0 and ox * oy / petite > 0.5


def flouter(img: Image.Image, boites: list) -> Image.Image:
    out = img.copy()
    W, H = out.size
    for b in boites:
        x0, y0, x1, y1 = b
        # une marge de 15 % : un flou qui laisse dépasser un menton ne protège personne
        mx, my = (x1 - x0) * 0.15, (y1 - y0) * 0.15
        box = (max(0, int((x0 - mx) * W)), max(0, int((y0 - my) * H)),
               min(W, int((x1 + mx) * W)), min(H, int((y1 + my) * H)))
        if box[2] - box[0] < 2 or box[3] - box[1] < 2:
            continue
        zone = out.crop(box)
        rayon = max(8, (box[2] - box[0]) // 6)
        out.paste(zone.filter(ImageFilter.GaussianBlur(rayon)), box)
    return out


# ── Cartes typographiques (compte à rebours, annonces) ───────────────────
def _lignes(texte: str, police, largeur_max: int) -> list:
    mots, lignes, cour = texte.split(), [], ""
    for m in mots:
        essai = (cour + " " + m).strip()
        if police.getlength(essai) <= largeur_max or not cour:
            cour = essai
        else:
            lignes.append(cour)
            cour = m
    if cour:
        lignes.append(cour)
    return lignes


def carte(kit: dict, nom_marque: str, titre: str, sous_titre: str = "", detail: str = "",
          fmt: str = "4:5", avec_logo: bool = True) -> Image.Image:
    """Un visuel 100 % charte quand il n'y a pas de photo : « J-7 », une date
    d'ouverture, une offre. Titre dans la police de titre, le reste dans la
    police de texte, le détail dans la police de détail."""
    W, H = FORMATS[fmt]
    c = couleurs(kit)
    img = Image.new("RGB", (W, H), c["fond"])
    d = ImageDraw.Draw(img)
    marge = round(W * 0.09)
    polices = kit.get("fonts", {})
    pt = _police(polices.get("title", "Manrope"), round(W * (0.2 if len(titre) <= 6 else 0.11)), 800)
    ps = _police(polices.get("text", "Manrope"), round(W * 0.052), 600)
    pd = _police(polices.get("detail", "CourierPrime-Regular"), round(W * 0.034))
    y = round(H * 0.24)
    for ligne in _lignes(titre, pt, W - 2 * marge):
        l, t, r, b = pt.getbbox(ligne)
        d.text(((W - (r - l)) / 2 - l, y - t), ligne, font=pt, fill=c["primaire"])
        y += (b - t) + round(W * 0.03)
    y += round(W * 0.04)
    for ligne in _lignes(sous_titre, ps, W - 2 * marge):
        l, t, r, b = ps.getbbox(ligne)
        d.text(((W - (r - l)) / 2 - l, y - t), ligne, font=ps, fill=c["encre"])
        y += (b - t) + round(W * 0.025)
    if detail:
        l, t, r, b = pd.getbbox(detail)
        d.text(((W - (r - l)) / 2 - l, H - round(H * 0.17)), detail, font=pd, fill=c["encre"])
    d.rectangle((0, H - round(H * 0.012), W, H), fill=c["accent"])
    kit_carte = dict(kit, band=False, watermark="")
    return habiller(img, kit_carte, nom_marque, fmt, avec_logo)[0]


# ── Enregistrement ───────────────────────────────────────────────────────
def enregistrer_jpeg(img: Image.Image, chemin: pathlib.Path, qualite: int = 90) -> bytes:
    """JPEG sans EXIF (aucune position GPS ne sort), sRGB, progressif."""
    tampon = io.BytesIO()
    img.convert("RGB").save(tampon, "JPEG", quality=qualite, optimize=True, progressive=True)
    octets = tampon.getvalue()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(octets)
    return octets
