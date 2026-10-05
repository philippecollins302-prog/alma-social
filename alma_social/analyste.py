"""L'Analyste — lire les résultats, comprendre, proposer (§ 11.2, 17.2 à 17.5).

Tout ce qui est ici est CALCULÉ, sans modèle de langue : un chiffre se
recompte, une phrase de modèle non. Les règles :

- **Le réel seulement.** Une publication simulée (bac à sable) ne nourrit
  jamais le carnet, un test A/B ni une alerte : on ne tire pas de leçon d'un
  chiffre inventé.
- **Une conclusion demande du volume.** Huit publications au moins de chaque
  côté, un écart d'au moins 20 %, et un test de rangs (Mann-Whitney) qui le
  juge peu probable par hasard (p < 0,10). Sinon : « échantillon
  insuffisant », et on le dit au lieu d'inventer une tendance.
- **Le score d'une publication est relatif à son réseau** : 3 % d'engagement
  sur LinkedIn et 3 % sur TikTok ne se valent pas. On divise par la médiane
  de la marque SUR CE RÉSEAU.
- **Une alerte s'explique** : « 40 commentaires en 2 h, dont 31 sous la
  publication du 12 sur Instagram », pas juste un chiffre.
"""
from __future__ import annotations

import datetime as dt
import math
import statistics

from sqlalchemy import func, insert, select, update

from . import acces, alertes, carnet, creneaux, db, journal, reseaux

MIN_GROUPE = 8
ECART_MIN = 0.20
P_MAX = 0.10


# ── Les observations ─────────────────────────────────────────────────────
def _tranche(heure: int) -> str:
    return "matin" if heure < 11 else "midi" if heure < 14 else "après-midi" if heure < 18 else "soir"


def observations(marque_id: str, jours: int = 120) -> list:
    """Chaque publication RÉELLE avec sa meilleure mesure (24 h, sinon 7 j,
    sinon 1 h), son score relatif à son réseau, ses clients et ses étiquettes."""
    depuis = db.maintenant() - dt.timedelta(days=jours)
    with db.moteur().connect() as c:
        posts = db.lignes(c.execute(select(db.posts).where(
            db.posts.c.brand_id == marque_id, db.posts.c.status == "publie",
            db.posts.c.simulated.is_not(True), db.posts.c.published_at >= depuis)))
        ids = [p["id"] for p in posts] or [0]
        mes = db.lignes(c.execute(select(db.metrics).where(db.metrics.c.post_id.in_(ids),
                                                           db.metrics.c.simulated.is_not(True))))
        clients = dict(c.execute(select(db.leads.c.post_id, func.count()).where(
            db.leads.c.post_id.in_(ids)).group_by(db.leads.c.post_id)).all())
        assets = {a["id"]: a for a in db.lignes(c.execute(select(db.assets).where(
            db.assets.c.id.in_([p["asset_id"] for p in posts if p["asset_id"]] or [0]))))}
    rang = {"24h": 3, "7j": 2, "1h": 1}
    meilleure = {}
    for m in mes:
        if rang.get(m["checkpoint"], 0) > rang.get((meilleure.get(m["post_id"]) or {}).get("checkpoint"), 0):
            meilleure[m["post_id"]] = m
    obs = []
    for p in posts:
        m = meilleure.get(p["id"])
        if not m:
            continue
        a = assets.get(p["asset_id"]) or {}
        v = a.get("vision") or {}
        t = creneaux.paris(p["published_at"])
        premiere = ((p["text"] or "").strip().splitlines() or [""])[0]
        etiquettes = {
            "format": p.get("post_format") or "image", "reseau": p["platform"], "pilier": p["pillar"] or "",
            "moment": _tranche(t.hour), "jour": "week-end" if t.weekday() >= 5 else "semaine",
            "ouverture": "question" if premiere.rstrip().endswith("?") else "affirmation",
            "longueur": "court" if len(p["text"] or "") < 280 else "long",
            "humains": "avec des gens" if (v.get("visages") or []) else "sans personne",
            "contenu": v.get("type_contenu") or "",
        }
        ab = (p.get("guard_report") or {}).get("ab")
        obs.append({"post": p, "mesure": m, "brut": creneaux.score_engagement(m), "clients": clients.get(p["id"], 0),
                    "etiquettes": etiquettes, "ab": ab, "vues": m["views"] or m["reach"] or 0})
    # Le score relatif : divisé par la médiane de la marque sur CE réseau.
    par_reseau = {}
    for o in obs:
        par_reseau.setdefault(o["post"]["platform"], []).append(o["brut"])
    med = {k: (statistics.median(v) or 1e-9) for k, v in par_reseau.items()}
    for o in obs:
        o["score"] = o["brut"] / med[o["post"]["platform"]] if med[o["post"]["platform"]] > 0 else 0.0
    return obs


