"""Cross-board dedupe and title similarity."""
import re

from .models import Job

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
