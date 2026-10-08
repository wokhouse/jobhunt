"""San Francisco State University (PageUp / ClinchTalent) board.

SF State publishes its openings on PageUp People's "ClinchTalent" career
pages at ``jobs.sfsu.edu``:

    https://jobs.sfsu.edu/en-us/listing/?page=<n>&page-items=20

The listing is server-rendered (Drupal-rendered markup) and keyless: each
opening is a table row with ``a.job-link`` (title + relative detail URL),
``span.location``, ``span.open-date`` and a following ``tr.summary`` row
holding the short description. Twenty rows per page.

Caveat -- bot protection: the host sits behind AWS WAF with CloudFront and
answers a JavaScript ``x-amzn-waf-action: challenge`` (HTTP 202, empty body)
to requests that look automated. Sending full browser headers and letting the
WAF's short-lived token cool down between calls makes the listing succeed with
a plain HTTP client; when the challenge is returned this board simply stops and
returns what it has. Detail pages (``/en-us/job/<id>/...``) are protected more
aggressively and are not fetched; the list row's summary is used as content.
This matches what the browser sees on the listing.

Verified live (see tests/test_universities_live.py): the listing returns ~63
openings across the paginated set.

Config (a spec dict, or a list of them):

    boards:
      pageup:
        - host: jobs.sfsu.edu        # required, no scheme
          company: San Francisco State University  # optional display name
          pages: 4                   # optional max listing pages (default 4)
          page_items: 20             # optional page size (default 20)
          max_jobs: 100              # optional cap (default 100)
"""
import html
import re
import time

from ..http import get
from ..models import Job
from ..registry import register_board
from ..util import strip_tags, MAX_CONTENT
from .base import Board

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

LIST = "https://{host}/en-us/listing/"

_ROW = re.compile(
    r'<a[^>]+class="job-link"[^>]+href="([^"]+)"[^>]*>(.*?)</a>(.*?)'
    r'(?=<a[^>]+class="job-link"|\Z)', re.S)


def _text(fragment):
    return re.sub(r"\s+", " ", html.unescape(strip_tags(fragment or ""))).strip()


def _span(block, cls):
    m = re.search(r'<span[^>]+class="[^"]*\b' + cls + r'\b[^"]*"[^>]*>(.*?)</span>',
                  block, re.S)
    return _text(m.group(1)) if m else ""


def _summary(block):
    m = re.search(r'<tr[^>]+class="summary"[^>]*>(.*?)</tr>', block, re.S)
    return _text(m.group(1)) if m else ""


def _fetch_listing(host, page, page_items):
    params = {"page": page, "page-items": page_items}
    for attempt in range(3):
        h = get(LIST.format(host=host), params=params, raw=True,
                headers=BROWSER_HEADERS, tries=1)
        # AWS WAF challenge page is ~2.4KB with an awsWafCookieDomainList blob.
        if h and "awsWafCookieDomainList" not in h and len(h) > 5000:
            return h
        time.sleep(4 * (attempt + 1))
    return None


def _parse(page_html, host):
    out = []
    if not page_html:
        return out
    for m in _ROW.finditer(page_html):
        href = m.group(1)
        title = _text(m.group(2))
        rest = m.group(3)
        if not href or not title:
            continue
        url = href if href.startswith("http") else f"https://{host}{href}"
        # The detail URL's leading numeric segment is the stable job id.
        jid = re.search(r"/job/(\d+)", href)
        out.append({
            "id": jid.group(1) if jid else href.rstrip("/").split("/")[-1],
            "title": title, "url": url,
            "location": _span(rest, "location"),
            "updated": _span(rest, "open-date"),
            "summary": _summary(rest),
        })
    return out


def pageup(spec: dict) -> list[Job]:
    """spec: {host, company?, pages?, page_items?, max_jobs?}."""
    host = spec["host"]
    company = spec.get("company") or host
    pages = int(spec.get("pages", 4))
    page_items = int(spec.get("page_items", 20))
    max_jobs = int(spec.get("max_jobs", 100))

    seen, rows = set(), []
    for page in range(1, pages + 1):
        batch = _parse(_fetch_listing(host, page, page_items), host)
        if not batch:
            break
        new = 0
        for r in batch:
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            rows.append(r)
            new += 1
        if new == 0 or len(batch) < page_items:
            break
        if len(rows) >= max_jobs:
            break
        time.sleep(3)

    return [Job(
        source="pageup", company=company, id=f"pu-{host.split('.')[0]}-{r['id']}",
        title=r["title"], url=r["url"], location=r["location"],
        updated=r["updated"], content=(r["summary"] or "")[:MAX_CONTENT],
    ) for r in rows[:max_jobs]]


@register_board("pageup")
class PageUpBoard(Board):
    """config: a spec dict, or a list of spec dicts.
    spec: {host, company, pages, page_items, max_jobs}"""

    def fetch(self) -> list[Job]:
        cfg = self.config or {}
        if isinstance(cfg, dict):
            cfg = [cfg]
        out = []
        for spec in cfg:
            if isinstance(spec, dict) and spec.get("host"):
                out.extend(pageup(spec))
        return out
