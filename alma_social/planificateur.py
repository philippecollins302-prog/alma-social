"""Le planificateur — le calendrier de chaque marque, et la banque qui le nourrit.

- un objectif de 3 à 5 publications par semaine et par marque (cadence en base) ;
- les meilleurs jours d'abord (créneaux.py), jamais deux fois de suite le même pilier ;
- les séries récurrentes (« le bowl du mardi ») et les campagnes posent leurs créneaux d'office ;
- le 25, le mois suivant est proposé ; la veille du 1er, un rappel ; le 1er, il
  s'applique — validé ou non (« la seule validation humaine de toute l'application ») ;
- chaque matin, les créneaux des 7 prochains jours sont remplis depuis la banque :
  photo du bon pilier d'abord, puis une ancienne qui a bien marché (plus de 90 jours,
  nouveau texte, nouveau cadrage), puis — pour une campagne — une carte à la charte ;
- s'il manque de quoi tenir la semaine, le responsable reçoit une demande PRÉCISE.

Tous les jours sont des jours de PARIS (acces.aujourdhui).
"""
from __future__ import annotations

import calendar
import datetime as dt
import math

from sqlalchemy import func, insert, select, update

from . import acces, alertes, creneaux, db, journal, mesure, reseaux

HORIZON = 7                     # jours remplis d'avance
FENETRE_RECYCLAGE = dt.timedelta(days=90)
_JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


# ── Outils ───────────────────────────────────────────────────────────────
def cible_hebdo(m: dict) -> int:
    """Le milieu de la fourchette, arrondi au-dessus : 3–5 → 4, 4–5 → 5."""
    lo, hi = m.get("cadence_min") or 3, m.get("cadence_max") or 5
    return max(lo, min(hi, math.ceil((lo + hi) / 2)))


def jours_fermes(m: dict) -> set:
    return set((m.get("links") or {}).get("jours_fermes") or [])


def calendrier_des(m: dict) -> dt.date | None:
    """Le jour où le calendrier ordinaire commence. Avant, seule une campagne
    publie : SAZÚ n'a rien à montrer avant son ouverture (le 27/11/2026), et
    une photo de bowl en octobre gâcherait le teasing qui ne montre que la date."""
    v = (m.get("links") or {}).get("calendrier_des")
    try:
        return dt.date.fromisoformat(v) if v else None
    except ValueError:
        return None


def _lundi(jour: dt.date) -> dt.date:
    return jour - dt.timedelta(days=jour.weekday())


def creneaux_de(marque_id: str, debut: dt.date, fin: dt.date, statuts=None) -> list:
    q = select(db.slots).where(db.slots.c.brand_id == marque_id, db.slots.c.day >= debut, db.slots.c.day <= fin)
    if statuts:
        q = q.where(db.slots.c.status.in_(statuts))
    with db.moteur().begin() as c:
        return db.lignes(c.execute(q.order_by(db.slots.c.day, db.slots.c.id)))


def _compte_semaine(marque_id: str, jour: dt.date) -> int:
    l = _lundi(jour)
    return len(creneaux_de(marque_id, l, l + dt.timedelta(days=6), ("libre", "rempli", "publie", "manque")))


def _parts(m: dict) -> dict:
    """Le poids de chaque pilier : la part déclarée (« 30 % ») ou l'égalité."""
    piliers = m.get("pillars") or []
    if not piliers:
        return {}
    parts = {p["key"]: float(p.get("share") or 0) for p in piliers if not p.get("hors_rotation")}
    if not parts:
        return {}
    if sum(parts.values()) <= 0:
        return {k: 1 / len(parts) for k in parts}
    total = sum(parts.values())
    return {k: v / total for k, v in parts.items()}


def _poser(m: dict, jour: dt.date, source: str, **vals) -> int:
    with db.moteur().begin() as c:
        return c.execute(insert(db.slots).values(
            brand_id=m["id"], day=jour, source=source, status="libre", created_at=db.maintenant(),
            **{k: v for k, v in vals.items() if v is not None})).inserted_primary_key[0]


