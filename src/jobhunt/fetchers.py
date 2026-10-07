"""ATS board fetchers. Each returns a list of Job.

Endpoints (all public, no key):
- Greenhouse: https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
- Lever:      https://api.lever.co/v0/postings/{slug}?mode=json
- Ashby:      https://api.ashbyhq.com/posting-api/job-board/{slug}
- Workable:   https://apply.workable.com/api/v3/accounts/{slug}/jobs?page=N
              fallback https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true
- Rippling:   https://api.rippling.com/platform/api/ats/v1/board/{slug}/jobs
              detail   .../jobs/{uuid}
- Workday:    POST https://{tenant}.{host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
"""
import concurrent.futures
import urllib.parse

from .http import get
from .models import Job
from .util import strip_tags, MAX_CONTENT


def greenhouse(slug: str) -> list[Job]:
    d = get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
    if not d or "jobs" not in d:
        return []
    out = []
    for j in d["jobs"]:
        out.append(Job(
            source="greenhouse", company=slug, id=f"gh-{slug}-{j['id']}",
            title=j.get("title", ""), url=j.get("absolute_url", ""),
            location=(j.get("location") or {}).get("name", ""),
            updated=j.get("updated_at", ""),
            content=strip_tags(j.get("content") or "")[:MAX_CONTENT],
        ))
    return out


def lever(slug: str) -> list[Job]:
    d = get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    if not isinstance(d, list):
        return []
    out = []
    for j in d:
        parts = [j.get("descriptionPlain") or ""]
        for lst in (j.get("lists") or []):
            parts.append("## " + (lst.get("text") or ""))
            for c in (lst.get("content") or []):
                parts.append(str(c.get("content", "")) if isinstance(c, dict) else str(c))
        created = j.get("createdAt")
        out.append(Job(
            source="lever", company=slug, id=f"lv-{slug}-{j['id']}",
            title=j.get("text", ""), url=j.get("hostedUrl", ""),
            location=(j.get("categories") or {}).get("location", ""),
            updated=str(created) if created else "",
            content="\n".join(parts)[:MAX_CONTENT],
        ))
    return out


def ashby(slug: str) -> list[Job]:
    d = get(f"https://api.ashbyhq.com/posting-api/job-board/{urllib.parse.quote(slug)}")
    if not d or "jobs" not in d:
        return []
    out = []
    for j in d["jobs"]:
        if not j.get("isListed", True):
            continue
        loc = j.get("location") or ""
        if isinstance(loc, dict):
            loc = loc.get("name") or ""
        secondary = ", ".join(
            s.get("location", "") if isinstance(s, dict) else str(s)
            for s in (j.get("secondaryLocations") or []))
        out.append(Job(
            source="ashby", company=slug, id=f"ash-{slug}-{j['id']}",
            title=j.get("title", ""),
            url=j.get("jobUrl") or j.get("applyUrl") or f"https://jobs.ashbyhq.com/{slug}",
            location=str(loc) + (f" (+ {secondary})" if secondary else ""),
            updated=j.get("publishedAt", ""),
            content=(j.get("descriptionPlain") or "")[:MAX_CONTENT],
            extra={"workplaceType": j.get("workplaceType", "")},
        ))
    return out


