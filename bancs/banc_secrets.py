"""Banc : les secrets — aucune clé dans le dépôt, aucun code d'essai en production.

Section 10 du cahier : « Aucune clé d'API, aucun jeton, aucun identifiant dans
le code ni dans le dépôt. Variables d'environnement, et un fichier d'exemple
sans valeurs. Les jetons des réseaux sont chiffrés en base. »

Ce banc lit le dépôt tel qu'il partira (tout ce que git ne ferait pas
ignorer), et refuse une clé à la FORME connue — pas un mot : un commentaire
qui explique la règle (« le secret whsec_… ») n'est pas une clé.
"""
import os
import re
import subprocess

import socle
from socle import egal, verifier

from alma_social import config, db, graines, securite

RACINE = socle.ICI.parent
ACCUSATIONS = {
    "clé Anthropic": r"sk-ant-[A-Za-z0-9_-]{12,}",
    "secret de webhook": r"whsec_[A-Za-z0-9+/=_-]{12,}",
    "jeton JWT": r"eyJ[A-Za-z0-9_-]{15,}\.eyJ[A-Za-z0-9_-]{15,}",
    "clé AWS": r"AKIA[0-9A-Z]{16}",
    "clé privée": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "adresse personnelle": r"[\w.+-]+@(?:gmail|googlemail|hotmail|outlook|live|yahoo|icloud|orange|free|wanadoo|sfr|laposte)\.\w+",
    "valeur littérale d'un secret": r"(?i)\b(?:api_?key|secret|token|password|mot_de_passe)\w*\s*[:=]\s*[\"'][A-Za-z0-9_\-]{24,}[\"']",
}
BINAIRES = {".png", ".jpg", ".jpeg", ".webp", ".ttf", ".otf", ".woff", ".woff2", ".ico", ".pdf", ".mp4"}


def suivis() -> list:
    """Les fichiers que git emporterait : suivis, ou nouveaux et non ignorés."""
    sortie = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "."],
                            cwd=RACINE, capture_output=True, text=True, check=True).stdout
    return [RACINE / l for l in sortie.splitlines() if l and (RACINE / l).is_file()]


print("— Les motifs attrapent ce qu'ils disent attraper")
# Des fautes fabriquées à l'exécution (par concaténation) : ce fichier ne les contient donc pas.
FAUTES = {
    "clé Anthropic": "sk-" + "ant-api03-" + "Zx9" * 8,
    "secret de webhook": "whsec" + "_" + "Q7mK" * 6,
    "jeton JWT": "eyJ" + "hbGciOiJIUzI1NiJ9" + ".eyJ" + "zdWIiOiJhbG1hLXJlZ2EifQ",
    "clé AWS": "AKIA" + "Z" * 16,
    "clé privée": "-----BEGIN " + "RSA PRIVATE KEY-----",
    "adresse personnelle": "philippe.exemple" + "@" + "gmail.com",
    "valeur littérale d'un secret": "API_KEY = '" + "a1b2c3d4" * 4 + "'",
}
for nom, faute in FAUTES.items():
    verifier(re.search(ACCUSATIONS[nom], faute), f"le motif « {nom} » attrape sa faute")
for innocent in ("Le secret `whsec_…` qui signe les notifications", "cle = config.cle_upload_post()",
                 "contact@groupe-alma.fr", 'os.environ["UPLOAD_POST_API_KEY"] = "cle-de-banc"'):
    verifier(not any(re.search(m, innocent) for m in ACCUSATIONS.values()), f"et laisse passer : {innocent[:40]}")

print("— Le dépôt ne porte aucune clé")
fichiers = suivis()
verifier(len(fichiers) > 40, f"le relevé voit les fichiers du dépôt ({len(fichiers)})")
verifier(not any(".venv" in f.parts or "donnees" in f.parts for f in fichiers),
         "ni l'environnement Python ni les données locales n'y entrent")
trouves = []
for f in fichiers:
    if f.suffix.lower() in BINAIRES:
        continue
    texte = f.read_text(encoding="utf-8", errors="replace")
    for nom, motif in ACCUSATIONS.items():
        for m in re.finditer(motif, texte):
            trouves.append(f"{f.relative_to(RACINE)} : {nom} ({m.group(0)[:12]}…)")