# ── Le mois ──────────────────────────────────────────────────────────────
def generer_mois(m: dict, annee: int, mois: int, a_partir_de: dt.date | None = None) -> list:
    """Le calendrier proposé d'un mois, SANS l'écrire : une liste de créneaux
    {jour, pilier, sujet, source, serie_id, heure, reseaux}."""
    premier = dt.date(annee, mois, 1)
    dernier = dt.date(annee, mois, calendar.monthrange(annee, mois)[1])
    debut = max(premier, a_partir_de or premier, calendrier_des(m) or premier)
    if debut > dernier:
        return []
    fermes = jours_fermes(m)
    profils = mesure.profils(m["id"])
    reseaux_actifs = m.get("active_platforms") or []
    existants = creneaux_de(m["id"], debut, dernier)
    pris = {s["day"] for s in existants}
    prevus = []

    with db.moteur().begin() as c:
        series = db.lignes(c.execute(select(db.series).where(
            db.series.c.brand_id == m["id"], db.series.c.active.is_(True))))
    jour = debut
    while jour <= dernier:
        for se in series:
            if se["weekday"] == jour.weekday() and (not se["starts_on"] or jour >= se["starts_on"]) \
                    and not any(s["series_id"] == se["id"] and s["day"] == jour for s in existants):
                prevus.append({"jour": jour, "pilier": se["pillar"], "sujet": se["label"], "source": "serie",
                               "serie_id": se["id"], "heure": se["time"] or "", "reseaux": se["platforms"] or []})
                pris.add(jour)
        jour += dt.timedelta(days=1)

    # Les semaines : on complète jusqu'à la cible avec les meilleurs jours.
    cible = cible_hebdo(m)
    lundi = _lundi(debut)
    while lundi <= dernier:
        jours = [lundi + dt.timedelta(days=i) for i in range(7)]
        jours = [j for j in jours if debut <= j <= dernier]
        deja = sum(1 for s in existants if s["day"] in jours and s["status"] != "annule") \
            + sum(1 for p in prevus if p["jour"] in jours)
        # Une semaine coupée par le mois n'a droit qu'à sa part de la cible.
        besoin = round(cible * len(jours) / 7) - deja
        valeur = {lundi + dt.timedelta(days=i): creneaux.poids_du_jour(
            m.get("sector", "b2c"), reseaux_actifs, i, profils) for i in range(7)}
        meilleur = max(valeur.values(), default=0)
        # Un jour qui vaut moins du tiers du meilleur jour de la semaine (le
        # dimanche d'une marque LinkedIn) n'est jamais pris, même pour finir
        # un bout de semaine coupé par le mois.
        libres = [j for j in jours if j not in pris and j.weekday() not in fermes
                  and valeur[j] >= 0.35 * meilleur]
        libres.sort(key=lambda j: -valeur[j])
        choisis = []
        # 1) Les bons jours, jamais deux d'affilée.
        for j in libres:
            if len(choisis) >= besoin:
                break
            if valeur[j] >= 0.5 * meilleur and not any(abs((j - k).days) == 1 for k in choisis):
                choisis.append(j)
        # 2) S'il en manque, les meilleurs qui restent : deux mardi-mercredi
        #    valent mieux qu'un samedi sur LinkedIn.
        for j in libres:
            if len(choisis) >= besoin:
                break
            if j not in choisis:
                choisis.append(j)
        for j in sorted(choisis):
            prevus.append({"jour": j, "pilier": "", "sujet": "", "source": "plan", "serie_id": None,
                           "heure": "", "reseaux": []})
            pris.add(j)
        lundi += dt.timedelta(days=7)

    # Les piliers : celui qui a le plus de retard sur sa part, jamais le même deux fois de suite.
    parts = _parts(m)
    faits = {k: 0 for k in parts}
    precedent = _dernier_pilier(m["id"], debut)
    for p in sorted(prevus, key=lambda x: x["jour"]):
        if p["source"] == "plan" and parts:
            n = sum(faits.values()) + 1
            candidats = sorted(parts, key=lambda k: faits[k] - parts[k] * n)
            choix = next((k for k in candidats if k != precedent), candidats[0])
            p["pilier"] = choix
            pil = acces.pilier(m, choix) or {}
            p["sujet"] = pil.get("label", choix) + (f" — {pil['description']}" if pil.get("description") else "")
        if p["pilier"] in faits:
            faits[p["pilier"]] += 1
        precedent = p["pilier"] or precedent
    return sorted(prevus, key=lambda x: (x["jour"], x["source"]))


