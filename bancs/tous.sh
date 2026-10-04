#!/bin/sh
# ALMA SOCIAL — tous les bancs, un seul verdict, et il bloque.
#
#     sh bancs/tous.sh
#
# Chaque banc_*.py est pris au lampadaire : aucune liste à tenir. On s'arrête
# au premier rouge — une boucle qui affiche ❌ sans interrompre la chaîne ne
# protège personne. Chaque banc part d'une base
# neuve dans un dossier temporaire : l'ordre ne compte pas.
set -u
cd "$(dirname "$0")/.." || exit 1
PY="${PYTHON:-.venv/bin/python}"
[ -x "$PY" ] || PY=python3
n=0
for b in bancs/banc_*.py; do
  printf '\n━━ %s\n' "$b"
  if ! PYTHONPATH=. "$PY" "$b"; then
    printf "\n❌ ROUGE : %s — rien ne part tant qu'il ne repasse pas au vert.\n" "$b"
    exit 1
  fi
  n=$((n + 1))
done
printf '\n✅ %s bancs verts.\n' "$n"
