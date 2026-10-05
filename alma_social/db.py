"""Le modèle de données — une seule définition, deux moteurs.

SQLAlchemy Core (pas d'ORM) : des tables déclarées une fois, des requêtes
lisibles, et le même code sur SQLite (poste, bancs) et sur PostgreSQL
(production). On n'emploie aucune fonction propre à l'un des deux : pas de
`ON CONFLICT`, pas de `FOR UPDATE SKIP LOCKED`, pas d'opérateur JSON en SQL.
Les colonnes JSON sont relues en Python.

Toutes les heures sont stockées en UTC, sans fuseau (naïves) ; la conversion
vers Paris se fait à l'affichage et dans le planificateur.
"""
from __future__ import annotations

import datetime as dt
import threading

from sqlalchemy import (
    JSON, Boolean, Column, Date, DateTime, Float, ForeignKey, Integer,
    MetaData, String, Table, Text, UniqueConstraint, create_engine, event,
    text,
)

from . import config

meta = MetaData()


def maintenant() -> dt.datetime:
    """L'horloge du produit : UTC naïf. Une seule définition — les bancs la
    remplacent pour rejouer une semaine en quelques secondes."""
    return _horloge()


def _horloge_reelle() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None, microsecond=0)


_horloge = _horloge_reelle


def figer_horloge(instant):
    """Pour les bancs : `figer_horloge(dt.datetime(2026, 11, 2, 9))`, ou None."""
    global _horloge
    _horloge = (lambda: instant) if instant else _horloge_reelle


# ── Marques, comptes, personnes ──────────────────────────────────────────
brands = Table(
    "brands", meta,
    Column("id", String(40), primary_key=True),          # slug : sazu, rega…
    Column("name", String(120), nullable=False),
    Column("activity", Text, default=""),
    Column("zone", Text, default=""),
    Column("audience", Text, default=""),
    Column("sector", String(20), default="b2c"),         # food | btp | b2b | retail
    Column("kit", JSON, default=dict),                   # charte : couleurs, polices, logo, filigrane
    Column("voice", JSON, default=dict),                 # fiche de voix
    Column("pillars", JSON, default=list),               # piliers de contenu
    Column("facts", JSON, default=dict),                 # chiffres VÉRIFIÉS (seuls autorisés dans un texte)
    Column("products", JSON, default=list),              # SAZÚ : bowls, prix réels par plateforme
    Column("links", JSON, default=dict),                 # site, devis, uber_eats, deliveroo, téléphone
    Column("faq", JSON, default=list),                   # réponses aux questions courantes
    Column("language", String(5), default="fr"),
    Column("cadence_min", Integer, default=3),
    Column("cadence_max", Integer, default=5),
    Column("active_platforms", JSON, default=list),
    Column("manager_id", Integer, nullable=True),
    Column("active", Boolean, default=True),
    Column("paused_until", DateTime, nullable=True),     # pause 48 h
    Column("paused_reason", Text, nullable=True),
    Column("kit_version", Integer, default=1),           # change → nouvelles déclinaisons
    # Une marque peut exiger qu'un humain valide chaque publication (SAZÚ :
    # « Lucie valide tout », d'après ses propres documents). Faux par défaut :
    # la règle d'ALMA SOCIAL est « aucune validation ».
    Column("requires_approval", Boolean, default=False),
    Column("todo", JSON, default=list),                  # ce qui manque encore (valeurs provisoires)
    Column("created_at", DateTime, default=maintenant),
)

users = Table(
    "users", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(120), nullable=False),
    Column("email", String(200), default=""),
    Column("role", String(20), nullable=False),          # pdg | responsable
    Column("brands", JSON, default=list),                # [] pour le PDG = toutes
    Column("code_hash", String(200), default=""),
    Column("active", Boolean, default=True),
    Column("created_at", DateTime, default=maintenant),
    Column("last_login", DateTime, nullable=True),
)

