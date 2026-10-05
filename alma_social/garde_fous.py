"""Les freins mécaniques. Rien ne vous attend jamais : ce sont des REFUS.

Puisque rien n'est validé avant publication, chaque texte et chaque image
passent ici juste avant l'envoi. Un refus n'arrête que ce qui est fautif — le
réseau concerné, la photo concernée — jamais toute la chaîne.

Contenu :
- le garde-fou de langage (mots interdits, promesses non autorisées, chiffres
  qui ne viennent pas de la base, superlatifs non prouvables) ;
- la conformité alimentaire (aucune allégation de santé, prix exact ou pas de prix) ;
- les contraintes de plateforme (longueur, hashtags, format, poids) ;
- l'anti-doublon (empreinte visuelle, 90 jours, même réseau) ;
- la quarantaine (logo concurrent, document confidentiel).
"""
from __future__ import annotations

import datetime as dt
import difflib
import re
import unicodedata

from . import images

# ── Langage ──────────────────────────────────────────────────────────────
# Superlatifs et promesses qu'aucune marque ne peut prouver. La fiche de voix
# de chaque marque AJOUTE ses propres interdits ; elle ne retire rien d'ici.
SUPERLATIFS = [
    r"\ble meilleur\b", r"\bla meilleure\b", r"\bles meilleur(e)?s\b", r"\bmeilleur de\b",
    r"\bn[°o]\s?1\b", r"\bnum[ée]ro\s?(1|un)\b", r"\bleader\b", r"\bimbattable(s)?\b",
    r"\bincomparable(s)?\b", r"\bin[ée]gal[ée](e)?s?\b", r"\bunique en france\b",
    r"\bjamais vu\b", r"\br[ée]volutionnaire(s)?\b", r"\ble moins cher\b",
    r"\bles moins chers\b", r"\bprix le plus bas\b", r"\b100\s?%", r"\bparfait(e)?(s)?\b",
    r"\bgaranti(e)?(s)? [àa] vie\b", r"\bz[ée]ro d[ée]faut\b", r"\bsans aucun risque\b",
]

# Allégations de santé ou nutritionnelles (règlement CE 1924/2006) : interdites
# d'office pour l'alimentaire. On ne dit pas qu'un bowl est sain ; on dit ce qu'il y a dedans.
SANTE = [
    r"\bsain(e)?(s)?\b", r"\bhealthy\b", r"\bd[ée]tox\b", r"\bminceur\b", r"\bmaigrir\b",
    r"\bperte de poids\b", r"\bbr[uû]le[- ]graisse(s)?\b", r"\bimmunit[ée]\b",
    r"\bbon(ne)? pour la sant[ée]\b", r"\bpour (votre|ta) sant[ée]\b", r"\bbienfaits?\b",
    r"\briche en\b", r"\bsource de (prot[ée]ines|fibres|vitamines|fer|calcium)\b",
    r"\ball[ée]g[ée](e)?(s)?\b", r"\blight\b", r"\bsuper[- ]?aliment(s)?\b", r"\bsuperfood(s)?\b",
    r"\bvitamin[ée]?(e)?s?\b", r"\banti[- ]?oxydant(s)?\b", r"\bbooste(r)?\b", r"\bgu[ée]ri(r|t)\b",
    r"\bpr[ée]vien(t|nent)\b", r"\b[ée]quilibr[ée](e)?(s)?\b", r"\bdi[ée]t[ée]tique(s)?\b",
    r"\bfaible(s)? en calories\b", r"\bsans calories\b",
]

_URL = re.compile(r"https?://\S+|\{LIEN\}|\bwww\.\S+", re.I)
_HASHTAG = re.compile(r"#[\wÀ-ÿ]+")
_MENTION = re.compile(r"@[\w.]+")
_TELEPHONE = re.compile(r"(?:\+33\s?|0)[1-9](?:[\s.-]?\d{2}){4}")
_PRIX = re.compile(r"(\d+(?:[.,]\d{1,2})?)\s?(?:€|euros?\b|EUR\b)", re.I)
_NOMBRE = re.compile(r"\d+(?:[.,]\d+)?")


# « Publications en français uniquement. » Quelques mots d'espagnol qui ont du
# goût (SAZÚ : sazón, fuego, ¡gracias!) passent ; une phrase entière dans une
# autre langue, non. On compte les petits mots outils, qui ne mentent pas.
_OUTILS_FR = set("le la les de des du et un une est sont pour sur avec dans au aux en ton ta tes votre vos "
                 "nous vous tu on ce cette ces qui que chez plus pas ne il elle ils notre nos son sa ses "
                 "mais ou donc car tout tous toute".split())
_OUTILS_AUTRES = set("the and of to for with your our is are this that we you it be have from at "
                     "el los las con para por una del muy está estamos nuestro nuestra "
                     "der die das und mit für ist".split())


