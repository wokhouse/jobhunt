from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import re


@dataclass
class Lead:
    """A (company, role) pair discovered on an aggregator board.

    The aggregator URL is kept only as evidence; the pipeline resolves the
    company's first-party ATS board and pulls the job from there.
    """
    source: str
    company: str            # slugified company key, e.g. 'dremio'
    company_display: str    # as shown on the board
    title: str
    url: str                # aggregator listing URL (evidence only)
    location: str = ""
    extra: dict = field(default_factory=dict)


def slugify(name: str) -> str:
    """Company display name -> lowercase key: 'Hinge Health' -> 'hinge-health'."""
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower())
    return s.strip("-")


class Source(ABC):
    """A public job-board scraper that yields company leads.

    config is the raw YAML value under the source key in the profile's
    'discover:' block (usually a dict with 'search' and 'max_leads').
    """
    name: str = ""

    def __init__(self, config):
        self.config = config if isinstance(config, dict) else {}

    @property
    def search(self) -> str:
        return self.config.get("search", "software engineer")

    @property
    def max_leads(self) -> int:
        return int(self.config.get("max_leads", 100))

    @abstractmethod
    def leads(self) -> list[Lead]:
        ...
