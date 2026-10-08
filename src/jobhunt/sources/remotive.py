"""Remotive — public remote tech job board with a free JSON API.

Endpoint: https://remotive.com/api/remote-jobs?search=<term>&limit=<n>
Gives company_name + company_website directly, which makes slug
resolution easy. Generic: search any field, not just tech.
"""
from ..http import get
from ..registry import register_source
from .base import Lead, Source, slugify

API = "https://remotive.com/api/remote-jobs"


@register_source("remotive")
class RemotiveSource(Source):
    def leads(self) -> list[Lead]:
        out: list[Lead] = []
        page = 1
        while len(out) < self.max_leads:
            d = get(API, params={"search": self.search, "limit": 50, "page": page})
            if not d:
                break
            jobs = d.get("jobs") or []
            if not jobs:
                break
            for j in jobs:
                name = j.get("company_name") or ""
                if not name:
                    continue
                out.append(Lead(
                    source="remotive",
                    company=slugify(name),
                    company_display=name,
                    title=j.get("title", ""),
                    url=j.get("application_url") or j.get("url", ""),
                    location=j.get("candidate_required_location", "") or "Remote",
                    extra={"website": j.get("company_website", ""),
                           "category": j.get("category", ""),
                           "tags": j.get("tags") or []},
                ))
                if len(out) >= self.max_leads:
                    break
            if int(d.get("pagination", {}).get("total_pages", 1)) <= page:
                break
            page += 1
        return out
