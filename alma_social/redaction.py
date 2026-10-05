"""Étape 4 et 5 — un texte par réseau, dans la voix de la marque.

Même idée, ton et longueur refaits pour chaque plateforme. Un seul appel au
modèle pour tous les réseaux d'une publication (moins cher, et le modèle voit
les textes côte à côte, ce qui l'aide à ne pas se répéter), puis le garde-fou
de langage sur chaque texte. Ce qui échoue est réécrit (deux fois au plus) en
disant au modèle ce qui n'allait pas ; ce qui échoue encore part en version
sûre écrite par le code, ou n'est pas publié.

Chaque texte est stocké avec le modèle et la version du prompt qui l'ont
produit : c'est ce qui permet de comprendre une dérive.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re

from pydantic import BaseModel, Field

from . import critique, garde_fous, ia, marque as marque_, reseaux

VERSION_PROMPT = "redaction-v2"


class TexteReseau(BaseModel):
    platform: str
    texte: str
    hashtags: list[str] = Field(description="sans le #, déjà inclus dans le texte s'il y en a")
    titre: str = Field(description="YouTube et Pinterest seulement, '' sinon")


class Redaction(BaseModel):
    textes: list[TexteReseau]


def _voix(marque: dict) -> str:
    v = marque.get("voice") or {}
    lignes = [
        f"Ton : {v.get('tone', 'clair et chaleureux')}.",
        "Tutoiement." if v.get("address") == "tu" else "Vouvoiement.",
        "Emojis permis, avec mesure (2 à 4 au plus)." if v.get("emojis") else "Aucun emoji.",
    ]
    if v.get("vocabulary"):
        lignes.append("Vocabulaire de la marque : " + ", ".join(v["vocabulary"]) + ".")
    if v.get("forbidden"):
        lignes.append("MOTS INTERDITS (ne jamais les écrire) : " + ", ".join(v["forbidden"]) + ".")
    if v.get("allowed_promises"):
        lignes.append("Seules promesses autorisées : " + " ; ".join(v["allowed_promises"]) + ".")
    if v.get("forbidden_promises"):
        lignes.append("Promesses interdites : " + " ; ".join(v["forbidden_promises"]) + ".")
    if v.get("cta"):
        lignes.append("Appels à l'action possibles : " + " ; ".join(v["cta"]) + ".")
    if v.get("hashtags"):
        lignes.append("Hashtags locaux de la marque (à choisir parmi eux d'abord) : "
                      + " ".join("#" + h.lstrip("#") for h in v["hashtags"]) + ".")
    if v.get("notes"):
        lignes.append(v["notes"])
    return "\n".join("- " + l for l in lignes)


def systeme(marque: dict, contraintes: dict, plateformes: list, aujourd_hui: dt.date) -> str:
    faits = marque.get("facts") or {}
    faits_txt = "\n".join(f"- {k} : {v}" for k, v in faits.items()) or "- (aucun : n'écris AUCUN chiffre)"
    prix_ok = garde_fous.prix_autorises(marque, aujourd_hui)
    produits = []
    for p in marque.get("products") or []:
        prix = {k: v for k, v in (p.get("prix") or {}).items() if v not in (None, "")}
        valeurs = {garde_fous._norm_nombre(str(x)) for x in prix.values()}
        affichable = len(valeurs) == 1 and valeurs <= prix_ok
        produits.append(f"- {p['nom']} : {p.get('description', '')}"
                        + (f" — prix affichable : {list(valeurs)[0]} €" if affichable else " — AUCUN prix à écrire"))
    regles_reseaux = []
    for pf in plateformes:
        c = contraintes.get(pf) or {}
        lim = c.get("caption_max")
        hmax = c.get("hashtags_max")
        regles_reseaux.append(
            f"### {pf}\n{reseaux.STYLE.get(pf, '')}"
            + (f"\nLongueur maximale : {min(lim, 2000)} caractères." if lim else "")
            + (f" Hashtags : {hmax} au plus." if hmax is not None else ""))
    alimentaire = ""
    if marque.get("sector") == "food":
        alimentaire = ("\nALIMENTAIRE — AUCUNE allégation de santé ou nutritionnelle (sain, healthy, "
                       "équilibré, riche en, détox, léger, vitaminé…). Décris ce qu'il y a dans "
                       "l'assiette, pas ce que ça fait au corps. Pour les allergènes, renvoie à la "
                       "fiche produit de l'application de livraison.")
    plateforme_txt = marque_.contexte(marque)
    longueur = {"court": "Textes COURTS : chaque mot gagne sa place.", "long": "Textes développés, sans délayer.",
                }.get((marque.get("voice") or {}).get("target_length", ""), "")
    return f"""Tu es le meilleur rédacteur social media de France, au service de « {marque['name']} » : {marque.get('activity', '')}.
