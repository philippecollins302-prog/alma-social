"""Le Critique — chaque publication notée sur 100 avant de partir (§ 11.1).

Neuf critères, pondérés. Moins de 80 : réécriture avec les remarques ;
trois tours au plus ; toujours en dessous, la publication retourne à la
banque avec la raison. Le Critique doit être SÉVÈRE : son taux de refus est
affiché dans Santé, et un Critique qui laisse tout passer ne sert à rien.

Deux juges :

- le MODÈLE (agent « critique », le plus capable), quand une clé existe :
  il juge l'arrêt du pouce, la voix, l'esthétique — ce qu'une règle ne voit
  pas ;
- la GRILLE LOCALE, sans clé : elle ne juge que la FORME (longueur de
  l'accroche, adresse, hashtags, appel à l'action, preuve citée). Elle ne
  sait pas juger le goût, et elle le dit : son seuil est plus bas (60), et
  chaque note porte le nom de son juge. Décision documentée dans
  DECISIONS.md — sans quoi, sans clé, plus rien ne sortirait du bac à sable.

Dans tous les cas, le garde-fou a le dernier mot sur le RISQUE : une
violation (superlatif, chiffre non sourcé, allégation de santé) met le
critère à zéro, quoi qu'en pense le modèle.
"""
from __future__ import annotations

import re
import unicodedata

from pydantic import BaseModel, Field
from sqlalchemy import func, insert, select

from . import db, garde_fous, ia, marque as marque_, reseaux

VERSION = "critique-v1"
SEUIL = 80
SEUIL_GRILLE = 60
TOURS = 3

CRITERES = [  # clé, poids, question
    ("arret_pouce", 15, "La première seconde ou la première ligne arrête-t-elle le défilement ?"),
    ("clarte", 10, "Comprend-on en trois secondes ?"),
    ("voix", 15, "Est-ce exactement la marque ?"),
    ("preuve", 10, "Un élément concret, vérifiable, local ?"),
    ("appel", 10, "Le bon geste pour ce réseau ?"),
    ("natif", 10, "Fait pour ce réseau, ou recyclé ?"),
    ("esthetique", 10, "Au niveau d'une agence haut de gamme ?"),
    ("charte", 10, "Couleurs, polices, logo conformes ?"),
    ("risque", 10, "Quelque chose pourrait-il embarrasser la marque ?"),
]
POIDS = {k: p for k, p, _ in CRITERES}


class NoteCritere(BaseModel):
    cle: str = Field(description="une des clés : " + ", ".join(k for k, _, _ in CRITERES))
    note: int = Field(description="0 à 10. 8 = niveau d'une agence haut de gamme. 10 = exceptionnel, rare.")
    remarque: str = Field(description="ce qu'il faut changer, concrètement ; '' si rien")


class Notation(BaseModel):
    criteres: list[NoteCritere]
    verdict: str = Field(description="une phrase : la chose la plus importante à corriger")


def seuil(juge: str) -> int:
    return SEUIL_GRILLE if juge == "grille-locale" else SEUIL


def _total(notes: dict) -> int:
    return round(sum(POIDS[k] * max(0, min(10, notes.get(k, 0))) / 10 for k in POIDS))


SYSTEME = """Tu es le Critique d'une agence de communication haut de gamme. Tu notes une
publication AVANT qu'elle parte, critère par critère, de 0 à 10.
Tu es SÉVÈRE : un premier jet honnête vaut 6 ou 7 ; 8 est le niveau d'une agence
haut de gamme ; 10 est rare. Une publication « correcte » est un échec.
Pour chaque critère sous 8, la remarque dit EXACTEMENT quoi changer (pas « améliorer
l'accroche » : « ouvrir sur le bœuf effiloché 12 h au lieu du nom de la marque »).

Critères :
""" + "\n".join(f"- {k} : {q}" for k, _, q in CRITERES)


# ── La grille locale (sans modèle) ───────────────────────────────────────
_GENERIQUES = ("nouvelle publication", "aujourd'hui :", "découvrez", "decouvrez", "petit aperçu",
               "instant du jour", "voici")
_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
HASHTAGS_NATIFS = {"instagram": (3, 8), "tiktok": (2, 5), "linkedin": (0, 3), "linkedin_perso": (0, 3),
                   "facebook": (0, 2), "threads": (0, 1), "gbp": (0, 0), "youtube": (1, 3), "pinterest": (0, 0)}
LONGUEUR_NATIVE = {"instagram": (80, 900), "tiktok": (20, 300), "facebook": (60, 700), "linkedin": (200, 1800),
                   "linkedin_perso": (200, 1800), "threads": (20, 400), "gbp": (60, 750), "youtube": (20, 400),
                   "pinterest": (60, 500)}


def _sans_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