# ── La statistique, sans bibliothèque ────────────────────────────────────
def mann_whitney(a: list, b: list) -> float:
    """p bilatéral du test de rangs de Mann-Whitney (approximation normale,
    correction des ex aequo). Robuste aux valeurs extrêmes — une publication
    virale ne fait pas, à elle seule, une leçon."""
    n1, n2 = len(a), len(b)
    if n1 < 2 or n2 < 2:
        return 1.0
    tous = sorted([(x, 0) for x in a] + [(x, 1) for x in b])
    rangs, i = [0.0] * len(tous), 0
    ties = 0.0
    while i < len(tous):
        j = i
        while j + 1 < len(tous) and tous[j + 1][0] == tous[i][0]:
            j += 1
        r = (i + j) / 2 + 1
        for k in range(i, j + 1):
            rangs[k] = r
        t = j - i + 1
        ties += t ** 3 - t
        i = j + 1
    r1 = sum(r for r, (_, g) in zip(rangs, tous) if g == 0)
    u = r1 - n1 * (n1 + 1) / 2
    mu = n1 * n2 / 2
    n = n1 + n2
    sigma = math.sqrt(n1 * n2 / 12 * ((n + 1) - ties / (n * (n - 1))))
    if sigma == 0:
        return 1.0
    z = (abs(u - mu) - 0.5) / sigma
    return max(0.0, min(1.0, math.erfc(z / math.sqrt(2))))


def comparer(a: list, b: list) -> dict:
    """→ {na, nb, ma, mb, ecart, p, net}. `ecart` : de b vers a, en part de b."""
    ma = statistics.median(a) if a else 0.0
    mb = statistics.median(b) if b else 0.0
    ecart = (ma - mb) / mb if mb > 0 else (1.0 if ma > 0 else 0.0)
    p = mann_whitney(a, b)
    net = len(a) >= MIN_GROUPE and len(b) >= MIN_GROUPE and abs(ecart) >= ECART_MIN and p < P_MAX
    return {"na": len(a), "nb": len(b), "ma": round(ma, 3), "mb": round(mb, 3), "ecart": round(ecart, 3),
            "p": round(p, 4), "net": net}


# ── Pourquoi ça marche (§ 17.3) → le carnet ──────────────────────────────
NOMS_ETIQUETTES = {"format": "le format", "reseau": "le réseau", "pilier": "le pilier", "moment": "le moment",
                   "jour": "le jour", "ouverture": "la première phrase", "longueur": "la longueur du texte",
                   "humains": "la présence humaine", "contenu": "le type de photo"}


