"""Built In network — city job boards (builtinsf.com, builtinnyc.com, ...).

Built In is a **company-lead discovery source only**. Listing and detail
pages are scraped purely to learn (company, role) pairs; the Built In URL is
kept as evidence and must never surface as a job link. The resolver maps each
company to its own first-party ATS board and jobs are fetched from there.

Pages embed schema.org ld+json; the ItemList node of a listing page gives the
job URLs and the JobPosting node of a detail page gives the company name and
location. Built In rate-limits aggressively (HTTP 429), so requests are
spaced out and retried with exponential backoff.
"""
import html
import json
import re
import time
import urllib.error
import urllib.request
from urllib.parse import quote

from ..registry import register_source
from .base import Lead, Source, slugify

# city key -> Built In host
CITIES = {
    "sf": "builtinsf.com",
    "nyc": "builtinnyc.com",
    "austin": "builtinaustin.com",
    "boston": "builtinboston.com",
    "chicago": "builtinchicago.com",
    "dallas": "builtindallas.com",
    "losangeles": "builtinlosangeles.com",
    "seattle": "builtinseattle.com",
}

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# ld+json script blocks (the type attribute may carry a charset suffix)
LD_JSON = re.compile(
    r'<script[^>]*type="application/ld[^"]*json"[^>]*>(.*?)</script>', re.S)

MAX_PAGES = 4         # listing pages per search term
DETAIL_CAP = 60       # hard cap on detail pages fetched per run
SLEEP = 2.5           # seconds between page fetches


def _fetch(url: str, retries: int = 5, base_delay: float = 3.0) -> str | None:
    """GET with a browser-like UA, exponential backoff on 429, None on failure."""
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.read().decode(errors="replace")
        except urllib.error.HTTPError as e:
            if e.code == 429 and i < retries:
                time.sleep(base_delay * (2 ** i))
                continue
            return None
        except Exception:
            if i < retries:
                time.sleep(base_delay)
                continue
            return None
    return None


def ld_nodes(body: str) -> list:
    """Parse every ld+json block into top-level nodes.

    Tolerates multiple script blocks, bare objects and @graph lists.
    """
    nodes: list = []
    for m in LD_JSON.finditer(body or ""):
        try:
            d = json.loads(html.unescape(m.group(1)))
        except Exception:
            continue
        if isinstance(d, dict) and isinstance(d.get("@graph"), list):
            nodes.extend(d["@graph"])
        elif isinstance(d, list):
            nodes.extend(d)
        else:
            nodes.append(d)
    return nodes


def parse_listing(body: str) -> list[dict]:
    """Listing-page HTML -> [{'title', 'url'}] for '/job/' ItemList entries."""
    out: list[dict] = []
    for node in ld_nodes(body):
        if not isinstance(node, dict) or node.get("@type") != "ItemList":
            continue
        for el in node.get("itemListElement") or []:
            if not isinstance(el, dict):
                continue
            url = el.get("url") or ""
            if "/job/" in url:
                out.append({"title": el.get("name") or "", "url": url})
    return out


def parse_detail(body: str) -> dict | None:
    """Detail-page HTML -> {'company', 'title', 'location'} or None.

    Returns None when no JobPosting node with a hiringOrganization name is
    found (entries with no company name are skipped by the caller).
    """
    for node in ld_nodes(body):
        if not isinstance(node, dict) or node.get("@type") != "JobPosting":
            continue
        org = node.get("hiringOrganization") or {}
        name = (org.get("name") or "") if isinstance(org, dict) else ""
        if not name:
            continue
        loc = node.get("jobLocation") or {}
        if isinstance(loc, list):
            loc = loc[0] if loc else {}
        addr = (loc.get("address") or {}) if isinstance(loc, dict) else {}
        locality = addr.get("addressLocality") or ""
        region = addr.get("addressRegion") or ""
        return {
            "company": name,
            "title": node.get("title") or "",
            "location": f"{locality}, {region}" if locality else "",
        }
    return None


@register_source("builtin")
class BuiltinSource(Source):
    """Built In city board -> company leads (evidence URLs only)."""

    def __init__(self, config):
        super().__init__(config)
        city = (self.config.get("city") or "sf").strip().lower()
        if city not in CITIES:
            raise ValueError(
                f"builtin: unknown city {city!r}; choose from {sorted(CITIES)}")
        self.city = city

    @property
    def host(self) -> str:
        return CITIES[self.city]

    def leads(self) -> list[Lead]:
        cap = min(self.max_leads, DETAIL_CAP)
        base = f"https://www.{self.host}/jobs"

        # phase 1: collect unique listing (evidence) URLs
        urls: list[str] = []
        seen: set[str] = set()
        for page in range(1, MAX_PAGES + 1):
            body = _fetch(f"{base}?search={quote(self.search)}&page={page}")
            if not body:
                break
            items = parse_listing(body)
            if not items:
                break
            new = 0
            for it in items:
                u = it["url"]
                if u and u not in seen:
                    seen.add(u)
                    urls.append(u)
                    new += 1
            if new == 0:
                break
            time.sleep(SLEEP)

        # phase 2: fetch details for up to the cap; yield company leads
        out: list[Lead] = []
        for u in urls[:cap]:
            if len(out) >= self.max_leads:
                break
            body = _fetch(u)
            d = parse_detail(body) if body else None
            if d and d["company"]:
                out.append(Lead(
                    source="builtin",
                    company=slugify(d["company"]),
                    company_display=d["company"],
                    title=d["title"],
                    url=u,
                    location=d["location"],
                ))
            time.sleep(SLEEP)
        return out
