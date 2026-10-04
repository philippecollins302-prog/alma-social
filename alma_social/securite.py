"""Codes d'accès, sessions, chiffrement des jetons, frein aux essais.

Un code par personne (six chiffres ou plus), jamais stocké en clair : scrypt,
avec un sel. Une session = un jeton aléatoire dont la base ne garde que
l'empreinte — une copie de la base ne permet donc pas de se connecter.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import secrets

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import delete, func, insert, select, update

from . import config, db

DUREE_SESSION = dt.timedelta(days=30)
ESSAIS_MAX = 6                       # par adresse, sur la fenêtre ci-dessous
FENETRE_ESSAIS = dt.timedelta(minutes=15)


# ── Codes ────────────────────────────────────────────────────────────────
def hacher_code(code: str) -> str:
    sel = secrets.token_bytes(16)
    h = hashlib.scrypt(code.encode(), salt=sel, n=2 ** 14, r=8, p=1, dklen=32)
    return "scrypt$" + base64.b64encode(sel).decode() + "$" + base64.b64encode(h).decode()


def code_valide(code: str, stocke: str) -> bool:
    try:
        algo, sel, h = stocke.split("$")
        if algo != "scrypt":
            return False
        calc = hashlib.scrypt(code.encode(), salt=base64.b64decode(sel),
                              n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(calc, base64.b64decode(h))
    except (ValueError, TypeError):
        return False


def code_acceptable(code: str) -> str:
    """Rend '' si le code convient, sinon la raison (en clair, pour l'écran)."""
    if not code or len(code) < 6:
        return "Un code fait au moins 6 caractères."
    if code.isdigit() and len(set(code)) == 1:
        return "Un code fait d'un seul chiffre répété se devine."
    if code in ("123456", "1234567", "12345678", "654321", "123123"):
        return "Ce code est le premier qu'on essaie."
    return ""


def generer_code() -> str:
    """Huit chiffres aléatoires — tapables au pouce, impossibles à deviner en
    six essais par quart d'heure."""
    while True:
        c = "".join(secrets.choice("0123456789") for _ in range(8))
        if not code_acceptable(c):
            return c


# ── Frein aux essais ─────────────────────────────────────────────────────
def trop_d_essais(ip: str) -> bool:
    depuis = db.maintenant() - FENETRE_ESSAIS
    with db.moteur().begin() as c:
        n = c.execute(select(func.count()).select_from(db.login_attempts).where(
            db.login_attempts.c.ip == ip, db.login_attempts.c.ok.is_(False),
            db.login_attempts.c.at >= depuis)).scalar_one()
    return n >= ESSAIS_MAX


def noter_essai(ip: str, ok: bool):
    with db.moteur().begin() as c:
        c.execute(insert(db.login_attempts).values(ip=ip, ok=ok, at=db.maintenant()))
        c.execute(delete(db.login_attempts).where(
            db.login_attempts.c.at < db.maintenant() - dt.timedelta(days=2)))


def identifier(code: str):
    """Le code tapé → la personne, ou None. Parcourt les comptes actifs : il y
    en a une dizaine, et scrypt ne se recherche pas par index (sel par code)."""
    with db.moteur().begin() as c:
        gens = db.lignes(c.execute(select(db.users).where(db.users.c.active.is_(True))))
    for u in gens:
        if u["code_hash"] and code_valide(code, u["code_hash"]):
            return u
    return None


# ── Sessions ─────────────────────────────────────────────────────────────
def _empreinte(jeton: str) -> str:
    return hashlib.sha256(jeton.encode()).hexdigest()


def ouvrir_session(user_id: int) -> str:
    jeton = secrets.token_urlsafe(32)
    with db.moteur().begin() as c:
        c.execute(insert(db.sessions).values(
            token_hash=_empreinte(jeton), user_id=user_id,
            created_at=db.maintenant(), expires_at=db.maintenant() + DUREE_SESSION))
        c.execute(update(db.users).where(db.users.c.id == user_id)
                  .values(last_login=db.maintenant()))
    return jeton


def session(jeton: str):
    if not jeton:
        return None
    with db.moteur().begin() as c:
        s = db.ligne(c.execute(select(db.sessions).where(
            db.sessions.c.token_hash == _empreinte(jeton))))
        if not s or s["expires_at"] < db.maintenant():
            return None
        u = db.ligne(c.execute(select(db.users).where(
            db.users.c.id == s["user_id"], db.users.c.active.is_(True))))
    return u


def fermer_session(jeton: str):
    with db.moteur().begin() as c:
        c.execute(delete(db.sessions).where(db.sessions.c.token_hash == _empreinte(jeton)))


def marques_de(user) -> list:
    """Le cloisonnement, en un seul endroit : le PDG voit tout, un responsable
    ne voit que ses marques. Toute route qui lit une marque passe par ici."""
    if user["role"] == "pdg":
        with db.moteur().begin() as c:
            return [r[0] for r in c.execute(select(db.brands.c.id).order_by(db.brands.c.created_at))]
    return list(user.get("brands") or [])


def peut_voir(user, brand_id: str) -> bool:
    return user["role"] == "pdg" or brand_id in (user.get("brands") or [])


# ── Chiffrement des jetons des réseaux ───────────────────────────────────
_DEV_SEULEMENT = "alma-social-cle-de-developpement-jamais-en-production"


def _fernet() -> Fernet:
    secret = config.cle_chiffrement()
    if not secret:
        if not config.env_dev():
            raise RuntimeError(
                "SOCIAL_CLE_CHIFFREMENT absente : aucun jeton ne sera stocké en clair. "
                "Posez-la dans l'environnement de l'hébergeur.")
        secret = _DEV_SEULEMENT
    cle = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(cle)


def chiffrer(valeur: str) -> str:
    if not valeur:
        return ""
    return _fernet().encrypt(valeur.encode()).decode()


def dechiffrer(valeur: str) -> str:
    if not valeur:
        return ""
    try:
        return _fernet().decrypt(valeur.encode()).decode()
    except InvalidToken:
        return ""


def masquer(valeur: str) -> str:
    """Pour l'écran : on montre qu'une clé existe, jamais la clé."""
    return "" if not valeur else "•••• " + valeur[-4:] if len(valeur) > 8 else "••••"
