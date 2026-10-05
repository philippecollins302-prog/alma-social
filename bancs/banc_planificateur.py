"""Banc : graines du Drive, calendrier du mois, rendez-vous, campagne SAZÚ, cycle du 25 et du 1er."""
import datetime as dt

import socle
from socle import egal, verifier

from alma_social import acces, alertes, db, graines, journal, planificateur

print("— Graines")
socle.figer(2026, 10, 4, 16)
r = graines.semer()
egal(sorted(r["marques"]), ["alma", "lms", "lms-paca", "rega", "sazu", "vipplus"], "six marques semées")
egal(r["campagnes"] != [], True, "la campagne d'ouverture de SAZÚ est créée")
egal(r["plateformes"], 6, "les six plateformes de marque sont semées")
egal(graines.semer(), {"contraintes": 0, "marques": [], "utilisateurs": [], "campagnes": [], "plateformes": 0},
     "semer deux fois ne crée rien de plus")
sazu = acces.marque("sazu")
egal(sazu["active_platforms"], ["instagram", "facebook", "tiktok", "gbp"],
     "SAZÚ : ni Threads, ni Pinterest, ni X (exclus par ses propres documents)")
egal(sazu["kit"]["watermark"], "", "SAZÚ : aucun filigrane")
egal(sazu["kit"]["logo_texte"], False, "SAZÚ : le nom n'est jamais retapé à la place du logo")
verifier(all(p["prix_verifie_le"] is None for p in sazu["products"]),
         "aucun prix SAZÚ n'est réputé vérifié tant que la carte n'est pas en ligne")
verifier(not acces.logo_permis(sazu, dt.datetime(2026, 11, 13, 17, 59, tzinfo=acces.creneaux.PARIS)),
         "logo SAZÚ caché le 13/11 à 17 h 59")
verifier(acces.logo_permis(sazu, dt.datetime(2026, 11, 13, 18, 0, tzinfo=acces.creneaux.PARIS)),
         "logo SAZÚ révélé le 13/11 à 18 h")
with db.moteur().begin() as c:
    from sqlalchemy import select
    gens = db.lignes(c.execute(select(db.users)))
    cpts = db.lignes(c.execute(select(db.accounts)))
egal(sorted(u["role"] for u in gens), ["pdg", "responsable"], "en développement : un PDG et une responsable d'essai")
verifier(all(c["status"] == "a_relier" for c in cpts), "tous les comptes naissent « à relier »")
egal(next(c["handle"] for c in cpts if c["brand_id"] == "sazu" and c["platform"] == "instagram"),
     "@sazu.montpellier", "le compte Instagram de SAZÚ est nommé")

print("— La campagne d'ouverture")
s = planificateur.creneaux_de("sazu", dt.date(2026, 10, 1), dt.date(2026, 11, 30))
egal(len(s), 12, "douze étapes, du 30/10 au 29/11")
egal(s[0]["day"], dt.date(2026, 10, 30), "J-28 le 30/10")
egal((s[0]["time"], s[0]["topic"]), ("18:00", "Boutonnet, ça va chauffer."), "J-28 : 18 h, l'accroche demandée")
jj = next(x for x in s if x["campaign_step"] == "Jour J")
egal((jj["day"], jj["time"]), (dt.date(2026, 11, 27), "11:30"), "Jour J : vendredi 27/11 à 11 h 30")
verifier("gbp" in jj["platforms"] and "gbp" not in s[0]["platforms"],
         "Google Business n'arrive qu'à l'ouverture (fiche demandée à J-7)")

print("— Le calendrier ordinaire")
egal(planificateur.generer_mois(sazu, 2026, 11), [], "SAZÚ : aucun créneau ordinaire avant l'ouverture")
dec = planificateur.generer_mois(sazu, 2026, 12)
egal(sum(1 for p in dec if p["source"] == "serie" and p["jour"].weekday() == 1), 5,
     "« Chaud devant » chaque mardi de décembre")
verifier(all(p["jour"].weekday() != 0 for p in dec), "SAZÚ : jamais le lundi (fermé)")
egal(min(p["jour"] for p in dec if p["sujet"] == "Viernes suave o fuego"), dt.date(2026, 12, 4),
     "« Viernes suave o fuego » commence le 4/12")
for mid in ("alma", "rega", "lms-paca", "vipplus", "lms"):
    m = acces.marque(mid)
    p = planificateur.generer_mois(m, 2026, 12)
    verifier(all(x["jour"].weekday() < 5 for x in p), f"{m['name']} : aucun week-end proposé")
    semaines = {}
    for x in p:
        semaines.setdefault(x["jour"].isocalendar()[1], []).append(x)
    pleines = [len(v) for k, v in semaines.items() if k not in (49, 53)]
    egal(set(pleines), {planificateur.cible_hebdo(m)}, f"{m['name']} : la cadence visée chaque semaine pleine")
    piliers = [x["pilier"] for x in p]
    verifier(all(a != b for a, b in zip(piliers, piliers[1:])), f"{m['name']} : jamais deux fois le même pilier de suite")

print("— Le cycle du mois (proposé le 25, appliqué le 1er même sans validation)")
rega = acces.marque("rega")
socle.figer(2026, 10, 25, 5)
planificateur.tour_du_matin()
plan = planificateur.plan_du_mois("rega", 2026, 11)
egal(plan and plan["status"], "propose", "le 25 : le calendrier de novembre est proposé")
socle.figer(2026, 10, 31, 5)
alertes.ENVOYES.clear()
planificateur.tour_du_matin()
verifier(any("s'applique demain" in a["sujet"] for a in alertes.ENVOYES), "la veille du 1er : un rappel, une fois")
n = len(alertes.ENVOYES)
planificateur.tour_du_matin()
egal(sum("s'applique demain" in a["sujet"] for a in alertes.ENVOYES[n:]), 0, "pas de second rappel")
socle.figer(2026, 11, 1, 5)
planificateur.tour_du_matin()
plan = planificateur.plan_du_mois("rega", 2026, 11)
egal(plan["status"], "applique", "le 1er : appliqué sans validation")
verifier(len(planificateur.creneaux_de("rega", dt.date(2026, 11, 2), dt.date(2026, 11, 30))) >= 16,
         "les créneaux de novembre existent")

print("— L'alerte de stock dit exactement quoi")
phrase = planificateur.alerte_stock(rega)
verifier(phrase.startswith("Il manque ") and "REGA Construction" in phrase and "avant" in phrase,
         f"phrase précise : « {phrase[:110]}… »")
planificateur.alerte_stock(rega)
with db.moteur().begin() as c:
    n_stock = c.execute(select(db.alerts.c.id).where(db.alerts.c.dedup_key == "stock:rega:2026-10-26")).all()
egal(len(n_stock), 1, "une seule alerte de stock par semaine, quel que soit le nombre de tours")
egal(planificateur.piliers_en_retard(rega), [], "une marque qui n'a encore rien publié n'a « oublié » aucun pilier")

print("— Journal")
egal(journal.verifier_chaine()["intact"], True, "la chaîne du journal est intacte")
socle.fin()
