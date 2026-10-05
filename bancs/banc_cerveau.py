"""Banc : l'équipe d'agents — modèles, coûts, plafond, plateforme de marque,
voix qui apprend, carnet, Critique et sa boucle de réécriture, migration douce."""
import json

import socle
from socle import FauxClaude, egal, verifier

from sqlalchemy import create_engine, func, select, text

from alma_social import (acces, agents, alertes, carnet, critique, db, graines, ia, journal, marque, redaction,
                         voix)

socle.figer(2026, 10, 5, 6)
graines.semer()
sazu, rega = acces.marque("sazu"), acces.marque("rega")


def runs(**filtre):
    q = select(db.agent_runs)
    for k, v in filtre.items():
        q = q.where(getattr(db.agent_runs.c, k) == v)
    with db.moteur().connect() as c:
        return db.lignes(c.execute(q.order_by(db.agent_runs.c.id)))


print("— L'équipe : un modèle par agent, réglable en base")
egal(agents.modele("critique"), "claude-opus-5-5", "le Critique a le modèle le plus capable")
egal(agents.modele("redacteur"), "claude-sonnet-5-5", "les Rédacteurs ont le modèle rapide")
egal(agents.modele("garde_fou"), "claude-haiku-4-5", "le tri en masse a le petit modèle")
egal(agents.modele("redaction"), "claude-sonnet-5-5", "l'ancien usage « redaction » est traduit vers son agent")
journal.ecrire("agents.modeles", {"redacteur": "fort", "cm": "claude-sonnet-5-5", "lecteur": "n'importe quoi"})
egal(agents.modele("redacteur"), "claude-opus-5-5", "un niveau réglé en base l'emporte")
egal(agents.modele("lecteur"), "claude-sonnet-5-5", "un réglage illisible est ignoré (on garde le niveau)")
journal.ecrire("agents.modeles", {})
egal(len(agents.tableau()), len(agents.EQUIPE), "le tableau de l'équipe liste chaque agent")
egal(agents.cout_usd("claude-opus-5-5", 1_000_000, 0), 4.0, "Opus : 4 $ le million de jetons d'entrée")
egal(agents.cout_usd("claude-sonnet-5-5", 0, 1_000_000), 10.0, "Sonnet : 10 $ le million en sortie")
egal(agents.cout_usd("claude-haiku-4-5", 0, 0, cache_lu=1_000_000), 0.1, "lecture du cache : un dixième")
egal(agents.cout_usd("modele-inconnu", 1_000_000, 0), 4.0, "un modèle inconnu est compté au prix du plus cher")

print("— La porte : ce qui part, ce qui est tracé")
from pydantic import BaseModel  # noqa: E402


class Essai(BaseModel):
    mot: str


faux = FauxClaude({"Essai": lambda p: socle.reponse(Essai(mot="ok"), "claude-sonnet-5-5")})
ia.CLIENT = faux
obj, modele = ia.appeler("SYSTÈME STABLE", [{"type": "text", "text": "bonjour"}], Essai, agent="redacteur",
                         marque_id="sazu", objet="slot:1")
egal(obj.mot, "ok", "la sortie structurée est rendue")
p = faux.appels[-1]
egal(p["model"], "claude-sonnet-5-5", "le modèle de l'agent est celui envoyé")
egal(p["system"][0].get("cache_control"), {"type": "ephemeral"}, "le contexte de marque part en cache")
egal(p.get("fallbacks"), "default", "le repli serveur est demandé sur Sonnet 5.5")
egal(p.get("output_config"), {"effort": "low"}, "l'effort de l'agent est fixé")
ia.appeler("S", [{"type": "text", "text": "x"}], Essai, agent="garde_fou")
p = faux.appels[-1]
verifier("output_config" not in p and "fallbacks" not in p and "betas" not in p,
         "Haiku : ni effort ni repli serveur (il ne les accepte pas)")
r = runs(agent="redacteur")[-1]
egal((r["brand_id"], r["objet"], r["model"], r["consignes"], r["issue"]),
     ("sazu", "slot:1", "claude-sonnet-5-5", "redaction-v2", "ok"), "l'appel est inscrit dans agent_runs")
egal(r["cout_usd"], agents.cout_usd("claude-sonnet-5-5", 1200, 400), "son coût est calculé sur les jetons réels")
verifier("bonjour" in r["entrees"] and '"mot":"ok"' in r["sortie"].replace(" ", ""), "entrées et sortie gardées")

