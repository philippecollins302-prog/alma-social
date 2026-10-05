"""Banc : une vidéo longue devient des clips notés.

La vidéo est fabriquée ici, par ffmpeg lui-même, avec des passages que tout
monteur jugerait mauvais (noir immobile et muet, gris flou et immobile) et
d'autres qu'il garderait (une scène nette qui bouge, avec du son). Le banc
exige que les clips tombent sur les bons passages, qu'ils soient au format
des réseaux vidéo, que chaque clip ait son image fixe en banque — et que
cette image porte le clip vers Instagram, TikTok et YouTube."""
import subprocess

import socle
from socle import egal, verifier

from sqlalchemy import select

from alma_social import acces, clips, db, file, graines, pipeline, stockage, studio

socle.figer(2026, 10, 5, 6)
graines.semer()
dossier = stockage.racine() / "banc-clips"
dossier.mkdir(parents=True, exist_ok=True)
source = dossier / "visite.mp4"

# 0-8 s : noir, immobile, muet · 8-22 s : mire animée nette + son ·
# 22-30 s : gris uni, muet · 30-44 s : fractale qui zoome + son · 44-50 s : noir.
SEG = [("color=c=0x080808:s=1280x720:r=25", 8, False), ("testsrc2=s=1280x720:r=25", 14, True),
       ("color=c=0x808080:s=1280x720:r=25", 8, False), ("mandelbrot=s=1280x720:r=25", 14, True),
       ("color=c=0x080808:s=1280x720:r=25", 6, False)]
cmd = [clips._ffmpeg(), "-y", "-v", "error"]
for src, d, _ in SEG:
    cmd += ["-f", "lavfi", "-t", str(d), "-i", src]
for _, d, son in SEG:
    cmd += ["-f", "lavfi", "-t", str(d), "-i", "sine=frequency=440:sample_rate=44100" if son
            else "anullsrc=r=44100:cl=mono"]
