"""Jobicy — public remote tech job board with a free JSON API.

Endpoint: https://jobicy.com/api/v2/remote-jobs?count=<n>&tag=<tag>
Company name is embedded in the job URL slug. Generic: search any field.
"""
import re
from urllib.parse import urlparse

from ..http import get
from ..registry import register_source
from .base import Lead, Source, slugify

API = "https://jobicy.com/api/v2/remote-jobs"


def _company_from_url(url: str) -> str:
    # .../remote-job/dremio-senior-software-engineer-... -> 'dremio'
    slug = urlparse(url).path.rsplit("/", 1)[-1]
    return slug.split("-")[0]


@register_source("jobicy")
class JobicySource(Source):
    def leads(self) -> list[Lead]:
        out: list[Lead] = []
        page = 1
        while len(out) < self.max_leads:
            d = get(API, params={"count": min(50, self.max_leads),
                                 "tag": self.search, "page": page})
            if not d:
                break
            jobs = d.get("jobs") or []
            if not jobs:
                break
            for j in jobs:
                url = j.get("url", "")
                name = j.get("company", {}).get("name") if isinstance(j.get("company"), dict) else ""
                name = name or _company_from_url(url).title()
                out.append(Lead(
                    source="jobicy",
                    company=slugify(name),
                    company_display=name,
                    title=j.get("title", ""),
                    url=url,
                    location=j.get("location", "") or "Remote",
                    extra={"category": j.get("category", ""),
                           "tech": j.get("tech") or []},
                ))
                if len(out) >= self.max_leads:
                    break
            if int(d.get("total_pages", 1)) <= page:
                break
            page += 1
        return out
