"""Discovery pipeline: public boards -> company leads -> first-party ATS.

discover_companies(profile) scrapes every Source in profile.discover,
resolves each company to its first-party ATS board, and returns board
specs that merge into profile.boards. Jobs are then fetched from the
company's own board (Greenhouse/Ashby/Lever/...), never the aggregator.
"""
from concurrent.futures import ThreadPoolExecutor

from . import sources as _sources  # noqa: F401 (registers built-in sources)
from .registry import SOURCES, load_plugins
from .resolver import resolve_company


def build_sources(profile) -> list:
    load_plugins()
    out = []
    for name, cfg in (profile.discover or {}).items():
        cls = SOURCES.get(name)
        if cls is None:
            raise KeyError(f"unknown source {name!r}; registered: {sorted(SOURCES)}")
        out.append(cls(cfg))
    return out


def collect_leads(profile) -> list:
    """Scrape all configured aggregator boards; dedupe by (company, title)."""
    leads = []
    seen: set[tuple[str, str]] = set()
    for src in build_sources(profile):
        try:
            got = src.leads()
        except Exception as e:
            print(f"[discover] source {src.name} failed: {e}")
            continue
        for lead in got:
            key = (lead.company, lead.title.lower())
            if key in seen:
                continue
            seen.add(key)
            leads.append(lead)
    return leads


def resolve_leads(leads, *, workers: int = 8) -> dict:
    """Resolve leads to first-party boards. Returns {company: resolution}.

    resolution = {kind, slug|tenant/site, verified, board_jobs, lead}
    """
    resolutions: dict[str, dict] = {}
    by_company: dict[str, list] = {}
    for lead in leads:
        by_company.setdefault(lead.company, []).append(lead)

    def one(company):
        lead = by_company[company][0]
        res = resolve_company(lead)
        if res:
            res["leads"] = by_company[company]
        return company, res

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for company, res in ex.map(one, by_company):
            if res:
                resolutions[company] = res
    return resolutions


def board_specs_from_resolutions(resolutions: dict) -> dict:
    """Turn resolutions into profile.boards-shaped specs (mergeable)."""
    specs: dict = {}
    for company, res in resolutions.items():
        kind = res["kind"]
        if kind == "workday":
            entry = {"tenant": res["tenant"], "host": res["host"],
                     "site": res["site"],
                     "terms": res.get("terms") or ["software engineer"]}
            specs.setdefault("workday", []).append(entry)
        else:
            specs.setdefault(kind, []).append(res["slug"])
    return specs


def merge_specs(profile, specs: dict) -> dict:
    """Merge discovered boards into profile.boards without duplicates."""
    boards = dict(profile.boards or {})
    added: dict[str, int] = {}
    for kind, entries in specs.items():
        cur = list(boards.get(kind) or [])
        cur_keys = {_spec_key(e) for e in cur}
        n = 0
        for e in entries:
            k = _spec_key(e)
            if k in cur_keys:
                continue
            cur_keys.add(k)
            cur.append(e)
            n += 1
        boards[kind] = cur
        if n:
            added[kind] = n
    profile.boards = boards
    return added


def _spec_key(entry):
    if isinstance(entry, str):
        return entry
    return tuple(sorted((k, str(v)) for k, v in entry.items()))
