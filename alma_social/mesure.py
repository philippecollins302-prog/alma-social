"""La mesure, jusqu'au client généré — la fonction qui justifie l'application.

Niveau 1 — audience : relevés à +1 h, +24 h et +7 jours, historisés (jamais écrasés).
Niveau 2 — clics : chaque lien sortant passe par le raccourcisseur maison
           (`go.<domaine>/<code>`, ou `/go/<code>` tant que le domaine n'est pas
           acheté). Un code = une publication, une marque, un réseau, une date.
Niveau 3 — clients : le lien dépose un marqueur (`am=<code>`) ; le formulaire du
           site de la marque le renvoie (script /s/marqueur.js) ; une demande de
           devis remonte donc jusqu'à la publication qui l'a déclenchée. Plus la
           saisie manuelle (« il nous a vus sur Instagram ») et, en option, un
           numéro de téléphone tracé par marque.

Le chiffre en haut du tableau de bord : par marque, sur 30 jours, le nombre de
demandes, de commandes ou d'appels, et les TROIS publications qui en sont
responsables. Pas une courbe de likes.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import secrets
import urllib.parse

from sqlalchemy import func, insert, select, update

from . import config, creneaux, db, file, journal

ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"     # ni 0/O ni 1/l : un code se dicte


def _code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(7))


def url_courte(code: str) -> str:
    return f"{config.url_liens()}/{code}"


def creer_lien(marque: dict, post_id: int | None, plateforme: str, sorte: str, cible: str) -> dict:
    """Un lien tracé, paramètres UTM compris. La cible manque (site pas encore
    renseigné) ? On renvoie vers la page « lien en bio » de la marque : le lien
    marche dès le premier jour."""
    cible = cible or f"{config.url_publique()}/b/{marque['id']}"
    utm = {"utm_source": plateforme or "direct", "utm_medium": "social",
           "utm_campaign": f"{marque['id']}-{db.maintenant():%Y%m}",
           "utm_content": f"post{post_id}" if post_id else sorte}
    for _ in range(5):
        code = _code()
        try:
            with db.moteur().begin() as c:
                r = c.execute(insert(db.links).values(
                    code=code, post_id=post_id, brand_id=marque["id"], platform=plateforme,
                    kind=sorte, target_url=cible, utm=utm, created_at=db.maintenant()))
                return {"id": r.inserted_primary_key[0], "code": code, "url": url_courte(code)}
        except Exception:
            continue
    raise RuntimeError("impossible de créer un code de lien unique")


def liens_de_publication(marque: dict, post_id: int, plateforme: str) -> dict:
    """Le lien principal d'une publication. Pour SAZÚ : la page de choix
    « Uber Eats ou Deliveroo », et derrière, un lien tracé DIFFÉRENT vers
    chacune des deux plateformes, propre à cette publication."""
    l = marque.get("links") or {}
    if marque.get("sector") == "food":
        principal = creer_lien(marque, post_id, plateforme, "commande", "")
        with db.moteur().begin() as c:
            c.execute(update(db.links).where(db.links.c.id == principal["id"]).values(
                target_url=f"{config.url_publique()}/c/{principal['code']}"))
        creer_lien(marque, post_id, plateforme, "uber_eats", l.get("uber_eats") or "")
        creer_lien(marque, post_id, plateforme, "deliveroo", l.get("deliveroo") or "")
        return principal
    return creer_lien(marque, post_id, plateforme, "devis" if l.get("devis") else "site",
                      l.get("devis") or l.get("site") or "")


def cible_avec_marqueur(lien: dict) -> str:
    """L'adresse finale : la cible, plus les UTM, plus le marqueur `am`."""
    u = urllib.parse.urlsplit(lien["target_url"])
    q = dict(urllib.parse.parse_qsl(u.query))
    q.update(lien.get("utm") or {})
    q["am"] = lien["code"]
    return urllib.parse.urlunsplit((u.scheme, u.netloc, u.path, urllib.parse.urlencode(q), u.fragment))


def appareil(agent: str) -> str:
    a = (agent or "").lower()
    if any(k in a for k in ("bot", "crawler", "spider", "preview", "facebookexternalhit", "slurp")):
        return "robot"
    if "ipad" in a or "tablet" in a:
        return "tablette"
    if any(k in a for k in ("iphone", "android", "mobile")):
        return "mobile"
    return "ordinateur"


