"""Le Coach terrain (parcours D) — ce qu'il faut photographier, précisément, et avant quand.

« SAZÚ avant vendredi : 3 bowls en lumière du jour, vue de dessus, fond crème ;
1 vidéo de 10 s du dressage, téléphone fixe ; 1 photo de l'équipe en tablier. »

Le brief part des créneaux vides des sept prochains jours (moins ce que la
banque peut déjà remplir), de la fiche photo de chaque pilier et de la
direction artistique de la marque. Chaque plan dit QUOI, COMMENT, et un
exemple. Il ne promet rien : il demande des photos.

Le viseur de l'application reprend les mêmes consignes en surimpression
(`/api/coach`), avec la grille et les conseils en direct (lumière, horizon,
netteté) calculés sur le téléphone.
"""
from __future__ import annotations

import datetime as dt

from . import acces, marque as marque_, planificateur

_JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]

# Comment photographier, par secteur — des gestes, pas des adjectifs.
COMMENT = {
    "food": ["près d'une fenêtre, lumière du jour, jamais le néon seul",
             "vue de dessus pour un bowl, ou à 45° pour la texture",
             "le bowl entier dans le cadre, rien d'autre autour (ni sachet, ni ticket)"],
    "btp": ["recule de deux pas : l'ensemble d'abord, puis un détail de finition",
            "horizon droit, téléphone à hauteur de poitrine",
            "zone rangée, aucun visage sans accord, aucune plaque lisible"],
    "b2b": ["des gens réels dans un lieu réel, la lumière derrière toi",
            "de face, à hauteur d'yeux",
            "aucun écran ni document lisible dans le cadre"],
    "retail": ["le produit en situation, lumière naturelle", "un plan large, un plan serré", "fond rangé"],
    "b2c": ["lumière du jour", "le sujet au centre", "téléphone stable"],
}
VIDEO = {
    "food": "1 vidéo de 10 s du dressage, téléphone posé et fixe, un seul geste du début à la fin",
    "btp": "1 vidéo de 10 s d'un geste de pose ou d'un panoramique lent, téléphone tenu à deux mains",
    "b2b": "1 vidéo de 10 s de l'équipe au travail, téléphone fixe",
}
RESEAUX_VIDEO = {"tiktok", "youtube", "instagram"}


def brief(m: dict) -> dict | None:
    """→ {marque, avant, titre, plans:[{n, quoi, comment, exemple}], comment, phrase} ou None si la semaine est couverte."""
    j0 = acces.aujourdhui()
    vides = planificateur.creneaux_de(m["id"], j0, j0 + dt.timedelta(days=planificateur.HORIZON), ("libre", "manque"))
    vides = [s for s in vides if s["source"] != "campagne"]
    restant = list(planificateur._banque(m))
    manque = {}
    for s in vides:
        bon = next((a for a in restant if s["pillar"] and a["pillar"] == s["pillar"]), None) \
            or next((a for a in restant if not s["pillar"]), None) or (restant[0] if restant else None)
        if bon:
            restant.remove(bon)
            continue
        manque.setdefault(s["pillar"] or "", []).append(s["day"])
    if not manque:
        return None
    avant = min(d for jours in manque.values() for d in jours)
    secteur = m.get("sector") or "b2c"
    da = (((marque_.courante(m["id"]) or {}).get("plateforme") or {}).get("direction_artistique") or {})
    plans = []
    for cle, jours in sorted(manque.items(), key=lambda kv: -len(kv[1])):
        p = acces.pilier(m, cle) or {}
        plans.append({"n": len(jours), "quoi": p.get("photo") or p.get("label") or "une photo de votre travail du jour",
                      "pilier": p.get("label") or "au choix", "exemple": p.get("description") or ""})
    if RESEAUX_VIDEO & set(m.get("active_platforms") or []) and secteur in VIDEO:
        plans.append({"n": 1, "quoi": VIDEO[secteur], "pilier": "vidéo", "exemple": "le studio en fera un Reel"})
    comment = COMMENT.get(secteur, COMMENT["b2c"])
    quand = f"{_JOURS[avant.weekday()]} {avant:%d/%m}"
    phrase = f"{m['name'].split(' — ')[0]} avant {quand} : " + " ; ".join(
        f"{p['n']} × {p['quoi']}" for p in plans) + "."
    return {"marque": m["id"], "avant": avant.isoformat(), "titre": f"À photographier avant {quand}",
            "plans": plans, "comment": comment, "style": da.get("style_photo") or "", "phrase": phrase}


def briefs(marque_ids: list) -> list:
    return [b for b in (brief(acces.marque(mid)) for mid in marque_ids) if b]