def _dernier_pilier(marque_id: str, avant: dt.date) -> str:
    with db.moteur().begin() as c:
        r = c.execute(select(db.slots.c.pillar).where(
            db.slots.c.brand_id == marque_id, db.slots.c.day < avant, db.slots.c.pillar != "")
            .order_by(db.slots.c.day.desc()).limit(1)).first()
    return r[0] if r else ""


def _lisible(prevus: list, m: dict) -> list:
    out = []
    for p in prevus:
        reseaux_ = p["reseaux"] or m.get("active_platforms") or []
        out.append({"jour": p["jour"].isoformat(), "jour_lisible": f"{_JOURS[p['jour'].weekday()]} {p['jour']:%d/%m}",
                    "pilier": p["pilier"], "sujet": p["sujet"], "source": p["source"], "serie_id": p["serie_id"],
                    "heure": p["heure"] or "la meilleure du jour",
                    "reseaux": [reseaux.NOMS.get(r, r) for r in reseaux_], "reseaux_cles": p["reseaux"]})
    return out


def proposer(m: dict, annee: int, mois: int, par: str = "systeme") -> dict:
    """Le 25 : le mois suivant, complet. Un plan déjà validé n'est pas réécrit."""
    cle = f"{annee:04d}-{mois:02d}"
    with db.moteur().begin() as c:
        plan = db.ligne(c.execute(select(db.plans).where(db.plans.c.brand_id == m["id"], db.plans.c.month == cle)))
    if plan and plan["status"] in ("valide", "applique"):
        return plan
    contenu = _lisible(generer_mois(m, annee, mois), m)
    with db.moteur().begin() as c:
        if plan:
            c.execute(update(db.plans).where(db.plans.c.id == plan["id"]).values(
                content=contenu, proposed_at=db.maintenant(), status="propose"))
        else:
            c.execute(insert(db.plans).values(brand_id=m["id"], month=cle, content=contenu, status="propose",
                                              proposed_at=db.maintenant()))
        plan = db.ligne(c.execute(select(db.plans).where(db.plans.c.brand_id == m["id"], db.plans.c.month == cle)))
    journal.noter(par, "plan_propose", "plan", plan["id"], m["id"], apres={"mois": cle, "creneaux": len(contenu)})
    return plan


def valider(plan_id: int, par: str) -> dict:
    with db.moteur().begin() as c:
        c.execute(update(db.plans).where(db.plans.c.id == plan_id, db.plans.c.status == "propose").values(
            status="valide", validated_at=db.maintenant(), validated_by=par))
        plan = db.ligne(c.execute(select(db.plans).where(db.plans.c.id == plan_id)))
    journal.noter(par, "plan_valide", "plan", plan_id, plan["brand_id"], apres={"mois": plan["month"]})
    return plan