def noter_clic(code: str, agent: str, referent: str, ip: str, ville: str = "", source: str = "lien"):
    """→ le lien (dict) ou None. Les robots d'aperçu (Facebook, Slack…)
    ouvrent chaque lien : ils sont consignés mais ne comptent pas comme clics."""
    with db.moteur().begin() as c:
        l = db.ligne(c.execute(select(db.links).where(db.links.c.code == code)))
        if not l:
            return None
        sorte = appareil(agent)
        c.execute(insert(db.clicks).values(
            link_id=l["id"], at=db.maintenant(), city=ville[:120], device=sorte,
            referrer=(referent or "")[:500], marker=code,
            ip_hash=hashlib.sha256((ip or "").encode()).hexdigest()[:32], source=source))
        if sorte != "robot":
            c.execute(update(db.links).where(db.links.c.id == l["id"]).values(clicks=db.links.c.clicks + 1))
    return l


def enregistrer_lead(marque_id: str, type_: str, canal: str, marqueur: str = "", post_id=None,
                     montant=None, source: str = "", note: str = "", par: str = "") -> int:
    """Une demande, une commande, un appel. Le marqueur, s'il est là, rattache
    la demande à la publication qui l'a déclenchée."""
    lien = None
    if marqueur:
        with db.moteur().begin() as c:
            lien = db.ligne(c.execute(select(db.links).where(db.links.c.code == marqueur)))
        if lien and lien["brand_id"] != marque_id:
            lien = None             # un marqueur d'une autre marque ne vaut rien ici
    if lien and not post_id:
        post_id = lien["post_id"]
    with db.moteur().begin() as c:
        r = c.execute(insert(db.leads).values(
            brand_id=marque_id, post_id=post_id, link_id=lien["id"] if lien else None,
            channel=canal, type=type_, amount=montant, source=source[:300], marker=marqueur[:40],
            note=note[:1000], created_by=par, created_at=db.maintenant()))
        lid = r.inserted_primary_key[0]
    journal.noter(par or "site", "lead", "lead", lid, marque_id,
                  apres={"type": type_, "canal": canal, "post_id": post_id, "marqueur": marqueur})
    return lid


# ── Relevés ──────────────────────────────────────────────────────────────
JALONS = {"1h": dt.timedelta(hours=1), "24h": dt.timedelta(hours=24), "7j": dt.timedelta(days=7)}


def programmer_releves(post_id: int, publie_le: dt.datetime):
    for jalon, delai in JALONS.items():
        file.ajouter("mesurer", {"post_id": post_id, "jalon": jalon}, quand=publie_le + delai,
                     dedup=f"mesurer:{post_id}:{jalon}", essais_max=3)


def enregistrer_mesures(post_id: int, jalon: str, m) -> None:
    with db.moteur().begin() as c:
        clics = c.execute(select(func.coalesce(func.sum(db.links.c.clicks), 0)).where(
            db.links.c.post_id == post_id)).scalar_one()
        c.execute(insert(db.metrics).values(
            post_id=post_id, checkpoint=jalon, measured_at=db.maintenant(), views=m.views,
            reach=m.reach, likes=m.likes, comments=m.comments, shares=m.shares, saves=m.saves,
            clicks=max(m.clicks, int(clics)), followers_gained=m.followers_gained,
            simulated=m.simulated, raw=m.raw or {}))


# ── Le tableau de bord ───────────────────────────────────────────────────
def resume_marque(marque_id: str, jours: int = 30) -> dict:
    """Le chiffre du haut : les clients générés, et les trois publications responsables."""
    depuis = db.maintenant() - dt.timedelta(days=jours)
    with db.moteur().begin() as c:
        leads = db.lignes(c.execute(select(db.leads).where(
            db.leads.c.brand_id == marque_id, db.leads.c.created_at >= depuis)))
        clics_commande = c.execute(select(func.coalesce(func.sum(db.links.c.clicks), 0)).where(
            db.links.c.brand_id == marque_id, db.links.c.kind.in_(("uber_eats", "deliveroo")),
            db.links.c.created_at >= depuis)).scalar_one()
        clics = c.execute(select(func.coalesce(func.sum(db.links.c.clicks), 0)).where(
            db.links.c.brand_id == marque_id, db.links.c.created_at >= depuis,
            db.links.c.kind.notin_(("uber_eats", "deliveroo")))).scalar_one()
        publies = db.lignes(c.execute(select(db.posts).where(
            db.posts.c.brand_id == marque_id, db.posts.c.status.in_(("publie", "simule")),
            db.posts.c.published_at >= depuis)))
    par_type = {"devis": 0, "commande": 0, "appel": 0}
    par_post = {}
    for l in leads:
        par_type[l["type"]] = par_type.get(l["type"], 0) + 1
        if l["post_id"]:
            par_post[l["post_id"]] = par_post.get(l["post_id"], 0) + 1
    top = sorted(par_post.items(), key=lambda kv: -kv[1])[:3]
    ids = [pid for pid, _ in top]
    infos = {}
    if ids:
        with db.moteur().begin() as c:
            for p in db.lignes(c.execute(select(db.posts).where(db.posts.c.id.in_(ids)))):
                infos[p["id"]] = p
    return {
        "marque": marque_id, "jours": jours, "clients": sum(par_type.values()), "par_type": par_type,
        "clics": int(clics), "clics_commande": int(clics_commande),
        "publications": len([p for p in publies if not p["simulated"]]),
        "publications_simulees": len([p for p in publies if p["simulated"]]),
        "top": [{"post_id": pid, "clients": n, "platform": infos.get(pid, {}).get("platform"),
                 "texte": (infos.get(pid, {}).get("text") or "")[:140],
                 "permalink": infos.get(pid, {}).get("permalink"),
                 "asset_id": infos.get(pid, {}).get("asset_id"),
                 "publie_le": infos[pid]["published_at"].isoformat() if pid in infos and infos[pid]["published_at"] else None}
                for pid, n in top],
    }