def langue_douteuse(texte: str) -> str:
    mots = re.findall(r"[a-zà-ÿñ']+", _URL.sub(" ", _HASHTAG.sub(" ", _MENTION.sub(" ", texte.lower()))))
    mots = [m.split("'")[-1] for m in mots]
    if len(mots) < 6:
        return ""
    fr = sum(m in _OUTILS_FR for m in mots)
    autres = sum(m in _OUTILS_AUTRES for m in mots)
    if autres >= 2 and autres > fr:
        return "texte qui n'est pas en français — les publications sont en français uniquement"
    return ""


def _sans_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _norm_nombre(n: str) -> str:
    n = n.replace(",", ".")
    try:
        f = float(n)
        return str(int(f)) if f == int(f) else ("%.2f" % f).rstrip("0").rstrip(".")
    except ValueError:
        return n


def nombres_autorises(marque: dict, contexte: dict | None = None) -> set:
    """Tout nombre qu'un texte a le droit d'écrire vient d'un champ renseigné
    en base : les chiffres vérifiés de la marque, les prix en vigueur, son
    adresse, ses horaires — et ceux du contexte (la date d'un événement)."""
    sources = []
    sources += [str(v) for v in (marque.get("facts") or {}).values()]
    for p in marque.get("products") or []:
        sources += [str(v) for v in (p.get("prix") or {}).values()]
    liens = marque.get("links") or {}
    sources += [str(liens.get("adresse", "")), str(liens.get("horaires", ""))]
    sources += [str(marque.get("zone", ""))]
    for v in (contexte or {}).values():
        sources.append(str(v))
    out = set()
    for s in sources:
        for n in _NOMBRE.findall(s):
            out.add(_norm_nombre(n))
    return out


def prix_autorises(marque: dict, aujourd_hui: dt.date) -> set:
    """Un prix ne s'affiche que s'il est le prix RÉEL sur TOUTES les plateformes
    où le produit est vendu, et vérifié depuis moins de 8 jours. Sinon : pas de
    prix. Un prix faux sur une appli de livraison, c'est une réclamation."""
    out = set()
    for p in marque.get("products") or []:
        prix = {k: v for k, v in (p.get("prix") or {}).items() if v not in (None, "")}
        verif = p.get("prix_verifie_le")
        if not prix or not verif:
            continue
        try:
            if (aujourd_hui - dt.date.fromisoformat(verif)).days > 7:
                continue
        except ValueError:
            continue
        valeurs = {_norm_nombre(str(v)) for v in prix.values()}
        if len(valeurs) == 1:
            out |= valeurs
    return out


def verifier_texte(texte: str, plateforme: str, marque: dict, contrainte: dict | None,
                   contexte: dict | None = None, autres_textes: dict | None = None,
                   aujourd_hui: dt.date | None = None) -> list:
    """→ la liste des violations (vide = publiable). Chaque violation est une
    phrase lisible : elle va telle quelle au journal."""
    aujourd_hui = aujourd_hui or dt.date.today()
    voix = marque.get("voice") or {}
    v = []
    bas = _sans_accents(texte.lower())

    langue = langue_douteuse(texte)
    if langue:
        v.append(langue)
    # « lien en bio » est la consigne d'Instagram, pas une allégation : SAZÚ
    # interdit « bio » (le produit ne l'est pas), pas l'adresse de son profil.
    bas_mots = re.sub(r"\b(lien|link) (en|in) bio\b", r"\1 \2 profil", bas)
    for mot in voix.get("forbidden") or []:
        motif = r"\b" + re.escape(_sans_accents(mot.lower())) + r"\b"
        if re.search(motif, bas_mots):
            v.append(f"mot interdit pour cette marque : « {mot} »")
    for promesse in voix.get("forbidden_promises") or []:
        if re.search(_sans_accents(promesse.lower()), bas):
            v.append(f"promesse non autorisée : « {promesse} »")
    autorisees = [_sans_accents(p.lower()) for p in voix.get("allowed_promises") or []]
    for motif in SUPERLATIFS:
        m = re.search(_sans_accents(motif), bas)
        if m and not any(m.group(0) in a for a in autorisees):
            v.append(f"superlatif non prouvable : « {m.group(0)} »")
    if marque.get("sector") == "food":
        for motif in SANTE:
            m = re.search(_sans_accents(motif), bas)
            if m:
                v.append(f"allégation de santé interdite : « {m.group(0)} »")

    # Les chiffres : on retire d'abord ce qui n'est pas une affirmation (liens,
    # hashtags, mentions, numéros de téléphone), puis on compare.
    nu = _TELEPHONE.sub(" ", _MENTION.sub(" ", _HASHTAG.sub(" ", _URL.sub(" ", texte))))
    prix_ok = prix_autorises(marque, aujourd_hui)
    for m in _PRIX.finditer(nu):
        if _norm_nombre(m.group(1)) not in prix_ok:
            v.append(f"prix non vérifié en base : « {m.group(0).strip()} » — pas de prix plutôt qu'un prix faux")
    nu_sans_prix = _PRIX.sub(" ", nu)
    permis = nombres_autorises(marque, contexte) | prix_ok
    for n in _NOMBRE.findall(nu_sans_prix):
        if _norm_nombre(n) not in permis:
            v.append(f"chiffre qui ne vient d'aucun champ renseigné : « {n} »")

    if contrainte:
        lim = contrainte.get("caption_max")
        if lim and len(texte) > lim:
            v.append(f"trop long pour {plateforme} : {len(texte)} caractères (maximum {lim})")
        hmax = contrainte.get("hashtags_max")
        nh = len(_HASHTAG.findall(texte))
        if hmax is not None and nh > hmax:
            v.append(f"trop de hashtags pour {plateforme} : {nh} (maximum {hmax})")

    for autre, t in (autres_textes or {}).items():
        if autre != plateforme and t and similarite(texte, t) > 0.82:
            v.append(f"texte presque identique à celui de {autre} — chaque réseau a le sien")
    # Dédoublonnées, dans l'ordre : un même mot répété ne fait qu'une ligne.
    return list(dict.fromkeys(v))