def appliquer(plan: dict, par: str = "systeme") -> int:
    """Le 1er : les créneaux du plan deviennent réels — validé ou non."""
    if plan["status"] == "applique":
        return 0
    m = acces.marque(plan["brand_id"])
    n = 0
    aujourd_hui = acces.aujourdhui()
    for p in plan["content"] or []:
        jour = dt.date.fromisoformat(p["jour"])
        if jour < aujourd_hui:
            continue
        if creneaux_de(m["id"], jour, jour) and p["source"] == "plan":
            continue                # un dépôt ou une campagne a déjà pris ce jour
        if p["source"] == "serie" and any(s["series_id"] == p["serie_id"] for s in creneaux_de(m["id"], jour, jour)):
            continue
        _poser(m, jour, p["source"], pillar=p["pilier"], topic=p["sujet"], plan_id=plan["id"],
               series_id=p.get("serie_id"), platforms=p.get("reseaux_cles") or [],
               time=p["heure"] if ":" in (p["heure"] or "") else "")
        n += 1
    with db.moteur().begin() as c:
        c.execute(update(db.plans).where(db.plans.c.id == plan["id"]).values(status="applique"))
    journal.noter(par, "plan_applique", "plan", plan["id"], m["id"],
                  apres={"mois": plan["month"], "creneaux": n, "valide_par": plan.get("validated_by")})
    return n


def demarrer(m: dict, par: str = "systeme") -> int:
    """Au premier démarrage (ou pour une marque qu'on vient d'activer) : le reste
    du mois en cours est planifié et appliqué tout de suite. Le bac à sable,
    ouvert par défaut, empêche que quoi que ce soit sorte sans qu'on l'ait vu."""
    j = acces.aujourdhui()
    plan = proposer(m, j.year, j.month, par)
    if plan["status"] != "applique":
        plan = dict(plan, content=_lisible(generer_mois(m, j.year, j.month, a_partir_de=j), m))
        with db.moteur().begin() as c:
            c.execute(update(db.plans).where(db.plans.c.id == plan["id"]).values(content=plan["content"]))
        return appliquer(plan, par)
    return 0


# ── Une photo déposée : où la mettre ? ───────────────────────────────────
def creneau_pour(m: dict, a: dict):
    """Le meilleur créneau des 7 prochains jours pour cette photo : un créneau
    libre (le bon pilier vaut deux jours d'avance), sinon un créneau neuf si
    la semaine n'a pas atteint sa cadence maximale, sinon None (banque)."""
    from . import pipeline
    j0 = acces.aujourdhui()
    heure = creneaux.paris(db.maintenant())
    debut = j0 if heure.hour < 21 else j0 + dt.timedelta(days=1)
    fin = j0 + dt.timedelta(days=HORIZON)
    libres = creneaux_de(m["id"], debut, fin, ("libre", "manque"))
    meilleurs = []
    for s in libres:
        if s["source"] == "campagne" and s["campaign_step"] and a["kind"] != "carte" \
                and s["pillar"] and s["pillar"] != a["pillar"]:
            continue                # une étape de campagne garde son sujet
        reseaux_ = s["platforms"] or m.get("active_platforms") or []
        if len(pipeline.doublons(a, reseaux_)) == len(reseaux_):
            continue
        ecart = (s["day"] - j0).days - (2 if a["pillar"] and s["pillar"] == a["pillar"] else 0)
        meilleurs.append((ecart, s["day"], s["id"], s))
    if meilleurs:
        return min(meilleurs)[3]
    fermes = jours_fermes(m)
    profils = mesure.profils(m["id"])
    reseaux_actifs = m.get("active_platforms") or []
    depart = calendrier_des(m)
    candidats = []
    for i in range(0, 4):
        jour = debut + dt.timedelta(days=i)
        if depart and jour < depart:
            continue                # avant l'ouverture : la photo attend en banque
        if jour.weekday() in fermes or creneaux_de(m["id"], jour, jour, ("libre", "rempli", "publie", "manque")):
            continue
        if _compte_semaine(m["id"], jour) >= (m.get("cadence_max") or 5):
            continue
        w = creneaux.poids_du_jour(m.get("sector", "b2c"), reseaux_actifs, jour.weekday(), profils)
        candidats.append((-(w / (1 + 0.35 * i)), jour))      # demain bien placé vaut mieux que dans trois jours
    if not candidats:
        return None
    jour = min(candidats)[1]
    sid = _poser(m, jour, "depot", pillar=a["pillar"] or "", topic=(a["vision"] or {}).get("sujet", ""))
    with db.moteur().begin() as c:
        return db.ligne(c.execute(select(db.slots).where(db.slots.c.id == sid)))


