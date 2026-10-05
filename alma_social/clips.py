"""Une vidéo longue devient cinq clips (§ 9 — « une visite de chantier de
4 minutes donne cinq clips, chacun noté sur son potentiel »).

Tout se fait ici, en local, avec l'encodeur que livre `imageio-ffmpeg` :
aucune vidéo ne sort de la maison pour être découpée.

1. LIRE la vidéo à 2 images par seconde, en petit (160 px) : pour chaque
   demi-seconde, la NETTETÉ (une image floue de bougé ne retient personne),
   la LUMIÈRE (ni noire, ni brûlée), le MOUVEMENT (un plan qui vit, sans
   être un tremblement) et le SON (quelqu'un parle, une machine tourne) ;
   les changements de plan francs sont repérés comme COUPES.
2. CHOISIR des fenêtres de 8 à 15 secondes — la longueur qu'un Reel ou un
   Short tient jusqu'au bout —, les mieux notées, sans chevauchement, calées
   sur les coupes quand il y en a une à moins d'une seconde (un clip qui
   commence au milieu d'un geste paraît coupé par erreur).
3. FABRIQUER chaque clip en 9:16 (1080×1920, H.264, son AAC) : recadrage
   au centre, l'accroche écrite sur les deux premières secondes, la marque
   en coin si son logo est permis à cette date.
4. Une IMAGE FIXE par clip — la plus nette de la fenêtre — entre dans la
   banque comme une photo déposée : c'est elle que le planificateur place,
   et c'est elle qui porte le clip vers les réseaux vidéo.

Ce qui n'est PAS fait, et c'est dit : aucun sous-titre. Il faudrait
transcrire la parole, et rien dans la chaîne ne le fait aujourd'hui ; un
sous-titre inventé serait pire que pas de sous-titre. Aucune musique non plus
(le réseau ajoute un titre de SA bibliothèque).
"""
from __future__ import annotations

import io
import logging
import pathlib
import subprocess

import numpy as np
from PIL import Image, ImageDraw
from sqlalchemy import insert, update

from . import db, images, journal, stockage

log = logging.getLogger("alma_social.clips")

EXTENSIONS = ("mp4", "mov", "m4v", "webm")
TAILLE_MAX = 200 * 1024 * 1024          # ≈ 4 minutes filmées au téléphone en 1080p
DUREE_MAX_S = 20 * 60                   # au-delà, ce n'est plus une visite : c'est un film
ECHANTILLONS_PAR_S = 2
COTE = 160                              # côté de l'image d'analyse
CLIP_MIN_S, CLIP_MAX_S = 8.0, 15.0
NB_CLIPS = 5
NOTE_MIN = 0.35                         # sous cette note (0-1), un passage ne vaut pas un clip
CALAGE_S = 1.0                          # une coupe à moins d'une seconde : on s'y cale
W, H = 1080, 1920
VERSION = "clips-1"


def est_video(octets: bytes, nom: str = "") -> bool:
    """Par le contenu d'abord (un nom de fichier ment), puis par l'extension."""
    tete = octets[:16]
    if len(tete) >= 12 and tete[4:8] == b"ftyp":
        marque_iso = tete[8:12]
        return marque_iso not in (b"heic", b"heix", b"mif1", b"msf1", b"avif", b"heim", b"heis")
    if tete[:4] == b"\x1a\x45\xdf\xa3":          # Matroska / WebM
        return True
    return pathlib.Path(nom or "").suffix.lower().lstrip(".") in EXTENSIONS and not tete[:3] == b"\xff\xd8\xff"


def _ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def sonder(chemin: pathlib.Path) -> dict:
    """→ {duree, largeur, hauteur, ips} — lus par ffmpeg lui-même."""
    import imageio_ffmpeg
    gen = imageio_ffmpeg.read_frames(str(chemin))
    try:
        meta = next(gen)
    finally:
        gen.close()
    l, h = meta.get("size") or (0, 0)
    if meta.get("rotate") in (90, 270, -90):
        l, h = h, l
    return {"duree": float(meta.get("duration") or 0), "largeur": int(l), "hauteur": int(h),
            "ips": float(meta.get("fps") or 0)}