faux.reponses["Essai"] = lambda p: socle.reponse(None, p["model"], stop="refusal")
try:
    ia.appeler("S", [{"type": "text", "text": "x"}], Essai, agent="cm")
    verifier(False, "un refus doit lever ErreurIA")
except ia.ErreurIA as e:
    verifier(not isinstance(e, ia.SansCle), "un refus du modèle lève ErreurIA (pas « sans clé »)")
egal(runs(agent="cm")[-1]["issue"], "refus", "le refus est tracé")

print("— Le plafond du mois : au-delà, les replis, et une alerte une fois")
faux.reponses["Essai"] = lambda p: socle.reponse(Essai(mot="ok"), p["model"])
journal.ecrire("ia.plafond_mois_usd", 0.001)
for _ in range(2):
    try:
        ia.appeler("S", [{"type": "text", "text": "x"}], Essai, agent="analyste")
        verifier(False, "le plafond doit bloquer")
    except ia.Plafond:
        pass
egal(runs(agent="analyste")[-1]["issue"], "plafond", "l'appel bloqué est tracé « plafond », à coût nul")
with db.moteur().connect() as c:
    n = c.execute(select(func.count()).select_from(db.alerts).where(db.alerts.c.kind == "cout")).scalar()
egal(n, 1, "une seule alerte de plafond, pas une par appel")
verifier(issubclass(ia.Plafond, ia.SansCle), "le plafond se comporte comme « sans clé » : chaque agent a son repli")
journal.ecrire("ia.plafond_mois_usd", 150)
c_ = ia.couts()
verifier(c_["mois_usd"] > 0 and any(a["agent"] == "redacteur" for a in c_["agents"]), "Santé lit les coûts par agent")

print("— La plateforme de marque")
egal(len([m for m in acces.marques() if marque.courante(m["id"])]), 6, "six plateformes semées")
p_sazu = marque.courante("sazu")
egal((p_sazu["version"], p_sazu["auteur"]), (1, "graines"), "version 1, écrite à la main d'après le Drive")
egal(p_sazu["plateforme"]["direction_artistique"]["mise_en_scene"], "studio_permis",
     "SAZÚ (produit) : le fond peut être refait en studio")
egal(marque.courante("rega")["plateforme"]["direction_artistique"]["mise_en_scene"], "decor_reel",
     "REGA (réalisation) : jamais de décor remplacé")
for m in acces.marques():
    pr = marque.courante(m["id"])["plateforme"]["preuves"]
    verifier(set(pr) <= set((m["facts"] or {}).keys()), f"{m['id']} : chaque preuve est un fait de la base")
nettoye = marque._nettoyer(rega, {"preuves": ["devis", "inventee"], "mix": {"utile": 2, "communaute": 1, "vente": 1},
                                  "direction_artistique": {"mise_en_scene": "studio_permis"}})
egal(nettoye["preuves"], ["devis"], "une preuve absente de la base est retirée")
egal(nettoye["mix"], {"utile": 50, "communaute": 25, "vente": 25}, "le mix est ramené à 100")
egal(nettoye["direction_artistique"]["mise_en_scene"], "decor_reel",
     "le modèle ne peut pas autoriser un décor refait pour un chantier")

html = """<html><head><title>La Maison des Sols</title><meta name="description" content="Pose de sols à Montpellier">
<style>h1{color:#1A2B3C;font-family:'Playfair Display',serif} p{color:#1A2B3C} .b{background:#C0FFEE}</style></head>
<body><h1>Des sols qui durent</h1><p>Nous préparons chaque support avant la pose, parce que c'est ce qui fait tenir un sol.</p>
<script>var x="#FFFFFF"</script></body></html>"""
lu = marque.lire_site(html)
egal((lu["titre"], lu["couleurs"][0], lu["polices"][0]), ("La Maison des Sols", "#1a2b3c", "Playfair Display"),
     "le site est lu : titre, couleur dominante, police")
verifier("#ffffff" not in lu["couleurs"], "le code des scripts n'est pas pris pour la charte")
marque._http = lambda url: html
adn = marque.extraire_adn(acces.marque("lms"))
egal(adn["sources"][-1], "https://lamaisondesservices.fr/", "l'ADN cite ses sources")


def _plateforme(params):
    g = marque._graines()["sazu"]
    g = dict(g, positionnement="Le bowl latino chaud de Boutonnet, version Stratège.", preuves=["salsas", "faux"])
    return socle.reponse(marque.PlateformeMarque(**g))