# ── Chaque matin : remplir la semaine ────────────────────────────────────
def _banque(m: dict) -> list:
    with db.moteur().begin() as c:
        return db.lignes(c.execute(select(db.assets).where(
            db.assets.c.brand_id == m["id"], db.assets.c.status == "banque", db.assets.c.kind == "photo")
            .order_by(db.assets.c.usability.desc(), db.assets.c.created_at)))


def _recyclables(m: dict) -> list:
    """Les meilleures anciennes : publiées, plus utilisées depuis 90 jours."""
    limite = db.maintenant() - FENETRE_RECYCLAGE
    with db.moteur().begin() as c:
        return db.lignes(c.execute(select(db.assets).where(
            db.assets.c.brand_id == m["id"], db.assets.c.status == "publie", db.assets.c.kind == "photo",
            db.assets.c.last_used_at < limite).order_by((db.assets.c.recyclage == "gagnant").desc(),
                                                        db.assets.c.score.desc(), db.assets.c.usability.desc())))


def choisir_photo(m: dict, s: dict, deja_pris: set):
    from . import pipeline
    reseaux_ = s["platforms"] or m.get("active_platforms") or []

    def possible(a):
        return a["id"] not in deja_pris and len(pipeline.doublons(a, reseaux_)) < len(reseaux_)
    banque = [a for a in _banque(m) if possible(a)]
    if s["pillar"]:
        bon = [a for a in banque if a["pillar"] == s["pillar"]]
        if bon:
            return bon[0]
    if banque and not (s["source"] == "campagne" and s["pillar"]):
        return banque[0]
    vieux = [a for a in _recyclables(m) if possible(a)]
    if s["pillar"]:
        vieux = [a for a in vieux if a["pillar"] == s["pillar"]] or vieux
    if vieux:
        return vieux[0]
    # Le stock frais manque : un intemporel ressort (au plus tous les 45 jours).
    from . import recyclage
    intemporels = [a for a in recyclage.evergreen_disponibles(m) if possible(a)]
    if s["pillar"]:
        intemporels = [a for a in intemporels if a["pillar"] == s["pillar"]] or intemporels
    return intemporels[0] if intemporels else None


def remplir(m: dict, par: str = "systeme") -> dict:
    """→ {rempli: n, manque: [créneaux sans photo]}."""
    from . import campagnes, pipeline
    j0 = acces.aujourdhui()
    rapport = {"rempli": 0, "manque": []}
    if not m["active"] or acces.en_pause(m):
        return rapport
    pris = set()
    for s in creneaux_de(m["id"], j0, j0 + dt.timedelta(days=HORIZON), ("libre", "manque")):
        a = choisir_photo(m, s, pris)
        if a is None and s["source"] == "campagne":
            a = campagnes.carte_pour(m, s)
        if a is None:
            if s["status"] != "manque":
                with db.moteur().begin() as c:
                    c.execute(update(db.slots).where(db.slots.c.id == s["id"]).values(status="manque"))
            rapport["manque"].append(s)
            continue
        pris.add(a["id"])
        if a.get("_evergreen"):
            from . import recyclage
            recyclage.evergreen_sorti(a["_evergreen"])
        if a["status"] == "publie":
            with db.moteur().begin() as c:     # recyclage : la photo repart de la banque
                c.execute(update(db.assets).where(db.assets.c.id == a["id"]).values(status="banque"))
        if pipeline.attacher(s, a, par):
            rapport["rempli"] += 1
    return rapport


