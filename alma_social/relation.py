"""La relation — commentaires, messages et avis des six marques dans une seule boîte.

Le classement d'entrée décide de tout (section 9 du cahier des charges) :

| catégorie   | ce que fait l'application                                         |
|-------------|-------------------------------------------------------------------|
| question    | répond seule, depuis la FAQ de la marque                          |
| compliment  | remercie seule, sans formule toute faite                          |
| devis       | répond une première fois ET alerte immédiatement                  |
| plainte     | ne répond pas, alerte immédiate (responsable + PDG)               |
| vip         | gros compte, journaliste, influenceur, institution : idem         |
| indesirable | insulte, spam, illégal : masqué dans l'application, consigné      |
| autre       | rien d'automatique : visible dans la boîte                        |

Avis Google : 4–5 ★ → réponse personnalisée automatique sous 24 h, qui reprend
un détail concret ; ≤ 3 ★ → aucune réponse automatique, alerte, et un
brouillon prêt que le responsable envoie en un tap.
"""
from __future__ import annotations

import datetime as dt
import logging
import re

from pydantic import BaseModel, Field
from sqlalchemy import func, insert, select, update

from . import acces, alertes, db, garde_fous, ia, journal, reseaux
from .publieurs.base import ErreurPublication

log = logging.getLogger("alma_social.relation")
VERSION_PROMPT = "relation-v1"
CATEGORIES = ("question", "compliment", "devis", "plainte", "vip", "indesirable", "autre")
SANS_REPONSE = {"plainte", "vip", "indesirable", "autre"}
AVEC_ALERTE = {"devis", "plainte", "vip"}
FENETRE_COMMENTAIRES = dt.timedelta(days=14)


class Classement(BaseModel):
    categorie: str = Field(description="question | compliment | devis | plainte | vip | indesirable | autre")
    urgence: int = Field(description="0 (rien) à 3 (à traiter dans l'heure)")
    raison: str = Field(description="une phrase : pourquoi cette catégorie")
    reponse: str = Field(description="la réponse publique, dans la voix de la marque ; '' si la catégorie "
                                     "interdit de répondre ou si rien de vrai ne peut être dit")


class ReponseAvis(BaseModel):
    reponse: str = Field(description="la réponse publique à l'avis")


def _faq(m: dict) -> list:
    """La FAQ vérifiée de la marque, sous une seule forme : (sujet, mots-clés, réponse).
    Les graines l'écrivent `topic / keywords / answer` ; une saisie plus ancienne
    `q / r` reste lue (ses mots de quatre lettres et plus servent de mots-clés)."""
    out = []
    for f in m.get("faq") or []:
        rep = f.get("answer") or f.get("r") or ""
        if not rep:
            continue
        cles = f.get("keywords") or re.findall(r"\w{4,}", f.get("q") or "")
        out.append((f.get("topic") or f.get("q") or "", [garde_fous._sans_accents(k.lower()) for k in cles], rep))
    return out


def _voix(m: dict) -> str:
    v = m.get("voice") or {}
    faq = "\n".join(f"- {sujet} (mots : {', '.join(cles)}) → {rep}" for sujet, cles, rep in _faq(m))
    return (f"Marque : {m['name']} — {m.get('activity', '')} ({m.get('zone', '')}).\n"
            f"Ton : {v.get('tone', 'chaleureux et clair')}. "
            f"{'Tutoiement' if v.get('address') == 'tu' else 'Vouvoiement'}.\n"
            f"Mots interdits : {', '.join(v.get('forbidden') or []) or 'aucun'}.\n"
            f"Réponses VÉRIFIÉES (n'invente rien d'autre — pas d'horaire, de prix, de délai inventés) :\n"
            f"{faq or '- (aucune : ne réponds qu’avec des généralités sûres, ou laisse vide)'}")


