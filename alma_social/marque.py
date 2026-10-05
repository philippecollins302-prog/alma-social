"""La plateforme de marque — l'ADN lu, puis la stratégie écrite (§ 7).

Deux temps, comme chez Pomelli ou SocialBee :

1. `extraire_adn` LIT ce qui existe : le site de la marque (titres, phrases,
   couleurs, polices), sa fiche de voix, ses faits vérifiés, ses piliers.
   Rien n'est demandé à Philippe qui puisse être lu.
2. Le Stratège en tire une PLATEFORME d'une à deux pages : positionnement,
   promesse, preuves, trois personas, objections, voix, mix, parcours,
   objectifs, direction artistique, accroches. Versionnée : chaque réécriture
   est une version de plus, l'ancienne reste.

Sans clé, la plateforme de départ est celle de `graines/plateformes.json`,
écrite à la main d'après le Drive. Dans les deux cas, une PREUVE ne peut
citer qu'un fait de la base : ce que la marque ne peut pas prouver, elle ne
l'écrit pas.

Tous les agents lisent `contexte(m)` avant de travailler : c'est ce bloc qui
est mis en cache côté modèle (il change rarement, il est relu à chaque appel).
"""
from __future__ import annotations

import collections
import json
import re

from pydantic import BaseModel, Field
from sqlalchemy import desc, insert, select, update

from . import config, db, ia, journal

# ── Le schéma de la plateforme ───────────────────────────────────────────


class Persona(BaseModel):
    nom: str
    qui: str
    veut: str
    bloque: str
    ou: str
    quand: str


class Objection(BaseModel):
    objection: str
    reponse: str


class Voix(BaseModel):
    on_dit: list[str]
    on_ne_dit_pas: list[str]
    longueur: str = Field(description="court | moyen | long")


class Mix(BaseModel):
    utile: int
    communaute: int
    vente: int


class Parcours(BaseModel):
    connaitre: str
    hesiter: str
    agir: str
    revenir: str


class Objectifs(BaseModel):
    j30: str
    j90: str
    j180: str


class DirectionArtistique(BaseModel):
    style_photo: str
    style_video: str
    gabarits: list[str]
    mise_en_scene: str = Field(description="studio_permis (produit) | decor_reel (réalisation)")


class PlateformeMarque(BaseModel):
    positionnement: str
    difference: str
    promesse: str
    preuves: list[str] = Field(description="UNIQUEMENT des clés de la liste des faits vérifiés")
    personas: list[Persona]
    objections: list[Objection]
    voix: Voix
    mix: Mix
    parcours: Parcours
    objectifs: Objectifs
    direction_artistique: DirectionArtistique
    accroches: list[str]