sessions = Table(
    "sessions", meta,
    Column("token_hash", String(64), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("created_at", DateTime, default=maintenant),
    Column("expires_at", DateTime, nullable=False),
)

login_attempts = Table(
    "login_attempts", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ip", String(64), nullable=False),
    Column("at", DateTime, default=maintenant),
    Column("ok", Boolean, default=False),
)

accounts = Table(
    "accounts", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("brand_id", String(40), ForeignKey("brands.id"), nullable=False),
    Column("platform", String(20), nullable=False),
    Column("handle", String(200), default=""),
    Column("mode", String(20), default="agregateur"),    # agregateur | direct
    Column("external_profile_enc", Text, default=""),    # clé de profil agrégateur, chiffrée
    Column("tokens_enc", Text, default=""),              # jetons API officielle, chiffrés
    Column("token_expires_at", DateTime, nullable=True),
    Column("status", String(20), default="a_relier"),    # a_relier | actif | pause | erreur
    Column("consecutive_failures", Integer, default=0),
    Column("last_error", Text, default=""),
    # Ce qui n'est PAS secret et que l'agrégateur réclame à chaque envoi :
    # page Facebook, page LinkedIn, tableau Pinterest, établissement Google.
    Column("options", JSON, default=dict),
    Column("updated_at", DateTime, default=maintenant),
    UniqueConstraint("brand_id", "platform", name="uq_compte_marque_reseau"),
)

# ── Photos et déclinaisons ───────────────────────────────────────────────
projects = Table(
    "projects", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("brand_id", String(40), ForeignKey("brands.id"), nullable=False),
    Column("name", String(200), nullable=False),
    Column("type", String(20), default="chantier"),      # chantier | recette | evenement | recrutement
    Column("start", Date, nullable=True),
    Column("end", Date, nullable=True),
)

assets = Table(
    "assets", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("brand_id", String(40), ForeignKey("brands.id"), nullable=False),
    Column("uploader_id", Integer, nullable=True),
    Column("client_ref", String(64), unique=True, nullable=True),   # idempotence de la file du téléphone
    Column("original_path", Text, nullable=False),
    Column("blurred_path", Text, nullable=True),         # version floutée (bouton « flouter »)
    Column("sha256", String(64), nullable=False),
    Column("phash", String(16), default=""),             # empreinte visuelle (anti-doublon)
    Column("width", Integer, default=0),
    Column("height", Integer, default=0),
    Column("exif", JSON, default=dict),
    Column("taken_at", DateTime, nullable=True),
    Column("location", JSON, nullable=True),
    Column("vision", JSON, nullable=True),               # lecture complète du modèle de vision
    Column("vision_model", String(60), default=""),
    Column("usability", Integer, nullable=True),
    Column("quality", JSON, nullable=True),              # mesures locales : netteté, exposition…
    Column("tags", JSON, default=list),
    Column("pillar", String(60), default=""),
    Column("project_id", Integer, nullable=True),
    Column("kind", String(10), default="photo"),         # photo | carte (visuel typographique généré)
    Column("status", String(20), default="recu"),        # recu | banque | programme | publie | refuse | quarantaine | retire
    Column("refusal_reason", Text, default=""),
    Column("note", Text, default=""),                    # la phrase dictée au dépôt (« livré hier, Lattes »)
    Column("score", Float, default=0.0),                 # performance des publications (recyclage)
    Column("last_used_at", DateTime, nullable=True),
    Column("created_at", DateTime, default=maintenant),
)

renditions = Table(
    "renditions", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("asset_id", Integer, ForeignKey("assets.id"), nullable=False),
    Column("format", String(10), nullable=False),        # 1:1 | 4:5 | 9:16 | 16:9 | 9:16v (vidéo)
    Column("path", Text, nullable=False),
    Column("public_token", String(40), unique=True, nullable=False),
    Column("treatments", JSON, default=list),
    Column("cache_key", String(64), unique=True, nullable=False),
    Column("sha256", String(64), default=""),
    Column("duration_s", Float, nullable=True),          # vidéo : la vraie durée (montage du studio)
    Column("created_at", DateTime, default=maintenant),
)

# ── Planification ────────────────────────────────────────────────────────
plans = Table(
    "plans", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("brand_id", String(40), ForeignKey("brands.id"), nullable=False),
    Column("month", String(7), nullable=False),          # 2026-11
    Column("content", JSON, default=list),               # aperçu lisible des créneaux
    Column("status", String(20), default="propose"),     # propose | valide | applique
    Column("proposed_at", DateTime, default=maintenant),
    Column("validated_at", DateTime, nullable=True),
    Column("validated_by", String(120), nullable=True),
    Column("reminder_sent_at", DateTime, nullable=True),
    UniqueConstraint("brand_id", "month", name="uq_plan_marque_mois"),
)

series = Table(
    "series", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("brand_id", String(40), ForeignKey("brands.id"), nullable=False),
    Column("label", String(120), nullable=False),        # « Le bowl du lundi »
    Column("weekday", Integer, nullable=False),          # 0 = lundi
    Column("time", String(5), default=""),               # "" = le planificateur choisit
    Column("platforms", JSON, default=list),             # [] = réseaux actifs de la marque
    Column("pillar", String(60), default=""),
    Column("tags", JSON, default=list),
    Column("starts_on", Date, nullable=True),            # SAZÚ : pas d'« offre du vendredi » avant l'ouverture
    Column("active", Boolean, default=True),
)

campaigns = Table(
    "campaigns", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(200), nullable=False),
    Column("brand_ids", JSON, default=list),
    Column("kind", String(20), default="evenement"),     # ouverture | promo | emploi | chantier | evenement
    Column("event_at", DateTime, nullable=True),         # l'heure H (UTC)
    Column("start", Date, nullable=False),
    Column("end", Date, nullable=False),
    Column("platforms", JSON, default=list),
    Column("brief", Text, default=""),
    Column("status", String(20), default="active"),      # active | terminee | annulee
    Column("created_by", String(120), default=""),
    Column("created_at", DateTime, default=maintenant),
)

