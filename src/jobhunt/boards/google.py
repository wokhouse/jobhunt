"""Google Careers board.

Google retired the old public JSON API (careers.google.com/api/v1/jobs now
404s and the Cloud Talent Solution jobs endpoint requires an API key), so this
board parses the server-rendered HTML of the hosted careers site instead. The
results and detail pages embed full job records in an
``AF_initDataCallback({key: 'ds:1', ...})`` blob of valid JSON, which we extract
directly -- no API key and no browser needed.

Verified live (see tests/test_google_live.py): ``q=software engineer`` returns
~1500 postings; the list page's embedded record already carries title, apply
URL, locations, and the full description HTML, so no per-job detail fetch is
required. The canonical per-job URL is
``.../jobs/results/<jobId>-<title-slug>``.

Config (a spec dict, or a list of them):

    boards:
      google:
        search: "software engineer"   # query, optional (default below)
        locations: ["United States"]  # optional; one search is run per location
        max_jobs: 200                 # optional cap (default 200)

Caveat: this scrapes Google's private frontend data. Field positions in the
embedded blob are undocumented and could shift without notice; parsing is
defensive (index-guarded) so a reshuffle yields fewer jobs, not an exception.
"""
import json
import re
import time
import urllib.parse

from ..http import get
from ..models import Job
from ..registry import register_board
from ..util import strip_tags, MAX_CONTENT
from .base import Board

LIST = "https://www.google.com/about/careers/applications/jobs/results/"
PAGE_SIZE = 20  # Google renders 20 rows per results page
DEFAULT_SEARCH = "software engineer"


def _init_data(html: str, key: str = "ds:1"):
    """Extract the JSON array from AF_initDataCallback({key: '<key>', ...}).

    Returns the parsed ``data`` array, or None when the blob is absent or the
    page reported no results (Google emits ``data:[null,...]`` for an empty
    query, which parses to None here).
    """
    marker = re.search(r"AF_initDataCallback\(\{key: '" + re.escape(key) + r"'", html or "")
    if not marker:
        return None
    di = html.find("data:", marker.end())
    if di < 0:
        return None
    start = di + len("data:")
    while start < len(html) and html[start] in " \t\n":
        start += 1
    if start >= len(html) or html[start] != "[":
        return None
    depth, quote, esc = 0, False, False
    for i in range(start, len(html)):
        c = html[i]
        if quote:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                quote = False
            continue
        if c == '"':
            quote = True
        elif c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[start:i + 1])
                except Exception:
                    return None
    return None


def _pull_html(cell) -> str:
    """Collect string fragments from a [null, '<html>'] style cell."""
    if not isinstance(cell, list):
        return ""
    return "".join(str(x) for x in cell if isinstance(x, str) and x)


def _slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")
    return s


def _date(v) -> str:
    """Field 12 is [epoch_seconds, nanos]; render as YYYY-MM-DD."""
    try:
        sec = int(v[0])
    except (TypeError, ValueError, IndexError):
        return ""
    if sec <= 0:
        return ""
    return time.strftime("%Y-%m-%d", time.gmtime(sec))


def _row_job(row: list) -> Job | None:
    if not isinstance(row, list) or len(row) < 2 or not row[0]:
        return None
    jid = str(row[0])
    title = str(row[1] or "")
    company = str(row[7]) if len(row) > 7 and row[7] else "Google"

    locs = row[9] if len(row) > 9 and isinstance(row[9], list) else []
    names = []
    for loc in locs:
        if isinstance(loc, list) and loc and isinstance(loc[0], str) and loc[0]:
            names.append(loc[0])
    location = "; ".join(dict.fromkeys(names))

    # Description is split across cells: intro (10), responsibilities (3),
    # minimum qualifications (4), preferred qualifications (19).
    body = "\n".join(_pull_html(row[i]) for i in (10, 3, 4, 19) if i < len(row))
    content = strip_tags(body).strip()

    updated = ""
    for i in (12, 13, 14):
        if i < len(row):
            updated = _date(row[i])
            if updated:
                break

    url = f"{LIST}{jid}"
    if slug := _slug(title):
        url = f"{url}-{slug}"

    return Job(
        source="google", company=company, id=f"goog-{jid}", title=title,
        url=url, location=location, updated=updated,
        content=content[:MAX_CONTENT],
    )


def _page(search: str, location: str | None, page: int) -> list:
    params = {"q": search, "page": page}
    if location:
        params["location"] = location
    url = LIST + "?" + urllib.parse.urlencode(params)
    html = get(url, raw=True)
    if not html:
        return []
    data = _init_data(html)
    if not isinstance(data, list) or len(data) < 1:
        return []
    rows = data[0]
    return rows if isinstance(rows, list) else []


def google_board(spec: dict) -> list[Job]:
    """spec: {search?, locations?, max_jobs?}."""
    search = spec.get("search") or DEFAULT_SEARCH
    max_jobs = int(spec.get("max_jobs", 200))
    locations = spec.get("locations") or [None]
    if isinstance(locations, str):
        locations = [locations]

    seen, out = set(), []
    for location in locations:
        page = 1
        while len(out) < max_jobs:
            rows = _page(search, location, page)
            if not rows:
                break
            new = 0
            for row in rows:
                job = _row_job(row)
                if job is None or job.id in seen:
                    continue
                seen.add(job.id)
                out.append(job)
                new += 1
            if len(rows) < PAGE_SIZE or new == 0:
                break
            page += 1
            if page > 1:
                time.sleep(0.7)
        if len(out) >= max_jobs:
            break
    return out[:max_jobs]


@register_board("google")
class GoogleBoard(Board):
    """config: a spec dict, or a list of spec dicts.
    spec: {search, locations: [...], max_jobs: N}"""

    def fetch(self) -> list[Job]:
        cfg = self.config or {}
        if isinstance(cfg, list):
            specs = [s for s in cfg if isinstance(s, dict)]
        elif isinstance(cfg, dict):
            specs = [cfg]
        else:
            specs = [{}]
        if not specs:
            specs = [{}]
        out = []
        for spec in specs:
            out.extend(google_board(spec))
        return out
