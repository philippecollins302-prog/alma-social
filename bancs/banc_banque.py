"""Banc : la banque qui travaille seule — créneaux, malchanceux, gagnants, intemporels, conditions."""
import datetime as dt

import socle
from socle import egal, verifier

from sqlalchemy import insert, select, update

from alma_social import (acces, conditions, creneaux, db, file, graines, pipeline, planificateur, recyclage)

print("— Les sept meilleurs créneaux, 80 % sur les meilleurs, 20 % pour apprendre")
for secteur, reseau in (("food", "instagram"), ("btp", "linkedin"), ("btp", "gbp"), ("food", "tiktok")):
    sept = creneaux.sept_meilleurs(secteur, reseau)
    jours = [x["jour"] for x in sept]
    verifier(len(sept) == 7 and max(jours.count(j) for j in set(jours)) <= 2 and max(x["note"] for x in sept) == 100,
             f"{reseau} ({secteur}) : sept créneaux, deux par jour au plus, le meilleur noté 100")
egal([x["jour"] for x in creneaux.sept_meilleurs("btp", "linkedin")].count(5), 0, "LinkedIn : aucun créneau le samedi")
part = sum(creneaux.explorer(f"banc:{i}") for i in range(2000)) / 2000
verifier(0.17 <= part <= 0.23, f"une publication sur cinq explore ({part:.0%})")
egal(creneaux.explorer("x:1:instagram"), creneaux.explorer("x:1:instagram"), "le tirage est stable (rejoué, il ne change pas)")
j = dt.date(2026, 11, 20)
sure = creneaux.choisir_heure("food", "instagram", j, [], [])
essai = creneaux.choisir_heure("food", "instagram", j, [], [], exploration=True)
egal(sure.strftime("%H:%M"), "11:00", "le créneau sûr de SAZÚ un vendredi : 11 h")
verifier(essai.hour not in (10, 11, 18) and creneaux.poids("food", "instagram", 4, essai.hour * 60 + essai.minute)
         >= 0.45 * creneaux.poids("food", "instagram", 4, 660), f"l'exploration va à une heure peu connue mais crédible ({essai:%H:%M})")
profil = {creneaux.cle(4, 17): {"n": 3, "rel": 1.0}}
essai2 = creneaux.choisir_heure("food", "instagram", j, [], [], profil, exploration=True)
verifier(essai2.hour != 17, f"une heure déjà observée trois fois n'est plus de l'exploration ({essai2:%H:%M})")

print("— Le tri du matin : malchanceux, gagnants, intemporels")
socle.figer(2026, 10, 5, 6)
graines.semer()
socle.figer(2026, 11, 2, 7)
ids = []
for i in range(8):
    a = pipeline.recevoir("rega", socle.image("chantier", graine=200 + i), f"c{i}.jpg")
    ids.append(a["id"])
file.vider(500)
with db.moteur().begin() as c:
    c.execute(update(db.assets).where(db.assets.c.id.in_(ids)).values(status="publie", pillar="second_oeuvre",
                                                                      last_used_at=db.maintenant() - dt.timedelta(days=10)))
    c.execute(update(db.assets).where(db.assets.c.id == ids[7]).values(pillar="gros_oeuvre"))
    c.execute(update(db.posts).where(db.posts.c.asset_id.in_(ids)).values(status="annule"))
# Huit publications Facebook réelles il y a dix jours ; médiane ≈ 4 %.
taux = [0.012, 0.09, 0.04, 0.035, 0.045, 0.04, 0.038, 0.042]
notes = [85, 85, 60, 85, 85, 85, 85, 85]
posts = []
with db.moteur().begin() as c:
    for i, (aid, t, n) in enumerate(zip(ids, taux, notes)):
        pid = c.execute(insert(db.posts).values(
            brand_id="rega", asset_id=aid, platform="facebook", text=f"texte {i}", status="publie", simulated=False,
            published_at=db.maintenant() - dt.timedelta(days=10), created_at=db.maintenant() - dt.timedelta(days=10),
            scheduled_at=db.maintenant() - dt.timedelta(days=10), guard_report={"critique": {"note": n}})
        ).inserted_primary_key[0]
        posts.append(pid)
        c.execute(insert(db.metrics).values(post_id=pid, checkpoint="7j", reach=1000, likes=int(t * 1000),
                                            simulated=False, measured_at=db.maintenant() - dt.timedelta(days=3)))
# Un pépin : la même publication mesurée en bac à sable ne compte pas.
with db.moteur().begin() as c:
    c.execute(insert(db.metrics).values(post_id=posts[0], checkpoint="7j", reach=1000, likes=900, simulated=True,
                                        measured_at=db.maintenant()))