slots = Table(
    "slots", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("brand_id", String(40), ForeignKey("brands.id"), nullable=False),
    Column("day", Date, nullable=False),
    Column("platforms", JSON, default=list),
    Column("pillar", String(60), default=""),
    Column("topic", Text, default=""),                   # le sujet proposé
    Column("source", String(20), default="plan"),        # plan | depot | serie | campagne
    Column("plan_id", Integer, nullable=True),
    Column("series_id", Integer, nullable=True),
    Column("campaign_id", Integer, nullable=True),
    Column("campaign_step", String(40), default=""),     # J-7, Jour J…
    Column("time", String(5), default=""),               # heure imposée (série, campagne) ; "" = la meilleure
    Column("brief", Text, default=""),                   # consigne d'écriture (étape de campagne, série)
    Column("asset_id", Integer, nullable=True),
    Column("status", String(20), default="libre"),       # libre | rempli | publie | manque | vide | annule
    Column("created_at", DateTime, default=maintenant),
)

posts = Table(
    "posts", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("brand_id", String(40), ForeignKey("brands.id"), nullable=False),
    Column("asset_id", Integer, nullable=True),
    Column("slot_id", Integer, nullable=True),
    Column("platform", String(20), nullable=False),
    Column("text", Text, default=""),
    Column("title", Text, default=""),                   # YouTube, Pinterest
    Column("rendition_id", Integer, nullable=True),
    Column("link_id", Integer, nullable=True),
    Column("scheduled_at", DateTime, nullable=True),
    Column("published_at", DateTime, nullable=True),
    Column("external_id", String(200), default=""),
    Column("permalink", Text, default=""),
    # preparation | programme | a_valider | envoi | publie | simule | suspendu | echec | refuse | retire | annule
    Column("status", String(20), default="programme"),
    Column("error", Text, default=""),
    Column("attempts", Integer, default=0),
    Column("trigger", String(20), default="depot"),      # depot | calendrier | campagne | serie | recyclage
    Column("pillar", String(60), default=""),
    Column("model", String(60), default=""),
    Column("prompt_version", String(20), default=""),
    Column("guard_report", JSON, default=dict),
    Column("simulated", Boolean, default=False),
    Column("sent_image_sha", String(64), default=""),
    Column("request_ref", String(120), default=""),      # identifiant de l'envoi chez l'agrégateur
    Column("post_format", String(12), default="image"),  # image | video | reel | carrousel | avant_apres
    Column("media_job_id", Integer, nullable=True),      # le montage du studio qui l'illustre
    Column("extra_renditions", JSON, default=list),      # carrousel : les vues 2…n, dans l'ordre
    Column("created_at", DateTime, default=maintenant),
)

# ── Mesure ───────────────────────────────────────────────────────────────
links = Table(
    "links", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("code", String(16), unique=True, nullable=False),
    Column("post_id", Integer, nullable=True),
    Column("brand_id", String(40), nullable=False),
    Column("platform", String(20), default=""),
    Column("kind", String(20), default="site"),          # site | devis | uber_eats | deliveroo | tel
    Column("target_url", Text, nullable=False),
    Column("utm", JSON, default=dict),
    Column("clicks", Integer, default=0),
    Column("created_at", DateTime, default=maintenant),
)

