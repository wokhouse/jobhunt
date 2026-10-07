from ..http import get
from ..models import Job
from ..registry import register_board
from ..util import strip_tags, MAX_CONTENT
from .base import Board, slug_list

API = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"


def greenhouse(slug: str) -> list[Job]:
    d = get(API.format(slug=slug))
    if not d or "jobs" not in d:
        return []
    out = []
    for j in d["jobs"]:
        out.append(Job(
            source="greenhouse", company=slug, id=f"gh-{slug}-{j['id']}",
            title=j.get("title", ""), url=j.get("absolute_url", ""),
            location=(j.get("location") or {}).get("name", ""),
            updated=j.get("updated_at", ""),
            content=strip_tags(j.get("content") or "")[:MAX_CONTENT],
        ))
    return out


@register_board("greenhouse")
class GreenhouseBoard(Board):
    def fetch(self) -> list[Job]:
        out = []
        for slug in slug_list(self.config):
            out.extend(greenhouse(slug))
        return out