def correler(m: dict, par: str = "analyste") -> dict:
    """Chaque étiquette, valeur contre le reste. Ce qui est net entre au
    carnet, avec sa preuve. → {lecons: [...], insuffisant: [...]}."""
    obs = observations(m["id"])
    periode = ""
    if obs:
        d = sorted(o["post"]["published_at"] for o in obs)
        periode = f"{d[0]:%d/%m/%Y} → {d[-1]:%d/%m/%Y}"
    lecons, insuffisant = [], []
    for cle, nom in NOMS_ETIQUETTES.items():
        valeurs = {o["etiquettes"][cle] for o in obs if o["etiquettes"][cle]}
        if len(valeurs) < 2:
            continue
        for v in sorted(valeurs):
            a = [o["score"] for o in obs if o["etiquettes"][cle] == v]
            b = [o["score"] for o in obs if o["etiquettes"][cle] != v and o["etiquettes"][cle]]
            r = comparer(a, b)
            if not r["net"]:
                if len(a) < MIN_GROUPE or len(b) < MIN_GROUPE:
                    insuffisant.append(f"{cle}:{v}")
                continue
            if r["ecart"] <= 0:
                continue                 # on écrit ce qui marche ; le reste se lit en creux
            libelle = reseaux.NOMS.get(v, v) if cle == "reseau" else (acces.pilier(m, v) or {}).get("label", v) \
                if cle == "pilier" else v
            clients_a = sum(o["clients"] for o in obs if o["etiquettes"][cle] == v)
            phrase = (f"Chez {m['name']}, {nom} « {libelle} » fait {round(100 * r['ecart'])} % d'engagement de plus "
                      f"que le reste ({r['na']} publications contre {r['nb']})"
                      + (f", et a amené {clients_a} client(s)" if clients_a else "") + ".")
            lid = carnet.apprendre(m["id"], f"{cle}:{v}", phrase,
                                   {"echantillon": r["na"] + r["nb"], "periode": periode, "groupe": r["na"],
                                    "reste": r["nb"], "ecart": r["ecart"], "p": r["p"]}, par)
            if lid:
                lecons.append(phrase)
    return {"lecons": lecons, "insuffisant": sorted(set(insuffisant))}


def prediction(marque_id: str, etiquettes: dict) -> dict:
    """§ 11.2 : la performance probable d'une variante, d'après les
    publications comparables de la marque. Sert à départager, jamais à bloquer."""
    obs = observations(marque_id)

    def communs(o):
        return sum(1 for k, v in etiquettes.items() if o["etiquettes"].get(k) == v)
    # Les plus proches d'abord (toutes les étiquettes) ; à défaut, une de moins.
    proches = [o["score"] for o in obs if communs(o) == len(etiquettes)]
    if len(proches) < 4:
        proches = [o["score"] for o in obs if communs(o) >= max(1, len(etiquettes) - 1)]
    if len(proches) < 4:
        return {"score": None, "base": len(proches), "phrase": "pas assez de publications comparables"}
    s = statistics.median(proches)
    return {"score": round(s, 2), "base": len(proches),
            "phrase": f"{'au-dessus' if s >= 1.1 else 'en dessous' if s <= 0.9 else 'dans'} la moyenne de la marque "
                      f"({len(proches)} publications comparables)"}


