"""Criteria engine: score jobs against a profile and report why."""
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .models import Job
from .profile import Criteria
from .util import parse_salary_range, parse_min_years

_TITLE_WORDS = re.compile(r"[^a-z0-9+#.]+")


def _norm(s: str) -> str:
    return (s or "").lower()


def _tokens(s: str) -> set[str]:
    return {t for t in _TITLE_WORDS.split(_norm(s)) if t}


def title_similarity(a: str, b: str) -> float:
    """Token overlap ratio in [0,1]. Used for cross-board dedupe."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))


@dataclass
class Verdict:
    job: Job
    passed: bool
    reasons: list[str] = field(default_factory=list)
    salary: tuple[int, int] | None = None
    min_years: int | None = None


def _age_days(job: Job) -> int | None:
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(job.updated[:26], fmt)
            return (datetime.now(timezone.utc) - dt.replace(tzinfo=timezone.utc)).days
        except ValueError:
            continue
    return None


def evaluate(job: Job, c: Criteria) -> Verdict:
    v = Verdict(job=job, passed=True)
    title, loc, body = _norm(job.title), _norm(job.location), _norm(job.content)
    hay = f"{title}\n{body}"

    if c.title_include and not any(t in title for t in map(_norm, c.title_include)):
        v.passed = False
        v.reasons.append("title: no include-term match")
    if any(t in title for t in map(_norm, c.title_exclude)):
        bad = next(t for t in c.title_exclude if t in title)
        v.passed = False
        v.reasons.append(f"title: excluded term {bad!r}")

    if c.locations and not any(t in loc or t in body[:2000] for t in map(_norm, c.locations)):
        v.passed = False
        v.reasons.append("location: no match")
    if any(t in loc for t in map(_norm, c.exclude_locations)):
        v.passed = False
        v.reasons.append("location: excluded")

    v.min_years = parse_min_years(body)
    if c.max_years_required is not None and v.min_years is not None and v.min_years > c.max_years_required:
        v.passed = False
        v.reasons.append(f"experience: requires {v.min_years}y > cap {c.max_years_required}y")

    if c.min_salary is not None:
        v.salary = parse_salary_range(body)
        if v.salary is None:
            v.reasons.append("salary: unposted (verify)")
        elif v.salary[1] < c.min_salary:
            v.passed = False
            v.reasons.append(f"salary: max ${v.salary[1]:,} < ${c.min_salary:,}")

    for t in map(_norm, c.require_terms):
        if t not in hay:
            v.passed = False
            v.reasons.append(f"term missing: {t!r}")
    if c.any_of_terms and not any(t in hay for t in map(_norm, c.any_of_terms)):
        v.passed = False
        v.reasons.append("none of any_of_terms present")
    for t in map(_norm, c.exclude_terms):
        if t in hay:
            v.passed = False
            v.reasons.append(f"term excluded: {t!r}")

    if c.max_age_days is not None:
        age = _age_days(job)
        if age is not None and age > c.max_age_days:
            v.passed = False
            v.reasons.append(f"stale: {age}d old > {c.max_age_days}d")

    return v


def dedupe(jobs: list[Job]) -> list[Job]:
    """Drop exact-URL duplicates and same-company near-identical titles."""
    seen_url: set[str] = set()
    kept: list[Job] = []
    by_company: dict[str, list[Job]] = {}
    for j in jobs:
        if j.url in seen_url:
            continue
        seen_url.add(j.url)
        dup = False
        for other in by_company.get(j.company, []):
            if title_similarity(j.title, other.title) >= 0.8:
                dup = True
                break
        if not dup:
            kept.append(j)
            by_company.setdefault(j.company, []).append(j)
    return kept
