from ..http import get
from ..models import Job
from ..registry import register_board
from ..util import MAX_CONTENT
from .base import Board, slug_list

API = "https://api.lever.co/v0/postings/{slug}?mode=json"


def lever(slug: str) -> list[Job]:
    d = get(API.format(slug=slug))
    if not isinstance(d, list):
        return []
    out = []
    for j in d:
        parts = [j.get("descriptionPlain") or ""]
        for lst in (j.get("lists") or []):
            parts.append("## " + (lst.get("text") or ""))
            for c in (lst.get("content") or []):
                parts.append(str(c.get("content", "")) if isinstance(c, dict) else str(c))
        created = j.get("createdAt")
        out.append(Job(
            source="lever", company=slug, id=f"lv-{slug}-{j['id']}",
            title=j.get("text", ""), url=j.get("hostedUrl", ""),
            location=(j.get("categories") or {}).get("location", ""),
            updated=str(created) if created else "",
            content="\n".join(parts)[:MAX_CONTENT],
        ))
    return out


@register_board("lever")
class LeverBoard(Board):
    def fetch(self) -> list[Job]:
        out = []
        for slug in slug_list(self.config):
            out.extend(lever(slug))
        return out