def classer(m: dict, auteur: str, texte: str, abonnes: int | None = None, plateforme: str = "") -> dict:
    """→ {categorie, urgence, raison, reponse, modele}. Sans clé : des règles
    simples et prudentes — dans le doute, on ne répond pas."""
    try:
        obj, modele = ia.appeler(
            "Tu tries les commentaires et messages reçus par une marque, et tu proposes une réponse "
            "quand la catégorie le permet.\n" + _voix(m) + "\n\n"
            "Catégories : question (horaires, prix, livraison, zone, délai) ; compliment ; devis (demande de "
            "devis, d'achat, de commande, de rendez-vous) ; plainte (litige, qualité, retard, mise en cause, "
            "sécurité alimentaire) ; vip (journaliste, influenceur, gros compte, institution, collectivité) ; "
            "indesirable (insulte, spam, contenu illégal) ; autre.\n"
            "Pour plainte, vip, indesirable, autre : réponse ''. Pour un compliment : un remerciement court qui "
            "reprend un mot du message. Pour une question : la réponse VÉRIFIÉE de la marque, sinon ''. Pour un "
            "devis : accuser réception chaleureusement et dire qu'on revient vers la personne très vite, sans "
            "promettre de prix ni de délai.",
            [{"type": "text", "text": f"Réseau : {reseaux.NOMS.get(plateforme, plateforme)}\nAuteur : {auteur}"
              + (f" ({abonnes} abonnés)" if abonnes else "") + f"\nMessage : {texte}"}],
            Classement, max_tokens=1500, usage="relation")
        d = obj.model_dump()
        d["modele"] = modele
    except ia.SansCle:
        d = _classer_sans_modele(m, texte)
    if d["categorie"] not in CATEGORIES:
        d["categorie"] = "autre"
    if abonnes and abonnes >= 10000 and d["categorie"] in ("question", "compliment", "autre"):
        d["categorie"], d["urgence"] = "vip", max(d["urgence"], 2)
    if d["categorie"] in SANS_REPONSE:
        d["reponse"] = ""
    if d["reponse"]:
        d["reponse"] = _sure(m, d["reponse"], plateforme)
    return d


_MOTS = {
    "indesirable": r"\b(connard|salope|encul|arnaque|escroc|viagra|crypto|bitcoin|gagnez|promo\s*code)\b",
    "plainte": r"\b(froid|retard|jamais re[çc]u|rembours|malade|intoxi|cheveu|d[ée]çu|honteu|plainte|avocat|"
               r"litige|malfa[çc]on|fuite|inadmissible|scandale|arnaqu)\w*",
    "devis": r"\b(devis|tarif|combien|prix pour|intervention|rendez-vous|rdv|disponibilit|chantier chez)\w*",
    "vip": r"\b(journaliste|r[ée]daction|mairie|conseil|presse|reportage|partenariat|collab)\w*",
    "compliment": r"\b(bravo|merci|super|top|g[ée]nial|d[ée]licieu|magnifique|beau travail|trop bon|excellent)\w*",
    "question": r"\?|\b(horaire|ouvert|livrez|livraison|zone|quand|o[uù] )",
}


def _classer_sans_modele(m: dict, texte: str) -> dict:
    t = garde_fous._sans_accents(texte.lower())
    for cat in ("indesirable", "plainte", "vip", "devis", "compliment", "question"):
        if re.search(garde_fous._sans_accents(_MOTS[cat]), t):
            break
    else:
        cat = "autre"
    urg = {"plainte": 3, "vip": 2, "devis": 2}.get(cat, 0)
    rep = ""
    tu = (m.get("voice") or {}).get("address") == "tu"
    if cat == "compliment":
        rep = "Merci beaucoup, ça nous touche !" if tu else "Merci beaucoup pour votre message, il nous touche."
    elif cat == "devis":
        rep = ("Merci pour ton message ! On revient vers toi très vite." if tu else
               "Merci pour votre demande : nous revenons vers vous très rapidement.")
    elif cat == "question":
        rep = _reponse_faq(m, texte)
        if not rep:
            cat = "autre"
    return {"categorie": cat, "urgence": urg, "raison": "règles locales (aucune clé de modèle)",
            "reponse": rep, "modele": "regles-locales"}


