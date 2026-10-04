"""Une photo devient un clip vertical — pour les réseaux qui n'acceptent que la vidéo.

YouTube Shorts ne publie pas d'image fixe. Plutôt que de laisser ce réseau
muet, la photo y part en clip 9:16 de quelques secondes avec un lent zoom
(« effet Ken Burns »), encodé en H.264 — le format que tous les réseaux lisent.
L'encodeur est celui que livre `imageio-ffmpeg` : rien à installer sur la machine.
"""
from __future__ import annotations

import pathlib

import numpy as np
from PIL import Image

DUREE_S = 6
IPS = 24


def disponible() -> bool:
    try:
        import imageio_ffmpeg
        imageio_ffmpeg.get_ffmpeg_exe()
        return True
    except Exception:
        return False


def clip(image_9x16: Image.Image, sortie: pathlib.Path, duree: int = DUREE_S) -> float:
    """→ la durée réelle en secondes. `image_9x16` est déjà habillée (1080×1920)."""
    import imageio_ffmpeg
    W, H = 1080, 1920
    base = image_9x16.convert("RGB").resize((W, H), Image.LANCZOS)
    n = duree * IPS
    sortie.parent.mkdir(parents=True, exist_ok=True)
    gen = imageio_ffmpeg.write_frames(str(sortie), (W, H), fps=IPS, codec="libx264",
                                      pix_fmt_out="yuv420p", quality=7, macro_block_size=8,
                                      output_params=["-movflags", "+faststart"])
    gen.send(None)
    try:
        for i in range(n):
            z = 1.0 + 0.07 * i / max(n - 1, 1)              # 7 % de zoom, lentement
            cw, ch = round(W / z), round(H / z)
            x0, y0 = (W - cw) // 2, round((H - ch) * 0.45)
            image = base.crop((x0, y0, x0 + cw, y0 + ch)).resize((W, H), Image.BILINEAR)
            gen.send(np.ascontiguousarray(np.asarray(image)))
    finally:
        gen.close()
    return float(duree)