def grille(m: dict, plateforme: str, texte: str, lecture: dict | None = None, rendu: dict | None = None,
           violations: list | None = None) -> dict:
    """→ {critère: (note, remarque)} — la forme seulement, et elle le sait."""
    v = m.get("voice") or {}
    t = texte or ""
    premiere = t.strip().split("\n", 1)[0]
    bas = _sans_accents(t)
    n = {}
    # Arrêt du pouce : une première ligne courte, concrète, qui ne commence ni
    # par une formule creuse ni par le nom de la marque.
    note, rq = 9, ""
    if len(premiere) > 125:
        note, rq = 5, "première ligne trop longue : l'accroche doit tenir en 125 caractères"
    if _sans_accents(premiere).startswith(_GENERIQUES):
        note, rq = 4, "accroche générique : ouvrir sur un détail concret de la photo"
    elif _sans_accents(premiere).startswith(_sans_accents(m["name"])):
        note, rq = min(note, 6), "ne pas ouvrir sur le nom de la marque : ouvrir sur ce qu'on voit"
    n["arret_pouce"] = (note, rq)
    # Clarté : des phrases courtes.
    phrases = [p for p in re.split(r"[.!?\n]+", t) if p.strip()]
    moy = sum(len(p.split()) for p in phrases) / max(1, len(phrases))
    n["clarte"] = (9, "") if moy <= 18 else (6, "phrases trop longues : couper à 15 mots") if moy <= 28 \
        else (3, "phrases beaucoup trop longues")
    # Voix : adresse, emojis, mots interdits, mots de la marque.
    note, rqs = 9, []
    tu = len(re.findall(r"\b(tu|toi|ton|ta|tes)\b", bas))
    vous = len(re.findall(r"\b(vous|votre|vos)\b", bas))
    if v.get("address") == "tu" and vous > tu:
        note, rqs = note - 4, rqs + ["la marque tutoie"]
    if v.get("address") != "tu" and tu > vous:
        note, rqs = note - 4, rqs + ["la marque vouvoie"]
    if not v.get("emojis") and _EMOJI.search(t):
        note, rqs = note - 3, rqs + ["aucun emoji pour cette marque"]
    p = (marque_.courante(m["id"]) or {}).get("plateforme") or {}
    jamais = [w for w in (p.get("voix") or {}).get("on_ne_dit_pas") or [] if _sans_accents(w) in bas]
    if jamais:
        note, rqs = note - 5, rqs + [f"la marque ne dit jamais : {', '.join(jamais)}"]
    vocab = [w for w in (v.get("vocabulary") or []) + ((p.get("voix") or {}).get("on_dit") or [])
             if _sans_accents(w) in bas]
    if not vocab and note >= 8:
        note, rqs = 7, rqs + ["aucun mot de la marque"]
    n["voix"] = (max(0, note), " ; ".join(rqs))
    # Preuve : un fait de la base, un lieu, un détail de la photo.
    faits = " ".join(str(x) for x in (m.get("facts") or {}).values())
    mots_faits = {w for w in re.findall(r"[a-z0-9]{4,}", _sans_accents(faits))}
    mots_lieu = {w for w in re.findall(r"[a-z]{5,}", _sans_accents(m.get("zone", "")))}
    mots_photo = {w for w in re.findall(r"[a-z]{5,}", _sans_accents(" ".join(
        [(lecture or {}).get("sujet", "")] + list((lecture or {}).get("elements") or []))))}
    mots_texte = set(re.findall(r"[a-z0-9]{4,}", bas))
    touches = sum(bool(mots_texte & s) for s in (mots_faits, mots_lieu, mots_photo))
    n["preuve"] = ({0: 3, 1: 7, 2: 9}.get(touches, 10),
                   "" if touches >= 2 else "ajouter un détail vérifiable : un fait de la marque, le lieu, ce qu'on voit")
    # Appel à l'action : le bon geste pour le réseau.
    a_lien = "{lien}" in bas or "lien en bio" in bas or plateforme in reseaux.LIEN_HORS_TEXTE
    cta = any(_sans_accents(c)[:12] in bas for c in v.get("cta") or [])
    n["appel"] = (9, "") if (a_lien and cta) else (7, "un appel à l'action de la marque") if a_lien \
        else (4, "aucun appel à l'action")
    # Natif : hashtags et longueur dans les usages du réseau.
    h = garde_fous.compter_hashtags(t)
    hmin, hmax = HASHTAGS_NATIFS.get(plateforme, (0, 5))
    lmin, lmax = LONGUEUR_NATIVE.get(plateforme, (20, 2000))
    note, rqs = 9, []
    if not hmin <= h <= hmax:
        note, rqs = note - 3, rqs + [f"{h} hashtags ; ce réseau en veut {hmin} à {hmax}"]
    if not lmin <= len(t) <= lmax:
        note, rqs = note - 3, rqs + [f"{len(t)} caractères ; ce réseau lit {lmin} à {lmax}"]
    n["natif"] = (note, " ; ".join(rqs))
    # Esthétique : la note d'utilisabilité de l'image, si on l'a.
    u = (lecture or {}).get("utilisabilite")
    n["esthetique"] = ((7, "") if u is None else (max(0, min(10, round(u / 10))),
                                                   "" if u >= 70 else "image faible : retoucher ou en choisir une autre"))
    # Charte : la déclinaison porte les traitements de la charte.
    tr = (rendu or {}).get("traitements") or []
    n["charte"] = (9, "") if (not rendu or any("charte" in str(x) or "logo" in str(x) or "bande" in str(x)
                                               for x in tr)) else (7, "habillage de la charte absent")
    n["risque"] = (0, "violations : " + "; ".join(violations)) if violations else (10, "")
    return n


