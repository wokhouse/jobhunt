"""Work at a Startup (YC) — public company listings.

Listing search: https://www.workatastartup.com/jobs/search?q=<term> returns
JSON with companyName/companySlug and a title per open role. Discovery source
only: the workatastartup.com company page is kept as evidence and the resolver
maps each company to its own first-party ATS board.

Anonymous browsing is capped at 30 roles per query (``page`` is ignored), so
pagination stops as soon as a page adds no new company.
"""
import time

from ..http import get
from ..registry import register_source
from .base import Lead, Source

API = "https://www.workatastartup.com/jobs/search"
COMPANY_URL = "https://www.workatastartup.com/companies/{}"

SLEEP = 1.0          # polite spacing between pages
MAX_PAGES = 5


def parse_jobs(data) -> list[dict]:
    """Search JSON -> [{'company', 'display', 'title'}] for entries with a name."""
    out: list[dict] = []
    for j in (data or {}).get("jobs") or []:
        name = j.get("companyName") or ""
        slug = (j.get("companySlug") or "").lower()
        if name and slug:
            out.append({"company": slug, "display": name,
                        "title": j.get("title") or ""})
    return out


def pick_title(titles: list[str], query: str) -> str:
    """Best-matching role title: most query tokens, then the shortest."""
    q = [w for w in (query or "").lower().split() if len(w) > 2]

    def score(t: str) -> tuple[int, int]:
        tl = t.lower()
        return (sum(w in tl for w in q), -len(t))

    return max(titles, key=score)


@register_source("waas")
class WaasSource(Source):
    def leads(self) -> list[Lead]:
        titles: dict[str, list[str]] = {}
        displays: dict[str, str] = {}
        for page in range(1, MAX_PAGES + 1):
            jobs = parse_jobs(get(API, params={"q": self.search, "page": page}))
            if not jobs:
                break
            fresh = 0
            for j in jobs:
                if j["company"] not in titles:
                    titles[j["company"]] = []
                    displays[j["company"]] = j["display"]
                    fresh += 1
                titles[j["company"]].append(j["title"])
            if fresh == 0:
                break
            time.sleep(SLEEP)

        out: list[Lead] = []
        for company, ts in titles.items():
            out.append(Lead(
                source="waas",
                company=company,
                company_display=displays[company],
                title=pick_title(ts, self.search),
                url=COMPANY_URL.format(company),
            ))
            if len(out) >= self.max_leads:
                break
        return out