def workable(slug: str) -> list[Job]:
    out: list[Job] = []
    seen: set[str] = set()
    # Primary: v3 paginated accounts API.
    page = 1
    while page <= 40:
        d = get(f"https://apply.workable.com/api/v3/accounts/{slug}/jobs?page={page}")
        if not d:
            break
        jobs = d.get("results") or d.get("jobs") or []
        if not jobs:
            break
        for j in jobs:
            code = j.get("shortcode") or j.get("id")
            if not code or code in seen:
                continue
            seen.add(code)
            loc = j.get("location") or {}
            if isinstance(loc, dict):
                loc = ", ".join(x for x in [loc.get("city"), loc.get("region"), loc.get("country")] if x)
            loc = loc or ", ".join(x for x in [j.get("city"), j.get("state"), j.get("country")] if x)
            out.append(Job(
                source="workable", company=slug, id=f"wk-{slug}-{code}",
                title=j.get("title", ""),
                url=j.get("url") or f"https://apply.workable.com/j/{code}",
                location=loc,
                updated=j.get("published_on") or j.get("created_at") or "",
                content=strip_tags(j.get("description") or "")[:MAX_CONTENT],
            ))
        page += 1
    if out:
        return out
    # Fallback: v1 widget endpoint (v3 is not always exposed).
    d = get(f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true")
    if not d or "jobs" not in d:
        return []
    for j in d["jobs"]:
        code = j.get("shortcode") or j.get("id")
        if not code or code in seen:
            continue
        seen.add(code)
        loc = ", ".join(x for x in [j.get("city"), j.get("state"), j.get("country")] if x)
        out.append(Job(
            source="workable", company=slug, id=f"wk-{slug}-{code}",
            title=j.get("title", ""),
            url=j.get("url") or f"https://apply.workable.com/j/{code}",
            location=loc,
            updated=j.get("published_on") or j.get("created_at") or "",
            content=strip_tags(j.get("description") or "")[:MAX_CONTENT],
        ))
    return out


def rippling(slug: str) -> list[Job]:
    q = urllib.parse.quote(slug)
    d = get(f"https://api.rippling.com/platform/api/ats/v1/board/{q}/jobs")
    if isinstance(d, dict):
        jobs = d.get("jobs") or d.get("results") or []
    elif isinstance(d, list):
        jobs = d
    else:
        return []

    def detail(uuid):
        return get(f"https://api.rippling.com/platform/api/ats/v1/board/{q}/jobs/{uuid}")

    descs: dict[str, dict] = {}
    uuids = [j.get("uuid") for j in jobs if j.get("uuid")]
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(detail, u): u for u in uuids}
        for f in concurrent.futures.as_completed(futs):
            try:
                r = f.result()
            except Exception:
                r = None
            if isinstance(r, dict):
                descs[futs[f]] = r

    out = []
    for j in jobs:
        uuid = j.get("uuid")
        if not uuid:
            continue
        wl = j.get("workLocation") or {}
        loc = (wl.get("label") or wl.get("id") or "") if isinstance(wl, dict) else str(wl)
        det = descs.get(uuid, {})
        parts = []
        desc = det.get("description")
        if isinstance(desc, dict):
            for k in ("company", "role"):
                if desc.get(k):
                    parts.append(strip_tags(desc[k]))
        elif isinstance(desc, str):
            parts.append(strip_tags(desc))
        out.append(Job(
            source="rippling", company=slug, id=f"rp-{slug}-{uuid}",
            title=j.get("name", ""),
            url=j.get("url") or f"https://ats.rippling.com/{q}/jobs/{uuid}",
            location=loc,
            updated=det.get("createdOn", ""),
            content="\n\n".join(p for p in parts if p).strip()[:MAX_CONTENT],
        ))
    return out


def workday(spec: dict) -> list[Job]:
    """Workday CXS JSON API. spec: {tenant, site, host?, search?, limit?}.

    The search key is 'searchText'. 'searchFor'/'search'/'query' are accepted
    by the endpoint but IGNORED (they silently return the full board).
    """
    tenant = spec["tenant"]
    site = spec["site"]
    host = spec.get("host", "wd1")
    url = f"https://{tenant}.{host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    out: list[Job] = []
    offset = 0
    limit = spec.get("limit", 20)
    max_jobs = spec.get("max_jobs", 500)
    while offset < max_jobs:
        body = {"appliedFacets": spec.get("facets", {}), "limit": limit,
                "offset": offset, "searchText": spec.get("search", "")}
        d = get(url, method="POST", body=body, tries=4, sleep=1.5)
        if not d or d.get("total") is None:
            break
        postings = d.get("jobPostings", [])
        if not postings:
            break
        for j in postings:
            path = j.get("externalPath", "")
            if not path:
                continue
            out.append(Job(
                source="workday", company=tenant, id=f"wd-{tenant}-{path.rsplit('_',1)[-1]}",
                title=j.get("title", ""),
                url=f"https://{tenant}.{host}.myworkdayjobs.com/en-US/{site}{path}",
                location=", ".join(j.get("locationsText", "").split("\n")),
                updated=j.get("postedOn", ""),
                content="",  # Workday list API has no body; fetch the job page for it
            ))
        total = d.get("total", 0)
        offset += limit
        if offset >= min(total, max_jobs):
            break
    return out


FETCHERS = {
    "greenhouse": greenhouse,
    "lever": lever,
    "ashby": ashby,
    "workable": workable,
    "rippling": rippling,
}


def fetch_all(companies: dict, workday_specs: list[dict] | None = None,
              max_workers: int = 20) -> list[Job]:
    """Fetch every board. companies: {ats_type: [slug, ...]}."""
    jobs: list[Job] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {}
        for ats, slugs in companies.items():
            fn = FETCHERS.get(ats)
            if not fn:
                continue
            for slug in slugs:
                futs[ex.submit(fn, slug)] = (ats, slug)
        for f in concurrent.futures.as_completed(futs):
            try:
                jobs.extend(f.result())
            except Exception:
                pass
    for spec in (workday_specs or []):
        try:
            jobs.extend(workday(spec))
        except Exception:
            pass
    return jobs