def alerte_stock(m: dict) -> str:
    """« Il manque 3 photos de plats et 1 photo d'équipe pour SAZÚ avant vendredi. »
    → le texte envoyé, ou '' si la semaine est couverte."""
    j0 = acces.aujourdhui()
    vides = creneaux_de(m["id"], j0, j0 + dt.timedelta(days=HORIZON), ("libre", "manque"))
    vides = [s for s in vides if s["source"] != "campagne"]     # une campagne a ses cartes
    if not vides:
        return ""
    banque = _banque(m)
    restant = list(banque)
    manque = {}
    for s in vides:
        bon = next((a for a in restant if s["pillar"] and a["pillar"] == s["pillar"]), None) \
            or next((a for a in restant if not s["pillar"]), None)
        if bon:
            restant.remove(bon)
            continue
        manque.setdefault(s["pillar"] or "", []).append(s["day"])
    # Une photo « sans pilier » en banque peut encore boucher un trou.
    for cle in list(manque):
        while manque[cle] and restant:
            restant.pop()
            manque[cle].pop()
        if not manque[cle]:
            del manque[cle]
    if not manque:
        return ""
    avant = min(d for jours in manque.values() for d in jours)
    morceaux = []
    for cle, jours in sorted(manque.items(), key=lambda kv: -len(kv[1])):
        lib = (acces.pilier(m, cle) or {}).get("photo") or (acces.pilier(m, cle) or {}).get("label") or "au choix"
        n = len(jours)
        morceaux.append(f"{n} photo{'s' if n > 1 else ''} « {lib} »")
    phrase = (f"Il manque {_et(morceaux)} pour {m['name']} avant {_JOURS[avant.weekday()]} {avant:%d/%m}.")
    from . import coach
    b = coach.brief(m)
    detail = ("\n\nLe brief du coach : " + b["phrase"] + "\nComment : " + " ; ".join(b["comment"]) + ".") if b else ""
    corps = (phrase + detail + "\n\nDéposez-les dans ALMA SOCIAL (un tap sur la marque) : elles partiront "
             "toutes seules aux créneaux prévus.\nEn banque aujourd'hui : "
             f"{len(banque)} photo{'s' if len(banque) > 1 else ''} prête{'s' if len(banque) > 1 else ''}.")
    semaine = _lundi(j0).isoformat()
    alertes.alerter(f"{m['name']} : photos à fournir avant {_JOURS[avant.weekday()]}", corps, marque=m["id"],
                    niveau="info", type_="stock", dedup=f"stock:{m['id']}:{semaine}",
                    delai_dedup=dt.timedelta(days=6))
    return phrase


def _et(morceaux: list) -> str:
    return morceaux[0] if len(morceaux) == 1 else ", ".join(morceaux[:-1]) + " et " + morceaux[-1]


def stock(m: dict) -> dict:
    """Pour la page santé et le rapport : de quoi tenir combien de jours ?"""
    j0 = acces.aujourdhui()
    banque = _banque(m)
    a_venir = creneaux_de(m["id"], j0, j0 + dt.timedelta(days=21), ("libre", "manque", "rempli"))
    vides = [s for s in a_venir if s["status"] != "rempli"]
    jours_couverts = HORIZON
    if vides:
        n = len(banque)
        for s in vides:
            if n == 0:
                jours_couverts = (s["day"] - j0).days
                break
            n -= 1
        else:
            jours_couverts = 21
    else:
        jours_couverts = 21
    return {"banque": len(banque), "creneaux_vides": len(vides), "jours_couverts": jours_couverts,
            "recyclables": len(_recyclables(m))}