# ── 1. Lire ──────────────────────────────────────────────────────────────
def mesurer(chemin: pathlib.Path) -> dict:
    """→ {pas, nettete[], lumiere[], mouvement[], son[], coupes[]} — une valeur
    par demi-seconde ; `coupes` en secondes."""
    import cv2
    cmd = [_ffmpeg(), "-v", "error", "-i", str(chemin), "-vf",
           f"fps={ECHANTILLONS_PAR_S},scale={COTE}:{COTE}", "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    brut = subprocess.run(cmd, capture_output=True, timeout=600).stdout
    n = len(brut) // (COTE * COTE)
    if not n:
        raise ValueError("cette vidéo ne se lit pas")
    vues = np.frombuffer(brut[:n * COTE * COTE], np.uint8).reshape(n, COTE, COTE)
    nettete, lumiere, mouvement = [], [], [0.0]
    for i, v in enumerate(vues):
        nettete.append(float(cv2.Laplacian(v, cv2.CV_32F).var()))
        lumiere.append(float(v.mean()))
        if i:
            mouvement.append(float(np.abs(v.astype(np.int16) - vues[i - 1].astype(np.int16)).mean()))
    # Le son : l'énergie par demi-seconde (mono 8 kHz). Une vidéo sans piste
    # son n'est pas une erreur — elle est seulement muette.
    son = [0.0] * n
    try:
        cmd = [_ffmpeg(), "-v", "error", "-i", str(chemin), "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"]
        a = np.frombuffer(subprocess.run(cmd, capture_output=True, timeout=600).stdout, np.int16)
        pas = 8000 // ECHANTILLONS_PAR_S
        for i in range(min(n, len(a) // pas)):
            bloc = a[i * pas:(i + 1) * pas].astype(np.float32)
            son[i] = float(np.sqrt((bloc ** 2).mean()))
    except Exception:
        log.info("pas de son lisible dans %s", chemin.name)
    # Une coupe : un saut d'image très au-dessus du mouvement habituel.
    mv = np.array(mouvement)
    seuil = max(28.0, float(np.median(mv)) * 4 + 6)
    coupes = [round(i / ECHANTILLONS_PAR_S, 2) for i in range(1, n) if mv[i] > seuil]
    return {"pas": 1 / ECHANTILLONS_PAR_S, "nettete": nettete, "lumiere": lumiere, "mouvement": mouvement,
            "son": son, "coupes": coupes}


def _norme(x: list) -> np.ndarray:
    a = np.array(x, dtype=np.float64)
    if not len(a):
        return a
    lo, hi = np.percentile(a, 5), np.percentile(a, 95)
    return np.clip((a - lo) / (hi - lo), 0, 1) if hi > lo else np.full_like(a, 0.5)


def notes(m: dict) -> np.ndarray:
    """Une note de 0 à 1 par demi-seconde. Le mouvement est noté en cloche :
    un plan fixe ennuie, un tremblement fatigue."""
    nette = _norme(m["nettete"])
    lum = np.array(m["lumiere"])
    lumiere = np.clip(1 - np.abs(lum - 128) / 100, 0, 1)
    mv = _norme(m["mouvement"])
    vie = 1 - np.abs(mv - 0.45) / 0.55
    son = _norme(m["son"]) if any(m["son"]) else np.full(len(lum), 0.4)
    coupe = np.zeros(len(lum))
    for c in m["coupes"]:
        i = int(round(c / m["pas"]))
        if i < len(coupe):
            coupe[i] = 1
    # Le saut d'image d'une coupe n'est pas du « mouvement » à récompenser.
    vie = np.where(coupe > 0, 0.3, vie)
    return 0.35 * nette + 0.2 * lumiere + 0.25 * np.clip(vie, 0, 1) + 0.2 * son


# ── 2. Choisir ───────────────────────────────────────────────────────────
def choisir(m: dict, duree: float, combien: int = NB_CLIPS) -> list:
    """→ [{debut, fin, note (0-100), coupe_debut, coupe_fin}], dans l'ordre du film."""
    s = notes(m)
    pas = m["pas"]
    n = len(s)
    total = min(duree or n * pas, n * pas)
    if total < 3:
        return []
    if total <= CLIP_MIN_S:
        return [{"debut": 0.0, "fin": round(total, 2), "note": int(round(100 * float(s.mean()))),
                 "coupe_debut": False, "coupe_fin": False}]
    candidats = []
    for longueur in (8.0, 10.0, 12.0, 15.0):
        k = int(longueur / pas)
        if k > n:
            continue
        cum = np.concatenate([[0], np.cumsum(s)])
        for i in range(0, n - k + 1):
            moy = (cum[i + k] - cum[i]) / k
            # Une fenêtre qui traverse une coupe raconte deux choses : légère pénalité.
            dedans = sum(1 for c in m["coupes"] if i * pas + 0.75 < c < (i + k) * pas - 0.75)
            # Plus long est mieux s'il tient la note (la durée de visionnage paie).
            candidats.append((moy - 0.06 * dedans + 0.05 * (longueur - 8) / 7, i * pas, (i + k) * pas))
    candidats.sort(key=lambda x: -x[0])
    if not candidats:
        return []
    # Un passage mort (noir, flou, immobile et muet) ne devient pas un clip
    # pour faire le compte : cinq clips est un plafond, pas un objectif.
    plancher = max(NOTE_MIN, 0.6 * candidats[0][0])
    pris = []
    for note, d, f in candidats:
        if note < plancher:
            break
        if all(f <= p[1] - 0.5 or d >= p[2] + 0.5 for p in pris):
            pris.append((note, d, f))
        if len(pris) >= combien:
            break
    out = []
    for note, d, f in sorted(pris, key=lambda x: x[1]):
        d2 = _caler(d, m["coupes"])
        f2 = _caler(f, m["coupes"])
        if f2 - d2 < CLIP_MIN_S - 1:
            d2, f2 = d, f
        out.append({"debut": round(d2, 2), "fin": round(min(f2, total), 2),
                    "note": int(round(100 * min(1.0, max(0.0, note)))),
                    "coupe_debut": d2 != d, "coupe_fin": f2 != f})
    return out


def _caler(t: float, coupes: list) -> float:
    """Le bord d'un clip se cale sur la coupe la plus proche, si elle est à moins d'une seconde."""
    proches = [c for c in coupes if abs(c - t) <= CALAGE_S]
    return min(proches, key=lambda c: abs(c - t)) if proches else t


def meilleur_instant(m: dict, debut: float, fin: float) -> float:
    """L'instant le plus net de la fenêtre (hors coupes) — l'image fixe du clip."""
    pas = m["pas"]
    i0, i1 = int(debut / pas), max(int(debut / pas) + 1, int(fin / pas))
    ns = m["nettete"][i0:i1]
    if not ns:
        return debut
    lum = m["lumiere"][i0:i1]
    sc = [x * (1 if 40 < lum[j] < 215 else 0.3) for j, x in enumerate(ns)]
    return round((i0 + int(np.argmax(sc))) * pas, 2)


# ── 3. Fabriquer ─────────────────────────────────────────────────────────
def image_a(chemin: pathlib.Path, t: float) -> bytes:
    """→ une image PNG pleine définition à l'instant `t`."""
    cmd = [_ffmpeg(), "-v", "error", "-ss", f"{t:.2f}", "-i", str(chemin), "-frames:v", "1",
           "-f", "image2pipe", "-vcodec", "png", "-"]
    octets = subprocess.run(cmd, capture_output=True, timeout=120).stdout
    if not octets:
        raise ValueError(f"aucune image à {t:.1f} s")
    return octets


def calques(m: dict, accroche: str, avec_logo: bool) -> tuple:
    """→ (calque de l'accroche, calque de la marque) en RGBA 1080×1920."""
    from .studio import _polices, _texte_centre
    kit = m.get("kit") or {}
    c = images.couleurs(kit)
    acc = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if accroche:
        titre_p, _, _ = _polices(m)
        pa = images._police(titre_p, 96 if len(accroche) < 30 else 78, 800)
        _texte_centre(ImageDraw.Draw(acc), accroche, pa, round(H * 0.30), W, (255, 255, 255, 255), 80,
                      contour=(6, c["encre"] + (255,)))
    marque = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if avec_logo:
        logo = images._logo(kit) or images._marque_texte(kit, m["name"], 46)
        logo.thumbnail((300, 130))
        # Haut gauche, sous la barre d'état et hors des boutons de droite.
        marque.alpha_composite(logo, (48, 150))
    return acc, marque


def encoder(source: pathlib.Path, debut: float, fin: float, sortie: pathlib.Path, calque_accroche: Image.Image,
            calque_marque: Image.Image, avec_son: bool = True) -> float:
    """Le clip 9:16 : recadré au centre, accroche 2 s, marque en coin. → durée."""
    sortie.parent.mkdir(parents=True, exist_ok=True)
    tmp_a, tmp_m = sortie.with_suffix(".acc.png"), sortie.with_suffix(".mar.png")
    calque_accroche.save(tmp_a)
    calque_marque.save(tmp_m)
    duree = round(fin - debut, 2)
    filtre = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps=30[v];"
              f"[v][2:v]overlay=0:0[vm];[vm][1:v]overlay=0:0:enable='lt(t,2)'[o]")
    cmd = [_ffmpeg(), "-y", "-v", "error", "-ss", f"{debut:.2f}", "-i", str(source), "-i", str(tmp_a),
           "-i", str(tmp_m), "-t", f"{duree:.2f}", "-filter_complex", filtre, "-map", "[o]"]
    cmd += (["-map", "0:a?", "-c:a", "aac", "-b:a", "128k"] if avec_son else ["-an"])
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(sortie)]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=900)
    finally:
        tmp_a.unlink(missing_ok=True)
        tmp_m.unlink(missing_ok=True)
    if r.returncode or not sortie.exists():
        raise ValueError("l'encodage du clip a échoué : " + r.stderr.decode("utf-8", "replace")[-300:])
    return duree