verifier(abs(recyclage.perf(posts[0]) - 0.012) < 1e-9, "la performance ne lit que les relevés réels")
tri = recyclage.classer(acces.marque("rega"), "banc")
egal(tri["malchanceux"], [ids[0]], "le malchanceux : bon texte (85), 30 % de la médiane")
egal(tri["gagnants"], [ids[1]], "le gagnant : plus de 1,5 fois la médiane")
a0, a2 = pipeline.asset(ids[0]), pipeline.asset(ids[2])
egal((a0["recyclage"], a0["status"]), ("seconde_chance", "banque"), "il revient en banque, marqué « seconde chance »")
egal(a2["recyclage"], "", "un texte faible (60) qui a mal marché n'a pas de seconde chance : le contenu était en cause")
egal(tri["evergreen"], 1, "la photo du pilier gros œuvre entre au fichier des intemporels")
egal(recyclage.classer(acces.marque("rega"), "banc")["malchanceux"], [], "le tri est idempotent")
egal(pipeline.fenetre_doublon(a0), dt.timedelta(days=21), "une seconde chance revient au bout de 21 jours (pas 90)")
egal(pipeline.fenetre_doublon(pipeline.asset(ids[7])), dt.timedelta(days=45), "un intemporel au bout de 45 jours")
egal(pipeline.fenetre_doublon(pipeline.asset(ids[3])), dt.timedelta(days=90), "les autres : 90 jours")
verifier("facebook" in pipeline.doublons(a0, ["facebook"]), "à J+10 elle est encore bloquée sur Facebook")

print("— La seconde chance : texte neuf, autre cadrage, un des meilleurs créneaux")
socle.figer(2026, 11, 16, 6)
for m in acces.marques():
    planificateur.demarrer(m)
with db.moteur().begin() as c:
    c.execute(update(db.assets).where(db.assets.c.id.in_(ids[1:])).values(status="retire"))
r = planificateur.remplir(acces.marque("rega"), "banc")
file.vider(500)
with db.moteur().connect() as c:
    nouveaux = db.lignes(c.execute(select(db.posts).where(db.posts.c.asset_id == ids[0],
                                                          db.posts.c.status.in_(("programme", "a_valider")))))
verifier(nouveaux, f"la seconde chance est reprogrammée ({len(nouveaux)} publication(s))")
verifier(all(p["guard_report"]["creneau"] in ("meilleur", "impose") for p in nouveaux),
         "jamais en exploration : c'est l'heure qui avait échoué")
verifier(all(any("cadrage resserré" in t for t in p["guard_report"]["traitements"]) for p in nouveaux),
         "un autre cadrage que la première fois")
verifier(all(p["text"] != "texte 0" for p in nouveaux), "un texte neuf")
egal(pipeline.asset(ids[0])["recyclage"], "seconde_chance_faite", "une seule seconde chance")

print("— Les intemporels ressortent quand le stock frais manque")
egal(recyclage.evergreen_disponibles(acces.marque("rega")), [], "pas avant 45 jours")
socle.figer(2026, 12, 20, 6)
dispo = recyclage.evergreen_disponibles(acces.marque("rega"))
with db.moteur().begin() as c:
    c.execute(update(db.assets).where(db.assets.c.id == ids[7]).values(status="publie"))
dispo = recyclage.evergreen_disponibles(acces.marque("rega"))
egal([a["id"] for a in dispo], [ids[7]], "au-delà de 45 jours, il est disponible")
s = {"id": 0, "platforms": ["facebook"], "pillar": "gros_oeuvre", "source": "plan", "brand_id": "rega"}
choisi = planificateur.choisir_photo(acces.marque("rega"), s, set())
egal((choisi or {}).get("id"), ids[7], "la banque vide, c'est lui qui remplit le créneau")
recyclage.evergreen_sorti(choisi["_evergreen"])
egal(recyclage.evergreen_disponibles(acces.marque("rega")), [], "et il repart pour 45 jours")

print("— La publication conditionnelle")
socle.figer(2026, 12, 21, 8)
with db.moteur().begin() as c:
    p1 = c.execute(insert(db.posts).values(brand_id="rega", asset_id=ids[3], platform="linkedin", text="Partie 1",
                                           status="simule", simulated=True, published_at=db.maintenant(),
                                           created_at=db.maintenant())).inserted_primary_key[0]
    p2 = c.execute(insert(db.posts).values(brand_id="rega", asset_id=ids[4], platform="linkedin", text="Partie 2",
                                           status="programme", scheduled_at=db.maintenant() + dt.timedelta(days=1),
                                           rendition_id=None, created_at=db.maintenant())).inserted_primary_key[0]