Zone : {marque.get('zone', '')}. Clientèle : {marque.get('audience', '')}.
Tu écris en FRANÇAIS les publications de la marque, une par réseau.

VOIX DE LA MARQUE
{_voix(marque)}
{longueur}

{plateforme_txt}

LA BARRE : chaque texte sera noté sur 100 par un critique sévère (arrêt du pouce, clarté,
voix, preuve concrète et locale, appel à l'action, natif du réseau, risque). Sous 80, il
revient. La PREMIÈRE LIGNE fait tout : elle ouvre sur ce qu'on voit ou sur un détail qui
intrigue — jamais sur le nom de la marque, jamais sur « Découvrez » ou « Nouvelle publication ».

CHIFFRES — tu n'as le droit d'écrire QUE les chiffres ci-dessous (et les dates ou heures
données dans le contexte de la publication). Aucun autre nombre, aucun pourcentage,
aucune durée, aucun « depuis X ans » qui ne figure pas ici :
{faits_txt}

PRODUITS
{chr(10).join(produits) or '- (aucun produit référencé)'}
{alimentaire}

INTERDITS POUR TOUTES LES MARQUES : les superlatifs non prouvables (le meilleur, n°1,
imbattable, unique, parfait, 100 %, le moins cher, révolutionnaire), les promesses de
résultat, les comparaisons avec un concurrent.

LIEN : là où le style du réseau le demande, l'appel à l'action se termine par le marqueur
exact {{LIEN}} (il sera remplacé par un lien tracé). Ne mets jamais d'adresse web toi-même.

CHAQUE RÉSEAU A SON TEXTE : même idée, mais angle, longueur, rythme et première phrase
différents. Deux textes qui se ressemblent seront refusés.

RÉSEAUX DEMANDÉS
{chr(10).join(regles_reseaux)}"""


def _contenu(lecture: dict, pilier: dict | None, contexte: dict, anciens: list | None,
             corrections: dict | None) -> str:
    l = lecture or {}
    lignes = [
        "PHOTO (lecture de l'image) :",
        f"- sujet : {l.get('sujet', '')}",
        f"- type : {l.get('type_contenu', '')}",
        f"- éléments visibles : {', '.join(l.get('elements') or [])}",
        f"- lieu probable : {l.get('lieu_probable', '')}",
    ]
    if pilier:
        lignes.append(f"PILIER DE CONTENU : {pilier.get('label', '')} — {pilier.get('description', '')}")
    for k, v in (contexte or {}).items():
        lignes.append(f"CONTEXTE — {k} : {v}")
    if anciens:
        lignes.append("CETTE PHOTO A DÉJÀ ÉTÉ PUBLIÉE il y a plus de 90 jours. Nouvel angle obligatoire ; "
                      "ne reprends rien de ces anciens textes :")
        lignes += [f"  « {a[:300]} »" for a in anciens[:3]]
    if corrections:
        lignes.append("TA VERSION PRÉCÉDENTE A ÉTÉ REFUSÉE par le contrôle. Corrige exactement ceci :")
        for pf, v in corrections.items():
            lignes.append(f"- {pf} : " + " ; ".join(v))
    return "\n".join(lignes)


def ecrire(marque: dict, lecture: dict, plateformes: list, contraintes: dict,
           pilier: dict | None = None, contexte: dict | None = None,
           anciens: list | None = None, aujourd_hui: dt.date | None = None,
           slot_id: int | None = None):
    """→ {plateforme: {texte, titre, hashtags, modele, prompt_version, violations, essais, critique}}.

    Trois tours au plus (§ 11.1). À chaque tour, chaque texte passe d'abord
    le GARDE-FOU (ce qui est interdit), puis le CRITIQUE (ce qui est
    médiocre). Ce qui échoue revient au rédacteur avec les remarques exactes.
    Au troisième échec, le texte porte des `violations` : l'appelant le
    refuse, et la photo retourne à la banque avec la raison.
    """
    aujourd_hui = aujourd_hui or dt.date.today()
    resultats = {}
    restants = list(plateformes)
    corrections = None
    for essai in range(critique.TOURS):
        if not restants:
            break
        try:
            obj, modele = ia.appeler(
                systeme(marque, contraintes, restants, aujourd_hui),
                [{"type": "text", "text": _contenu(lecture, pilier, contexte, anciens, corrections)
                  + "\n\nÉcris un texte pour chacun de ces réseaux : " + ", ".join(restants)}],
                Redaction, max_tokens=8000, agent="redacteur", marque_id=marque["id"],
                objet=f"slot:{slot_id}" if slot_id else "")
            recus = {t.platform: t for t in obj.textes}
        except ia.SansCle:
            modele, recus = "gabarit-local", {}
            for pf in restants:
                g = gabarit(marque, lecture, pf, pilier, contexte)
                recus[pf] = TexteReseau(platform=pf, texte=g["texte"], hashtags=g["hashtags"], titre=g["titre"])
        corrections = {}
        tous = {pf: r["texte"] for pf, r in resultats.items()}
        tous.update({pf: t.texte for pf, t in recus.items()})
        dernier = essai == critique.TOURS - 1 or modele == "gabarit-local"
        for pf in list(restants):
            t = recus.get(pf)
            if t is None:
                corrections[pf] = ["texte manquant"]
                continue
            texte = nettoyer(t.texte, pf)
            v = garde_fous.verifier_texte(texte, pf, marque, contraintes.get(pf), contexte,
                                          tous, aujourd_hui)
            j = critique.noter(marque, pf, texte, lecture, None, v, objet=f"slot:{slot_id}" if slot_id else "")
            passe = not v and j["note"] >= j["seuil"]
            decision = "passe" if passe else ("banque" if dernier else "reecrire")
            critique.enregistrer(marque, pf, essai + 1, j, decision, slot_id=slot_id)
            resultats[pf] = {"texte": texte, "titre": t.titre.strip()[:100], "hashtags": t.hashtags,
                             "modele": modele, "prompt_version": VERSION_PROMPT,
                             "violations": v, "essais": essai + 1,
                             "critique": {"note": j["note"], "juge": j["juge"], "remarques": j["remarques"][:5]}}
            if passe:
                restants.remove(pf)
            else:
                corrections[pf] = v + j["remarques"][:4]
                if not v:
                    resultats[pf]["violations"] = [
                        f"critique : {j['note']}/100 (seuil {j['seuil']}) — "
                        + (j["remarques"][0] if j["remarques"] else j.get("verdict", ""))]
        if modele == "gabarit-local":
            break
    return resultats


def nettoyer(texte: str, plateforme: str) -> str:
    """Ce que le code impose quoi que le modèle ait écrit : pas d'adresse web
    inventée, le marqueur de lien là où il a sa place, et nulle part ailleurs."""
    t = re.sub(r"https?://\S+|\bwww\.\S+", "", texte).strip()
    if plateforme in reseaux.LIEN_EN_BIO or plateforme in reseaux.LIEN_HORS_TEXTE:
        t = t.replace("{LIEN}", "").replace("()", "")
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return re.sub(r"[ \t]{2,}", " ", t).strip()


def poser_lien(texte: str, plateforme: str, url: str) -> str:
    if plateforme in reseaux.LIEN_EN_BIO or plateforme in reseaux.LIEN_HORS_TEXTE:
        return texte.replace("{LIEN}", "").strip()
    if "{LIEN}" in texte:
        return texte.replace("{LIEN}", url)
    return texte.rstrip() + "\n" + url


def ajouter_mentions(texte: str, marque: dict, limite: int | None) -> str:
    """Les mentions légales d'office de la fiche de voix (allergènes…)."""
    for m in (marque.get("voice") or {}).get("legal_mentions") or []:
        essai = texte.rstrip() + "\n\n" + m
        if not limite or len(essai) <= limite:
            texte = essai
    return texte


# ── La version sûre, écrite par le code ──────────────────────────────────
def _choix(options: list, graine: str):
    if not options:
        return ""
    i = int(hashlib.sha256(graine.encode()).hexdigest(), 16) % len(options)
    return options[i]


def _phrase(t: str) -> str:
    """Une phrase propre : majuscule en tête, un seul point au bout."""
    t = (t or "").strip().rstrip(".!? ")
    return (t[:1].upper() + t[1:] + ".") if t else ""


def _court(t: str) -> str:
    """Le premier membre d'une description longue (avant « : » ou « — »)."""
    return re.split(r"\s[:—]\s|\s:\s|:\s", t or "", maxsplit=1)[0].strip()


def gabarit(marque: dict, lecture: dict, plateforme: str, pilier: dict | None, contexte: dict | None) -> dict:
    """Sans modèle de langue (clé absente) ou en dernier recours : des phrases
    sûres — aucun chiffre qui ne soit dans la fiche, aucun superlatif — et une
    construction PROPRE À CHAQUE RÉSEAU (le garde-fou refuse deux textes trop
    proches). Moins brillant qu'un texte de modèle, jamais faux."""
    v = marque.get("voice") or {}
    tu = v.get("address") == "tu"
    nom = marque["name"]
    sujet = (pilier or {}).get("label") or "Nouvelle publication"
    detail = (pilier or {}).get("description") or ""
    graine = f"{nom}{plateforme}{sujet}{(lecture or {}).get('sujet', '')}"
    tags = [h.lstrip("#") for h in (v.get("hashtags") or [])]
    ctx = contexte or {}
    # Une étape de campagne : son accroche d'abord, et la date tant qu'elle est à venir.
    evenement = ""
    if ctx.get("étape"):
        evenement = _phrase(ctx.get("sujet proposé") or ctx["étape"])
        if ctx.get("annonce") and str(ctx["étape"]).startswith("J-"):
            evenement += f" Rendez-vous le {ctx['annonce']}."
    ctas = v.get("cta") or (["Écris-nous"] if tu else ["Contactez-nous"])
    cta = _choix(ctas, graine).rstrip(".!")
    cta2 = _choix(ctas, graine + "2").rstrip(".!")
    zone = _court(marque.get("zone", ""))
    activite = _court(marque.get("activity", ""))
    faits = [str(f) for f in (marque.get("facts") or {}).values()]
    fait = _choix(faits, graine) if faits else ""
    emoji = " " + _choix(v.get("emoji_set") or ["✨"], graine) if v.get("emojis") else ""
    # La première ligne ouvre sur CE QU'ON VOIT (la lecture de la photo), sinon
    # sur une accroche de la plateforme de marque — jamais sur une formule creuse
    # ni sur le nom de la marque : le Critique les refuse.
    vu = _phrase((lecture or {}).get("sujet", ""))
    accroches = ((marque_.courante(marque["id"]) or {}).get("plateforme") or {}).get("accroches") or []
    tete = evenement or vu or _choix(accroches, graine) or f"{sujet}."
    ht = lambda n: " ".join("#" + t for t in tags[:n])
    if plateforme == "instagram":
        texte = f"{tete}{emoji}\n\n{_phrase(detail)}\n\n{cta} : lien en bio.\n\n{ht(6)}"
        hashtags = tags[:6]
    elif plateforme == "tiktok":
        texte = f"{('Regarde' if tu else 'Regardez')} 👀 {sujet}{emoji}\n{cta2} : lien en bio.\n{ht(4)}"
        hashtags = tags[:4]
    elif plateforme == "facebook":
        texte = f"{tete}\n\n{_phrase(activite)} {zone}.\n\n{cta} : {{LIEN}}"
        hashtags = []
    elif plateforme == "linkedin":
        texte = (f"{sujet} : {detail[:1].lower() + detail[1:] if detail else 'notre savoir-faire'}.\n\n"
                 + (f"{_phrase(fait)}\n\n" if fait else "") + f"{nom}. {cta2} → {{LIEN}}")
        hashtags = []
    elif plateforme == "linkedin_perso":
        texte = (f"Ce que j'aime dans notre métier chez {nom} : {sujet[:1].lower() + sujet[1:]}.\n\n"
                 f"{_phrase(detail)}\n\n{cta2} → {{LIEN}}")
        hashtags = []
    elif plateforme == "gbp":
        texte = f"{sujet} — {zone}.\n" + (f"{_phrase(fait)}\n" if fait else "") + f"{_phrase(cta)}"
        hashtags = []
    elif plateforme == "youtube":
        texte = f"{sujet} en images{emoji}\n{cta2} : {{LIEN}}\n#Shorts {ht(2)}"
        hashtags = ["Shorts"] + tags[:2]
    elif plateforme == "threads":
        texte = f"{tete}{emoji} {{LIEN}}"
        hashtags = []
    elif plateforme == "pinterest":
        texte = f"Idée {sujet[:1].lower() + sujet[1:]} : {detail or activite}. {nom}, {zone}."
        hashtags = []
    else:
        texte, hashtags = f"{tete}\n{cta} : {{LIEN}}", []
    titre = f"{sujet} — {nom}"[:100] if plateforme in ("youtube", "pinterest") else ""
    return {"texte": texte, "titre": titre, "hashtags": hashtags}