# ── Le tableau de bord : ce que ça rapporte, ce que ça coûte (§ 17.2) ────
def valeur(m: dict, jours: int = 30) -> dict:
    depuis = db.maintenant() - dt.timedelta(days=jours)
    with db.moteur().connect() as c:
        leads = db.lignes(c.execute(select(db.leads).where(db.leads.c.brand_id == m["id"],
                                                           db.leads.c.created_at >= depuis)))
        posts = {p["id"]: p for p in db.lignes(c.execute(select(db.posts.c.id, db.posts.c.platform).where(
            db.posts.c.id.in_([l["post_id"] for l in leads if l["post_id"]] or [0]))))}
        ia_usd = c.execute(select(func.coalesce(func.sum(db.agent_runs.c.cout_usd), 0.0)).where(
            db.agent_runs.c.brand_id == m["id"], db.agent_runs.c.created_at >= depuis)).scalar_one()
        budget = db.ligne(c.execute(select(db.budgets).where(
            db.budgets.c.brand_id == m["id"], db.budgets.c.mois == f"{db.maintenant():%Y-%m}")))
        liens = {x["id"]: x for x in db.lignes(c.execute(select(db.links.c.id, db.links.c.platform).where(
            db.links.c.id.in_([l["link_id"] for l in leads if l["link_id"]] or [0]))))}
    par_canal, par_reseau, chiffre, avec_montant = {}, {}, 0.0, 0
    for l in leads:
        par_canal[l["channel"]] = par_canal.get(l["channel"], 0) + 1
        pf = posts.get(l["post_id"], {}).get("platform") or (liens.get(l["link_id"]) or {}).get("platform") or {
            "telephone": "téléphone", "uber_eats": "Uber Eats", "deliveroo": "Deliveroo",
            "manuel": "saisi à la main"}.get(l["channel"], "sans source")
        nom = f"QR « {pf.removeprefix('terrain:')} »" if pf.startswith("terrain:") else reseaux.NOMS.get(pf, pf)
        par_reseau[nom] = par_reseau.get(nom, 0) + 1
        if l["amount"]:
            chiffre += l["amount"]
            avec_montant += 1
    pub = float((budget or {}).get("consomme") or 0.0)
    cout = round(float(ia_usd) + pub, 2)
    n = len(leads)
    return {"clients": n, "par_canal": par_canal,
            "par_reseau": dict(sorted(par_reseau.items(), key=lambda kv: -kv[1])),
            "chiffre": round(chiffre, 2), "avec_montant": avec_montant,
            "cout": cout, "cout_ia": round(float(ia_usd), 2), "cout_pub": pub,
            "cout_par_client": round(cout / n, 2) if n and cout else None,
            "rattaches": sum(1 for l in leads if l["post_id"])}


# ── Anomalies et alertes (§ 17.5) ────────────────────────────────────────
EMBALLEMENT = 3.0           # trois fois la médiane du réseau
DECROCHAGE = 0.25           # un quart de la médiane, après 24 h
PIC_MIN = 10                # messages en 2 h, au moins
NEGATIFS = ("plainte",)      # les catégories de la Boîte qui disent « ça tourne mal »


def emballement(post_id: int) -> dict | None:
    """Après un relevé : la publication s'emballe-t-elle, en bien ou en mal ?"""
    with db.moteur().connect() as c:
        p = db.ligne(c.execute(select(db.posts).where(db.posts.c.id == post_id)))
    if not p or p["simulated"]:
        return None
    obs = observations(p["brand_id"])
    moi = next((o for o in obs if o["post"]["id"] == post_id), None)
    sur_reseau = [o for o in obs if o["post"]["platform"] == p["platform"] and o["post"]["id"] != post_id]
    if not moi or len(sur_reseau) < 5:
        return None
    m = acces.marque(p["brand_id"])
    with db.moteur().connect() as c:
        coms = db.lignes(c.execute(select(db.conversations).where(db.conversations.c.post_id == post_id)))
    negatifs = [x for x in coms if (x["category"] or "") in NEGATIFS]
    reseau = reseaux.NOMS.get(p["platform"], p["platform"])
    jour = f"{creneaux.paris(p['published_at']):%d/%m à %H h %M}"
    me = moi["mesure"]
    detail = (f"{me['views'] or me['reach']} vues, {me['likes']} réactions, {me['comments']} commentaires, "
              f"{me['shares']} partages ; {moi['score']:.1f} fois la médiane de {m['name']} sur {reseau}.")
    if len(negatifs) >= 5 and len(negatifs) >= 0.4 * max(1, len(coms)):
        sujet = f"{m['name']} : la publication du {jour} sur {reseau} s'emballe EN MAL"
        corps = (f"{len(negatifs)} commentaires négatifs sur {len(coms)}. {detail}\n"
                 f"Exemple : « {(negatifs[0]['text'] or '')[:160]} »\n"
                 "Ouvrez la Boîte : répondre vite, et « Retirer partout » si besoin.")
        alertes.alerter(sujet, corps, marque=m["id"], niveau="urgent", type_="emballement",
                        dedup=f"emballement-mal:{post_id}", delai_dedup=dt.timedelta(days=2))
        return {"sens": "mal", "sujet": sujet}
    if moi["score"] >= EMBALLEMENT:
        sujet = f"{m['name']} : la publication du {jour} sur {reseau} s'emballe"
        corps = (f"{detail}\nCe qui la distingue : {moi['etiquettes']['format']}, {moi['etiquettes']['moment']}, "
                 f"ouverture en {moi['etiquettes']['ouverture']}.\nRépondre aux commentaires maintenant "
                 "entretient la diffusion.")
        alertes.alerter(sujet, corps, marque=m["id"], niveau="info", type_="emballement",
                        dedup=f"emballement:{post_id}", delai_dedup=dt.timedelta(days=2))
        return {"sens": "bien", "sujet": sujet}
    return None


