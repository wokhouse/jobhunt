import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from ..http import get
from ..models import Job
from ..registry import register_board
from ..util import strip_tags, MAX_CONTENT
from .base import Board, slug_list

API = "https://api.rippling.com/platform/api/ats/v1/board/{slug}/jobs"
DETAIL = "https://api.rippling.com/platform/api/ats/v1/board/{slug}/jobs/{uid}"


def _detail(slug: str, uid: str) -> str:
    d = get(DETAIL.format(slug=slug, uid=uid), timeout=20)
    if not isinstance(d, dict):
        return ""
    desc = d.get("description")
    if not isinstance(desc, dict):
        return ""
    parts = [strip_tags(desc.get(k) or "") for k in ("company", "role")]
    return "\n".join(p for p in parts if p)


def rippling(slug: str) -> list[Job]:
    q = urllib.parse.quote(slug)
    d = get(API.format(slug=q))
    jobs = d if isinstance(d, list) else ((d or {}).get("jobs") or (d or {}).get("results") or [])
    uuids = [j.get("uuid") for j in jobs if j.get("uuid")]
    with ThreadPoolExecutor(max_workers=10) as ex:
        descs = dict(zip(uuids, ex.map(lambda u: _detail(q, u), uuids)))
    out = []
    for j in jobs:
        uid = j.get("uuid")
        if not uid:
            continue
        wl = j.get("workLocation") or {}
        loc = (wl.get("label") or wl.get("id") or "") if isinstance(wl, dict) else str(wl)
        out.append(Job(
            source="rippling", company=slug, id=f"rp-{slug}-{uid}",
            title=j.get("name") or j.get("title") or "",
            url=j.get("url") or f"https://ats.rippling.com/{slug}/jobs/{uid}",
            location=loc,
            updated=j.get("createdOn") or j.get("publishedOn") or "",
            content=descs.get(uid, "")[:MAX_CONTENT],
        ))
    return out


@register_board("rippling")
class RipplingBoard(Board):
    def fetch(self) -> list[Job]:
        out = []
        for slug in slug_list(self.config):
            out.extend(rippling(slug))
        return out