def _reponse_faq(m: dict, texte: str) -> str:
    """La réponse vérifiée dont le plus de mots-clés figurent dans le message ;
    aucune si rien ne correspond (on ne répond pas au hasard)."""
    t = garde_fous._sans_accents(texte.lower())
    meilleur, score = "", 0
    for _, cles, rep in _faq(m):
        s = sum(1 for k in cles if k and k in t)
        if s > score:
            meilleur, score = rep, s
    return meilleur


def _sure(m: dict, texte: str, plateforme: str) -> str:
    """Une réponse passe le même garde-fou de langage qu'une publication.
    Si elle échoue, on ne répond pas (et la boîte le montre)."""
    v = garde_fous.verifier_texte(texte, plateforme, m, None)
    return "" if v else texte.strip()


# ── Commentaires ─────────────────────────────────────────────────────────
def relever(m: dict) -> int:
    """Va chercher les nouveaux commentaires des publications des 14 derniers jours."""
    from . import pipeline
    depuis = db.maintenant() - FENETRE_COMMENTAIRES
    with db.moteur().begin() as c:
        posts = db.lignes(c.execute(select(db.posts).where(
            db.posts.c.brand_id == m["id"], db.posts.c.status == "publie",
            db.posts.c.simulated.is_(False), db.posts.c.published_at >= depuis)))
    n = 0
    for p in posts:
        try:
            pub = pipeline._publieur(p, acces.compte(m["id"], p["platform"]))
            recus = pub.comments(p["external_id"])
        except ErreurPublication as e:
            log.info("commentaires %s/%s : %s", m["id"], p["platform"], e)
            continue
        for cm in recus:
            n += recevoir(m, p["platform"], cm.external_id, cm.author, cm.text, post_id=p["id"],
                          kind=cm.kind, meta=cm.author_meta)
    return n


def recevoir(m: dict, plateforme: str, external_id: str, auteur: str, texte: str, post_id=None,
             kind: str = "commentaire", meta: dict | None = None) -> int:
    """→ 1 si le message est nouveau. Il est classé, répondu ou signalé, et tout est au journal."""
    with db.moteur().begin() as c:
        if c.execute(select(db.conversations.c.id).where(db.conversations.c.external_id == external_id)).first():
            return 0
    meta = meta or {}
    d = classer(m, auteur, texte, meta.get("followers"), plateforme)
    with db.moteur().begin() as c:
        cid = c.execute(insert(db.conversations).values(
            brand_id=m["id"], platform=plateforme, kind=kind, external_id=external_id, post_id=post_id,
            author=auteur[:200], author_meta=meta, text=texte, category=d["categorie"], urgency=d["urgence"],
            status="masque" if d["categorie"] == "indesirable" else "nouveau",
            received_at=db.maintenant())).inserted_primary_key[0]
    journal.noter("systeme", "message_recu", "conversation", cid, m["id"],
                  apres={"reseau": plateforme, "categorie": d["categorie"], "raison": d["raison"],
                         "modele": d.get("modele")})
    if d["reponse"] and d["categorie"] not in SANS_REPONSE:
        repondre(cid, d["reponse"], par="ia")
    if d["categorie"] in AVEC_ALERTE:
        sujet = {"devis": "demande de devis", "plainte": "PLAINTE", "vip": "message important"}[d["categorie"]]
        alertes.alerter(f"{m['name']} — {sujet} sur {reseaux.NOMS.get(plateforme, plateforme)}",
                        f"De : {auteur}\n\n« {texte[:1500]} »\n\n"
                        + ("Une première réponse est partie pour ne pas laisser la personne en plan.\n"
                           if d["categorie"] == "devis" else "AUCUNE réponse automatique n'est partie.\n")
                        + "Ouvrez la boîte d'ALMA SOCIAL pour répondre.",
                        marque=m["id"], niveau="urgent", type_=d["categorie"], dedup=f"conv:{cid}")
        with db.moteur().begin() as c:
            c.execute(update(db.conversations).where(db.conversations.c.id == cid).values(
                alert_sent=True, status="alerte" if d["categorie"] != "devis" else "repondu"))
    return 1


