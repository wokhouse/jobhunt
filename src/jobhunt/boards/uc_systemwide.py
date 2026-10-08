"""University of California systemwide job board (UCOP / PeopleSoft).

UC campuses publish staff openings to one shared, server-rendered board at
``jobs.universityofcalifornia.edu`` (a Yii app fronting UCOP's PeopleSoft
HCM). It is keyless and filterable by campus and keyword:

    https://jobs.universityofcalifornia.edu/site/advancedsearch
        ?keywords=<kw>&MCampus[0]=<code>&search=Search&page=<n>

Ten results per page; the ``.numresults`` block reports the total
(``Viewing: 1 - 10 of 168 results``). Each result is a ``div.jobspot`` carrying
title (``a.jtitle``), the apply URL (a PeopleSoft ``HRS_APP_JBPST_FL`` deep
link), location (``.jloc``), job type (``.jtype``), category (``.jfamily``),
requisition number (``.jreq``), posting date (``.jclose``) and a short summary
(``p.jdesc``).

The deep link resolves to the full posting on UCOP PeopleSoft
(``careerspub.universityofcalifornia.edu/psc/<campus>/...``). That page needs
the session cookies set on first contact -- a bare urllib request without a
cookie jar is bounced to the PeopleSoft login -- so this board fetches the
detail through a small cookie-aware opener and falls back to the list summary
when the detail is unavailable.

Verified live (see tests/test_universities_live.py): Berkeley (campus ``BK``)
returns ~168 postings.

Config (a spec dict, or a list of them):

    boards:
      uc_systemwide:
        - campus: BK          # required, UCOP campus code (BK=Berkeley, ...)
          company: UC Berkeley  # optional display name (default: the campus code)
          search: engineer    # optional keyword (default: all)
          detail: true        # optional; fetch full PeopleSoft posting (default true)
          max_jobs: 200       # optional cap (default 200)

Campus codes seen on the board include BK (Berkeley), DA (Davis), IR (Irvine),
LA (Los Angeles), MR (Merced), SD (San Diego), SB (Santa Barbara), SC (Santa
Cruz), CR (Riverside). UCSF is *not* on this board -- it runs Oracle Recruiting
Cloud (see the ``oracle_recruiting`` board).
"""
import html
import re
import time
import urllib.request
import http.cookiejar

from ..http import get, UA
from ..models import Job
from ..registry import register_board
from ..util import class_text, text_of, MAX_CONTENT
from .base import Board

BASE = "https://jobs.universityofcalifornia.edu"
SEARCH = BASE + "/site/advancedsearch"
PAGE_SIZE = 10


def _field(block, cls):
    return class_text(block, cls, tag="[^>]+")


def _job_link(block):
    m = re.search(r'<a\b([^>]*)class="jtitle"([^>]*)>(.*?)</a>', block, re.S)
    if not m:
        return "", ""
    attrs = m.group(1) + m.group(2)
    href = re.search(r'href="([^"]+)"', attrs)
    if not href:
        return "", ""
    return html.unescape(href.group(1)), text_of(m.group(3))


def _total(page_html):
    m = re.search(r"of\s+([\d,]+)\s+results", page_html)
    return int(m.group(1).replace(",", "")) if m else 0


def _parse(page_html):
    out = []
    for block in re.findall(r'<div class="jobspot">(.*?)(?=<div class="jobspot">|\Z)',
                            page_html, re.S):
        url, title = _job_link(block)
        if not url or not title:
            continue
        out.append({
            "title": title,
            "url": url,
            "location": _field(block, "jloc"),
            "updated": _field(block, "jclose").replace("Posting Date:", "").strip(),
            "summary": _field(block, "jdesc"),
            "requisition": _field(block, "jreq").replace("Requisition:", "").strip(),
        })
    return out


def _opener():
    """One cookie-aware opener per board run (PeopleSoft needs session
    cookies; they must persist across detail requests)."""
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    opener.addheaders = [("User-Agent", UA["User-Agent"]),
                         ("Accept", "text/html,application/xhtml+xml,*/*;q=0.8"),
                         ("Accept-Language", "en-US,en;q=0.9")]
    return opener


def _get_html(opener, url, timeout=25):
    try:
        with opener.open(url, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return ""


def _detail_body(page_html):
    """Extract the job-description region from a PeopleSoft posting page."""
    if not page_html or "Departmental Overview" not in page_html:
        return ""
    m = re.search(r"(Departmental Overview.*?)"
                  r"(?:Application Review Date|Responsibilities|Required "
                  r"Qualifications|Salary & Benefits)", page_html, re.S)
    return text_of(m.group(1)) if m else ""


def uc_systemwide(spec: dict) -> list[Job]:
    """spec: {campus, company?, search?, detail?, max_jobs?}."""
    campus = spec["campus"]
    company = spec.get("company") or campus
    search = spec.get("search") or ""
    want_detail = spec.get("detail", True)
    max_jobs = int(spec.get("max_jobs", 200))

    seen, rows = set(), []
    page = 1
    while len(rows) < max_jobs:
        params = {"keywords": search, "MCampus[0]": campus, "search": "Search"}
        if page > 1:
            params["page"] = page
        h = get(SEARCH, params=params, raw=True)
        if not h:
            break
        batch = _parse(h)
        if not batch:
            break
        new = 0
        for r in batch:
            key = r["requisition"] or r["url"]
            if key in seen:
                continue
            seen.add(key)
            rows.append(r)
            new += 1
        total = _total(h)
        if new == 0 or len(batch) < PAGE_SIZE or (total and len(rows) >= total):
            break
        page += 1
        time.sleep(0.4)

    out = []
    opener = _opener()
    for r in rows[:max_jobs]:
        content = r["summary"]
        if want_detail and r["url"]:
            full = _detail_body(_get_html(opener, r["url"]))
            if len(full) > len(content):
                content = full
            time.sleep(0.3)
        out.append(Job(
            source="uc_systemwide", company=company,
            id=f"uc-{campus}-{r['requisition'] or r['url']}",
            title=r["title"], url=r["url"], location=r["location"],
            updated=r["updated"], content=(content or "")[:MAX_CONTENT],
        ))
    return out


@register_board("uc_systemwide")
class UcSystemwideBoard(Board):
    """config: a spec dict, or a list of spec dicts.
    spec: {campus, company, search, detail, max_jobs}"""

    def fetch(self) -> list[Job]:
        cfg = self.config or {}
        if isinstance(cfg, dict):
            cfg = [cfg]
        out = []
        for spec in cfg:
            if isinstance(spec, dict) and spec.get("campus"):
                out.extend(uc_systemwide(spec))
        return out