def piliers_en_retard(m: dict, jours: int = 21) -> list:
    """Le rapport du lundi : quel pilier n'a rien sorti depuis trop longtemps ?"""
    depuis = db.maintenant() - dt.timedelta(days=jours)
    with db.moteur().begin() as c:
        # Une marque qui publie depuis moins de trois semaines n'a « oublié » personne.
        premier = c.execute(select(func.min(db.posts.c.published_at)).where(
            db.posts.c.brand_id == m["id"], db.posts.c.status.in_(("publie", "simule")))).scalar()
        if not premier or premier > depuis:
            return []
        sortis = {r[0] for r in c.execute(select(db.posts.c.pillar).where(
            db.posts.c.brand_id == m["id"], db.posts.c.status.in_(("publie", "simule")),
            db.posts.c.published_at >= depuis))}
    return [p["label"] for p in m.get("pillars") or [] if p["key"] not in sortis and not p.get("hors_rotation")]


# ── Les rendez-vous du mois ──────────────────────────────────────────────
def rappel_veille(m: dict, plan: dict):
    """La veille du 1er : le plan non validé s'applique demain, on le dit une fois."""
    if plan["status"] != "propose" or plan.get("reminder_sent_at"):
        return False
    alertes.alerter(f"{m['name']} : le calendrier de {plan['month']} s'applique demain",
                    f"{len(plan['content'] or [])} publications prévues. Sans réponse de votre part, il "
                    "s'applique tel quel demain matin. Pour le modifier ou le valider : ALMA SOCIAL → Calendrier.",
                    marque=None, niveau="info", type_="plan", dedup=f"rappel:{plan['id']}",
                    delai_dedup=dt.timedelta(days=40))
    with db.moteur().begin() as c:
        c.execute(update(db.plans).where(db.plans.c.id == plan["id"]).values(reminder_sent_at=db.maintenant()))
    return True


def plan_du_mois(marque_id: str, annee: int, mois: int):
    with db.moteur().begin() as c:
        return db.ligne(c.execute(select(db.plans).where(
            db.plans.c.brand_id == marque_id, db.plans.c.month == f"{annee:04d}-{mois:02d}")))


def mois_suivant(j: dt.date) -> tuple:
    return (j.year + (j.month == 12), 1 if j.month == 12 else j.month + 1)


def tour_du_matin(par: str = "systeme") -> dict:
    """Une fois par jour, tôt : le calendrier avance d'un cran pour chaque marque."""
    j = acces.aujourdhui()
    out = {}
    for m in acces.marques():
        if j.day == 1 or not plan_du_mois(m["id"], j.year, j.month):
            plan = plan_du_mois(m["id"], j.year, j.month)
            if plan is None:
                demarrer(m, par)
            elif plan["status"] != "applique":
                appliquer(plan, par)
            if j.day == 1:
                mesure.recalibrer(m)
        a, mo = mois_suivant(j)
        if j.day >= 25 and not plan_du_mois(m["id"], a, mo):
            proposer(m, a, mo, par)
        if (j + dt.timedelta(days=1)).day == 1:
            plan = plan_du_mois(m["id"], a, mo)
            if plan:
                rappel_veille(m, plan)
        from . import recyclage, temps_forts
        tri = recyclage.classer(m, par)
        temps_forts.poser(m, par)
        r = remplir(m, par)
        phrase = alerte_stock(m)
        out[m["id"]] = {"rempli": r["rempli"], "manque": len(r["manque"]), "stock": phrase,
                        "seconde_chance": len(tri["malchanceux"]), "gagnants": len(tri["gagnants"])}
    journal.noter(par, "tour_du_matin", "planificateur", j.isoformat(), None, apres=out)
    return out


def nb_publications_semaine(marque_id: str, jour: dt.date) -> int:
    l = _lundi(jour)
    debut = creneaux.utc(dt.datetime.combine(l, dt.time(0), tzinfo=creneaux.PARIS))
    with db.moteur().begin() as c:
        return c.execute(select(func.count(func.distinct(db.posts.c.slot_id))).where(
            db.posts.c.brand_id == marque_id, db.posts.c.scheduled_at >= debut,
            db.posts.c.scheduled_at < debut + dt.timedelta(days=7),
            db.posts.c.status.in_(("programme", "publie", "simule", "envoi")))).scalar_one()
