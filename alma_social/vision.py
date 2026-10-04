"""Étape 2 — lire l'image avant d'écrire une ligne.

Le modèle de vision décrit ce qu'il voit et rend une fiche structurée : sujet,
lieu probable, éléments, qualité, visages, texte, logo tiers, document
confidentiel, objets parasites à effacer, et une note d'utilisabilité.
Tout est stocké : c'est ce qui rend les textes justes et le journal vérifiable.

L'application ne devine JAMAIS la marque (on la tape) ; elle ne devine que le
sujet — et le pilier de contenu parmi ceux de la marque.
"""
from __future__ import annotations

import io

from pydantic import BaseModel, Field

from . import ia, images

VERSION_PROMPT = "vision-v1"


class Boite(BaseModel):
    label: str = Field(description="ce que contient la boîte, en français")
    box: list[float] = Field(description="[x0, y0, x1, y1] normalisés entre 0 et 1")


class LectureImage(BaseModel):
    sujet: str = Field(description="le sujet en une phrase concrète")
    type_contenu: str = Field(description="plat | coulisses | equipe | chantier_avant | chantier_en_cours | "
                                          "chantier_apres | realisation | produit | evenement | bureau | autre")
    pilier: str = Field(description="la clé du pilier de contenu de la marque le plus proche, ou ''")
    lieu_probable: str
    elements: list[str]
    sujet_boite: list[float] = Field(description="boîte normalisée du sujet principal [x0,y0,x1,y1]")
    nettete: str = Field(description="nette | acceptable | floue")
    exposition: str = Field(description="bonne | sous-exposee | surexposee")
    bruit: str = Field(description="faible | moyen | fort")
    visages: list[Boite]
    plaques: list[Boite]
    texte_visible: str = Field(description="texte lisible sur la photo, '' sinon")
    logos_tiers: list[str] = Field(description="marques ou enseignes d'AUTRES entreprises visibles")
    document_confidentiel: str = Field(description="'' ou le type : plan, devis, facture, ecran, badge, contrat")
    parasites: list[Boite] = Field(description="objets parasites à effacer : poubelle, cône, câble, gobelet…")
    utilisabilite: int = Field(description="0 à 100 : publiable telle quelle sur les réseaux de la marque ?")
    raison_note: str
    etiquettes: list[str]


def _systeme(marque: dict) -> str:
    piliers = "\n".join(f"- {p['key']} : {p['label']} — {p.get('description', '')}"
                        for p in marque.get("pillars") or [])
    return f"""Tu lis des photos pour l'équipe communication de la marque « {marque['name']} »
({marque.get('activity', '')}, {marque.get('zone', '')}).
Décris uniquement ce qui est visible. Ne devine pas la marque : elle est connue.
Piliers de contenu de la marque :
{piliers or '- (aucun)'}

Règles :
- logos_tiers : toute marque, enseigne ou logo d'une AUTRE entreprise (concurrent, gobelet
  d'une autre chaîne, panneau d'un autre artisan, camion d'un autre transporteur).
  Le logo de « {marque['name']} » lui-même n'en fait pas partie.
- document_confidentiel : un plan, un devis, une facture, un écran lisible, un badge,
  un contrat visible et lisible. Vide sinon.
- parasites : objets qui gâchent la photo et qu'un retoucheur effacerait. Boîtes serrées.
- utilisabilite : 80+ = belle photo publiable ; 50–79 = correcte ; < 45 = à ne pas publier.
- Coordonnées normalisées de 0 à 1, origine en haut à gauche."""


def lire(marque: dict, octets_jpeg: bytes):
    """→ (dict lecture, modèle). Sans clé : une lecture SIMULÉE, marquée comme telle."""
    try:
        obj, modele = ia.appeler(_systeme(marque), [
            ia.image_bloc(octets_jpeg),
            {"type": "text", "text": "Lis cette photo et remplis la fiche."},
        ], LectureImage, max_tokens=4000, usage="vision")
        d = obj.model_dump()
        d["simule"] = False
        d["prompt_version"] = VERSION_PROMPT
        return d, modele
    except ia.SansCle:
        return lecture_simulee(marque, octets_jpeg), "simulation-locale"


def lecture_simulee(marque: dict, octets_jpeg: bytes) -> dict:
    """Le mode sans clé : on ne prétend pas voir. Les mesures locales donnent la
    qualité, OpenCV compte les visages, et le pilier tourne dans l'ordre."""
    img = images.ouvrir(io.BytesIO(octets_jpeg))
    m = images.mesurer(img)
    refus = images.refus_technique(m)
    note = 30 if refus else int(min(92, 55 + min(m["nettete"], 600) / 20))
    piliers = marque.get("pillars") or [{"key": ""}]
    pilier = piliers[int(m["luminosite"]) % len(piliers)]["key"]
    return {
        "sujet": "photo déposée (lecture simulée : aucune clé de modèle configurée)",
        "type_contenu": "autre", "pilier": pilier, "lieu_probable": marque.get("zone", ""),
        "elements": [], "sujet_boite": [0.2, 0.2, 0.8, 0.8],
        "nettete": "floue" if "floue" in refus else "nette",
        "exposition": "sous-exposee" if "sous" in refus else ("surexposee" if "sur" in refus else "bonne"),
        "bruit": "fort" if m["bruit"] > 6 else "faible",
        "visages": [{"label": "visage", "box": b} for b in images.visages(img)[:10]],
        "plaques": [], "texte_visible": "", "logos_tiers": [], "document_confidentiel": "",
        "parasites": [], "utilisabilite": note,
        "raison_note": refus or "mesures locales correctes", "etiquettes": [],
        "simule": True, "prompt_version": VERSION_PROMPT,
    }
