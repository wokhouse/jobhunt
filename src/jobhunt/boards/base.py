from abc import ABC, abstractmethod

from ..models import Job


class Board(ABC):
    """A job source. Subclasses register with @register_board(name).

    config is the raw YAML value under the board key in the profile.
    """
    name: str = ""

    def __init__(self, config):
        self.config = config

    @abstractmethod
    def fetch(self) -> list[Job]:
        ...


def slug_list(config) -> list[str]:
    """Normalize slug-board config: list of strings, list of {slug: ...},
    or {slugs: [...]}."""
    if isinstance(config, dict):
        config = config.get("slugs") or []
    if isinstance(config, str):
        config = [config]
    out = []
    for c in config or []:
        if isinstance(c, str):
            out.append(c)
        elif isinstance(c, dict) and c.get("slug"):
            out.append(c["slug"])
    return out
