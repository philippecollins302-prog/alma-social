"""L'unique porte vers le modèle de langue — et le registre de ce qu'il coûte.

Tous les agents passent par `appeler` : lecture d'image, écriture, Critique,
tri des messages, Stratège, Analyste. Les bancs remplacent `ia.CLIENT` par un
faux — aucun banc ne parle à l'extérieur.

Ce que fait la porte, à chaque appel :

- elle choisit le MODÈLE DE L'AGENT (`agents.modele`), réglable en base ;
- elle met en cache le contexte de marque (le `system`) : il est identique
  d'un appel à l'autre pour une même marque, et le relire coûte dix fois
  moins cher que l'envoyer ;
- elle demande le repli côté serveur sur les modèles qui l'acceptent ;
- elle inscrit l'appel dans `agent_runs` : agent, marque, objet, modèle qui
  a VRAIMENT répondu, version des consignes, entrées, sortie, jetons, coût,
  durée (§ 6, la traçabilité) ;
- elle refuse de dépasser le PLAFOND MENSUEL : au-delà, chaque agent passe
  sur son repli déterministe et une alerte part une fois. Une dépense que
  Philippe n'a pas décidée n'a pas lieu (§ 23).

Sorties structurées : un schéma Pydantic par usage, le modèle rend du JSON
valide, jamais du texte à déchiffrer.
"""
from __future__ import annotations

import base64
import datetime as dt
import time

from . import agents, config

try:
    import anthropic
except ImportError:                     # pragma: no cover
    anthropic = None


class ErreurIA(Exception):
    pass


class SansCle(ErreurIA):
    """Aucune clé : chaque appelant a un repli déterministe et le dit."""


class Plafond(SansCle):
    """Le plafond mensuel est atteint : même conduite que sans clé."""


CLIENT = None          # remplacé par les bancs ; construit à la demande sinon
APPELS = []            # trace des derniers appels (page santé), sans contenu

# Les modèles qui acceptent le réglage d'effort et le repli serveur.
_AVEC_EFFORT = ("claude-opus-5", "claude-sonnet-5", "claude-opus-4", "claude-sonnet-4")
_AVEC_REPLI = ("claude-opus-5-5", "claude-sonnet-5-5")


def _client():
    global CLIENT
    if CLIENT is not None:
        return CLIENT
    if anthropic is None or not config.cle_anthropic():
        raise SansCle("ANTHROPIC_API_KEY absente")
    CLIENT = anthropic.Anthropic(api_key=config.cle_anthropic(), max_retries=2, timeout=180.0)
    return CLIENT


def disponible() -> bool:
    try:
        _client()
        return True
    except SansCle:
        return False


def image_bloc(octets: bytes, media_type: str = "image/jpeg") -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                       "data": base64.standard_b64encode(octets).decode()}}


# ── Le plafond ───────────────────────────────────────────────────────────
def plafond_usd() -> float:
    from . import journal
    v = journal.lire("ia.plafond_mois_usd")
    if v is None:
        v = config._env("SOCIAL_PLAFOND_IA_USD", "150")
    try:
        return float(v)
    except (TypeError, ValueError):
        return 150.0


def depense_du_mois(jour: dt.date | None = None) -> float:
    from sqlalchemy import func, select

    from . import db
    jour = jour or db.maintenant().date()
    debut = dt.datetime(jour.year, jour.month, 1)
    with db.moteur().connect() as c:
        v = c.execute(select(func.coalesce(func.sum(db.agent_runs.c.cout_usd), 0.0))
                      .where(db.agent_runs.c.created_at >= debut)).scalar()
    return round(float(v or 0.0), 4)


def _verifier_plafond():
    if depense_du_mois() < plafond_usd():
        return
    from . import alertes
    try:
        alertes.alerter("Plafond IA du mois atteint",
                        f"Les agents passent sur leurs replis jusqu'au 1er. Plafond : {plafond_usd():.0f} $. "
                        "Pour le relever : Réglages → Coûts.", niveau="panne", type_="cout",
                        dedup="plafond-ia", delai_dedup=dt.timedelta(days=31))
    except Exception:
        pass
    raise Plafond("plafond mensuel atteint")


# ── L'appel ──────────────────────────────────────────────────────────────
def _texte_de(contenu: list) -> str:
    morceaux = []
    for b in contenu:
        if isinstance(b, dict) and b.get("type") == "text":
            morceaux.append(b.get("text", ""))
        elif isinstance(b, dict) and b.get("type") == "image":
            morceaux.append("[image]")
    return "\n".join(morceaux)


