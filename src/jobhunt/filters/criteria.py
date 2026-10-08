"""Keyword/criteria filter: the default stage.

Config keys (all optional):
  title_include / title_exclude : regex lists applied to title
  locations / exclude_locations : substrings on location
  require_terms / any_of_terms / exclude_terms : substrings on full text
  max_years_required : reject postings demanding more years
  min_salary : reject postings whose parsed max salary is below this
  max_age_days : reject postings older than this
"""
import re

from ..models import Job
from ..registry import register_filter
from ..util import parse_min_years, parse_salary_range
from .base import Filter

ENGINEER_TITLES = re.compile(
    r"\b(software engineer|full[- ]?stack|fullstack|frontend|front[- ]?end|"
    r"backend|back[- ]?end|product engineer|member of technical staff|"
    r"\bmts\b|\bpmts\b|staff engineer|platform engineer|developer)\b", re.I)
NON_ENGINEER = re.compile(
    r"\b(manager|director|vp|vice president|head of|intern|internship|"
    r"new grad|student|sales|account executive|solutions? engineer|"
    r"customer success|support|marketing|recruit|trainer|analyst|"
    r"consultant|paralegal|program manager|project manager|scrum|"
    r"product owner|designer|scientist|technician)\b", re.I)


def _any(hay: str, needles) -> bool:
    return any(n.lower() in hay.lower() for n in needles)


@register_filter("criteria")
class CriteriaFilter(Filter):
    def filter(self, jobs):
        c = self.config
        kept, verdicts = [], {}
        for j in jobs:
            text = f"{j.title}\n{j.location}\n{j.content}"
            low = text.lower()

            inc = c.get("title_include")
            if inc:
                if not any(re.search(p, j.title, re.I) for p in inc):
                    verdicts[j.id] = "title: no include match"
                    continue
            elif not ENGINEER_TITLES.search(j.title):
                verdicts[j.id] = "title: not an engineering role"
                continue

            exc = c.get("title_exclude")
            if exc and any(re.search(p, j.title, re.I) for p in exc):
                verdicts[j.id] = "title: excluded"
                continue
            elif not exc and NON_ENGINEER.search(j.title):
                verdicts[j.id] = "title: non-engineer role"
                continue

            locs = c.get("locations")
            if locs and not _any(j.location, locs) and "remote" not in low:
                verdicts[j.id] = f"location: {j.location!r} not in list"
                continue
            if c.get("exclude_locations") and _any(j.location, c["exclude_locations"]):
                verdicts[j.id] = "location: excluded"
                continue

            for t in c.get("require_terms") or []:
                if t.lower() not in low:
                    verdicts[j.id] = f"missing required term: {t}"
                    break
            else:
                anyof = c.get("any_of_terms")
                if anyof and not _any(low, anyof):
                    verdicts[j.id] = f"none of terms present: {anyof}"
                    continue
                ex = c.get("exclude_terms")
                if ex and _any(low, ex):
                    verdicts[j.id] = "contains excluded term"
                    continue

                yrs = c.get("max_years_required")
                if yrs is not None:
                    need = parse_min_years(text)
                    if need is not None and need > yrs:
                        verdicts[j.id] = f"requires {need} years > max {yrs} years"
                        continue

                sal = c.get("min_salary")
                if sal is not None:
                    rng = parse_salary_range(text)
                    if rng is not None and rng[1] < sal:
                        verdicts[j.id] = f"salary max {rng[1]} < min {sal}"
                        continue

                age = c.get("max_age_days")
                if age is not None:
                    days = _age_days(j.updated)
                    if days is not None and days > age:
                        verdicts[j.id] = f"posted {days}d ago > max {age}d"
                        continue

                kept.append(j)
        return kept, verdicts


def _age_days(updated: str) -> int | None:
    """Parse ISO date, epoch-ms (Lever), or Workday 'N Days Ago' strings."""
    if not updated:
        return None
    if re.fullmatch(r"\d{12,13}", str(updated)):
        import time as _time
        return max(0, int((_time.time() - int(updated) / 1000) // 86400))
    m = re.search(r"(\d+)\s+days?\s+ago", updated, re.I)
    if m:
        return int(m.group(1))
    if re.search(r"today|now", updated, re.I):
        return 0
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", updated)
    if m:
        from datetime import date
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return (date.today() - d).days
        except ValueError:
            return None
    return None