def audience(marque_ids: list, jours: int = 30, plateforme: str | None = None) -> dict:
    """Niveau 1, filtrable par marque, période et réseau — en dessous du chiffre qui compte."""
    depuis = db.maintenant() - dt.timedelta(days=jours)
    q = select(db.posts.c.id, db.posts.c.brand_id, db.posts.c.platform, db.posts.c.simulated).where(
        db.posts.c.brand_id.in_(marque_ids), db.posts.c.published_at >= depuis)
    if plateforme:
        q = q.where(db.posts.c.platform == plateforme)
    with db.moteur().begin() as c:
        posts = db.lignes(c.execute(q))
        ids = [p["id"] for p in posts]
        mesures = db.lignes(c.execute(select(db.metrics).where(db.metrics.c.post_id.in_(ids)))) if ids else []
    dernier = {}
    for m in sorted(mesures, key=lambda x: x["measured_at"]):
        dernier[m["post_id"]] = m
    out = {}
    for p in posts:
        m = dernier.get(p["id"])
        cle = (p["brand_id"], p["platform"])
        o = out.setdefault(cle, {"marque": p["brand_id"], "reseau": p["platform"], "publications": 0,
                                 "vues": 0, "portee": 0, "engagement": 0, "abonnes": 0, "simule": False})
        o["publications"] += 1
        o["simule"] = o["simule"] or bool(p["simulated"])
        if m:
            o["vues"] += m["views"]
            o["portee"] += m["reach"]
            o["engagement"] += m["likes"] + m["comments"] + m["shares"] + m["saves"]
            o["abonnes"] += m["followers_gained"]
    return {"lignes": sorted(out.values(), key=lambda o: (o["marque"], o["reseau"]))}


def recalibrer(marque: dict) -> dict:
    """Le recalage mensuel des créneaux, sur les chiffres RÉELS (jamais simulés)."""
    depuis = db.maintenant() - dt.timedelta(days=120)
    rapport = {}
    with db.moteur().begin() as c:
        posts = db.lignes(c.execute(select(db.posts).where(
            db.posts.c.brand_id == marque["id"], db.posts.c.status == "publie",
            db.posts.c.simulated.is_(False), db.posts.c.published_at >= depuis)))
        ids = [p["id"] for p in posts]
        mesures = db.lignes(c.execute(select(db.metrics).where(
            db.metrics.c.post_id.in_(ids), db.metrics.c.checkpoint == "24h",
            db.metrics.c.simulated.is_(False)))) if ids else []
    par_post = {m["post_id"]: m for m in mesures}
    for reseau in set(p["platform"] for p in posts):
        obs = []
        for p in posts:
            if p["platform"] != reseau or p["id"] not in par_post:
                continue
            t = creneaux.paris(p["published_at"])
            obs.append((t.weekday(), t.hour, creneaux.score_engagement(par_post[p["id"]])))
        profil = creneaux.apprendre(obs)
        with db.moteur().begin() as c:
            existe = c.execute(select(db.slot_profiles.c.id).where(
                db.slot_profiles.c.brand_id == marque["id"], db.slot_profiles.c.platform == reseau)).first()
            vals = {"weights": profil, "observations": len(obs), "computed_at": db.maintenant()}
            if existe:
                c.execute(update(db.slot_profiles).where(db.slot_profiles.c.id == existe[0]).values(**vals))
            else:
                c.execute(insert(db.slot_profiles).values(brand_id=marque["id"], platform=reseau, **vals))
        rapport[reseau] = len(obs)
    return rapport


def profils(marque_id: str) -> dict:
    with db.moteur().begin() as c:
        rows = db.lignes(c.execute(select(db.slot_profiles).where(db.slot_profiles.c.brand_id == marque_id)))
    return {r["platform"]: r["weights"] for r in rows}