clicks = Table(
    "clicks", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("link_id", Integer, ForeignKey("links.id"), nullable=False),
    Column("at", DateTime, default=maintenant),
    Column("city", String(120), default=""),
    Column("device", String(20), default=""),
    Column("referrer", Text, default=""),
    Column("marker", String(40), default=""),
    Column("ip_hash", String(64), default=""),
)

leads = Table(
    "leads", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("brand_id", String(40), nullable=False),
    Column("post_id", Integer, nullable=True),
    Column("link_id", Integer, nullable=True),
    Column("channel", String(20), default="formulaire"), # formulaire | manuel | telephone | uber_eats | deliveroo
    Column("type", String(20), default="devis"),         # devis | commande | appel
    Column("amount", Float, nullable=True),
    Column("source", Text, default=""),
    Column("marker", String(40), default=""),
    Column("note", Text, default=""),
    Column("created_by", String(120), default=""),
    # v3 : la qualification (§ 15.3) et la porte par laquelle il est entré
    Column("temperature", String(6), default=""),         # chaud | tiede | froid
    Column("qualification", JSON, default=dict),          # besoin, ville, délai, budget, contact
    Column("entry_door", String(20), default=""),         # commentaire | message | qr | chat | formulaire
    Column("first_reply_s", Integer, nullable=True),      # délai de première réponse, en secondes
    Column("created_at", DateTime, default=maintenant),
)

metrics = Table(
    "metrics", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("post_id", Integer, ForeignKey("posts.id"), nullable=False),
    Column("checkpoint", String(5), nullable=False),     # 1h | 24h | 7j
    Column("measured_at", DateTime, default=maintenant),
    Column("views", Integer, default=0),
    Column("reach", Integer, default=0),
    Column("likes", Integer, default=0),
    Column("comments", Integer, default=0),
    Column("shares", Integer, default=0),
    Column("saves", Integer, default=0),
    Column("clicks", Integer, default=0),
    Column("followers_gained", Integer, default=0),
    Column("simulated", Boolean, default=False),
    Column("raw", JSON, default=dict),
)

slot_profiles = Table(
    "slot_profiles", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("brand_id", String(40), nullable=False),
    Column("platform", String(20), nullable=False),
    Column("computed_at", DateTime, default=maintenant),
    Column("weights", JSON, default=dict),               # {"0-11": 0.8, …} jour-heure → score
    Column("observations", Integer, default=0),
    UniqueConstraint("brand_id", "platform", name="uq_profil_creneaux"),
)

# ── Relation ─────────────────────────────────────────────────────────────
conversations = Table(
    "conversations", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("brand_id", String(40), nullable=False),
    Column("platform", String(20), nullable=False),
    Column("kind", String(15), default="commentaire"),   # commentaire | message
    Column("external_id", String(200), unique=True, nullable=False),
    Column("post_id", Integer, nullable=True),
    Column("author", String(200), default=""),
    Column("author_meta", JSON, default=dict),
    Column("text", Text, default=""),
    Column("category", String(30), default=""),
    Column("urgency", Integer, default=0),
    Column("reply", Text, default=""),
    Column("replied_by", String(10), default=""),        # ia | humain
    Column("alert_sent", Boolean, default=False),
    Column("status", String(20), default="nouveau"),     # nouveau | repondu | alerte | masque | traite
    Column("received_at", DateTime, default=maintenant),
)

reviews = Table(
    "reviews", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("brand_id", String(40), nullable=False),
    Column("platform", String(20), default="gbp"),
    Column("external_id", String(200), unique=True, nullable=False),
    Column("rating", Integer, nullable=False),
    Column("text", Text, default=""),
    Column("author", String(200), default=""),
    Column("reply", Text, default=""),
    Column("draft", Text, default=""),
    Column("reply_due_at", DateTime, nullable=True),
    Column("status", String(20), default="nouveau"),     # nouveau | a_repondre | repondu | alerte
    Column("received_at", DateTime, default=maintenant),
    Column("replied_at", DateTime, nullable=True),
)

competitors = Table(
    "competitors", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("brand_id", String(40), nullable=False),
    Column("name", String(200), nullable=False),
    Column("platform", String(20), default=""),
    Column("handle", String(200), default=""),
    Column("google_place", String(200), default=""),
    Column("last_observation", JSON, default=dict),
)