def repondre(conversation_id: int, texte: str, par: str = "humain") -> bool:
    from . import pipeline
    with db.moteur().begin() as c:
        cv = db.ligne(c.execute(select(db.conversations).where(db.conversations.c.id == conversation_id)))
    if not cv:
        raise ValueError("message inconnu")
    m = acces.marque(cv["brand_id"])
    if journal.bac_a_sable():
        ok, erreur = True, ""
    else:
        try:
            p = pipeline.post(cv["post_id"]) if cv["post_id"] else {"platform": cv["platform"], "simulated": False}
            pub = pipeline._publieur(p, acces.compte(m["id"], cv["platform"]))
            pub.reply(cv["external_id"], texte)
            ok, erreur = True, ""
        except ErreurPublication as e:
            ok, erreur = False, str(e)
    if ok:
        with db.moteur().begin() as c:
            c.execute(update(db.conversations).where(db.conversations.c.id == conversation_id).values(
                reply=texte, replied_by="ia" if par == "ia" else "humain", status="repondu"))
    journal.noter(par, "reponse" if ok else "reponse_echec", "conversation", conversation_id, m["id"],
                  apres={"texte": texte, "erreur": erreur, "simulee": journal.bac_a_sable()})
    return ok


def boite(marque_ids: list, limite: int = 200) -> list:
    """La boîte unique : urgence d'abord, puis le plus récent."""
    with db.moteur().begin() as c:
        rows = db.lignes(c.execute(select(db.conversations).where(
            db.conversations.c.brand_id.in_(marque_ids), db.conversations.c.status != "masque")
            .order_by(db.conversations.c.urgency.desc(), db.conversations.c.received_at.desc()).limit(limite)))
    return rows


# ── Avis Google ──────────────────────────────────────────────────────────
def relever_avis(m: dict) -> int:
    from . import pipeline
    if "gbp" not in (m.get("active_platforms") or []):
        return 0
    cpt = acces.compte(m["id"], "gbp")
    if not cpt or cpt["status"] != "actif" or journal.bac_a_sable():
        return 0
    try:
        pub = pipeline._publieur({"platform": "gbp", "simulated": False}, cpt)
        avis = pub.reviews()
    except ErreurPublication as e:
        log.info("avis %s : %s", m["id"], e)
        return 0
    return sum(recevoir_avis(m, a.external_id, a.rating, a.text, a.author, a.reply) for a in avis)


def recevoir_avis(m: dict, external_id: str, note: int, texte: str, auteur: str, reponse_existante: str = "") -> int:
    with db.moteur().begin() as c:
        if c.execute(select(db.reviews.c.id).where(db.reviews.c.external_id == external_id)).first():
            return 0
    maintenant = db.maintenant()
    brouillon = rediger_reponse_avis(m, note, texte, auteur)
    statut = "repondu" if reponse_existante else ("a_repondre" if note >= 4 else "alerte")
    with db.moteur().begin() as c:
        rid = c.execute(insert(db.reviews).values(
            brand_id=m["id"], external_id=external_id, rating=note, text=texte, author=auteur,
            reply=reponse_existante, draft=brouillon, status=statut, received_at=maintenant,
            # « sous 24 h » : on laisse passer un peu de temps, une réponse à la
            # seconde sent la machine.
            reply_due_at=maintenant + dt.timedelta(hours=3))).inserted_primary_key[0]
    journal.noter("systeme", "avis_recu", "review", rid, m["id"], apres={"note": note, "auteur": auteur})
    if note <= 3 and not reponse_existante:
        alertes.alerter(f"{m['name']} — avis Google {note} ★ de {auteur}",
                        f"« {texte[:1500]} »\n\nAucune réponse n'est partie. Un brouillon vous attend dans "
                        f"l'application, à envoyer en un tap :\n\n{brouillon}",
                        marque=m["id"], niveau="urgent", type_="avis", dedup=f"avis:{rid}")
    return 1