def appeler(systeme: str, contenu: list, schema, max_tokens: int = 8000, usage: str = "",
            agent: str = "", marque_id: str | None = None, objet: str = "", cacher: bool = True):
    """→ (objet Pydantic validé, modèle qui a vraiment répondu).

    `agent` désigne le membre de l'équipe (`agents.EQUIPE`) ; à défaut,
    l'ancien `usage` de la v1 y est traduit. Le repli côté serveur laisse
    l'API relancer la même demande sur un autre modèle si le premier
    décline ; le modèle réellement utilisé est relu dans la réponse.
    """
    a = agents.agent(agent or usage)
    modele = agents.modele(a.cle)
    debut = time.monotonic()
    try:
        c = _client()
        _verifier_plafond()
    except SansCle as e:
        _tracer(a, marque_id, objet, modele, "plafond" if isinstance(e, Plafond) else "repli", debut,
                _texte_de(contenu))
        raise
    params = dict(model=modele, max_tokens=max_tokens,
                  messages=[{"role": "user", "content": contenu}], output_format=schema)
    params["system"] = ([{"type": "text", "text": systeme, "cache_control": {"type": "ephemeral"}}]
                        if cacher else systeme)
    if modele.startswith(_AVEC_EFFORT):
        params["output_config"] = {"effort": a.effort}
    if modele.startswith(_AVEC_REPLI):
        params["betas"] = ["server-side-fallback-2026-07-01"]
        params["fallbacks"] = "default"
    try:
        rep = c.beta.messages.parse(**params)
    except Exception as e:      # erreurs réseau / API : la file de travaux réessaiera
        _tracer(a, marque_id, objet, modele, "erreur", debut, _texte_de(contenu), sortie=str(e)[:500])
        raise ErreurIA(f"{type(e).__name__}: {e}") from e
    vrai = getattr(rep, "model", None) or modele
    u = getattr(rep, "usage", None)
    jetons = dict(entree=getattr(u, "input_tokens", 0) or 0, sortie=getattr(u, "output_tokens", 0) or 0,
                  lu=getattr(u, "cache_read_input_tokens", 0) or 0,
                  ecrit=getattr(u, "cache_creation_input_tokens", 0) or 0)
    raison = getattr(rep, "stop_reason", None)
    obj = getattr(rep, "parsed_output", None)
    issue = ("refus" if raison == "refusal" else "tronque" if raison == "max_tokens"
             else "vide" if obj is None else "ok")
    sortie = ""
    if obj is not None:
        try:
            sortie = obj.model_dump_json()
        except Exception:
            sortie = str(obj)
    _tracer(a, marque_id, objet, vrai, issue, debut, _texte_de(contenu), sortie, jetons)
    if issue == "refus":
        raise ErreurIA("le modèle a décliné la demande")
    if issue == "tronque":
        raise ErreurIA("réponse tronquée (max_tokens)")
    if issue == "vide":
        raise ErreurIA("réponse sans contenu structuré")
    return obj, vrai


def _tracer(a, marque_id, objet, modele, issue, debut, entrees="", sortie="", jetons=None):
    secondes = round(time.monotonic() - debut, 2)
    APPELS.append({"usage": a.cle, "secondes": secondes, "issue": issue})
    del APPELS[:-50]
    j = jetons or {}
    cout = agents.cout_usd(modele, j.get("entree", 0), j.get("sortie", 0), j.get("lu", 0), j.get("ecrit", 0))
    try:
        from sqlalchemy import insert

        from . import db
        with db.moteur().begin() as c:
            c.execute(insert(db.agent_runs).values(
                agent=a.cle, brand_id=marque_id, objet=str(objet)[:80], model=modele, consignes=a.consignes,
                entrees=(entrees or "")[:4000], sortie=(sortie or "")[:8000], issue=issue,
                tokens_in=j.get("entree", 0), tokens_out=j.get("sortie", 0),
                tokens_cache=j.get("lu", 0), cout_usd=cout, secondes=secondes))
    except Exception:           # la trace ne doit jamais faire tomber le travail
        pass


def couts(jours: int = 30) -> dict:
    """Pour l'écran Santé : ce qu'a coûté chaque agent, et la part de replis."""
    from sqlalchemy import func, select

    from . import db
    depuis = db.maintenant() - dt.timedelta(days=jours)
    t = db.agent_runs
    with db.moteur().connect() as c:
        rangs = c.execute(select(t.c.agent, t.c.issue, func.count(), func.sum(t.c.cout_usd),
                                 func.avg(t.c.secondes))
                          .where(t.c.created_at >= depuis).group_by(t.c.agent, t.c.issue)).all()
    par = {}
    for ag, issue, n, cout, sec in rangs:
        d = par.setdefault(ag, {"agent": ag, "appels": 0, "replis": 0, "echecs": 0, "cout_usd": 0.0,
                                "secondes": 0.0})
        d["appels"] += n
        d["cout_usd"] = round(d["cout_usd"] + float(cout or 0), 4)
        if issue in ("repli", "plafond"):
            d["replis"] += n
        elif issue != "ok":
            d["echecs"] += n
        if issue == "ok":
            d["secondes"] = round(float(sec or 0), 1)
    return {"jours": jours, "mois_usd": depense_du_mois(), "plafond_usd": plafond_usd(),
            "agents": sorted(par.values(), key=lambda d: -d["cout_usd"])}
