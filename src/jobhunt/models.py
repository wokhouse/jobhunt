from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Job:
    """Normalized job record shared by every fetcher."""
    source: str
    company: str
    id: str
    title: str
    url: str
    location: str = ""
    updated: str = ""
    content: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if not d["extra"]:
            d.pop("extra")
        return d
