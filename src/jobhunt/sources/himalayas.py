"""Himalayas — public remote job board with a free JSON API.

Endpoint: https://himalayas.app/jobs/api?search=<term>&limit=<n>
Returns companySlug directly. Generic: search any field.
"""
from ..http import get
from ..registry import register_source
from .base import Lead, Source, slugify

API = "https://himalayas.app/jobs/api"


@register_source("himalayas")
class HimalayasSource(Source):
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
                name = j.get("companyName") or ""
                if not name:
                    continue
                out.append(Lead(
                    source="himalayas",
                    company=(j.get("companySlug") or "").lower() or slugify(name),
                    company_display=name,
                    title=j.get("title", ""),
                    url=j.get("applicationLink") or j.get("guid", ""),
                    location=j.get("location", "") or "Remote",
                    extra={"salary": f"{j.get('minSalary', '')}-{j.get('maxSalary', '')}",
                           "seniority": j.get("seniority", "")},
                ))
                if len(out) >= self.max_leads:
                    break
            if int(d.get("totalPages", 1)) <= page:
                break
            page += 1
        return out
