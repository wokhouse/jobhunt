import time

from ..http import get
from ..models import Job
from ..registry import register_board
from ..util import strip_tags, MAX_CONTENT
from .base import Board

LIST = "https://{tenant}.{host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
DETAIL = "https://{tenant}.{host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}{path}"
PAGE = "https://{tenant}.{host}.myworkdayjobs.com/en-US/{site}{path}"

DEFAULT_TERMS = ["software engineer", "full stack", "frontend", "developer"]


def _term_jobs(tenant, host, site, term, max_jobs):
    """Paginate one searchText term. total=0 means the term is unusable on
    this board (filler results) — stop immediately."""
    out, offset = [], 0
    while offset < max_jobs:
        d = get(LIST.format(tenant=tenant, host=host, site=site),
                method="POST",
                body={"appliedFacets": {}, "limit": 20, "offset": offset,
                      "searchText": term})
        if not d or d.get("jobPostings") is None:
            break
        total = d.get("total") or 0
        postings = d["jobPostings"]
        if not postings:
            break
        if total == 0:
            break
        out.extend(postings)
        offset += 20
        time.sleep(0.8)
        if offset >= total:
            break
    return out


def workday_board(spec: dict) -> list[Job]:
    """spec: {tenant, site, host?, terms?, max_jobs?}.

    Workday list API returns no descriptions; fetch CXS detail JSON per job.
    """
    tenant = spec["tenant"]
    site = spec["site"]
    host = spec.get("host", "wd1")
    terms = spec.get("terms") or DEFAULT_TERMS
    max_jobs = int(spec.get("max_jobs", 400))

    seen, postings = set(), []
    for term in terms:
        for j in _term_jobs(tenant, host, site, term, max_jobs):
            path = j.get("externalPath")
            if path and path not in seen:
                seen.add(path)
                postings.append(j)
        time.sleep(1.0)

    out = []
    for j in postings:
        path = j["externalPath"]
        d = get(DETAIL.format(tenant=tenant, host=host, site=site, path=path))
        info = (d or {}).get("jobPostingInfo") or {}
        desc = strip_tags(info.get("jobDescription") or "")
        out.append(Job(
            source="workday", company=tenant, id=f"wd-{tenant}-{info.get('jobReqId') or path.rsplit('_',1)[-1]}",
            title=info.get("title") or j.get("title", ""),
            url=PAGE.format(tenant=tenant, host=host, site=site, path=path),
            location=info.get("location") or (j.get("locationsText") or "").replace("\n", ", "),
            updated=info.get("timeToPost") or j.get("postedOn", ""),
            content=desc[:MAX_CONTENT],
        ))
    return out


@register_board("workday")
class WorkdayBoard(Board):
    """config: list of specs, or one spec.
    spec: {tenant, site, host, terms: [...], max_jobs: N}"""
    def fetch(self) -> list[Job]:
        cfg = self.config or []
        if isinstance(cfg, dict):
            cfg = [cfg]
        out = []
        for spec in cfg:
            out.extend(workday_board(spec))
        return out