competitor_observations = Table(
    "competitor_observations", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("competitor_id", Integer, ForeignKey("competitors.id"), nullable=False),
    Column("observed_at", DateTime, default=maintenant),
    Column("posts_7d", Integer, nullable=True),
    Column("rating", Float, nullable=True),
    Column("reviews_count", Integer, nullable=True),
    Column("source", String(20), default="manuel"),
)

# ── Contraintes, alertes, journal, file, réglages ────────────────────────
platform_constraints = Table(
    "platform_constraints", meta,
    Column("platform", String(20), primary_key=True),
    Column("formats", JSON, default=list),
    Column("ratio_min", Float, nullable=True),
    Column("ratio_max", Float, nullable=True),
    Column("max_weight_mb", Float, nullable=True),
    Column("video_max_mb", Float, nullable=True),
    Column("duration_min", Float, nullable=True),
    Column("duration_max", Float, nullable=True),
    Column("caption_max", Integer, nullable=False),
    Column("hashtags_max", Integer, nullable=True),
    Column("posts_per_day", Integer, nullable=True),
    Column("links_clickable", Boolean, default=False),
    Column("carousel_max", Integer, nullable=True),
    Column("preferred_format", String(10), default="4:5"),
    Column("source", Text, default=""),
    Column("verified_on", String(10), default=""),
    Column("confirmed", Boolean, default=False),
    Column("notes", Text, default=""),
)

alerts = Table(
    "alerts", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("brand_id", String(40), nullable=True),
    Column("level", String(10), default="urgent"),       # urgent | panne | info
    Column("kind", String(30), default=""),
    Column("subject", Text, nullable=False),
    Column("body", Text, default=""),
    Column("sent_to", JSON, default=list),
    Column("dedup_key", String(120), nullable=True),
    Column("created_at", DateTime, default=maintenant),
    Column("read_at", DateTime, nullable=True),
)

audit_log = Table(
    "audit_log", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("at", DateTime, default=maintenant),
    Column("actor", String(120), nullable=False),
    Column("action", String(60), nullable=False),
    Column("object_type", String(30), default=""),
    Column("object_id", String(60), default=""),
    Column("brand_id", String(40), nullable=True),
    Column("before", JSON, nullable=True),
    Column("after", JSON, nullable=True),
    Column("prev_hash", String(64), default=""),
    Column("hash", String(64), nullable=False),
)

jobs = Table(
    "jobs", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("kind", String(40), nullable=False),
    Column("payload", JSON, default=dict),
    Column("run_at", DateTime, default=maintenant),
    Column("attempts", Integer, default=0),
    Column("max_attempts", Integer, default=4),
    Column("status", String(10), default="attente"),     # attente | encours | fait | echec
    Column("last_error", Text, default=""),
    Column("dedup_key", String(120), unique=True, nullable=True),
    Column("created_at", DateTime, default=maintenant),
    Column("updated_at", DateTime, default=maintenant),
)

settings = Table(
    "settings", meta,
    Column("key", String(60), primary_key=True),
    Column("value", JSON),
    Column("updated_at", DateTime, default=maintenant),
    Column("updated_by", String(120), default=""),
)


# ── v3 : le cerveau (agents, plateforme de marque, apprentissage) ────────
brand_platforms = Table(
    "brand_platforms", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("brand_id", String(40), ForeignKey("brands.id"), nullable=False),
    Column("version", Integer, nullable=False),
    Column("adn", JSON, default=dict),                   # ce qui a été LU (sources citées)
    Column("plateforme", JSON, default=dict),            # positionnement, promesse, personas…
    Column("auteur", String(60), default=""),            # modèle, ou « graines » sans clé
    Column("relue_le", DateTime, nullable=True),         # Philippe la relit une fois
    Column("created_at", DateTime, default=maintenant),
    UniqueConstraint("brand_id", "version", name="uq_plateforme_version"),
)

voice_corrections = Table(
    "voice_corrections", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("brand_id", String(40), nullable=False),
    Column("contexte", String(30), default=""),          # avis | reponse | plan | texte
    Column("avant", Text, default=""),
    Column("apres", Text, default=""),
    Column("type", String(40), default=""),              # le genre de correction (tutoiement, longueur…)
    Column("regle", Text, default=""),                   # la règle qu'on en tire
    Column("appliquee", Boolean, default=False),         # entrée dans la fiche de voix
    Column("par", String(120), default=""),
    Column("created_at", DateTime, default=maintenant),
)