def pic_de_mentions(m: dict) -> dict | None:
    """Plus de messages en deux heures que d'habitude ? On dit d'OÙ ils viennent."""
    maintenant = db.maintenant()
    with db.moteur().connect() as c:
        recents = db.lignes(c.execute(select(db.conversations).where(
            db.conversations.c.brand_id == m["id"], db.conversations.c.received_at >= maintenant - dt.timedelta(hours=2))))
        avant = c.execute(select(func.count()).select_from(db.conversations).where(
            db.conversations.c.brand_id == m["id"],
            db.conversations.c.received_at >= maintenant - dt.timedelta(days=14),
            db.conversations.c.received_at < maintenant - dt.timedelta(hours=2))).scalar_one()
    habituel = avant / (14 * 12)                      # par tranche de deux heures
    n = len(recents)
    if n < max(PIC_MIN, 4 * habituel):
        return None
    par_post, par_auteur = {}, {}
    for x in recents:
        par_post[x["post_id"]] = par_post.get(x["post_id"], 0) + 1
        par_auteur[x["author"]] = par_auteur.get(x["author"], 0) + 1
    post_id, sous = max(par_post.items(), key=lambda kv: kv[1])
    origine = ""
    if post_id and sous >= n / 2:
        with db.moteur().connect() as c:
            p = db.ligne(c.execute(select(db.posts).where(db.posts.c.id == post_id)))
        if p:
            origine = (f", dont {sous} sous la publication du {creneaux.paris(p['published_at'] or p['scheduled_at']):%d/%m} "
                       f"sur {reseaux.NOMS.get(p['platform'], p['platform'])} (« {(p['text'] or '')[:60]} »)")
    auteur, de_lui = max(par_auteur.items(), key=lambda kv: kv[1])
    if de_lui >= 3:
        origine += f" ; {de_lui} viennent du même compte ({auteur})"
    negatifs = sum(1 for x in recents if (x["category"] or "") in NEGATIFS)
    sujet = f"{m['name']} : {n} messages en 2 h (d'habitude {habituel:.1f})"
    corps = f"{n} commentaires et messages en deux heures{origine}. {negatifs} négatif(s).\nOuvrez la Boîte."
    alertes.alerter(sujet, corps, marque=m["id"], niveau="urgent" if negatifs >= n / 3 else "info",
                    type_="pic", dedup=f"pic:{m['id']}", delai_dedup=dt.timedelta(hours=6))
    return {"n": n, "habituel": habituel, "sujet": sujet, "corps": corps}