n = len(SEG)
filtre = "".join(f"[{i}:v][{n + i}:a]" for i in range(n)) + f"concat=n={n}:v=1:a=1[v][a]"
cmd += ["-filter_complex", filtre, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p", "-c:a", "aac", str(source)]
subprocess.run(cmd, check=True, capture_output=True)
octets = source.read_bytes()

print("— Reconnaître une vidéo")
verifier(clips.est_video(octets, "visite.mp4"), "un MP4 est une vidéo")
verifier(clips.est_video(octets, "photo.jpg"), "même mal nommé : c'est le contenu qui décide")
verifier(not clips.est_video(socle.image("chantier"), "x.mp4"), "un JPEG nommé .mp4 n'est pas une vidéo")
heic = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 20
verifier(not clips.est_video(heic, "IMG_1.HEIC"), "une photo HEIC (ftyp heic) n'est pas une vidéo")
info = clips.sonder(source)
verifier(49 <= info["duree"] <= 51, f"durée lue : {info['duree']:.1f} s")
egal((info["largeur"], info["hauteur"]), (1280, 720), "dimensions lues")

print("— Lire et choisir")
mes = clips.mesurer(source)
egal(len(mes["nettete"]), 100, "deux mesures par seconde")
verifier(any(abs(c - 8) <= 0.5 for c in mes["coupes"]), f"la coupe à 8 s est vue ({mes['coupes']})")
verifier(any(abs(c - 30) <= 0.5 for c in mes["coupes"]), "la coupe à 30 s est vue")
verifier(max(mes["son"][20:40]) > 10 * max(1, max(mes["son"][:14])), "le son est entendu là où il y en a")
fen = clips.choisir(mes, info["duree"])
verifier(1 <= len(fen) <= clips.NB_CLIPS, f"{len(fen)} clip(s) choisis")
for f in fen:
    verifier(clips.CLIP_MIN_S - 1 <= f["fin"] - f["debut"] <= clips.CLIP_MAX_S, f"clip {f['debut']}–{f['fin']} : 7 à 15 s")
for a, b in zip(fen, fen[1:]):
    verifier(a["fin"] <= b["debut"], "aucun chevauchement")
meilleurs = sorted(fen, key=lambda f: -f["note"])[:2]
bons = [(8, 22), (30, 44)]
for f in meilleurs:
    milieu = (f["debut"] + f["fin"]) / 2
    verifier(any(d <= milieu <= e for d, e in bons), f"un des deux meilleurs clips ({f['debut']}–{f['fin']}, "
                                                    f"note {f['note']}) tombe sur un passage vivant")
verifier(any(abs(f["debut"] - 8) <= 0.5 or abs(f["debut"] - 30) <= 0.5 for f in fen),
         "au moins un clip commence sur un changement de plan")
verifier(not any(f["fin"] <= 8 or (22 <= f["debut"] and f["fin"] <= 30) or f["debut"] >= 44 for f in fen),
         "aucun clip pris entièrement dans un passage mort (noir, gris immobile)")
verifier(max(f["fin"] - f["debut"] for f in fen) >= 12, "un passage vivant de 14 s donne un clip long")
# Le calage : une fenêtre qui commence 0,5 s avant une coupe s'y recale.
egal(clips._caler(29.5, [30.0]), 30.0, "un début à 0,5 s d'une coupe s'y cale")
egal(clips._caler(44.5, [44.0]), 44.0, "une fin juste après une coupe s'y cale")
egal(clips._caler(20.0, [30.0]), 20.0, "une coupe lointaine ne déplace rien")
t = clips.meilleur_instant(mes, 30, 44)
verifier(30 <= t <= 44, "l'image fixe est prise dans la fenêtre")
verifier(clips.meilleur_instant(mes, 22, 30) is not None, "une fenêtre plate rend quand même un instant")
court = {k: v[:10] if isinstance(v, list) else v for k, v in mes.items()}
court["coupes"] = []
egal(len(clips.choisir(court, 5.0)), 1, "une vidéo de 5 s donne un seul clip, entière")
egal(clips.choisir({**court, "nettete": court["nettete"][:4], "lumiere": court["lumiere"][:4],
                    "mouvement": court["mouvement"][:4], "son": court["son"][:4]}, 2.0), [],
     "une vidéo de 2 s ne donne rien")

print("— Le dépôt d'une vidéo")
a = pipeline.recevoir("rega", octets, "visite.mp4", client_ref="ref-video-1", note="visite du chantier de Lattes")
egal(a["kind"], "video", "rangée comme vidéo")
egal(a["status"], "decoupage", "en découpage")
verifier(a["original_path"].endswith(".mp4"), "l'original garde son extension")
egal(pipeline.recevoir("rega", octets, "visite.mp4", client_ref="ref-video-1")["deja"], True,
     "le renvoi de la file du téléphone ne crée rien")
with db.moteur().connect() as c:
    jobs = [j for j in db.lignes(c.execute(select(db.jobs))) if j["kind"] == "decouper"]
egal(len(jobs), 1, "un découpage en file")
try:
    pipeline.recevoir("rega", octets[:4] + b"ftypisom" + b"\x00" * 1000, "casse.mp4")
    verifier(False, "une vidéo illisible est refusée")
except ValueError as e:
    verifier("ne se lit pas" in str(e), "une vidéo illisible est refusée, et c'est dit")
gros = clips.TAILLE_MAX
clips.TAILLE_MAX = 1000
try:
    pipeline.recevoir("rega", octets, "lourde.mp4")
    verifier(False, "une vidéo trop lourde est refusée")
except ValueError as e:
    verifier("1080p" in str(e), "une vidéo trop lourde est refusée, avec le geste à faire")
clips.TAILLE_MAX = gros

print("— Le découpage")
file.vider(1)                               # seulement le découpage : les images fixes attendent
v = pipeline.asset(a["id"])
egal(v["status"], "decoupee", "la vidéo est découpée")
with db.moteur().connect() as c:
    tr = [j for j in db.lignes(c.execute(select(db.media_jobs).where(db.media_jobs.c.type == "clip")))]
egal(len(tr), len(fen), "un travail par clip")
verifier(all(j["statut"] == "fait" for j in tr), "tous fabriqués")
for j in tr:
    w = studio.travail(j["id"])
    f = w["fichiers"][0]
    verifier(f["video"] and f["url"].endswith(".mp4"), "le clip est une vidéo servie par jeton")
    r = pipeline._info_rendu(pipeline._un(db.renditions, f["rendition_id"]))
    egal((r["largeur"], r["hauteur"]), (1080, 1920), "clip en 9:16")
    verifier(clips.CLIP_MIN_S - 1 <= r["duree"] <= clips.CLIP_MAX_S, f"durée {r['duree']} s")
    sortie = stockage.chemin(pipeline._un(db.renditions, f["rendition_id"])["path"])
    egal(clips.sonder(sortie)["largeur"], 1080, "ffmpeg relit le clip en 1080 de large")
    verifier(sortie.with_suffix(".jpg").exists(), "le clip a sa couverture")
    verifier("aucun sous-titre : la parole n'est pas transcrite" in j["traitements"],
             "il dit qu'il n'a pas de sous-titres")
    verifier(any("visite du chantier de lattes" in x.lower() for x in j["traitements"]), "l'accroche vient de la phrase dictée")
    verifier(isinstance(j["score"], int) and 0 <= j["score"] <= 100, "chaque clip est noté sur 100")
    egal(j["asset_ids"][1], a["id"], "le travail cite sa vidéo")
    still = pipeline.asset(j["asset_ids"][0])
    egal(still["kind"], "photo", "son image fixe est une photo")
    verifier(still["client_ref"].startswith(f"video:{a['id']}:still"), "rattachée à la vidéo")
    egal(still["note"], "visite du chantier de Lattes", "elle garde la phrase dictée")
    egal(set(studio.montages_de(still["id"])), {"clip"}, "elle porte son clip")

print("— Le clip part sur les réseaux vidéo")
m = acces.marque("rega")
mt = studio.montages_de(tr[0]["asset_ids"][0])
egal(studio.montage_pour("instagram", mt)["type"], "clip", "Instagram → le clip")
egal(studio.montage_pour("tiktok", mt)["type"], "clip", "TikTok → le clip")
egal(studio.montage_pour("facebook", mt)["type"], "clip", "Facebook sans carrousel → le clip")
egal(studio.montage_pour("gbp", mt), None, "Google : la photo")
egal(studio.montage_pour("linkedin", {"carrousel": {"type": "carrousel"}, **mt})["type"], "carrousel",
     "LinkedIn préfère un carrousel s'il existe")

print("— La reprise ne refait rien")
avant = len(tr)
pipeline._maj(db.assets, a["id"], status="decoupage")
clips.decouper(a["id"])
with db.moteur().connect() as c:
    egal(len(db.lignes(c.execute(select(db.media_jobs).where(db.media_jobs.c.type == "clip")))), avant,
         "un découpage relancé ne fabrique pas de doublons")

print("— Le studio n'en fait pas une rafale")
verifier(all(not (x.get("client_ref") or "").startswith("video:")
             for j in studio.travaux(["sazu"]) for x in [pipeline.asset(i) for i in j["asset_ids"]] if x),
         "aucune image fixe de vidéo dans un montage SAZÚ")

print("— De la banque aux réseaux")
from alma_social import planificateur
planificateur.demarrer(acces.marque("rega"))
socle.figer(2026, 10, 5, 7)
file.vider(300)
with db.moteur().connect() as c:
    posts = db.lignes(c.execute(select(db.posts).where(db.posts.c.asset_id.in_([j["asset_ids"][0] for j in tr]))))
print("    publications préparées :", sorted({(p["platform"], p["post_format"], p["status"]) for p in posts}))
video_pf = [p for p in posts if p["platform"] in ("instagram", "tiktok", "youtube") and p["status"] != "refuse"]
verifier(video_pf and all(p["post_format"] == "clip" and p["media_job_id"] for p in video_pf),
         "sur Instagram, TikTok, YouTube : c'est le clip qui part")
verifier(all(p["post_format"] != "clip" for p in posts if p["platform"] == "gbp"), "sur Google : la photo")

socle.fin()