faux.reponses["PlateformeMarque"] = _plateforme
v2 = marque.rediger("sazu", par="banc")
egal((v2["version"], v2["plateforme"]["preuves"]), (2, ["salsas"]), "le Stratège écrit la version 2, preuves filtrées")
egal(marque.courante("sazu")["plateforme"]["positionnement"].endswith("version Stratège."), True,
     "la version courante est la dernière")
v3 = marque.corriger("sazu", {"promesse": "Chaud, généreux, à ta salsa.", "inconnu": 1}, "Philippe")
egal((v3["version"], v3["plateforme"]["promesse"], "inconnu" in v3["plateforme"]), (3, "Chaud, généreux, à ta salsa.", False),
     "une correction fait une version de plus ; un champ inconnu est ignoré")
egal(len(marque.versions("sazu")), 3, "les anciennes versions restent")
verifier(marque.relire("sazu", "Philippe")["relue_le"] is not None, "Philippe marque la plateforme comme relue")
ctx = marque.contexte(sazu)
verifier("Chaud, généreux" in ctx and "On ne dit JAMAIS" in ctx and "Persona" in ctx,
         "le contexte des agents porte promesse, interdits et personas")

print("— Le carnet d'apprentissage")
egal(carnet.apprendre("lms", "format:avant_apres", "x", {"echantillon": 3, "periode": "sept."}), None,
     "trois publications : une anecdote, pas une leçon")
l1 = carnet.apprendre("lms", "format:avant_apres", "Avant/après en carrousel : 3,1× plus d'enregistrements.",
                      {"echantillon": 14, "periode": "sept.–oct. 2026", "rapport": 3.1})
verifier(l1 is not None, "une leçon avec sa preuve entre au carnet")
verifier("3,1×" in marque.contexte(acces.marque("lms")), "les agents la lisent")
l2 = carnet.apprendre("lms", "format:avant_apres", "Avant/après : l'écart se resserre (1,4×).",
                      {"echantillon": 22, "periode": "oct.–nov. 2026", "rapport": 1.4})
egal([l["id"] for l in carnet.lecons("lms")], [l2], "la nouvelle mesure remplace l'ancienne (qui passe « contredite »)")
egal(len(carnet.lecons("lms", toutes=True)), 2, "l'ancienne reste lisible")

print("— La voix qui apprend")
egal([g for g, _ in voix.lire_correction("Un bowl délicieux, tu vas adorer 🔥", "Un bowl tout chaud, tu vas adorer")],
     ["sans_emoji", "mot_retire:delicieux"], "la correction est lue : emoji retiré, mot retiré")
egal([g for g, _ in voix.lire_correction("Un bowl généreux et chaud, cuisiné ce matin, à commander tout de suite.",
                                         "Un bowl chaud.")][0], "plus_court", "et le texte raccourci")
for i in range(2):
    voix.noter_correction("sazu", "avis", f"Merci {i}, c'est délicieux ici", f"Merci {i}, à très vite ici", "Lucie")
verifier("delicieux" not in (acces.marque("sazu")["voice"].get("forbidden") or []),
         "deux corrections ne font pas une règle")
appris = voix.noter_correction("sazu", "avis", "Toujours délicieux chez nous", "Toujours chez nous", "Lucie")
verifier("delicieux" in acces.marque("sazu")["voice"]["forbidden"] and appris,
         "à la troisième, le mot entre dans les interdits de la fiche de voix")
with db.moteur().connect() as c:
    j = c.execute(select(db.audit_log).where(db.audit_log.c.action == "voix_apprise")).first()
verifier(j is not None, "et le journal le dit")
avant_adresse = acces.marque("rega")["voice"]["address"]
for _ in range(3):
    voix.noter_correction("rega", "texte", "Vous allez aimer votre terrasse, vous verrez",
                          "Tu vas aimer ta terrasse, tu verras", "Philippe")
egal((avant_adresse, acces.marque("rega")["voice"]["address"]), ("vous", "tu"),
     "trois passages au tutoiement : la marque tutoie")