egal(trouves, [], "aucune clé, aucun jeton, aucune adresse personnelle dans les fichiers")
verifier(not any(f.name == ".env" for f in fichiers), "aucun fichier .env n'entrerait dans le dépôt")
verifier((RACINE / ".env.example") in fichiers, "le fichier d'exemple, lui, est suivi")

print("— Le fichier d'exemple : tous les noms, aucune valeur")
exemple = (RACINE / ".env.example").read_text(encoding="utf-8")
avec_valeur = [l for l in exemple.splitlines() if l.strip() and not l.lstrip().startswith("#")
               and not re.fullmatch(r"[A-Z0-9_]+=", l.strip())]
egal(avec_valeur, [], "chaque ligne est « NOM= », sans valeur")
lus = set()
for f in [*(RACINE / "alma_social").rglob("*.py"), RACINE / "app.py"]:
    lus |= set(re.findall(r"""(?:_env|_env_bool|getenv|env\.get)\(\s*["']([A-Z][A-Z0-9_]+)["']""", f.read_text()))
manquants = sorted(n for n in lus if n not in exemple)
egal(manquants, [], f"les {len(lus)} variables lues par le code y sont toutes nommées")

print("— En production : aucun code d'essai, aucune clé de secours")
os.environ["INSTANCE_ID"] = "banc"                       # ce que Clever Cloud pose sur ses instances
verifier(config.heberge() and not config.env_dev(), "Clever détecté : plus de mode développement, même en SQLite")
graines.contraintes()
graines.marques()
egal(graines.utilisateurs(), [], "sans SOCIAL_CODE_PDG : personne n'est créé (pas de code par défaut)")
with db.moteur().begin() as c:
    egal(c.execute(db.users.select()).fetchall(), [], "la table des utilisateurs reste vide")
try:
    securite.chiffrer("jeton")
    verifier(False, "sans SOCIAL_CLE_CHIFFREMENT : refus de stocker un jeton")
except RuntimeError as e:
    verifier("SOCIAL_CLE_CHIFFREMENT" in str(e), "sans SOCIAL_CLE_CHIFFREMENT : refus de stocker un jeton")
os.environ["SOCIAL_CODE_PDG"] = "11111111"
egal(graines.utilisateurs(), [], "un code trivial (un seul chiffre) est refusé")
os.environ["SOCIAL_CODE_PDG"] = "40718263"
os.environ["SOCIAL_EMAIL_PDG"] = "pdg@groupe-alma.test"
egal(graines.utilisateurs(), ["pdg"], "avec SOCIAL_CODE_PDG : le PDG est créé")
egal(securite.identifier("101010"), None, "le code d'essai 101010 n'ouvre rien")
u = securite.identifier("40718263")
egal((u or {}).get("role"), "pdg", "le code de l'environnement ouvre la session du PDG")
egal((u or {}).get("email"), "pdg@groupe-alma.test", "son adresse vient de l'environnement")
with db.moteur().begin() as c:
    h = c.execute(db.users.select()).mappings().first()["code_hash"]
verifier("40718263" not in h, "le code est rangé haché, jamais en clair")

print("— Les jetons des réseaux, chiffrés")
os.environ["SOCIAL_CLE_CHIFFREMENT"] = "une-longue-phrase-de-banc-qui-ne-sert-qu-ici-0123456789"
ch = securite.chiffrer("alma-rega")
verifier(ch and "alma-rega" not in ch, "le profil chiffré ne laisse rien lire")
egal(securite.dechiffrer(ch), "alma-rega", "et se relit avec la clé")
os.environ["SOCIAL_CLE_CHIFFREMENT"] = "une-autre-cle"
egal(securite.dechiffrer(ch), "", "avec une autre clé : rien (pas d'erreur, pas de fuite)")
egal(securite.masquer("abcdefghijklmnop"), "•••• mnop", "à l'écran : seulement les quatre derniers caractères")

for k in ("INSTANCE_ID", "SOCIAL_CODE_PDG", "SOCIAL_EMAIL_PDG", "SOCIAL_CLE_CHIFFREMENT"):
    os.environ.pop(k, None)
socle.fin()