learnings = Table(
    "learnings", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("brand_id", String(40), nullable=False),
    Column("cle", String(80), nullable=False),           # ce qu'on compare (format:carrousel…)
    Column("lecon", Text, nullable=False),
    Column("preuve", JSON, default=dict),                # échantillon, période, chiffres
    Column("statut", String(12), default="active"),      # active | contredite
    Column("created_at", DateTime, default=maintenant),
    Column("updated_at", DateTime, default=maintenant),
)

experiments = Table(
    "experiments", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("brand_id", String(40), nullable=False),
    Column("hypothese", Text, nullable=False),
    Column("variable", String(30), default="accroche"),  # accroche | couverture | format | heure
    Column("variantes", JSON, default=list),             # [{nom, post_ids}]
    Column("taille", Integer, default=0),
    Column("resultat", JSON, default=dict),
    Column("conclusion", Text, default=""),
    Column("statut", String(12), default="en_cours"),    # en_cours | nette | pas_nette
    Column("created_at", DateTime, default=maintenant),
)

agent_runs = Table(
    "agent_runs", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("agent", String(30), nullable=False),
    Column("brand_id", String(40), nullable=True),
    Column("objet", String(80), default=""),             # post:12, asset:4, plan:sazu-2026-11…
    Column("model", String(60), default=""),             # le modèle qui a VRAIMENT répondu
    Column("consignes", String(30), default=""),         # version des consignes
    Column("entrees", Text, default=""),                 # le texte envoyé (sans les images), tronqué
    Column("sortie", Text, default=""),
    Column("issue", String(12), default="ok"),           # ok | refus | tronque | erreur | repli | plafond
    Column("tokens_in", Integer, default=0),
    Column("tokens_out", Integer, default=0),
    Column("tokens_cache", Integer, default=0),
    Column("cout_usd", Float, default=0.0),
    Column("secondes", Float, default=0.0),
    Column("created_at", DateTime, default=maintenant),
)

critic_scores = Table(
    "critic_scores", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("post_id", Integer, nullable=True),
    Column("slot_id", Integer, nullable=True),
    Column("brand_id", String(40), nullable=False),
    Column("platform", String(20), default=""),
    Column("tour", Integer, default=1),
    Column("note", Integer, default=0),
    Column("detail", JSON, default=dict),                # critère → note, remarques
    Column("decision", String(12), default=""),          # passe | reecrire | banque
    Column("juge", String(60), default=""),              # modèle, ou « grille-locale »
    Column("created_at", DateTime, default=maintenant),
)

visual_tags = Table(
    "visual_tags", meta,
    Column("asset_id", Integer, primary_key=True),
    Column("tags", JSON, default=dict),                  # objets, couleurs, cadrage, humains…
    Column("created_at", DateTime, default=maintenant),
)

media_jobs = Table(
    "media_jobs", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("brand_id", String(40), nullable=False),
    Column("asset_ids", JSON, default=list),
    Column("type", String(20), nullable=False),          # carrousel | avant_apres | reel | clip | story | declinaison
    Column("statut", String(12), default="attente"),     # attente | fait | echec
    Column("sortie", JSON, default=dict),                # fichiers produits, durée, vues
    Column("score", Integer, nullable=True),             # potentiel estimé
    Column("traitements", JSON, default=list),           # ce qui a été fait à l'image, dans l'ordre
    Column("erreur", Text, default=""),
    Column("created_at", DateTime, default=maintenant),
)

rehearsals = Table(
    "rehearsals", meta,                                  # la répétition générale d'une campagne
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("campaign_id", Integer, nullable=False),
    Column("etapes", JSON, default=list),                # par étape : visuel, textes, verdicts
    Column("resume", JSON, default=dict),
    Column("par", String(120), default=""),
    Column("created_at", DateTime, default=maintenant),
)

evergreen = Table(
    "evergreen", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("brand_id", String(40), nullable=False),
    Column("categorie", String(40), default=""),
    Column("post_source_id", Integer, nullable=False),
    Column("derniere_sortie", DateTime, nullable=True),
    Column("sorties", Integer, default=0),
)

post_conditions = Table(
    "post_conditions", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("post_id", Integer, nullable=False),
    Column("condition", JSON, default=dict),             # {"meteo": "soleil"} · {"si_vues_lt": 300, "relancer": …}
    Column("etat", String(12), default="attente"),
)