try:
    conditions.poser(p2, p1)
    verifier(False, "une condition sans seuil est refusée")
except ValueError:
    verifier(True, "une condition sans seuil est refusée")
conditions.poser(p2, p1, engagement_min=0.05, par="banc")
egal(conditions.verifier(pipeline.post(p2)), "attendre", "la partie 1 n'est pas mesurée : la partie 2 attend")
with db.moteur().begin() as c:
    c.execute(insert(db.metrics).values(post_id=p1, checkpoint="24h", reach=1000, likes=20, simulated=True,
                                        measured_at=db.maintenant()))
raison = conditions.verifier(pipeline.post(p2))
verifier("sous le seuil" in raison, f"la partie 1 a fait 2 % : la partie 2 ne part pas ({raison})")
p3 = None
with db.moteur().begin() as c:
    p3 = c.execute(insert(db.posts).values(brand_id="rega", asset_id=ids[5], platform="linkedin", text="Partie 2 bis",
                                           status="programme", created_at=db.maintenant())).inserted_primary_key[0]
conditions.poser(p3, p1, engagement_min=0.01, par="banc")
egal(conditions.verifier(pipeline.post(p3)), "", "au-dessus du seuil : elle part")
egal(conditions.verifier(pipeline.post(p2)), raison, "le verdict est gardé : il ne se rejuge pas")
with db.moteur().begin() as c:
    p4 = c.execute(insert(db.posts).values(brand_id="rega", asset_id=ids[6], platform="linkedin", text="Partie 2 ter",
                                           status="programme", created_at=db.maintenant())).inserted_primary_key[0]
conditions.poser(p4, p1, engagement_min=0.5, par="banc")
pipeline.publier({"post_id": p4})
p4_ = pipeline.post(p4)
egal(p4_["status"], "annule", "au départ, une condition non remplie annule la publication")
verifier("condition non remplie" in p4_["error"], "et la raison est écrite")

print("— Les temps forts de l'année")
from alma_social import temps_forts
egal([t["cle"] for t in temps_forts.a_venir("sazu", dt.date(2027, 2, 1), dt.date(2027, 2, 28))], ["saint-valentin"],
     "SAZÚ : la Saint-Valentin en février")
egal(temps_forts.a_venir("rega", dt.date(2027, 2, 1), dt.date(2027, 2, 28)), [], "REGA : pas de Saint-Valentin")
egal([t["jour"].isoformat() for t in temps_forts.a_venir("vipplus", dt.date(2026, 12, 15), dt.date(2027, 1, 10))],
     ["2026-12-22", "2027-01-05"], "VIP Plus : la fin d'année puis les vœux, à cheval sur deux années")
socle.figer(2026, 12, 10, 6)
poses = temps_forts.poser(acces.marque("lms"), "banc")
with db.moteur().connect() as c:
    sl = db.lignes(c.execute(select(db.slots).where(db.slots.c.id.in_(poses))))
egal(sorted(x["topic"] for x in sl), ["Fin d'année"], "LMS au 10/12 : la fin d'année (les vœux du 5/01 sont au-delà de trois semaines)")
verifier(all(x["brief"] and x["source"] == "temps_fort" for x in sl), "chacun avec sa consigne")
egal(temps_forts.poser(acces.marque("lms"), "banc"), [], "posés une seule fois")
verifier(temps_forts.a_confirmer(), "les salons sans date officielle restent « à confirmer » (aucune date inventée)")

print("— Le brief du coach terrain")
from alma_social import coach
socle.figer(2026, 12, 21, 6)
planificateur.demarrer(acces.marque("sazu"))
b = coach.brief(acces.marque("sazu"))
verifier(b and b["plans"], f"SAZÚ : un brief précis ({(b or {}).get('phrase', '')[:120]}…)")
verifier(any("vidéo de 10 s" in p["quoi"] for p in b["plans"]), "il demande aussi une vidéo de 10 s (Instagram, TikTok)")
verifier(any("fenêtre" in x for x in b["comment"]), "et dit comment : près d'une fenêtre, lumière du jour")
verifier(b["avant"] >= "2026-12-21", "avec une date limite")
br = coach.brief(acces.marque("rega"))
verifier(br is None or all("vidéo" not in p["pilier"] or "geste de pose" in p["quoi"] for p in br["plans"]),
         "REGA : les consignes du chantier, pas celles de la cuisine")

socle.fin()
