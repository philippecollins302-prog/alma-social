"""Le mode crise (§ 8 H) — un bouton par marque, et le même geste quand le
Veilleur voit monter une vague de messages négatifs.

En crise, pour cette marque seulement :
- **tout s'arrête** : les publications programmées sont retenues (suspendues,
  pas effacées), et le planificateur n'en prépare plus ;
- **les réponses automatiques se taisent** : commentaires, messages, avis —
  tout arrive dans la boîte, plus rien ne part tout seul, pas même un
  « merci » sous un compliment (il passerait pour du mépris) ;
- **un brouillon de prise de parole** est écrit et envoyé au PDG. Il ne part
  jamais seul : une prise de parole engage la marque, c'est une personne qui
  la publie.

Le déclenchement automatique ne tient pas à un seul message en colère : il
faut, sur les deux dernières heures, au moins cinq messages négatifs
(plaintes, avis de deux étoiles ou moins), qu'ils fassent au moins 40 % de
ce qui est arrivé, et trois fois le rythme habituel de la marque. Un
restaurant qui reçoit deux plaintes un samedi soir n'est pas en crise.

Rien ne sort du mode crise tout seul : il faut le geste « Lever la crise »,
et ce qui a été retenu repart alors à des heures futures, espacées.
"""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field
from sqlalchemy import func, select, update

from . import acces, alertes, db, garde_fous, ia, journal

FENETRE = dt.timedelta(hours=2)
SEUIL = 5
PART = 0.40
FOIS = 3.0
HISTOIRE = dt.timedelta(days=14)


class PriseDeParole(BaseModel):
    texte: str = Field(description="la prise de parole publique, 3 à 6 phrases")


def en_crise(m: dict | None) -> bool:
    return bool(m and m.get("crisis_since"))


def declencher(m: dict, par: str, raison: str, auto: bool = False) -> dict:
    """→ {crise, retenues, brouillon}. Deux déclenchements ne font qu'une crise."""
    if en_crise(m):
        return {"crise": True, "retenues": 0, "brouillon": m.get("crisis_draft") or "", "deja": True}
    raison = (raison or "mode crise")[:300]
    maintenant = db.maintenant()
    with db.moteur().begin() as c:
        retenues = c.execute(update(db.posts).where(
            db.posts.c.brand_id == m["id"], db.posts.c.status == "programme").values(
            status="suspendu", error=f"mode crise : {raison}"[:2000])).rowcount
    brouillon = rediger(m, raison)
    with db.moteur().begin() as c:
        c.execute(update(db.brands).where(db.brands.c.id == m["id"]).values(
            crisis_since=maintenant, crisis_reason=raison, crisis_draft=brouillon))
    journal.noter(par, "crise_declenchee", "brand", m["id"], m["id"],
                  apres={"raison": raison, "auto": auto, "retenues": retenues})
    alertes.alerter(f"🚨 {m['name']} — MODE CRISE {'déclenché automatiquement' if auto else 'activé'}",
                    f"Pourquoi : {raison}\n\n"
                    f"Ce qui est fait : {retenues} publication{'s' if retenues != 1 else ''} retenue"
                    f"{'s' if retenues != 1 else ''}, plus aucune réponse automatique pour {m['name']}.\n\n"
                    f"Brouillon de prise de parole (rien n'est parti) :\n\n{brouillon}\n\n"
                    "Pour sortir : ALMA SOCIAL → la marque → « Lever la crise ».",
                    marque=m["id"], niveau="urgent", type_="crise", dedup=f"crise:{m['id']}:{maintenant:%Y%m%d%H}")
    return {"crise": True, "retenues": retenues, "brouillon": brouillon}


def lever(m: dict, par: str) -> dict:
    from . import pipeline
    if not en_crise(m):
        return {"crise": False, "repris": 0}
    with db.moteur().begin() as c:
        c.execute(update(db.brands).where(db.brands.c.id == m["id"]).values(
            crisis_since=None, crisis_reason=None))
    journal.noter(par, "crise_levee", "brand", m["id"], m["id"], avant={"depuis": m["crisis_since"]})
    return {"crise": False, "repris": pipeline.reprendre(par, m["id"])}