budgets = Table(
    "budgets", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("brand_id", String(40), nullable=True),       # None = l'IA du groupe
    Column("mois", String(7), nullable=False),           # 2026-11
    Column("enveloppe_outils", Float, default=0.0),
    Column("enveloppe_pub", Float, default=0.0),         # ZÉRO tant que Philippe n'a rien décidé
    Column("consomme", Float, default=0.0),
    UniqueConstraint("brand_id", "mois", name="uq_budget_mois"),
)

ask_threads = Table(
    "ask_threads", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, nullable=False),
    Column("question", Text, nullable=False),
    Column("reponse", Text, default=""),
    Column("actions", JSON, default=list),               # ce que l'agent a fait, annoncé
    Column("model", String(60), default=""),
    Column("created_at", DateTime, default=maintenant),
)


# ── Le moteur ────────────────────────────────────────────────────────────
_moteur = None
_verrou = threading.Lock()


def moteur():
    global _moteur
    with _verrou:
        if _moteur is None:
            _moteur = _creer(config.url_base_de_donnees())
        return _moteur


def _creer(url: str):
    if url.startswith("sqlite"):
        eng = create_engine(url, future=True,
                            connect_args={"check_same_thread": False, "timeout": 30})

        @event.listens_for(eng, "connect")
        def _pragmas(conn, _):
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()
        return eng
    return create_engine(url, future=True, pool_pre_ping=True, pool_size=5, max_overflow=5)


def brancher(url: str):
    """Pour les bancs : une base neuve et isolée."""
    global _moteur
    with _verrou:
        if _moteur is not None:
            _moteur.dispose()
        _moteur = _creer(url)
    initialiser()
    return _moteur


# LE JOURNAL N'EST PAS MODIFIABLE — et ce n'est pas une promesse de l'application,
# c'est la base qui refuse. Une publication automatique n'a pas d'autre preuve
# que ce journal : il ne doit pas pouvoir être retouché après coup, même par
# erreur, même par un prestataire pressé.
_JOURNAL_SQLITE = [
    """CREATE TRIGGER IF NOT EXISTS journal_sans_modification
       BEFORE UPDATE ON audit_log
       BEGIN SELECT RAISE(ABORT, 'journal non modifiable'); END""",
    """CREATE TRIGGER IF NOT EXISTS journal_sans_effacement
       BEFORE DELETE ON audit_log
       BEGIN SELECT RAISE(ABORT, 'journal non modifiable'); END""",
]
_JOURNAL_PG = [
    """CREATE OR REPLACE FUNCTION journal_fige() RETURNS trigger AS $$
       BEGIN RAISE EXCEPTION 'journal non modifiable'; END; $$ LANGUAGE plpgsql""",
    "DROP TRIGGER IF EXISTS journal_fige_t ON audit_log",
    """CREATE TRIGGER journal_fige_t BEFORE UPDATE OR DELETE ON audit_log
       FOR EACH ROW EXECUTE FUNCTION journal_fige()""",
]


def _completer_colonnes(eng):
    """`create_all` crée les tables qui manquent, jamais les COLONNES qui
    manquent : une base de production née en v1 garderait ses tables v1
    pour toujours, et la première requête v3 tomberait. On ajoute donc ce
    qui manque, colonne par colonne, sans valeur par défaut côté base (les
    défauts vivent dans le code) — et on ne retire ni ne modifie jamais rien.
    """
    from sqlalchemy import inspect
    insp = inspect(eng)
    existantes = set(insp.get_table_names())
    with eng.begin() as c:
        for t in meta.sorted_tables:
            if t.name not in existantes:
                continue
            presentes = {col["name"] for col in insp.get_columns(t.name)}
            for col in t.columns:
                if col.name in presentes:
                    continue
                type_sql = col.type.compile(dialect=eng.dialect)
                c.execute(text(f'ALTER TABLE {t.name} ADD COLUMN {col.name} {type_sql}'))


def initialiser():
    eng = moteur()
    meta.create_all(eng)
    _completer_colonnes(eng)
    instructions = _JOURNAL_SQLITE if eng.dialect.name == "sqlite" else _JOURNAL_PG
    with eng.begin() as c:
        for sql in instructions:
            c.execute(text(sql))


def lignes(resultat):
    """Résultat SQLAlchemy → liste de dicts (pour le JSON et les gabarits)."""
    return [dict(r._mapping) for r in resultat]


def ligne(resultat):
    r = resultat.first()
    return dict(r._mapping) if r is not None else None