def rediger_reponse_avis(m: dict, note: int, texte: str, auteur: str) -> str:
    consigne = ("Réponds à cet avis Google au nom de la marque. Reprends UN détail concret de l'avis (un plat, "
                "une personne, un délai, un geste). Pas de formule toute faite, pas de promesse, aucun chiffre. "
                "Prénom de l'auteur s'il est donné. 2 à 4 phrases.")
    if note <= 3:
        consigne += (" Avis critique : reconnais le problème sans te justifier, sans contester, propose de "
                     "poursuivre en privé. Vouvoiement si l'auteur vouvoie.")
    try:
        obj, _ = ia.appeler(consigne + "\n" + _voix(m),
                            [{"type": "text", "text": f"Note : {note}/5\nAuteur : {auteur}\nAvis : {texte}"}],
                            ReponseAvis, max_tokens=1200, usage="avis")
        rep = obj.reponse.strip()
    except ia.SansCle:
        rep = _avis_sans_modele(m, note, texte, auteur)
    except ia.ErreurIA:
        rep = _avis_sans_modele(m, note, texte, auteur)
    if garde_fous.verifier_texte(rep, "gbp", m, None):
        rep = _avis_sans_modele(m, note, texte, auteur)
    if garde_fous.verifier_texte(rep, "gbp", m, None):
        # Le détail repris de l'avis peut porter un mot interdit à la marque
        # (« le restaurant » pour SAZÚ) : on n'en reprend alors aucun.
        rep = _avis_sans_modele(m, note, texte, auteur, reprendre=False)
    return rep


def _avis_sans_modele(m: dict, note: int, texte: str, auteur: str, reprendre: bool = True) -> str:
    prenom = (auteur or "").split(" ")[0] if reprendre else ""
    detail = _detail(texte) if reprendre else ""
    tu = (m.get("voice") or {}).get("address") == "tu"
    if note >= 4:
        merci = f"Merci {prenom} !" if prenom else "Merci !"
        corps = (f" Ravis que {detail} t'ait plu." if tu else f" Nous sommes ravis que {detail} vous ait plu.") \
            if detail else (" Ça nous fait vraiment plaisir." if tu else " Votre retour nous fait vraiment plaisir.")
        return merci + corps + (" À très vite !" if tu else " Au plaisir de vous retrouver.")
    return (f"Bonjour {prenom}, merci d'avoir pris le temps de nous écrire. " if prenom else
            "Bonjour, merci d'avoir pris le temps de nous écrire. ") + \
        ("Ce que vous décrivez n'est pas ce que nous voulons offrir. Pouvez-vous nous contacter directement "
         "pour que nous regardions cela ensemble ?")


def _detail(texte: str) -> str:
    """Le premier groupe nominal un peu concret de l'avis : « le bowl Salvador »."""
    # L'article, insensible à la casse (un avis commence souvent par « Le … ») ;
    # un second mot seulement s'il porte une majuscule — un nom (« le bowl
    # Salvador »), jamais un verbe (« la livraison était »).
    m = re.search(r"\b((?i:le|la|les|l'))\s?([A-Za-zÀ-ÿ'-]{3,}(?:\s[A-ZÀ-Ý][A-Za-zÀ-ÿ'-]{2,})?)", texte or "")
    if not m:
        return ""
    article = m.group(1).lower()
    groupe = (article + (" " if not article.endswith("'") else "") + m.group(2)).strip()
    return groupe if len(groupe) <= 40 else ""


def repondre_aux_avis_dus() -> int:
    """4–5 ★ : la réponse part seule, à son heure (sous 24 h)."""
    from . import pipeline
    with db.moteur().begin() as c:
        dus = db.lignes(c.execute(select(db.reviews).where(
            db.reviews.c.status == "a_repondre", db.reviews.c.rating >= 4,
            db.reviews.c.reply_due_at <= db.maintenant())))
    n = 0
    for r in dus:
        if envoyer_reponse_avis(r["id"], r["draft"], par="ia"):
            n += 1
    return n


