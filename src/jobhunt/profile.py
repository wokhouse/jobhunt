"""Profile schema and loader.

A profile is a YAML file that defines the search boards and the filter
pipeline. Personal criteria belong in YOUR profile, not in the library.

Example:

    boards:
      greenhouse: [stripe, elastic]
      ashby: [openai, hex]
      lever: [dexterity]
      workday:
        - tenant: salesforce
          site: External_Career_Site
          host: wd12
          terms: ["full stack", "frontend"]

    filters:                      # ordered stages; default: [criteria]
      - name: criteria
        title_include: ["engineer", "developer"]
        title_exclude: ["manager", "director", "vp", "intern", "sales"]
        locations: ["san francisco", "remote"]
        max_years_required: 6
        min_salary: 200000
      - name: llm_judge           # optional second stage
        base_url: http://localhost:8080/v1
        model: my-model
        min_score: 7

    judge_rubric: |               # free text sent to the LLM judge
      Product engineer ... SF Bay Area or remote ...
"""
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Profile:
    name: str = "default"
    boards: dict = field(default_factory=dict)   # {board_name: config}
    discover: dict = field(default_factory=dict)  # {source_name: config}
    filters: list[dict] = field(default_factory=list)
    criteria_raw: dict = field(default_factory=dict)  # legacy 'criteria:' block
    judge_rubric: str = ""

    @classmethod
    def load(cls, path: str | Path) -> "Profile":
        raw = yaml.safe_load(Path(path).read_text()) or {}
        filters = raw.get("filters") or []
        criteria_raw = raw.get("criteria") or {}
        if not filters and criteria_raw:
            filters = [{"name": "criteria", **criteria_raw}]
        return cls(
            name=raw.get("name", Path(path).stem),
            boards=raw.get("boards") or {},
            discover=raw.get("discover") or {},
            filters=filters,
            criteria_raw=criteria_raw,
            judge_rubric=raw.get("judge_rubric") or "",
        )