def _graines() -> dict:
    try:
        return json.loads((config.GRAINES / "plateformes.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def _nettoyer(m: dict, p: dict) -> dict:
    """Ce que le code impose quel que soit l'auteur : des preuves qui existent,
    un mix qui fait 100, une mise en scène qui suit le secteur."""
    faits = m.get("facts") or {}
    p = dict(p)
    p["preuves"] = [k for k in (p.get("preuves") or []) if k in faits]
    mix = p.get("mix") or {}
    total = sum(max(0, int(mix.get(k, 0) or 0)) for k in ("utile", "communaute", "vente"))
    if total and total != 100:
        p["mix"] = {k: round(100 * max(0, int(mix.get(k, 0) or 0)) / total) for k in ("utile", "communaute", "vente")}
    da = dict(p.get("direction_artistique") or {})
    # RÈGLE D'HONNÊTETÉ (§ 9.2) : seul un PRODUIT peut voir son décor refait.
    # Une réalisation (chantier, sol posé) montre son état réel — le modèle ne
    # peut pas en décider autrement.
    da["mise_en_scene"] = "studio_permis" if m.get("sector") == "food" else "decor_reel"
    p["direction_artistique"] = da
    return p


# ── Lire l'ADN ───────────────────────────────────────────────────────────
def _http_get(url: str) -> str:
    import httpx
    r = httpx.get(url, timeout=20, follow_redirects=True,
                  headers={"User-Agent": "ALMA-SOCIAL/1 (lecture de la marque)"})
    r.raise_for_status()
    return r.text[:2_000_000]


_http = _http_get           # les bancs le remplacent : aucun banc ne sort


def lire_site(html: str) -> dict:
    """Ce qu'une page dit d'une marque : titres, phrases, couleurs, polices."""
    sans = re.sub(r"(?is)<(script|noscript)\b.*?</\1>", " ", html)
    titre = re.search(r"(?is)<title[^>]*>(.*?)</title>", sans)
    desc_ = re.search(r'(?is)<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', sans)
    titres = [re.sub(r"<[^>]+>|\s+", " ", t).strip() for t in re.findall(r"(?is)<h[1-3][^>]*>(.*?)</h[1-3]>", sans)]
    paras = [re.sub(r"<[^>]+>|\s+", " ", t).strip() for t in re.findall(r"(?is)<p[^>]*>(.*?)</p>", sans)]
    styles = " ".join(re.findall(r"(?is)<style[^>]*>(.*?)</style>", html)) + " " + " ".join(
        re.findall(r'style=["\'](.*?)["\']', html))
    couleurs = collections.Counter(c.lower() for c in re.findall(r"#[0-9a-fA-F]{6}\b", styles))
    polices = collections.Counter(
        f.split(",")[0].strip().strip("'\"") for f in re.findall(r"font-family\s*:\s*([^;}{]+)", styles))
    return {
        "titre": (titre.group(1).strip() if titre else "")[:200],
        "description": (desc_.group(1).strip() if desc_ else "")[:400],
        "titres": [t for t in titres if t][:20],
        "phrases": [p for p in paras if len(p) > 40][:20],
        "couleurs": [c for c, _ in couleurs.most_common(6)],
        "polices": [p for p, _ in polices.most_common(4) if p],
    }


def extraire_adn(m: dict) -> dict:
    adn = {"sources": [], "fiche": {
        "activite": m.get("activity", ""), "zone": m.get("zone", ""), "clientele": m.get("audience", ""),
        "voix": m.get("voice") or {}, "faits": m.get("facts") or {},
        "piliers": [p.get("label") for p in m.get("pillars") or []],
        "charte": {k: (m.get("kit") or {}).get(k) for k in ("colors", "fonts")}}}
    site = (m.get("links") or {}).get("site")
    adn["sources"].append("fiche de la marque (graines, Drive)")
    if site:
        try:
            adn["site"] = lire_site(_http(site))
            adn["sources"].append(site)
        except Exception as e:      # un site qui ne répond pas n'empêche pas d'écrire
            adn["site_erreur"] = f"{type(e).__name__}: {str(e)[:120]}"
    return adn


# ── Lire, écrire, versionner ─────────────────────────────────────────────
def courante(marque_id: str) -> dict | None:
    with db.moteur().connect() as c:
        return db.ligne(c.execute(select(db.brand_platforms).where(db.brand_platforms.c.brand_id == marque_id)
                                  .order_by(desc(db.brand_platforms.c.version)).limit(1)))


def versions(marque_id: str) -> list:
    with db.moteur().connect() as c:
        return db.lignes(c.execute(select(db.brand_platforms.c.version, db.brand_platforms.c.auteur,
                                          db.brand_platforms.c.created_at, db.brand_platforms.c.relue_le)
                                   .where(db.brand_platforms.c.brand_id == marque_id)
                                   .order_by(desc(db.brand_platforms.c.version))))


def _enregistrer(m: dict, plateforme: dict, adn: dict, auteur: str, par: str) -> dict:
    p = _nettoyer(m, plateforme)
    with db.moteur().begin() as c:
        v = (c.execute(select(db.brand_platforms.c.version).where(db.brand_platforms.c.brand_id == m["id"])
                       .order_by(desc(db.brand_platforms.c.version)).limit(1)).scalar() or 0) + 1
        c.execute(insert(db.brand_platforms).values(brand_id=m["id"], version=v, adn=adn, plateforme=p,
                                                    auteur=auteur, created_at=db.maintenant()))
    journal.noter(par, "plateforme_ecrite", "brand", m["id"], m["id"], apres={"version": v, "auteur": auteur})
    return courante(m["id"])


def semer(marques: list, par: str = "systeme") -> int:
    """Au démarrage : chaque marque sans plateforme reçoit celle des graines."""
    g = _graines()
    n = 0
    for m in marques:
        if courante(m["id"]) is None and m["id"] in g:
            _enregistrer(m, g[m["id"]], {"sources": ["graines/plateformes.json"]}, "graines", par)
            n += 1
    return n


SYSTEME_STRATEGE = """Tu es le directeur de la stratégie d'une agence de communication haut de gamme,
spécialiste des réseaux sociaux pour les entreprises locales du Sud de la France.
Tu écris la PLATEFORME DE MARQUE d'une entreprise : le document que toute l'équipe
(rédacteurs, directeur artistique, community manager) lira avant chaque publication.

Exigences :
- Concret, local, vérifiable. Pas une phrase qui pourrait s'appliquer à un concurrent.
- PREUVES : uniquement des CLÉS de la liste « faits vérifiés ». Rien d'autre.
- Trois personas réels, décrits par ce qu'ils veulent, ce qui les bloque, où ils sont, QUAND ils décident.
- Objectifs : tant que quatre semaines de mesure réelle n'existent pas, écris CE QU'ON MESURE, pas un chiffre.
- Voix : « on dit / on ne dit pas » avec des exemples tirés du métier.
- Accroches : cinq premières lignes qui arrêtent le pouce, chacune différente.
- Pas de superlatifs invérifiables, pas d'allégations de santé, aucun chiffre qui ne soit pas dans les faits."""


def rediger(marque_id: str, par: str = "systeme", consigne: str = "") -> dict:
    """Le Stratège (ré)écrit la plateforme. Sans clé : les graines, une fois."""
    from . import acces
    m = acces.marque(marque_id)
    adn = extraire_adn(m)
    avant = courante(marque_id)
    try:
        obj, modele = ia.appeler(
            SYSTEME_STRATEGE,
            [{"type": "text", "text": "ADN LU :\n" + json.dumps(adn, ensure_ascii=False, indent=1)
              + ("\n\nPLATEFORME ACTUELLE (à améliorer, pas à jeter) :\n"
                 + json.dumps(avant["plateforme"], ensure_ascii=False, indent=1) if avant else "")
              + (f"\n\nCONSIGNE DE PHILIPPE : {consigne}" if consigne else "")
              + "\n\nFAITS VÉRIFIÉS (clés citables) : " + ", ".join((m.get("facts") or {}).keys())}],
            PlateformeMarque, max_tokens=12000, agent="stratege", marque_id=marque_id,
            objet=f"plateforme:{marque_id}")
        return _enregistrer(m, obj.model_dump(), adn, modele, par)
    except ia.SansCle:
        if avant:
            return avant
        g = _graines().get(marque_id)
        if not g:
            raise ValueError("aucune plateforme de départ pour cette marque")
        return _enregistrer(m, g, adn, "graines", par)


def relire(marque_id: str, par: str) -> dict:
    p = courante(marque_id)
    if not p:
        raise ValueError("pas de plateforme")
    with db.moteur().begin() as c:
        c.execute(update(db.brand_platforms).where(db.brand_platforms.c.id == p["id"])
                  .values(relue_le=db.maintenant()))
    journal.noter(par, "plateforme_relue", "brand", marque_id, marque_id, apres={"version": p["version"]})
    return courante(marque_id)


def corriger(marque_id: str, champs: dict, par: str) -> dict:
    """Philippe corrige un passage : une nouvelle version, l'ancienne reste."""
    from . import acces
    m = acces.marque(marque_id)
    p = courante(marque_id) or {"plateforme": _graines().get(marque_id, {}), "adn": {}}
    neuve = dict(p["plateforme"])
    for k, v in champs.items():
        if k in PlateformeMarque.model_fields:
            neuve[k] = v
    return _enregistrer(m, neuve, p.get("adn") or {}, f"corrigée par {par}", par)


# ── Le contexte que lisent tous les agents ───────────────────────────────
def contexte(m: dict) -> str:
    """Le bloc stable (mis en cache) : la plateforme, en clair, et les leçons."""
    p = (courante(m["id"]) or {}).get("plateforme") or _graines().get(m["id"]) or {}
    if not p:
        return ""
    faits = m.get("facts") or {}
    lignes = [f"PLATEFORME DE MARQUE — {m['name']}",
              f"Positionnement : {p.get('positionnement', '')}",
              f"Différence : {p.get('difference', '')}",
              f"Promesse : {p.get('promesse', '')}"]
    preuves = [f"{faits[k]}" for k in p.get("preuves") or [] if k in faits]
    if preuves:
        lignes.append("Preuves citables : " + " · ".join(preuves))
    for pe in p.get("personas") or []:
        lignes.append(f"Persona « {pe.get('nom')} » : {pe.get('qui')} ; veut {pe.get('veut')} ; "
                      f"bloque sur {pe.get('bloque')} ; décide {pe.get('quand')}.")
    for o in p.get("objections") or []:
        lignes.append(f"Objection : « {o.get('objection')} » → {o.get('reponse')}")
    v = p.get("voix") or {}
    if v.get("on_dit"):
        lignes.append("On dit : " + " ; ".join(v["on_dit"]))
    if v.get("on_ne_dit_pas"):
        lignes.append("On ne dit JAMAIS : " + " ; ".join(v["on_ne_dit_pas"]))
    if p.get("accroches"):
        lignes.append("Accroches de la marque (le niveau attendu, pas à recopier) : "
                      + " / ".join(p["accroches"][:5]))
    da = p.get("direction_artistique") or {}
    if da:
        lignes.append(f"Direction artistique : {da.get('style_photo', '')}")
    from . import carnet
    for l in carnet.lecons(m["id"], limite=8):
        lignes.append(f"Leçon apprise : {l['lecon']}")
    return "\n".join(lignes)


def mise_en_scene(m: dict) -> str:
    return "studio_permis" if m.get("sector") == "food" else "decor_reel"
