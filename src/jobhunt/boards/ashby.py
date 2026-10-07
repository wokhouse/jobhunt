import urllib.parse

from ..http import get
from ..models import Job
from ..registry import register_board
from ..util import MAX_CONTENT
from .base import Board, slug_list

API = "https://api.ashbyhq.com/posting-api/job-board/{slug}"


def ashby(slug: str) -> list[Job]:
    d = get(API.format(slug=urllib.parse.quote(slug)))
    if not d or "jobs" not in d:
        return []
    out = []
    for j in d["jobs"]:
        if not j.get("isListed", True):
            continue
        loc = j.get("location") or ""
        if isinstance(loc, dict):
            loc = loc.get("name") or ""
        secondary = ", ".join(
            s.get("location", "") if isinstance(s, dict) else str(s)
            for s in (j.get("secondaryLocations") or []))
        out.append(Job(
            source="ashby", company=slug, id=f"ash-{slug}-{j['id']}",
            title=j.get("title", ""),
            url=j.get("jobUrl") or j.get("applyUrl") or f"https://jobs.ashbyhq.com/{slug}",
            location=str(loc) + (f" (+ {secondary})" if secondary else ""),
            updated=j.get("publishedAt", ""),
            content=(j.get("descriptionPlain") or "")[:MAX_CONTENT],
            extra={"workplaceType": j.get("workplaceType", "")},
        ))
    return out


@register_board("ashby")
class AshbyBoard(Board):
    def fetch(self) -> list[Job]:
        out = []
        for slug in slug_list(self.config):
            out.extend(ashby(slug))
        return out