print("— Le Critique : sévère, et sa boucle de réécriture")
lect = {"sujet": "un bowl fumant vu de dessus", "elements": ["bol", "coriandre"], "utilisabilite": 85}
j = critique.noter(sazu, "instagram", "Découvrez notre bowl.", lect, violations=["superlatif : le meilleur"])
egal(j["criteres"]["risque"]["note"], 0, "une violation du garde-fou met le risque à zéro")
egal(j["juge"], "grille-locale", "sans modèle, la grille juge — et elle porte son nom")
verifier(any("générique" in r for r in j["remarques"]), "« Découvrez » est relevé comme accroche générique")


def textes(params):
    demandes = params["messages"][0]["content"][0]["text"].rsplit(":", 1)[1]
    pfs = [x.strip() for x in demandes.split(",")]
    return redaction.Redaction(textes=[redaction.TexteReseau(
        platform=pf, texte=f"Le bœuf du SALVADOR, effiloché 12 h, ce matin à Boutonnet ({pf}). Lien en bio.",
        hashtags=[], titre="") for pf in pfs])


tours = {"n": 0}


def notation(params):
    tours["n"] += 1
    n = 6 if tours["n"] == 1 else 9          # premier jet moyen, deuxième au niveau
    return critique.Notation(criteres=[critique.NoteCritere(cle=k, note=n, remarque="" if n >= 8 else f"{k} à revoir")
                                       for k, _, _ in critique.CRITERES], verdict="ouvrir sur la vapeur")


faux.reponses.update({"Redaction": textes, "Notation": notation})
r = redaction.ecrire(sazu, lect, ["instagram"], acces.contraintes(), None, {}, None, slot_id=77)
egal((r["instagram"]["essais"], r["instagram"]["violations"], r["instagram"]["critique"]["note"]), (2, [], 90),
     "60/100 au premier tour : réécrit ; 90 au second : il passe")
redac = [a for a in faux.appels if a["output_format"].__name__ == "Redaction"]
verifier("arret_pouce à revoir" in redac[-1]["messages"][0]["content"][0]["text"],
         "le rédacteur reçoit les remarques exactes du Critique")
with db.moteur().connect() as c:
    notes = db.lignes(c.execute(select(db.critic_scores).where(db.critic_scores.c.slot_id == 77)
                                .order_by(db.critic_scores.c.id)))
egal([(n["tour"], n["note"], n["decision"]) for n in notes], [(1, 60, "reecrire"), (2, 90, "passe")],
     "chaque tour est noté et gardé")

faux.reponses["Notation"] = lambda p: critique.Notation(
    criteres=[critique.NoteCritere(cle=k, note=5, remarque="plat") for k, _, _ in critique.CRITERES], verdict="plat")
r = redaction.ecrire(sazu, lect, ["facebook"], acces.contraintes(), None, {}, None, slot_id=78)
egal(r["facebook"]["essais"], 3, "trois tours au plus")
verifier(r["facebook"]["violations"] and r["facebook"]["violations"][0].startswith("critique : 50/100"),
         "toujours sous 80 : le texte porte la raison et ne partira pas (retour à la banque)")
with db.moteur().connect() as c:
    egal(c.execute(select(db.critic_scores.c.decision).where(db.critic_scores.c.slot_id == 78)
                   .order_by(db.critic_scores.c.id.desc())).scalar(), "banque", "la dernière décision est « banque »")
t = critique.taux()
verifier(t["reecritures"] >= 1 and t["a_la_banque"] >= 1 and not t["trop_indulgent"],
         "Santé lit le taux de refus du Critique")
ia.CLIENT = None

print("— La migration douce : une base v1 reçoit les colonnes v3")
import tempfile  # noqa: E402
chemin = tempfile.mktemp(suffix=".db")
eng = create_engine(f"sqlite:///{chemin}")
with eng.begin() as c:
    c.execute(text("CREATE TABLE leads (id INTEGER PRIMARY KEY, brand_id VARCHAR(40) NOT NULL, note TEXT)"))
    c.execute(text("INSERT INTO leads (id, brand_id, note) VALUES (1, 'rega', 'ancien')"))
db._completer_colonnes(eng)
with eng.connect() as c:
    cols = [r[1] for r in c.execute(text("PRAGMA table_info(leads)"))]
    egal(c.execute(text("SELECT note FROM leads WHERE id=1")).scalar(), "ancien", "les lignes existantes restent")
verifier({"temperature", "qualification", "entry_door"} <= set(cols), "les colonnes v3 sont ajoutées à l'ancienne table")
db._completer_colonnes(eng)
verifier(True, "la relancer ne fait rien de plus (pas d'erreur)")

socle.fin()