def anomalies(m: dict, jours: int = 7) -> list:
    """Pour le lundi : ce qui a décroché cette semaine, et la cause probable."""
    obs = [o for o in observations(m["id"], 60)]
    recentes = [o for o in obs if o["post"]["published_at"] >= db.maintenant() - dt.timedelta(days=jours)]
    out = []
    for o in recentes:
        if o["score"] <= DECROCHAGE and len([x for x in obs if x["post"]["platform"] == o["post"]["platform"]]) >= 5:
            e = o["etiquettes"]
            out.append(f"{reseaux.NOMS.get(e['reseau'], e['reseau'])} du {creneaux.paris(o['post']['published_at']):%d/%m} : "
                       f"{o['score']:.0%} de la médiane — {e['format']}, {e['moment']}, {e['contenu'] or 'sujet non lu'}")
    return out


# ── Les décisions du lundi (§ 17.4) ──────────────────────────────────────
def proposer_decisions(m: dict, semaine: str) -> list:
    """Trois décisions au plus, calculées, chacune avec son pourquoi.
    Appliquées le lundi à midi sauf refus. Une dépense n'est JAMAIS
    appliquée seule : elle est « à décider »."""
    from . import planificateur
    with db.moteur().connect() as c:
        deja = c.execute(select(func.count()).select_from(db.decisions).where(
            db.decisions.c.brand_id == m["id"], db.decisions.c.semaine == semaine)).scalar_one()
    if deja:
        return lister(m["id"], semaine)
    obs = observations(m["id"], 60)
    props = []
    stock = planificateur.stock(m)
    v = valeur(m)
    if stock["jours_couverts"] >= 21 and m["cadence_max"] < 7 and v["clients"] >= 3:
        props.append(("cadence", f"Passer {m['name']} à {m['cadence_max'] + 1} publications par semaine au plus",
                      f"{stock['banque']} photos en banque ({stock['jours_couverts']} jours d'avance) et "
                      f"{v['clients']} clients en 30 jours : la matière et la demande sont là.",
                      {"cadence_max": m["cadence_max"] + 1}, True))
    elif stock["jours_couverts"] < 5 and m["cadence_max"] > max(2, m["cadence_min"]):
        props.append(("cadence", f"Ramener {m['name']} à {m['cadence_max'] - 1} publications par semaine au plus",
                      f"Il reste de quoi tenir {stock['jours_couverts']} jour(s) : mieux vaut moins, mais tenir.",
                      {"cadence_max": m["cadence_max"] - 1}, True))
    par_pilier = {}
    for o in obs:
        if o["etiquettes"]["pilier"]:
            par_pilier.setdefault(o["etiquettes"]["pilier"], []).append(o["score"])
    bons = [(statistics.median(s), k) for k, s in par_pilier.items() if len(s) >= 4]
    if len(bons) >= 2:
        _, k = max(bons)
        r = comparer(par_pilier[k], [x for kk, s in par_pilier.items() if kk != k for x in s])
        if r["net"] and r["ecart"] > 0:
            lab = (acces.pilier(m, k) or {}).get("label", k)
            props.append(("pilier", f"Donner dix points de plus au pilier « {lab} » chez {m['name']}",
                          f"Sur {r['na']} publications, il fait {round(100 * r['ecart'])} % d'engagement de plus "
                          f"que les autres piliers ({r['nb']} publications).",
                          {"pilier": k, "points": 10}, True))
    gagnant = max(obs, key=lambda o: o["score"], default=None)
    if gagnant and gagnant["score"] >= 2 and gagnant["post"]["platform"] in ("instagram", "facebook"):
        props.append(("budget", f"Booster la publication du {creneaux.paris(gagnant['post']['published_at']):%d/%m} "
                                f"sur {reseaux.NOMS.get(gagnant['post']['platform'])} (à décider : c'est une dépense)",
                      f"Elle fait {gagnant['score']:.1f} fois la médiane sans un euro ; l'enveloppe publicitaire "
                      "est à zéro tant que vous n'en décidez pas une.", {"post_id": gagnant["post"]["id"]}, False))
    out = []
    for type_, phrase, pourquoi, params, auto in props[:3]:
        with db.moteur().begin() as c:
            c.execute(insert(db.decisions).values(
                brand_id=m["id"], semaine=semaine, type=type_, phrase=phrase, pourquoi=pourquoi, parametres=params,
                auto=auto, statut="proposee" if auto else "a_decider", created_at=db.maintenant()))
    return lister(m["id"], semaine)