def _accroche(m: dict, note: str) -> str:
    """La phrase dictée au dépôt d'abord (elle dit ce qu'on voit) ; sinon la
    signature de la marque. Jamais une phrase inventée sur un chantier réel."""
    note = (note or "").strip()
    if 4 <= len(note) <= 60:
        return note[0].upper() + note[1:]
    return (m.get("kit") or {}).get("band_text") or ""


def decouper(video_id: int, par: str = "systeme") -> list:
    """La vidéo (un asset `kind="video"`) → ses clips. Chaque clip est un
    travail du studio (`media_jobs`, type `clip`) porté par son image fixe,
    elle-même déposée en banque. → la liste des travaux créés."""
    from . import acces, pipeline, studio
    v = pipeline.asset(video_id)
    if not v or v["kind"] != "video":
        raise ValueError("vidéo inconnue")
    m = acces.marque(v["brand_id"])
    source = stockage.chemin(v["original_path"])
    info = sonder(source)
    mes = mesurer(source)
    fenetres = choisir(mes, info["duree"])
    avec_logo = acces.logo_permis(m)
    accroche = _accroche(m, v.get("note"))
    acc, mar = calques(m, accroche, avec_logo)
    avec_son = any(mes["son"])
    racine = stockage.racine()
    faits_ok = []
    for n, f in enumerate(fenetres, 1):
        ref = f"video:{video_id}:clip{n}"
        if studio.travail_par_ref(ref):
            continue                                    # déjà fait (reprise après une coupure)
        t = meilleur_instant(mes, f["debut"], f["fin"])
        still = pipeline.recevoir(m["id"], png_en_jpeg(image_a(source, t)), f"video-{video_id}-{n}.jpg",
                                  client_ref=f"video:{video_id}:still{n}", auteur={"name": par},
                                  pilier=v.get("pillar") or "", note=v.get("note") or "")
        with db.moteur().begin() as c:
            jid = c.execute(insert(db.media_jobs).values(
                brand_id=m["id"], asset_ids=[still["id"], video_id], type="clip", statut="attente",
                sortie={"ref": ref}, created_at=db.maintenant())).inserted_primary_key[0]
        rel = f"studio/{m['id']}/{jid}/clip.mp4"
        try:
            duree = encoder(source, f["debut"], f["fin"], racine / rel, acc, mar, avec_son)
            couverture = images.recadrer(images.ouvrir(stockage.chemin(still["original_path"])), "9:16")
            couverture = Image.alpha_composite(couverture.convert("RGBA").resize((W, H)), mar).convert("RGB")
            images.enregistrer_jpeg(couverture, (racine / rel).with_suffix(".jpg"), 86)
            faits = [f"extrait de {f['debut']:.0f} s à {f['fin']:.0f} s d'une vidéo de {info['duree']:.0f} s",
                     "recadré en 9:16 au centre",
                     "calé sur un changement de plan" if f["coupe_debut"] or f["coupe_fin"] else "pris dans un plan continu",
                     f"accroche « {accroche} » sur les deux premières secondes" if accroche else "sans accroche (aucune phrase au dépôt)",
                     "marque en coin" if avec_logo else "logo caché (pas encore permis)",
                     "son d'origine" if avec_son else "vidéo muette",
                     "aucun sous-titre : la parole n'est pas transcrite",
                     "aucune musique incrustée (bibliothèque du réseau)"]
            rid = studio._ranger(jid, still["id"], 0, (racine / rel).read_bytes(), rel, True, faits, duree)
            with db.moteur().begin() as c:
                c.execute(update(db.media_jobs).where(db.media_jobs.c.id == jid).values(
                    statut="fait", score=f["note"], traitements=faits,
                    sortie={"ref": ref, "fichiers": [{"rendition_id": rid, "video": True, "duree": duree}],
                            "params": {"accroche": accroche, "avec_logo": avec_logo, "auto": True,
                                       "debut": f["debut"], "fin": f["fin"], "instant_fixe": t}}))
            faits_ok.append(jid)
        except Exception as e:
            with db.moteur().begin() as c:
                c.execute(update(db.media_jobs).where(db.media_jobs.c.id == jid).values(
                    statut="echec", erreur=str(e)[:500]))
            raise
    journal.noter(par, "decoupage", "asset", video_id, m["id"],
                  apres={"duree": info["duree"], "clips": len(fenetres), "notes": [f["note"] for f in fenetres]})
    return faits_ok


def png_en_jpeg(octets: bytes) -> bytes:
    buf = io.BytesIO()
    Image.open(io.BytesIO(octets)).convert("RGB").save(buf, "JPEG", quality=92)
    return buf.getvalue()
