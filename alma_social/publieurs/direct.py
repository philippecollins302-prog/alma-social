"""Les API officielles, réseau par réseau — la phase 2, derrière la même interface.

Aucune n'est encore branchée : les accès se demandent (voir API-STATUS.md) et
leurs délais ne dépendent pas de nous. Tant qu'un réseau est en mode `direct`
sans implémentation, il échoue PROPREMENT (NonBranche) : le journal le dit, les
autres réseaux publient normalement, et le réseau ne compte pas comme « en
panne » — c'est un réglage, pas un refus.

Pour brancher un réseau : écrire sa classe ici (publish, metrics, comments,
reply, delete), l'ajouter à DIRECTS, puis passer le compte en mode `direct`
depuis l'écran Réglages. Rien d'autre à toucher.
"""
from __future__ import annotations

from .base import NonBranche, Publisher


class DirectNonBranche(Publisher):
    mode = "direct"

    def _non(self):
        raise NonBranche(f"API officielle {self.name} pas encore branchée "
                         f"(demande d'accès en cours, voir API-STATUS.md)")

    def publish(self, post):
        self._non()

    def metrics(self, external_id):
        self._non()

    def comments(self, external_id):
        self._non()

    def reply(self, target_id, text):
        self._non()

    def delete(self, external_id):
        self._non()


DIRECTS = {}        # "instagram": InstagramDirect, … — au fil des validations obtenues