def lister(marque_id: str | None = None, semaine: str | None = None) -> list:
    q = select(db.decisions)
    if marque_id:
        q = q.where(db.decisions.c.brand_id == marque_id)
    if semaine:
        q = q.where(db.decisions.c.semaine == semaine)
    with db.moteur().connect() as c:
        return db.lignes(c.execute(q.order_by(db.decisions.c.id).limit(60)))


def trancher(decision_id: int, oui: bool, par: str) -> dict:
    with db.moteur().begin() as c:
        d = db.ligne(c.execute(select(db.decisions).where(db.decisions.c.id == decision_id)))
    if not d or d["statut"] not in ("proposee", "a_decider"):
        raise ValueError("décision déjà tranchée")
    if not oui:
        _statut(d, "refusee", par)
        return {"statut": "refusee"}
    if d["type"] == "budget":
        # Une dépense acceptée est notée ; elle ne part que si l'enveloppe
        # publicitaire existe (§ 14.6, jalon 6).
        _statut(d, "appliquee", par)
        return {"statut": "appliquee", "note": "noté : le boost partira dès que l'enveloppe sera posée"}
    appliquer(d, par)
    return {"statut": "appliquee"}


def _statut(d: dict, statut: str, par: str):
    with db.moteur().begin() as c:
        c.execute(update(db.decisions).where(db.decisions.c.id == d["id"]).values(
            statut=statut, par=par, decide_le=db.maintenant()))
    journal.noter(par, f"decision_{statut}", "decision", d["id"], d["brand_id"], apres={"phrase": d["phrase"]})


def appliquer(d: dict, par: str = "systeme"):
    m = acces.marque(d["brand_id"])
    p = d["parametres"] or {}
    if d["type"] == "cadence":
        n = int(p["cadence_max"])
        with db.moteur().begin() as c:
            c.execute(update(db.brands).where(db.brands.c.id == m["id"]).values(
                cadence_max=max(n, m["cadence_min"]), cadence_min=min(m["cadence_min"], n)))
    elif d["type"] == "pilier":
        piliers = [dict(x) for x in (m.get("pillars") or [])]
        rot = [x for x in piliers if not x.get("hors_rotation")]
        if not any(float(x.get("share") or 0) for x in rot):
            for x in rot:
                x["share"] = round(100 / len(rot), 1)
        cible = next((x for x in rot if x["key"] == p["pilier"]), None)
        if cible:
            pts = float(p.get("points") or 10)
            autres = [x for x in rot if x is not cible]
            for x in autres:
                x["share"] = round(max(0.0, float(x["share"]) - pts / len(autres)), 1)
            cible["share"] = round(float(cible["share"]) + pts, 1)
            with db.moteur().begin() as c:
                c.execute(update(db.brands).where(db.brands.c.id == m["id"]).values(pillars=piliers))
    _statut(d, "appliquee", par)


def appliquer_decisions_dues(par: str = "systeme") -> int:
    """Le lundi à midi : ce qui n'a pas été refusé s'applique."""
    lundi = acces.aujourdhui() - dt.timedelta(days=acces.aujourdhui().weekday())
    n = 0
    for d in lister(semaine=lundi.isoformat()):
        if d["statut"] == "proposee" and d["auto"]:
            appliquer(d, par)
            n += 1
    return n


def tour(par: str = "analyste") -> dict:
    """Chaque jour : le carnet se met à jour, les tests A/B se concluent, les pics se voient."""
    from . import ab
    out = {}
    for m in acces.marques():
        r = correler(m, par)
        out[m["id"]] = {"lecons": len(r["lecons"]), "ab": ab.conclure_tout(m, par)}
    return out
