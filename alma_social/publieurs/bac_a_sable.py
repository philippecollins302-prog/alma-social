"""Le bac à sable : tout le pipeline tourne, RIEN ne sort.

La publication n'est écrite que dans le journal, avec un lien vers son aperçu
dans l'application. Les chiffres renvoyés sont simulés — et marqués comme tels :
ils ne nourrissent jamais l'apprentissage des créneaux, et le tableau de bord
les affiche à part.
"""
from __future__ import annotations

import hashlib

from .. import config
from .base import Mesures, Publisher, Resultat


class BacASable(Publisher):
    mode = "bac_a_sable"

    def publish(self, post):
        return Resultat(external_id=f"sim-{self.name}-{post.post_id}",
                        permalink=f"{config.url_publique()}/apercu/{post.post_id}",
                        raw={"simule": True})

    def metrics(self, external_id):
        h = int(hashlib.sha256(external_id.encode()).hexdigest(), 16)
        vues = 200 + h % 1800
        return Mesures(views=vues, reach=int(vues * 0.8), likes=h % 90, comments=h % 7,
                       shares=h % 5, saves=h % 11, clicks=h % 13, followers_gained=h % 4,
                       raw={"simule": True}, simulated=True)

    def comments(self, external_id):
        return []

    def reply(self, target_id, text):
        return None

    def delete(self, external_id):
        return True

    def reviews(self):
        return []

    def reply_review(self, review_id, text):
        return None
