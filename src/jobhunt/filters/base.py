from abc import ABC, abstractmethod

from ..models import Job


class Filter(ABC):
    """A stage in the match pipeline. Subclasses register with
    @register_filter(name).

    filter() returns (kept_jobs, verdicts) where verdicts maps job.id to a
    reason string for jobs it REJECTED. Kept jobs pass to the next stage.
    """
    name: str = ""

    def __init__(self, config: dict, profile=None):
        self.config = config or {}
        self.profile = profile

    @abstractmethod
    def filter(self, jobs: list[Job]) -> tuple[list[Job], dict[str, str]]:
        ...
