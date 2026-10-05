"""Le troisième niveau de la mesure : les CLIENTS (§ 17.1).

Un like ne paie pas les salaires. Ce module rattache à une publication tout
ce qui ressemble à un client, par cinq portes :

1. **Le QR code** d'un lien tracé (panneau de chantier, camion, flyer, sac de
   livraison) : le même lien `go`, avec `?q=1` — les scans se comptent à part
   des clics, par lieu et par appareil.
2. **La conversion côté serveur** [Dub conversions] : le site d'une marque
   (son serveur, pas le navigateur) envoie la demande signée — elle passe les
   bloqueurs de publicité, que le petit script du navigateur ne passe pas.
   Signature HMAC-SHA256 du corps avec `SOCIAL_CONVERSIONS_SECRET`.
3. **Le numéro d'appel tracé** [CallRail] : un numéro par marque et par
   source ; le fournisseur prévient d'un appel (webhook, jeton
   `SOCIAL_APPELS_SECRET`), l'appel devient un client — un appel de moins de
   20 secondes est consigné mais ne compte pas.
4. **Le code promo** par publication, réseau ou créateur. L'OFFRE derrière
   le code est une décision commerciale : elle est écrite par une personne,
   jamais inventée par l'application.
5. **Les rapports Uber Eats et Deliveroo** : faute d'API ouverte aux
   restaurants pour ces données, le fichier hebdomadaire exporté depuis leur
   espace restaurant s'importe tel quel ; les colonnes se reconnaissent à
   leur nom, en français ou en anglais. Une commande déjà importée ne compte
   jamais deux fois.

Un même événement reçu par deux portes (le script du navigateur ET le serveur
du site, pour le même formulaire) ne fait qu'un client.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import hmac
import io
import json
import os
import re
import secrets

from sqlalchemy import func, insert, select, update

from . import acces, db, journal, mesure

APPEL_MIN_S = 20                         # en dessous : un faux numéro, un raccroché — pas un client
FENETRE_DOUBLON = dt.timedelta(minutes=15)


# ── 1. Le QR code ────────────────────────────────────────────────────────
def lien_terrain(marque: dict, support: str, cible: str = "", par: str = "") -> dict:
    """Un lien tracé pour un support physique (« panneau chantier Lattes »,
    « camion 2 », « flyer marché »). → {id, code, url, qr}."""
    support = re.sub(r"\s+", " ", (support or "").strip())[:60]
    if not support:
        raise ValueError("nommez le support (panneau, camion, flyer…)")
    l = marque.get("links") or {}
    cible = cible or l.get("devis") or l.get("site") or ""
    lien = mesure.creer_lien(marque, None, f"terrain:{support}", "qr", cible)
    journal.noter(par or "systeme", "qr", "link", lien["id"], marque["id"], apres={"support": support})
    return {**lien, "qr": url_qr(lien["code"])}


def url_qr(code: str) -> str:
    return f"{mesure.url_courte(code)}?q=1"


def qr(code: str, sorte: str = "svg", couleur: str = "#000000") -> bytes:
    """Le QR du lien, en SVG (impression) ou PNG (écran). Correction d'erreur
    élevée : un panneau de chantier se salit."""
    import segno
    q = segno.make(url_qr(code), error="h", micro=False)
    buf = io.BytesIO()
    if sorte == "png":
        q.save(buf, kind="png", scale=12, border=3, dark=couleur)
    else:
        q.save(buf, kind="svg", scale=10, border=3, dark=couleur, xmldecl=False)
    return buf.getvalue()


def liens_terrain(marque_ids: list) -> list:
    with db.moteur().connect() as c:
        ls = db.lignes(c.execute(select(db.links).where(db.links.c.brand_id.in_(marque_ids),
                                                        db.links.c.kind == "qr").order_by(db.links.c.id.desc())))
        par = dict(c.execute(select(db.clicks.c.link_id, func.count()).where(
            db.clicks.c.link_id.in_([x["id"] for x in ls] or [0]), db.clicks.c.source == "qr",
            db.clicks.c.device != "robot").group_by(db.clicks.c.link_id)).all())
        clients = dict(c.execute(select(db.leads.c.link_id, func.count()).where(
            db.leads.c.link_id.in_([x["id"] for x in ls] or [0])).group_by(db.leads.c.link_id)).all())
    return [{"id": x["id"], "marque": x["brand_id"], "support": (x["platform"] or "").removeprefix("terrain:"),
             "code": x["code"], "url": mesure.url_courte(x["code"]), "scans": par.get(x["id"], 0),
             "clics": x["clicks"], "clients": clients.get(x["id"], 0), "cree_le": x["created_at"]} for x in ls]


# ── Un client, une seule fois ────────────────────────────────────────────
def _deja(marque_id: str, canal: str, external_id: str):
    if not external_id:
        return None
    with db.moteur().connect() as c:
        return c.execute(select(db.leads.c.id).where(db.leads.c.brand_id == marque_id,
                                                     db.leads.c.channel == canal,
                                                     db.leads.c.external_id == external_id)).scalar()


def _completer(lid: int, **vals):
    with db.moteur().begin() as c:
        c.execute(update(db.leads).where(db.leads.c.id == lid).values(**vals))


# ── 2. La conversion côté serveur ────────────────────────────────────────
def secret_conversions() -> str:
    return (os.environ.get("SOCIAL_CONVERSIONS_SECRET") or "").strip()


def signer(corps: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), corps, hashlib.sha256).hexdigest()


def conversion_serveur(corps: bytes, signature: str) -> dict:
    """→ {id, deja, rattache}. Lève PermissionError si la signature manque ou ment,
    ValueError si le contenu ne va pas."""
    secret = secret_conversions()
    if not secret:
        raise PermissionError("conversions serveur non branchées (SOCIAL_CONVERSIONS_SECRET absente)")
    attendu = signer(corps, secret)
    if not signature or not hmac.compare_digest(attendu, signature.strip().removeprefix("sha256=")):
        raise PermissionError("signature invalide")
    try:
        d = json.loads(corps or b"{}")
    except ValueError as e:
        raise ValueError("corps JSON illisible") from e
    m = acces.marque(str(d.get("marque") or ""))
    if not m:
        raise ValueError("marque inconnue")
    type_ = d.get("type") if d.get("type") in ("devis", "commande", "appel") else "devis"
    ext = str(d.get("id") or "")[:120]
    marqueur = str(d.get("marqueur") or "")[:40]
    montant = _nombre(d.get("montant"))
    deja = _deja(m["id"], "serveur", ext)
    if deja:
        return {"id": deja, "deja": True, "rattache": bool(marqueur)}
    # Le même formulaire, déjà annoncé par le navigateur il y a quelques minutes :
    # on COMPLÈTE cette ligne au lieu d'en créer une seconde.
    if marqueur:
        with db.moteur().connect() as c:
            jumeau = c.execute(select(db.leads.c.id).where(
                db.leads.c.brand_id == m["id"], db.leads.c.channel == "formulaire",
                db.leads.c.marker == marqueur, db.leads.c.type == type_,
                db.leads.c.created_at >= db.maintenant() - FENETRE_DOUBLON)
                .order_by(db.leads.c.id.desc())).scalar()
        if jumeau:
            _completer(jumeau, channel="serveur", external_id=ext, amount=montant)
            return {"id": jumeau, "deja": True, "rattache": True}
    lid = mesure.enregistrer_lead(m["id"], type_, "serveur", marqueur=marqueur, montant=montant,
                                  source=str(d.get("source") or "")[:300], par="site")
    _completer(lid, external_id=ext)
    return {"id": lid, "deja": False, "rattache": bool(marqueur)}


# ── 3. Le numéro d'appel tracé ───────────────────────────────────────────
def secret_appels() -> str:
    return (os.environ.get("SOCIAL_APPELS_SECRET") or "").strip()


def normaliser_numero(n: str) -> str:
    """« 04 67 12 34 56 », « +33 4 67… », « 0033467… » → « +33467123456 »."""
    chiffres = re.sub(r"[^\d+]", "", str(n or ""))
    if chiffres.startswith("00"):
        chiffres = "+" + chiffres[2:]
    if chiffres.startswith("0") and len(chiffres) == 10:
        chiffres = "+33" + chiffres[1:]
    return chiffres


def poser_numero(marque: dict, numero: str, source: str, fournisseur: str = "", renvoi: str = "",
                 par: str = "") -> int:
    n = normaliser_numero(numero)
    if not re.fullmatch(r"\+\d{9,15}", n):
        raise ValueError("numéro illisible")
    source = (source or "").strip()[:40]
    if not source:
        raise ValueError("nommez la source (google, instagram, panneau…)")
    with db.moteur().begin() as c:
        nid = c.execute(insert(db.tracking_numbers).values(
            brand_id=marque["id"], numero=n, source=source, fournisseur=(fournisseur or "")[:40],
            renvoi_vers=normaliser_numero(renvoi), actif=True, created_at=db.maintenant())).inserted_primary_key[0]
    journal.noter(par or "systeme", "numero_trace", "tracking_number", nid, marque["id"],
                  apres={"source": source, "fournisseur": fournisseur})
    return nid


# Les noms de champ que les fournisseurs emploient (Invox, Wannaspeak,
# CallRail, CallTrackingMetrics…) : on lit le premier présent.
CHAMPS_APPEL = {
    "appele": ("appele", "called", "called_number", "tracking_number", "to", "numero_appele", "did", "ddi"),
    "appelant": ("appelant", "caller", "caller_number", "from", "customer_phone_number", "numero_appelant", "cli"),
    "duree": ("duree", "duration", "call_duration", "billsec", "talk_time"),
    "id": ("id", "call_id", "callid", "uuid", "call_uuid"),
}


def _champ(d: dict, cle: str):
    for k in CHAMPS_APPEL[cle]:
        if d.get(k) not in (None, ""):
            return d[k]
    return None


def appel_entrant(d: dict, jeton: str) -> dict:
    """Le webhook du fournisseur. → {compte, raison, id}."""
    secret = secret_appels()
    if not secret:
        raise PermissionError("numéros tracés non branchés (SOCIAL_APPELS_SECRET absente)")
    if not jeton or not hmac.compare_digest(secret, jeton):
        raise PermissionError("jeton invalide")
    if isinstance(d.get("call"), dict):          # certains enveloppent l'appel
        d = {**d, **d["call"]}
    appele = normaliser_numero(_champ(d, "appele") or "")
    with db.moteur().connect() as c:
        num = db.ligne(c.execute(select(db.tracking_numbers).where(db.tracking_numbers.c.numero == appele)))
    if not num:
        return {"compte": False, "raison": "numéro inconnu"}
    duree = int(_nombre(_champ(d, "duree")) or 0)
    ext = str(_champ(d, "id") or "")[:120]
    if _deja(num["brand_id"], "telephone", ext):
        return {"compte": False, "raison": "déjà reçu"}
    # L'appelant n'est JAMAIS gardé en clair : une empreinte suffit à
    # reconnaître le même client qui rappelle.
    appelant = normaliser_numero(_champ(d, "appelant") or "")
    empreinte = hashlib.sha256(appelant.encode()).hexdigest()[:16] if appelant else ""
    if duree < APPEL_MIN_S:
        journal.noter("telephone", "appel_court", "tracking_number", num["id"], num["brand_id"],
                      apres={"duree": duree, "source": num["source"]})
        return {"compte": False, "raison": f"appel de {duree} s (moins de {APPEL_MIN_S} s)"}
    if empreinte:
        with db.moteur().connect() as c:
            rappel = c.execute(select(db.leads.c.id).where(
                db.leads.c.brand_id == num["brand_id"], db.leads.c.channel == "telephone",
                db.leads.c.marker == empreinte,
                db.leads.c.created_at >= db.maintenant() - dt.timedelta(days=30))).scalar()
        if rappel:
            journal.noter("telephone", "rappel", "lead", rappel, num["brand_id"], apres={"duree": duree})
            return {"compte": False, "raison": "le même client rappelle (déjà compté)", "id": rappel}
    lid = mesure.enregistrer_lead(num["brand_id"], "appel", "telephone", source=num["source"],
                                  note=f"appel de {duree} s sur le numéro {num['source']}", par="telephone")
    _completer(lid, external_id=ext, marker=empreinte, entry_door="telephone")
    return {"compte": True, "raison": "", "id": lid}


# ── 4. Les codes promo ───────────────────────────────────────────────────
def creer_code(marque: dict, offre: str, post_id=None, plateforme: str = "", createur: str = "",
               code: str = "", par: str = "") -> dict:
    offre = (offre or "").strip()
    if not offre:
        raise ValueError("l'offre est une décision : écrivez-la (« -10 % sur le premier bowl »)")
    base = re.sub(r"[^A-Z0-9]", "", (code or "").upper())[:16]
    if not base:
        tete = re.sub(r"[^A-Z]", "", marque["id"].upper())[:4]
        qui = re.sub(r"[^A-Z0-9]", "", (createur or plateforme or "").upper())[:5]
        base = f"{tete}{qui}"
    for i in range(6):
        essai = base if (i == 0 and code) else f"{base}{secrets.randbelow(90) + 10}"
        try:
            with db.moteur().begin() as c:
                pid = c.execute(insert(db.promo_codes).values(
                    brand_id=marque["id"], code=essai, post_id=post_id, platform=plateforme or "",
                    createur=(createur or "")[:120], offre=offre[:300], created_at=db.maintenant())
                ).inserted_primary_key[0]
            journal.noter(par or "systeme", "code_promo", "promo_code", pid, marque["id"],
                          apres={"code": essai, "offre": offre})
            return {"id": pid, "code": essai}
        except Exception:
            if code and i == 0:
                raise ValueError(f"le code {essai} existe déjà")
    raise RuntimeError("impossible de créer un code unique")


def codes(marque_ids: list) -> list:
    with db.moteur().connect() as c:
        return db.lignes(c.execute(select(db.promo_codes).where(db.promo_codes.c.brand_id.in_(marque_ids))
                                   .order_by(db.promo_codes.c.id.desc())))


def _code_connu(marque_id: str, code: str):
    code = re.sub(r"[^A-Z0-9]", "", (code or "").upper())
    if not code:
        return None
    with db.moteur().connect() as c:
        return db.ligne(c.execute(select(db.promo_codes).where(db.promo_codes.c.brand_id == marque_id,
                                                               db.promo_codes.c.code == code)))


# ── 5. Les rapports Uber Eats et Deliveroo ───────────────────────────────
COLONNES = {
    "id": ("order id", "order_id", "id de commande", "n° de commande", "numéro de commande", "commande",
           "order number", "order uuid", "workflow uuid", "référence"),
    "date": ("date", "order date", "date de commande", "created at", "heure de commande", "order placed at",
             "date de la commande"),
    "montant": ("total", "montant", "order total", "sales", "ventes", "total ttc", "montant ttc", "subtotal",
                "sous-total", "ventes (ttc)", "prix total"),
    "code": ("promo", "promo code", "code promo", "promotion", "code", "promotion code", "offer", "offre"),
    "statut": ("status", "statut", "état", "order status"),
}
STATUTS_EXCLUS = ("annul", "cancel", "refus", "rembours", "refund", "failed", "échou")


def _colonne(entetes: list, cle: str):
    norm = {re.sub(r"\s+", " ", h.strip().lower()): h for h in entetes if h}
    for nom in COLONNES[cle]:
        if nom in norm:
            return norm[nom]
    for nom in COLONNES[cle]:                        # puis « contient », pour les variantes
        for k, h in norm.items():
            if nom in k:
                return h
    return None


def _nombre(v):
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d,.\-]", "", str(v))
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _date(v: str):
    v = (v or "").strip()
    for f in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S",
              "%d/%m/%Y %H:%M", "%d/%m/%Y", "%m/%d/%Y %H:%M", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(v[:19].rstrip("Z"), f)
        except ValueError:
            continue
    return None


def importer_livraisons(marque: dict, plateforme: str, octets: bytes, par: str = "") -> dict:
    """Un export CSV d'Uber Eats ou de Deliveroo. → le bilan de l'import."""
    if plateforme not in ("uber_eats", "deliveroo"):
        raise ValueError("plateforme : uber_eats ou deliveroo")
    texte = None
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            texte = octets.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if not texte or not texte.strip():
        raise ValueError("fichier vide")
    try:
        dialecte = csv.Sniffer().sniff(texte[:4000], delimiters=",;\t")
    except csv.Error:
        dialecte = csv.excel
    lignes = list(csv.DictReader(io.StringIO(texte), dialect=dialecte))
    if not lignes:
        raise ValueError("aucune ligne")
    entetes = list(lignes[0].keys())
    col = {k: _colonne(entetes, k) for k in COLONNES}
    if not col["id"] or not col["montant"]:
        raise ValueError("colonnes introuvables : il faut au moins le numéro de commande et le montant "
                         f"(colonnes lues : {', '.join(h for h in entetes if h)[:300]})")
    bilan = {"lignes": len(lignes), "importees": 0, "deja": 0, "annulees": 0, "avec_code": 0,
             "rattachees": 0, "chiffre": 0.0, "codes_inconnus": set(), "colonnes": col}
    for l in lignes:
        ext = (l.get(col["id"]) or "").strip()[:120]
        if not ext:
            continue
        if col["statut"] and any(x in (l.get(col["statut"]) or "").lower() for x in STATUTS_EXCLUS):
            bilan["annulees"] += 1
            continue
        if _deja(marque["id"], plateforme, ext):
            bilan["deja"] += 1
            continue
        montant = _nombre(l.get(col["montant"]))
        code = (l.get(col["code"]) or "").strip() if col["code"] else ""
        promo = _code_connu(marque["id"], code) if code else None
        if code and not promo:
            bilan["codes_inconnus"].add(code[:40])
        quand = _date(l.get(col["date"]) or "") if col["date"] else None
        lid = mesure.enregistrer_lead(marque["id"], "commande", plateforme, post_id=(promo or {}).get("post_id"),
                                      montant=montant, source=f"code {promo['code']}" if promo else "",
                                      note="import du rapport", par=par or "import")
        vals = {"external_id": ext, "promo_code": promo["code"] if promo else ""}
        if quand:
            vals["created_at"] = quand
        _completer(lid, **vals)
        if promo:
            bilan["avec_code"] += 1
            bilan["rattachees"] += 1 if promo.get("post_id") else 0
            with db.moteur().begin() as c:
                c.execute(update(db.promo_codes).where(db.promo_codes.c.id == promo["id"]).values(
                    utilisations=db.promo_codes.c.utilisations + 1,
                    chiffre=db.promo_codes.c.chiffre + (montant or 0)))
        bilan["importees"] += 1
        bilan["chiffre"] += montant or 0
    bilan["codes_inconnus"] = sorted(bilan["codes_inconnus"])
    bilan["chiffre"] = round(bilan["chiffre"], 2)
    journal.noter(par or "import", "import_livraisons", "brand", marque["id"], marque["id"],
                  apres={k: v for k, v in bilan.items() if k != "colonnes"} | {"plateforme": plateforme})
    return bilan
