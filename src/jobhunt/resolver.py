"""Resolve a company name to its first-party ATS board.

Strategy (in order):
1. Probe public ATS APIs with the slugified company name (Greenhouse,
   Ashby, Lever, Workable, Rippling). A 200 with jobs means the board
   exists; a job title matching the lead confirms it belongs to THIS
   company (not a squatter on the same slug).
2. Fallback: fetch the company's careers page and parse ATS links
   (including Workday tenants), then verify the parsed board with a
   title match where possible.

A resolution is 'verified' when a job title on the resolved board
matches the lead title (exact normalized, or fuzzy >= 0.8).
"""
import re
import urllib.parse

from .http import get
from .matcher import title_similarity

BROWSER_UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
              "Accept": "text/html,application/xhtml+xml"}

ATS_ORDER = ("greenhouse", "ashby", "lever", "workable", "rippling")

ATS_LINK_PATS = {
    "greenhouse": [r"greenhouse\.io/jobs/([a-z0-9-]+)",
                   r"job-boards\.greenhouse\.io/([a-z0-9-]+)",
                   r"boards-api\.greenhouse\.io/v1/boards/([a-z0-9-]+)"],
    "lever": [r"jobs\.lever\.co/([a-z0-9-]+)",
              r"api\.lever\.co/v0/postings/([a-z0-9-]+)"],
    "ashby": [r"jobs\.ashbyhq\.com/([a-z0-9-]+)"],
    "workable": [r"apply\.workable\.com/([a-z0-9-]+)"],
    "rippling": [r"ats\.rippling\.com/([a-z0-9-]+)"],
}
WORKDAY_LINK_PAT = re.compile(
    r"([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:en-US/)?([A-Za-z0-9_-]+)")

LEVEL_WORDS = {"senior", "sr", "junior", "staff", "lead", "principal",
               "founding", "associate", "ii", "iii", "iv"}


def norm_title(t: str) -> str:
    t = re.sub(r"[.,:;/|()&]+", " ", (t or "").lower())
    return re.sub(r"\s+", " ", t).strip()


def core_title(t: str) -> str:
    return " ".join(w for w in norm_title(t).split() if w not in LEVEL_WORDS)


def slug_ok(slug: str, company_key: str, display: str) -> bool:
    """Is this ATS slug plausibly THIS company's board?"""
    s = re.sub(r"[^a-z0-9]", "", (slug or "").lower())
    ckey = re.sub(r"[^a-z0-9]", "", (company_key or "").lower())
    ddisp = re.sub(r"[^a-z0-9]", "", (display or "").lower())
    if not s:
        return False
    if s == ckey or s == ddisp:
        return True
    if len(s) >= 5 and (s.startswith(ckey) or ckey.startswith(s)):
        return True
    if len(ddisp) >= 5 and (s.startswith(ddisp) or ddisp.startswith(s)):
        return True
    words = [w for w in re.sub(r"[^a-z0-9 ]", "", (display or " ")).lower().split()
             if len(w) >= 3]
    return any(w in s for w in words)


