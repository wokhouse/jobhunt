"""Profile schema and loader.

A profile is a YAML file that defines the search boards and the criteria
engine. Personal criteria belong in YOUR profile, not in the library.

Example:

    boards:
      greenhouse: [stripe, ramp]
      ashby: [openai, hex]
      workday:
        - tenant: salesforce
          site: External_Career_Site
          host: wd12
          search: "full stack"

    criteria:
      title_include: ["engineer", "developer"]
      title_exclude: ["manager", "director", "vp", "intern", "sales"]
      locations: ["san francisco", "remote"]
      max_years_required: 6
      min_salary: 200000
      require_terms: ["typescript", "react"]
      any_of_terms: ["next.js"]
"""
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Criteria:
    title_include: list[str] = field(default_factory=list)
    title_exclude: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)   # lowercase substrings; empty = any
    exclude_locations: list[str] = field(default_factory=list)
    max_years_required: int | None = None
    min_salary: int | None = None
    require_terms: list[str] = field(default_factory=list)   # all must appear in title+body
    any_of_terms: list[str] = field(default_factory=list)    # at least one must appear
    exclude_terms: list[str] = field(default_factory=list)   # none may appear
    max_age_days: int | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "Criteria":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in (d or {}).items() if k in known})


@dataclass
class Profile:
    name: str = "default"
    boards: dict = field(default_factory=dict)      # {ats: [slug,...]}; 'workday' holds specs
    criteria: Criteria = field(default_factory=Criteria)

    @classmethod
    def load(cls, path: str | Path) -> "Profile":
        raw = yaml.safe_load(Path(path).read_text()) or {}
        boards = raw.get("boards") or {}
        workday_specs = boards.get("workday") or []
        if isinstance(workday_specs, dict):
            workday_specs = [workday_specs]
        plain = {k: v for k, v in boards.items() if k != "workday" and v}
        p = cls(
            name=raw.get("name", Path(path).stem),
            boards=plain,
            criteria=Criteria.from_dict(raw.get("criteria")),
        )
        p.workday_specs = workday_specs  # type: ignore[attr-defined]
        return p
