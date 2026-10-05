"""L'interface Publisher — la règle d'architecture la plus importante du projet.

Tout le reste de l'application ne parle QU'À cette interface. Derrière elle :
le bac à sable (rien ne sort), l'agrégateur (tous les réseaux, par défaut), et
plus tard une API officielle par réseau. On passe de l'un à l'autre réseau par
réseau, par un réglage en base (`accounts.mode`), sans toucher au reste.
C'est la porte de sortie : aucun fournisseur n'est indispensable.

Trois sortes d'échec, parce qu'elles n'appellent pas la même réponse :
- `RefusReseau` : le réseau (ou l'agrégateur) a répondu NON. Ça compte pour la
  détection de panne (trois refus d'affilée → réseau en pause, alerte).
- `PanneTransitoire` : délai dépassé, 5xx, coupure. On réessaie, ça ne compte pas.
- `NonBranche` : ce réseau n'a pas (encore) de voie de publication configurée.
  Le réseau concerné échoue proprement, le reste continue.
"""
from __future__ import annotations

import dataclasses
from typing import Optional


class ErreurPublication(Exception):
    pass


class RefusReseau(ErreurPublication):
    pass


class PanneTransitoire(ErreurPublication):
    pass


class NonBranche(ErreurPublication):
    pass


@dataclasses.dataclass
class Contraintes:
    platform: str
    formats: list
    caption_max: int
    hashtags_max: Optional[int] = None
    ratio_min: Optional[float] = None
    ratio_max: Optional[float] = None
    max_weight_mb: Optional[float] = None
    video_max_mb: Optional[float] = None
    duration_min: Optional[float] = None
    duration_max: Optional[float] = None
    posts_per_day: Optional[int] = None
    links_clickable: bool = False
    carousel_max: Optional[int] = None
    preferred_format: str = "4:5"
    verified_on: str = ""
    confirmed: bool = False


@dataclasses.dataclass
class PostPrepare:
    """Tout ce qu'il faut pour publier — et rien que l'application doive deviner ensuite."""
    post_id: int
    brand_id: str
    platform: str
    text: str
    title: str
    media_url: str                 # adresse publique de l'image ou de la vidéo
    media_path: str                # chemin local du même fichier
    is_video: bool
    link_url: str = ""             # lien tracé (bouton GBP, destination Pinterest)
    profile: str = ""              # profil chez l'agrégateur (déchiffré au dernier moment)
    options: dict = dataclasses.field(default_factory=dict)
    extra_paths: list = dataclasses.field(default_factory=list)   # carrousel : les vues 2…n, dans l'ordre


@dataclasses.dataclass
class Resultat:
    external_id: str
    permalink: str
    raw: dict = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class Mesures:
    views: int = 0
    reach: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    clicks: int = 0
    followers_gained: int = 0
    raw: dict = dataclasses.field(default_factory=dict)
    simulated: bool = False


@dataclasses.dataclass
class Commentaire:
    external_id: str
    author: str
    text: str
    kind: str = "commentaire"      # commentaire | message
    author_meta: dict = dataclasses.field(default_factory=dict)
    post_external_id: str = ""


@dataclasses.dataclass
class Avis:
    external_id: str
    rating: int
    text: str
    author: str
    reply: str = ""


class Publisher:
    """Ce que chaque implémentation doit savoir faire. `name` est le réseau."""
    name: str = ""
    mode: str = ""
    constraints: Contraintes

    def __init__(self, platform: str, constraints: Contraintes, profile: str = ""):
        self.name, self.constraints, self.profile = platform, constraints, profile

    def publish(self, post: PostPrepare) -> Resultat:
        raise NotImplementedError

    def metrics(self, external_id: str) -> Mesures:
        raise NotImplementedError

    def comments(self, external_id: str) -> list:
        raise NotImplementedError

    def reply(self, target_id: str, text: str) -> None:
        raise NotImplementedError

    def private_reply(self, comment_id: str, text: str) -> None:
        """Répondre à un commentaire par un MESSAGE PRIVÉ (§ 15.2). Seule l'API
        officielle de Meta le permet (« private replies ») ; tant qu'elle n'est
        pas branchée, l'application répond en public et le dit au journal."""
        raise NonBranche("message privé non disponible par ce branchement")

    def delete(self, external_id: str) -> bool:
        """Retirer une publication. → False si le réseau ne le permet pas par
        API (Instagram, TikTok, Threads) : l'application le dit, elle ne
        prétend pas avoir retiré."""
        raise NotImplementedError

    def reviews(self) -> list:
        return []

    def reply_review(self, review_id: str, text: str) -> None:
        raise NonBranche("réponse aux avis non disponible sur ce réseau")
