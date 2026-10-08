"""SmartRecruiters board (first-party ATS).

Probe verdict for careers.sfgov.org: that hostname does not resolve; the live
City and County of San Francisco portal is careers.sf.gov, which runs on
SmartRecruiters (company identifier ``CityAndCountyOfSanFrancisco1``). It is
**not** NeoGov -- the classic NeoGov/GovernmentJobs path
(``governmentjobs.com/careers/<tenant>/home/loadJobsOnMaps``) 302s to
``/Error/NotFound`` for every SF tenant slug tried (sfgov, sf, sanfrancisco,
cityofsanfrancisco), and api.neogov.com requires a key.

SmartRecruiters exposes a fully keyless public JSON API (no auth header, no key;
the jobhunt ``get`` UA is accepted):

    GET https://api.smartrecruiters.com/v1/companies/<company>/postings
        ?limit=<n>&offset=<n>[&q=<term>]
    GET https://api.smartrecruiters.com/v1/companies/<company>/postings/<id>

The list response carries id, name, location (incl. fullLocation), refNumber,
releasedDate, department, typeOfEmployment and the canonical ``postingUrl``;
the numeric ``id`` is the last path segment of the public posting URL. The
per-posting detail response adds ``jobAd.sections`` (companyDescription,
jobDescription, qualifications, additionalInformation) with the description
HTML, so content is populated.

Verified live (2026-10-08): ``CityAndCountyOfSanFrancisco1`` reports
totalFound=159; list pages of 100 paginate to the full set; a per-job detail
fetch returns ~18 KB with all four description sections. See
tests/test_sfgov_live.py.

Config -- a company identifier string, a list of them, or a list of spec dicts
(mix freely). Examples:

    boards:
      smartrecruiters:
        - CityAndCountyOfSanFrancisco1   # City & County of San Francisco
        - Ubisoft2                        # any public SmartRecruiters company

    boards:
      smartrecruiters:
        - company: CityAndCountyOfSanFrancisco1
          q: engineer        # optional server-side keyword filter
          max_jobs: 200      # optional cap (default 300)

Note: ``q`` filters on the SmartRecruiters side (``totalFound`` shrinks); with
no ``q`` the board walks every open posting. The generic company slug is used
verbatim, so this board serves any SmartRecruiters customer, not just SF.
"""
import time
from dataclasses import dataclass

from ..http import get
from ..models import Job
from ..registry import register_board
from ..util import strip_tags, MAX_CONTENT
from .base import Board, slug_list

API = "https://api.smartrecruiters.com/v1/companies/{company}/postings"
DETAIL = "https://api.smartrecruiters.com/v1/companies/{company}/postings/{id}"
PAGE_SIZE = 100
DEFAULT_MAX = 300
_SECTIONS = ("companyDescription", "jobDescription", "qualifications",
             "additionalInformation")


@dataclass
class _Spec:
    company: str
    q: str = ""
    max_jobs: int = DEFAULT_MAX


def _specs(config) -> list[_Spec]:
    """Normalize config: strings, a string, or spec dicts (mixed allowed)."""
    if config is None:
        return []
    if isinstance(config, (str, dict)):
        config = [config]
    out = []
    for c in config or []:
        if isinstance(c, str) and c:
            out.append(_Spec(company=c))
        elif isinstance(c, dict) and c.get("company"):
            out.append(_Spec(
                company=str(c["company"]),
                q=str(c.get("q") or ""),
                max_jobs=int(c.get("max_jobs", DEFAULT_MAX)),
            ))
    return out


def _loc(loc) -> str:
    if not isinstance(loc, dict):
        return ""
    if loc.get("fullLocation"):
        return str(loc["fullLocation"])
    parts = [loc.get("city"), loc.get("region"), loc.get("country")]
    return ", ".join(p for p in parts if p)


def _content(detail: dict) -> str:
    sections = ((detail or {}).get("jobAd") or {}).get("sections") or {}
    body = "\n".join(
        strip_tags((sections.get(k) or {}).get("text") or "")
        for k in _SECTIONS if isinstance(sections.get(k), dict))
    return body.strip()


def _list(company: str, q: str, max_jobs: int) -> list[dict]:
    """Paginate the postings list. Stops on empty page or when total reached."""
    out, offset = [], 0
    while offset < max_jobs:
        params: dict = {"limit": min(PAGE_SIZE, max_jobs - offset), "offset": offset}
        if q:
            params["q"] = q
        d = get(API.format(company=company), params=params)
        if not d or not isinstance(d.get("content"), list):
            break
        rows = d["content"]
        if not rows:
            break
        out.extend(rows)
        total = d.get("totalFound") or 0
        offset += len(rows)
        if offset >= total or len(rows) < params["limit"]:
            break
        time.sleep(0.5)
    return out


def smartrecruiters_board(spec: _Spec) -> list[Job]:
    out = []
    for row in _list(spec.company, spec.q, spec.max_jobs):
        jid = str(row.get("id") or "")
        if not jid:
            continue
        url = row.get("postingUrl") or (
            f"https://jobs.smartrecruiters.com/{spec.company}/{jid}")
        detail = get(DETAIL.format(company=spec.company, id=jid)) or {}
        content = _content(detail)
        loc = _loc(row.get("location") or detail.get("location"))
        dept = (row.get("department") or {}).get("label") or ""
        out.append(Job(
            source="smartrecruiters",
            company=(row.get("company") or {}).get("name") or spec.company,
            id=f"sr-{spec.company}-{jid}",
            title=row.get("name") or "",
            url=url,
            location=loc or dept,
            updated=(row.get("releasedDate") or "")[:10],
            content=content[:MAX_CONTENT],
            extra={"department": dept, "ref": row.get("refNumber") or ""},
        ))
    return out


@register_board("smartrecruiters")
class SmartRecruitersBoard(Board):
    """config: a company id string, a list of them, or spec dicts
    {company, q?, max_jobs?} (mixed allowed)."""

    def fetch(self) -> list[Job]:
        out = []
        for spec in _specs(self.config):
            out.extend(smartrecruiters_board(spec))
        return out