def envoyer_reponse_avis(review_id: int, texte: str, par: str) -> bool:
    from . import pipeline
    with db.moteur().begin() as c:
        r = db.ligne(c.execute(select(db.reviews).where(db.reviews.c.id == review_id)))
    if not r or not texte.strip():
        return False
    m = acces.marque(r["brand_id"])
    erreur = ""
    if not journal.bac_a_sable():
        try:
            pub = pipeline._publieur({"platform": "gbp", "simulated": False}, acces.compte(m["id"], "gbp"))
            pub.reply_review(r["external_id"], texte)
        except ErreurPublication as e:
            erreur = str(e)
    if not erreur:
        with db.moteur().begin() as c:
            c.execute(update(db.reviews).where(db.reviews.c.id == review_id).values(
                reply=texte, status="repondu", replied_at=db.maintenant()))
    journal.noter(par, "reponse_avis" if not erreur else "reponse_avis_echec", "review", review_id, m["id"],
                  apres={"texte": texte, "erreur": erreur, "simulee": journal.bac_a_sable()})
    return not erreur


def note_moyenne(marque_id: str) -> dict:
    with db.moteur().begin() as c:
        n, moy = c.execute(select(func.count(), func.avg(db.reviews.c.rating)).where(
            db.reviews.c.brand_id == marque_id)).one()
    return {"avis": int(n or 0), "moyenne": round(float(moy), 2) if moy else None}


# ── Veille concurrents ───────────────────────────────────────────────────
def noter_concurrent(concurrent_id: int, posts_7j=None, note=None, nb_avis=None, source: str = "manuel",
                     par: str = "") -> int:
    """Un relevé (saisi à la main, ou plus tard par une source automatique).
    Rien n'est aspiré sur les pages des concurrents : les conditions des
    réseaux l'interdisent, et un compte suspendu coûte plus que la veille."""
    with db.moteur().begin() as c:
        oid = c.execute(insert(db.competitor_observations).values(
            competitor_id=concurrent_id, observed_at=db.maintenant(), posts_7d=posts_7j, rating=note,
            reviews_count=nb_avis, source=source)).inserted_primary_key[0]
        c.execute(update(db.competitors).where(db.competitors.c.id == concurrent_id).values(
            last_observation={"posts_7j": posts_7j, "note": note, "avis": nb_avis,
                              "le": db.maintenant().isoformat()}))
    journal.noter(par or "systeme", "veille", "competitor", concurrent_id, None,
                  apres={"posts_7j": posts_7j, "note": note, "avis": nb_avis})
    return oid


def veille(m: dict) -> dict:
    """La ligne du lundi : est-ce qu'on décroche, ou est-ce qu'on prend de l'avance ?"""
    depuis = db.maintenant() - dt.timedelta(days=7)
    with db.moteur().begin() as c:
        nous = c.execute(select(func.count(func.distinct(db.posts.c.slot_id))).where(
            db.posts.c.brand_id == m["id"], db.posts.c.status.in_(("publie",)),
            db.posts.c.published_at >= depuis)).scalar_one()
        conc = db.lignes(c.execute(select(db.competitors).where(db.competitors.c.brand_id == m["id"])))
    eux = [c_ for c_ in conc if (c_["last_observation"] or {}).get("posts_7j") is not None]
    moyenne = (sum(c_["last_observation"]["posts_7j"] for c_ in eux) / len(eux)) if eux else None
    avis = note_moyenne(m["id"])
    if moyenne is None:
        phrase = f"{len(conc)} concurrent{'s' if len(conc) > 1 else ''} suivi{'s' if len(conc) > 1 else ''}, aucun relevé cette semaine."
    elif nous >= moyenne:
        phrase = f"On prend de l'avance : {nous} publications contre {moyenne:.1f} en moyenne chez eux."
    else:
        phrase = f"On décroche : {nous} publications contre {moyenne:.1f} en moyenne chez eux."
    return {"phrase": phrase, "nous_7j": nous, "eux_7j": moyenne, "concurrents": conc, "avis": avis}