def _jobs_list(kind: str, slug: str) -> list[dict] | None:
    """Light list-only probe of a public ATS API. None = board not found."""
    q = urllib.parse.quote(slug)
    try:
        if kind == "greenhouse":
            d = get(f"https://boards-api.greenhouse.io/v1/boards/{q}/jobs")
            return [{"title": j.get("title", ""), "url": j.get("absolute_url", "")}
                    for j in (d or {}).get("jobs", [])] if d else None
        if kind == "ashby":
            d = get(f"https://api.ashbyhq.com/posting-api/job-board/{q}")
            if not d:
                return None
            return [{"title": j.get("title", ""),
                     "url": j.get("jobUrl") or j.get("applyUrl", "")}
                    for j in d.get("jobs", []) if j.get("isListed", True)]
        if kind == "lever":
            d = get(f"https://api.lever.co/v0/postings/{q}?mode=json")
            if not isinstance(d, list):
                return None
            return [{"title": j.get("text", ""), "url": j.get("hostedUrl", "")}
                    for j in d]
        if kind == "workable":
            d = get(f"https://apply.workable.com/api/v1/widget/accounts/{q}")
            if not d:
                return None
            return [{"title": j.get("title", ""),
                     "url": f"https://apply.workable.com/{slug}/j/{j.get('shortcode', '')}/"}
                    for j in d.get("jobs", [])]
        if kind == "rippling":
            d = get(f"https://api.rippling.com/platform/api/ats/v1/board/{q}/jobs")
            if d is None:
                return None
            rows = d if isinstance(d, list) else (d.get("jobs") or [])
            return [{"title": j.get("title", ""), "url": j.get("url", "")}
                    for j in rows]
    except Exception:
        return None
    return None


def title_match(lead_title: str, jobs: list[dict]) -> bool:
    lt = norm_title(lead_title)
    for j in jobs:
        jt = norm_title(j.get("title", ""))
        if not jt:
            continue
        if lt == jt or core_title(lt) == core_title(jt):
            return True
        if title_similarity(lt, jt) >= 0.8:
            return True
    return False


def slug_variants(slug: str) -> list[str]:
    """Ashby slugs can contain spaces ('hippocratic ai'); try both forms."""
    out = [slug]
    spaced = slug.replace("-", " ")
    if spaced != slug:
        out.append(spaced)
    return out


def probe_api(kind: str, slug: str, lead) -> dict | None:
    for variant in slug_variants(slug):
        jobs = _jobs_list(kind, variant)
        if not jobs:
            continue
        verified = title_match(lead.title, jobs)
        return {"kind": kind, "slug": variant, "verified": verified,
                "board_jobs": len(jobs)}
    return None


def careers_page_probe(slug: str, lead) -> dict | None:
    """Parse the company's own careers page for ATS links."""
    for path in ("/careers", "/jobs", ""):
        html = get(f"https://www.{slug}.com{path}", headers=BROWSER_UA,
                   raw=True, tries=2, timeout=12)
        if not html:
            continue
        # Workday tenant embedded on the careers page
        m = WORKDAY_LINK_PAT.search(html)
        if m and slug_ok(m.group(1), slug, lead.company_display):
            tenant, host, site = m.group(1), m.group(2), m.group(3)
            d = get(f"https://{tenant}.{host}.myworkdayjobs.com/wday/cxs/"
                    f"{tenant}/{site}/jobs", method="POST",
                    body={"appliedFacets": {}, "limit": 20, "offset": 0,
                          "searchText": core_title(lead.title)},
                    headers=BROWSER_UA, tries=2)
            rows = (d or {}).get("jobPostings") or []
            verified = bool(rows) and title_match(
                lead.title, [{"title": r.get("title", "")} for r in rows])
            return {"kind": "workday", "tenant": tenant, "host": host,
                    "site": site, "terms": [core_title(lead.title)],
                    "verified": verified, "board_jobs": len(rows)}
        for kind, pats in ATS_LINK_PATS.items():
            for pat in pats:
                mm = re.search(pat, html, re.I)
                if mm and slug_ok(mm.group(1), slug, lead.company_display):
                    found = probe_api(kind, mm.group(1).lower(), lead)
                    if found:
                        return found
                    return {"kind": kind, "slug": mm.group(1).lower(),
                            "verified": False, "board_jobs": 0}
    return None


def resolve_company(lead) -> dict | None:
    """Locate the first-party ATS board for one lead's company."""
    weak = None
    for kind in ATS_ORDER:
        found = probe_api(kind, lead.company, lead)
        if not found:
            continue
        if found["verified"]:
            return found
        weak = weak or found
    found = careers_page_probe(lead.company, lead)
    if found and found.get("verified"):
        return found
    return found or weak
