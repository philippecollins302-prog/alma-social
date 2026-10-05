"""La voix qui apprend (§ 7.2).

Chaque fois qu'un responsable corrige un texte — une réponse à un avis, un
brouillon de crise, une publication —, la correction est lue : qu'a-t-il
enlevé, ajouté, raccourci ? Après TROIS corrections du même genre pour la
même marque, la règle entre d'elle-même dans la fiche de voix, et le
journal le dit. Une seule correction ne fait pas une règle : c'est peut-être
une humeur.

La lecture des corrections est déterministe (des règles, pas un modèle) : on
sait toujours POURQUOI la voix a bougé.
"""
from __future__ import annotations

import re
import unicodedata

from sqlalchemy import func, insert, select, update

from . import db, journal

SEUIL = 3
LONGUEURS = ["court", "moyen", "long"]
_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
# Des mots qui ne disent rien d'un style : les retirer n'apprend rien.
_VIDES = set("avec dans pour vous nous votre notre leur leurs cette cela sont mais plus tout tous "
             "toute toutes aussi bien très comme elle elles ils sera être avoir fait faire".split())


def _mots(t: str) -> set:
    t = unicodedata.normalize("NFKD", t.lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return {w for w in re.findall(r"[a-z][a-z'-]{4,}", t) if w not in _VIDES}


def _adresse(t: str) -> str:
    tu = len(re.findall(r"\b(tu|toi|ton|ta|tes|t')\b", t.lower()))
    vous = len(re.findall(r"\b(vous|votre|vos)\b", t.lower()))
    return "tu" if tu > vous else "vous" if vous > tu else ""


def lire_correction(avant: str, apres: str) -> list:
    """→ les genres de correction, chacun avec la règle qu'il porterait."""
    genres = []
    if avant.strip() == apres.strip():
        return genres
    if apres and len(apres) < 0.7 * len(avant):
        genres.append(("plus_court", "Des textes plus courts."))
    if _EMOJI.search(avant) and not _EMOJI.search(apres):
        genres.append(("sans_emoji", "Aucun emoji."))
    a1, a2 = _adresse(avant), _adresse(apres)
    if a1 and a2 and a1 != a2:
        genres.append((f"adresse_{a2}", "Tutoiement." if a2 == "tu" else "Vouvoiement."))
    for mot in sorted(_mots(avant) - _mots(apres))[:5]:
        genres.append((f"mot_retire:{mot}", f"Ne plus écrire « {mot} »."))
    return genres


def noter_correction(marque_id: str, contexte: str, avant: str, apres: str, par: str) -> list:
    """Enregistre la correction ; → les règles entrées dans la fiche de voix."""
    genres = lire_correction(avant or "", apres or "")
    if not genres:
        return []
    t = db.voice_corrections
    appliquees = []
    with db.moteur().begin() as c:
        for genre, regle in genres:
            c.execute(insert(t).values(brand_id=marque_id, contexte=contexte, avant=avant[:4000],
                                       apres=apres[:4000], type=genre, regle=regle, par=par,
                                       created_at=db.maintenant()))
    for genre, regle in genres:
        with db.moteur().connect() as c:
            n = c.execute(select(func.count()).select_from(t).where(
                t.c.brand_id == marque_id, t.c.type == genre, t.c.appliquee.is_(False))).scalar()
        if n >= SEUIL and _appliquer(marque_id, genre, par):
            with db.moteur().begin() as c:
                c.execute(update(t).where(t.c.brand_id == marque_id, t.c.type == genre).values(appliquee=True))
            appliquees.append(regle)
    return appliquees


def _appliquer(marque_id: str, genre: str, par: str) -> bool:
    with db.moteur().connect() as c:
        m = db.ligne(c.execute(select(db.brands).where(db.brands.c.id == marque_id)))
    v = dict(m.get("voice") or {})
    avant = dict(v)
    if genre == "plus_court":
        i = LONGUEURS.index(v.get("target_length", "moyen")) if v.get("target_length") in LONGUEURS else 1
        v["target_length"] = LONGUEURS[max(0, i - 1)]
    elif genre == "sans_emoji":
        v["emojis"] = False
    elif genre.startswith("adresse_"):
        v["address"] = genre.split("_", 1)[1]
    elif genre.startswith("mot_retire:"):
        mot = genre.split(":", 1)[1]
        v["forbidden"] = sorted(set(v.get("forbidden") or []) | {mot})
    else:
        return False
    if v == avant:
        return False
    with db.moteur().begin() as c:
        c.execute(update(db.brands).where(db.brands.c.id == marque_id).values(voice=v))
    journal.noter(par, "voix_apprise", "brand", marque_id, marque_id,
                  avant={"voix": avant}, apres={"voix": v, "regle": genre, "apres_corrections": SEUIL})
    return True


def historique(marque_id: str, limite: int = 30) -> list:
    t = db.voice_corrections
    with db.moteur().connect() as c:
        return db.lignes(c.execute(select(t.c.type, t.c.regle, t.c.appliquee, t.c.contexte, t.c.created_at)
                                   .where(t.c.brand_id == marque_id).order_by(t.c.id.desc()).limit(limite)))