def rediger(m: dict, raison: str) -> str:
    """Le brouillon : reconnaître sans se justifier, ne rien affirmer qu'on ne
    sait pas, proposer un contact direct, dire qu'on reviendra."""
    tu = (m.get("voice") or {}).get("address") == "tu"
    try:
        obj, _ = ia.appeler(
            "Tu écris le brouillon d'une prise de parole publique pour une marque qui traverse un afflux de "
            "messages négatifs. Règles : reconnaître que des clients sont mécontents, sans minimiser ni se "
            "justifier ; n'affirmer AUCUN fait (cause, chiffre, responsabilité) qui n'est pas donné ; ne rien "
            "promettre de précis ; proposer un contact direct en privé ; dire qu'on reviendra vers eux. "
            f"{'Tutoiement' if tu else 'Vouvoiement'}. Signé « L'équipe {m['name']} ».",
            [{"type": "text", "text": f"Marque : {m['name']} — {m.get('activity', '')[:300]}\n"
                                      f"Ce qu'on observe : {raison}"}],
            PriseDeParole, max_tokens=1200, agent="reputation", marque_id=m["id"], objet="crise")
        texte = obj.texte.strip()
    except ia.ErreurIA:
        texte = ""
    if not texte or garde_fous.verifier_texte(texte, "facebook", m, None):
        texte = _modele(m, tu)
    return texte


def _modele(m: dict, tu: bool) -> str:
    if tu:
        return ("On a lu vos messages, un par un. Certains d'entre vous ne sont pas contents, et ça compte pour "
                "nous. On regarde ce qui s'est passé, sans rien laisser de côté. Si tu es concerné, écris-nous en "
                "privé : on te répond personnellement. On revient ici très vite.\n— L'équipe " + m["name"])
    return ("Nous avons lu vos messages, un par un. Certains d'entre vous sont mécontents, et nous le prenons au "
            "sérieux. Nous regardons ce qui s'est passé, sans rien laisser de côté. Si vous êtes concerné, "
            "écrivez-nous en privé : nous vous répondrons personnellement. Nous reviendrons ici très vite.\n"
            "— L'équipe " + m["name"])


# ── Le Veilleur ──────────────────────────────────────────────────────────
def _negatifs(c, marque_id: str, depuis: dt.datetime, jusqua: dt.datetime) -> tuple:
    """→ (négatifs, total) entre deux instants : plaintes et avis de 2 ★ ou moins."""
    conv = db.conversations.c
    plaintes = c.execute(select(func.count()).where(
        conv.brand_id == marque_id, conv.category == "plainte",
        conv.received_at > depuis, conv.received_at <= jusqua)).scalar_one()
    tous = c.execute(select(func.count()).where(
        conv.brand_id == marque_id, conv.received_at > depuis, conv.received_at <= jusqua)).scalar_one()
    rv = db.reviews.c
    mauvais = c.execute(select(func.count()).where(
        rv.brand_id == marque_id, rv.rating <= 2, rv.received_at > depuis, rv.received_at <= jusqua)).scalar_one()
    avis = c.execute(select(func.count()).where(
        rv.brand_id == marque_id, rv.received_at > depuis, rv.received_at <= jusqua)).scalar_one()
    return plaintes + mauvais, tous + avis


def surveiller(m: dict) -> dict | None:
    """Une vague négative ? → la crise déclenchée, sinon None."""
    if en_crise(m):
        return None
    maintenant = db.maintenant()
    with db.moteur().connect() as c:
        n, total = _negatifs(c, m["id"], maintenant - FENETRE, maintenant)
        if n < SEUIL:
            return None
        avant, _ = _negatifs(c, m["id"], maintenant - HISTOIRE, maintenant - FENETRE)
    habituel = avant / (HISTOIRE / FENETRE)          # négatifs par fenêtre de deux heures, d'habitude
    if n < PART * total or n < FOIS * max(habituel, 0.5):
        return None
    raison = (f"{n} messages négatifs en deux heures ({round(100 * n / total)} % de ce qui est arrivé), "
              f"contre {habituel:.1f} d'habitude")
    return declencher(m, "veilleur", raison, auto=True)


def surveiller_tout() -> int:
    return sum(1 for m in acces.marques() if surveiller(m))
