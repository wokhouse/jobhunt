from ..http import get
from ..models import Job
from ..registry import register_board
from ..util import strip_tags, MAX_CONTENT
from .base import Board, slug_list

API_V3 = "https://apply.workable.com/api/v3/accounts/{slug}/jobs?page={page}"
API_V1 = "https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true"


def _loc(j) -> str:
    loc = j.get("location") or {}
    if isinstance(loc, dict):
        loc = ", ".join(x for x in (loc.get("city"), loc.get("region"), loc.get("country")) if x)
    return loc or ", ".join(x for x in (j.get("city"), j.get("state"), j.get("country")) if x)


def workable(slug: str) -> list[Job]:
    out, seen = [], set()
    # Primary: v3 paginated accounts API (not always exposed)
    page = 1
    while page <= 40:
        d = get(API_V3.format(slug=slug, page=page))
        jobs = (d or {}).get("results") or (d or {}).get("jobs") or []
        if not jobs:
            break
        for j in jobs:
            code = j.get("shortcode") or j.get("id")
            if not code or code in seen:
                continue
            seen.add(code)
            out.append(Job(
                source="workable", company=slug, id=f"wk-{slug}-{code}",
                title=j.get("title", ""),
                url=j.get("url") or f"https://apply.workable.com/j/{code}",
                location=_loc(j),
                updated=j.get("published_on") or j.get("created_at") or "",
                content=strip_tags(j.get("description") or "")[:MAX_CONTENT],
            ))
        page += 1
    if out:
        return out
    # Fallback: v1 widget endpoint (all jobs, includes description)
    d = get(API_V1.format(slug=slug))
    for j in (d or {}).get("jobs") or []:
        code = j.get("shortcode") or j.get("id")
        if not code or code in seen:
            continue
        seen.add(code)
        out.append(Job(
            source="workable", company=slug, id=f"wk-{slug}-{code}",
            title=j.get("title", ""),
            url=j.get("url") or f"https://apply.workable.com/j/{code}",
            location=_loc(j),
            updated=j.get("published_on") or j.get("created_at") or "",
            content=strip_tags(j.get("description") or "")[:MAX_CONTENT],
        ))
    return out


@register_board("workable")
class WorkableBoard(Board):
    def fetch(self) -> list[Job]:
        out = []
        for slug in slug_list(self.config):
            out.extend(workable(slug))
        return out