def similarite(a: str, b: str) -> float:
    a = _HASHTAG.sub("", _URL.sub("", a.lower()))
    b = _HASHTAG.sub("", _URL.sub("", b.lower()))
    return difflib.SequenceMatcher(None, a, b).ratio()


def compter_hashtags(texte: str) -> int:
    return len(_HASHTAG.findall(texte))


# ── Image ────────────────────────────────────────────────────────────────
def quarantaine(lecture: dict) -> str:
    """Protection d'image, pas validation éditoriale : un logo concurrent ou un
    document lisible met la photo de côté et prévient."""
    if not lecture:
        return ""
    if lecture.get("logos_tiers"):
        return "logo ou enseigne d'une autre entreprise visible : " + ", ".join(lecture["logos_tiers"][:3])
    if lecture.get("document_confidentiel"):
        return "document potentiellement confidentiel visible : " + lecture["document_confidentiel"]
    return ""


def doublon(phash: str, publies: list, seuil: int = 8):
    """`publies` : [(phash, post_id)] des images déjà sorties sur CE réseau
    dans les 90 derniers jours. → post_id du doublon, ou None."""
    for h, pid in publies:
        if images.distance(phash, h) <= seuil:
            return pid
    return None


def verifier_media(rendu: dict, contrainte: dict | None) -> list:
    """`rendu` : {format, largeur, hauteur, poids_mo, video, duree}."""
    if not contrainte:
        return []
    v = []
    formats = [f.lower() for f in contrainte.get("formats") or []]
    ext = "mp4" if rendu.get("video") else "jpeg"
    if formats and ext not in formats and not (ext == "jpeg" and "jpg" in formats):
        v.append(f"format {ext} non accepté (acceptés : {', '.join(formats)})")
    r = rendu["largeur"] / rendu["hauteur"]
    # Les bornes de ratio des fiches sont celles des IMAGES du fil : un Reel
    # 9:16 sur Instagram est la norme, pas une faute. La vidéo n'est bornée
    # que là où la fiche le dit pour elle (YouTube Shorts : vertical).
    if not rendu.get("video"):
        bornes = ("ratio_min", "ratio_max")
    else:
        bornes = ("ratio_max",) if (contrainte.get("ratio_max") or 9) <= 1 else ()
    if "ratio_min" in bornes and contrainte.get("ratio_min") and r < contrainte["ratio_min"] - 0.01:
        v.append(f"ratio {r:.2f} sous le minimum {contrainte['ratio_min']}")
    if "ratio_max" in bornes and contrainte.get("ratio_max") and r > contrainte["ratio_max"] + 0.01:
        v.append(f"ratio {r:.2f} au-dessus du maximum {contrainte['ratio_max']}")
    vues = rendu.get("vues") or 1
    if vues > 1 and contrainte.get("carousel_max") and vues > contrainte["carousel_max"]:
        v.append(f"carrousel de {vues} vues, maximum {contrainte['carousel_max']}")
    lim = contrainte.get("video_max_mb") if rendu.get("video") else contrainte.get("max_weight_mb")
    if lim and rendu["poids_mo"] > lim:
        v.append(f"fichier de {rendu['poids_mo']:.1f} Mo, maximum {lim} Mo")
    if rendu.get("video"):
        d = rendu.get("duree") or 0
        if contrainte.get("duration_min") and d < contrainte["duration_min"]:
            v.append(f"vidéo de {d:.0f} s, minimum {contrainte['duration_min']:.0f} s")
        if contrainte.get("duration_max") and d > contrainte["duration_max"]:
            v.append(f"vidéo de {d:.0f} s, maximum {contrainte['duration_max']:.0f} s")
    return v