# ── Le jugement ──────────────────────────────────────────────────────────
def noter(m: dict, plateforme: str, texte: str, lecture: dict | None = None, rendu: dict | None = None,
          violations: list | None = None, objet: str = "") -> dict:
    """→ {note, criteres: {clé: {note, remarque}}, remarques: [...], juge, verdict}."""
    juge = "grille-locale"
    verdict = ""
    try:
        obj, juge = ia.appeler(
            SYSTEME + "\n\n" + marque_.contexte(m),
            [{"type": "text", "text":
              f"RÉSEAU : {reseaux.NOMS.get(plateforme, plateforme)}\n"
              f"Ce que montre l'image : {(lecture or {}).get('sujet', '')} — "
              f"{', '.join((lecture or {}).get('elements') or [])}\n"
              f"Qualité de l'image : {(lecture or {}).get('utilisabilite', '?')}/100\n"
              f"Habillage appliqué : {', '.join(str(x) for x in (rendu or {}).get('traitements') or []) or '?'}\n"
              f"\nTEXTE :\n{texte}"}],
            Notation, max_tokens=3000, agent="critique", marque_id=m["id"], objet=objet)
        notes = {c.cle: (max(0, min(10, c.note)), c.remarque) for c in obj.criteres if c.cle in POIDS}
        local = grille(m, plateforme, texte, lecture, rendu, violations)
        for k in POIDS:                         # un critère oublié par le modèle : la grille le remplit
            notes.setdefault(k, local[k])
        verdict = obj.verdict
    except ia.SansCle:
        notes = grille(m, plateforme, texte, lecture, rendu, violations)
    except ia.ErreurIA:
        notes = grille(m, plateforme, texte, lecture, rendu, violations)
    if violations:
        notes["risque"] = (0, "violations : " + "; ".join(violations))
    total = _total({k: v[0] for k, v in notes.items()})
    remarques = [f"{k} ({v[0]}/10) : {v[1]}" for k, v in sorted(notes.items(), key=lambda kv: kv[1][0])
                 if v[1] and v[0] < 8]
    return {"note": total, "criteres": {k: {"note": v[0], "remarque": v[1]} for k, v in notes.items()},
            "remarques": remarques, "juge": juge, "verdict": verdict, "seuil": seuil(juge)}


def enregistrer(m: dict, plateforme: str, tour: int, jugement: dict, decision: str,
                slot_id: int | None = None, post_id: int | None = None):
    with db.moteur().begin() as c:
        c.execute(insert(db.critic_scores).values(
            brand_id=m["id"], platform=plateforme, tour=tour, note=jugement["note"],
            detail={"criteres": jugement["criteres"], "verdict": jugement.get("verdict", "")},
            decision=decision, juge=jugement["juge"], slot_id=slot_id, post_id=post_id,
            created_at=db.maintenant()))


def taux(jours: int = 30, marque_id: str | None = None) -> dict:
    """Pour Santé : combien passent au premier tour, combien vont à la banque.
    Un taux de refus nul est une ALERTE, pas une victoire."""
    import datetime as dt
    t = db.critic_scores
    q = select(t.c.decision, t.c.tour, func.count(), func.avg(t.c.note)).where(
        t.c.created_at >= db.maintenant() - dt.timedelta(days=jours))
    if marque_id:
        q = q.where(t.c.brand_id == marque_id)
    with db.moteur().connect() as c:
        rangs = c.execute(q.group_by(t.c.decision, t.c.tour)).all()
    total = sum(r[2] for r in rangs)
    passe_1 = sum(r[2] for r in rangs if r[0] == "passe" and r[1] == 1)
    reecrit = sum(r[2] for r in rangs if r[0] == "reecrire")
    banque = sum(r[2] for r in rangs if r[0] == "banque")
    moy = (sum((r[3] or 0) * r[2] for r in rangs) / total) if total else None
    return {"jugements": total, "passe_premier_tour": passe_1, "reecritures": reecrit, "a_la_banque": banque,
            "note_moyenne": round(moy, 1) if moy is not None else None,
            "trop_indulgent": total >= 20 and reecrit + banque == 0}
