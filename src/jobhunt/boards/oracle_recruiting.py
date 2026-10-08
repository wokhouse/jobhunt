"""Oracle Recruiting Cloud (Oracle Fusion HCM Candidate Experience) board.

Universities that run Oracle Recruiting Cloud publish two keyless REST
resources under ``/hcmRestApi/resources/latest/`` on their Candidate
Experience host:

* ``recruitingCEJobRequisitions`` -- paginated search. A ``finder`` parameter
  selects the career site and sort, e.g.
  ``findReqs;siteNumber=CX_1,facetsList=LOCATIONS,limit=200,offset=200,sortBy=POSTING_DATES_DESC``.
  Each row carries title, primary/secondary locations, posted date and a short
  summary, but *not* the full description.
* ``recruitingCEJobRequisitionDetails`` -- one job. The finder is
  ``ById;Id="<id>",siteNumber=<site>`` (the Id must be quoted; without the
  quotes the API answers ``400 ... finder ... is not valid``). ``expand=all``
  returns ``ExternalDescriptionStr``, ``ExternalResponsibilitiesStr`` and
  ``ExternalQualificationsStr`` as HTML.

The public per-job page is
``<base>/hcmUI/CandidateExperience/en/sites/<site>/job/<id>``.

Verified live (see tests/test_universities_live.py): Stanford
(``careersearch.stanford.edu``, site ``CX_1``, ~380 postings) and UCSF
(``iazuqy.fa.ocs.oraclecloud.com``, site ``CX_1``, ~788 postings).

Config (a spec dict, or a list of them):

    boards:
      oracle_recruiting:
        - host: careersearch.stanford.edu   # required, no scheme
          site: CX_1                        # required, career-site number
          company: Stanford                 # optional display name
          base: https://careersearch.stanford.edu  # optional; default https://<host>
          search: engineer                  # optional keyword (default: none)
          facets: LOCATIONS                 # optional facetsList (or null)
          terms: [engineer, analyst]        # optional; overrides search
          max_jobs: 500                     # optional cap (default 500)

The endpoint family is documented by Oracle as the Candidate Experience REST
API; field names are stable across tenants we tested but parsing is defensive
so a schema shift yields fewer jobs, not an exception.
"""
import time
from urllib.parse import quote

from ..http import get
from ..models import Job
from ..registry import register_board
from ..util import strip_tags, MAX_CONTENT
from .base import Board

REQS = "{base}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
DETAIL = "{base}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"
JOB_PAGE = "{base}/hcmUI/CandidateExperience/en/sites/{site}/job/{id}"
PAGE_SIZE = 200  # Oracle caps a page well above this; 200 is a safe batch


def _finder(site, *, search=None, facets="LOCATIONS", limit=PAGE_SIZE, offset=0):
    parts = [f"siteNumber={site}"]
    if facets:
        parts.append(f"facetsList={facets}")
    if search:
        parts.append(f"keyword={search}")
    parts.append(f"limit={limit}")
    parts.append(f"offset={offset}")
    parts.append("sortBy=POSTING_DATES_DESC")
    return "findReqs;" + ",".join(parts)


def _rows(spec):
    """Yield list rows across search terms, paginating by offset."""
    base = spec.get("base") or f"https://{spec['host']}"
    site = spec["site"]
    max_jobs = int(spec.get("max_jobs", 500))
    facets = spec.get("facets", "LOCATIONS")
    terms = spec.get("terms")
    if terms is None:
        terms = [spec.get("search")]

    seen, out = set(), []
    for term in terms:
        offset = 0
        while len(out) < max_jobs:
            d = get(REQS.format(base=base),
                    params={"onlyData": "true", "expand": "all",
                            "finder": _finder(site, search=term, facets=facets,
                                              offset=offset)})
            row = ((d or {}).get("items") or [{}])[0]
            reqs = row.get("requisitionList") or []
            if not reqs:
                break
            new = 0
            for r in reqs:
                jid = str(r.get("Id") or "")
                if not jid or jid in seen:
                    continue
                seen.add(jid)
                out.append(r)
                new += 1
            if len(reqs) < PAGE_SIZE or new == 0:
                break
            offset += PAGE_SIZE
            time.sleep(0.5)
        if len(out) >= max_jobs:
            break
    return out[:max_jobs], base, site


def _detail(base, site, jid):
    """Fetch one requisition's full description HTML (None on failure)."""
    d = get(DETAIL.format(base=base),
            params={"onlyData": "true", "expand": "all",
                    "finder": f'ById;Id="{jid}",siteNumber={site}'})
    items = (d or {}).get("items") or []
    return items[0] if items else None


def _locations(row):
    names = []
    for key in ("PrimaryLocation", "secondaryLocations", "otherWorkLocations",
                "workLocation"):
        v = row.get(key)
        if isinstance(v, str) and v:
            names.append(v)
        elif isinstance(v, list):
            for loc in v:
                if isinstance(loc, str) and loc:
                    names.append(loc)
                elif isinstance(loc, dict):
                    n = loc.get("Name") or loc.get("LocationName") or loc.get("name")
                    if n:
                        names.append(str(n))
    return "; ".join(dict.fromkeys(names))


def oracle_recruiting(spec: dict) -> list[Job]:
    """spec: {host, site, company?, base?, search?, terms?, facets?, max_jobs?}."""
    rows, base, site = _rows(spec)
    company = spec.get("company") or spec["host"].split(".")[0]
    out = []
    for r in rows:
        jid = str(r["Id"])
        det = _detail(base, site, jid) or {}
        body = "\n".join(
            strip_tags(det.get(k) or r.get(k) or "")
            for k in ("ExternalDescriptionStr", "ExternalResponsibilitiesStr",
                      "ExternalQualificationsStr", "ShortDescriptionStr"))
        out.append(Job(
            source="oracle_recruiting", company=company, id=f"oracle-{site}-{jid}",
            title=det.get("Title") or r.get("Title", ""),
            url=JOB_PAGE.format(base=base, site=site, id=quote(jid)),
            location=_locations(det) or _locations(r),
            updated=(r.get("PostedDate") or det.get("ExternalPostedStartDate") or ""),
            content=body.strip()[:MAX_CONTENT],
        ))
        time.sleep(0.25)
    return out


@register_board("oracle_recruiting")
class OracleRecruitingBoard(Board):
    """config: a spec dict, or a list of spec dicts.
    spec: {host, site, company, base, search, terms, facets, max_jobs}"""

    def fetch(self) -> list[Job]:
        cfg = self.config or {}
        if isinstance(cfg, dict):
            cfg = [cfg]
        out = []
        for spec in cfg:
            if isinstance(spec, dict) and spec.get("host") and spec.get("site"):
                out.extend(oracle_recruiting(spec))
        return out
