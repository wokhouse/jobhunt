"""jobhunt CLI: fetch boards, run the filter pipeline, verify links."""
import argparse
import json
import sys
from pathlib import Path

from .models import Job
from .pipeline import build_boards, run_pipeline
from .profile import Profile
from .registry import BOARDS, FILTERS, JUDGES, load_plugins


def _rows(jobs: list[Job]) -> list[dict]:
    rows = []
    for j in jobs:
        d = j.to_dict()
        d.pop("content", None)
        rows.append(d)
    return rows


def cmd_fetch(args) -> int:
    p = Profile.load(args.profile)
    res = run_pipeline(p, fetch_only=True)
    out = Path(args.out)
    out.write_text(json.dumps([j.to_dict() for j in res["jobs"]], indent=1))
    boards = len({(j.source, j.company) for j in res["jobs"]})
    print(f"fetched {len(res['jobs'])} jobs from {boards} boards -> {out}")
    return 0


def cmd_match(args) -> int:
    p = Profile.load(args.profile)
    raw = json.loads(Path(args.jobs).read_text())
    jobs = [Job(**{k: j.get(k, {} if k == "extra" else "")
                   for k in ("source", "company", "id", "title", "url",
                             "location", "updated", "content", "extra")})
            for j in raw]
    res = run_pipeline(p, match_only=True, raw_jobs=jobs)
    out = Path(args.out)
    out.write_text(json.dumps(_rows(res["matches"]), indent=1))
    print(f"matched {len(res['matches'])} / {len(res['jobs'])} jobs -> {out}")
    if args.verbose:
        for jid, why in res["rejected"].items():
            print(f"REJECT {jid} :: {why}", file=sys.stderr)
    return 0


def cmd_run(args) -> int:
    p = Profile.load(args.profile)
    res = run_pipeline(p)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "raw_jobs.json").write_text(
        json.dumps([j.to_dict() for j in res["jobs"]], indent=1))
    (outdir / "matches.json").write_text(
        json.dumps(_rows(res["matches"]), indent=1))
    print(f"fetched {len(res['jobs'])} jobs; matched {len(res['matches'])} "
          f"-> {outdir}/matches.json")
    return 0


def cmd_boards(args) -> int:
    """Probe each configured board; report job counts or DEAD."""
    p = Profile.load(args.profile)
    load_plugins()
    bad = 0
    for board in build_boards(p):
        try:
            jobs = board.fetch()
        except Exception as e:
            jobs = []
            print(f"{board.name}: ERROR {e}")
        status = f"{len(jobs)} jobs" if jobs else "DEAD/EMPTY"
        if not jobs:
            bad += 1
        print(f"{board.name}: {status}")
    return 1 if bad else 0


def cmd_plugins(args) -> int:
    load_plugins()
    from . import discover as _discover  # noqa: F401 (registers built-in sources)
    print("boards:", ", ".join(sorted(BOARDS)))
    print("filters:", ", ".join(sorted(FILTERS)))
    print("judges:", ", ".join(sorted(JUDGES)))
    from .registry import SOURCES
    print("sources:", ", ".join(sorted(SOURCES)))
    return 0


def cmd_discover(args) -> int:
    """Scrape public aggregator boards, resolve companies to first-party
    ATS boards, write a merged profile + company report. Optionally fetch
    and match the resolved boards in the same pass."""
    from .discover import collect_leads, resolve_leads, board_specs_from_resolutions
    p = Profile.load(args.profile)
    if not p.discover:
        print("profile has no 'discover:' block; nothing to scrape", file=sys.stderr)
        return 1

    leads = collect_leads(p)
    companies = {}
    for lead in leads:
        companies.setdefault(lead.company, lead)
    resolutions = resolve_leads(leads)
    verified = {c: r for c, r in resolutions.items() if r.get("verified")}

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    report = []
    for company, res in sorted(resolutions.items()):
        lead = res["leads"][0]
        report.append({
            "company": company,
            "display": lead.company_display,
            "lead_source": lead.source,
            "lead_title": lead.title,
            "lead_url": lead.url,
            "ats": res["kind"],
            "slug": res.get("slug") or f"{res.get('tenant')}/{res.get('site')}",
            "verified_title_match": bool(res.get("verified")),
            "board_jobs": res.get("board_jobs", 0),
            "leads": len(res["leads"]),
        })
    (outdir / "companies.json").write_text(json.dumps(report, indent=1))

    specs = board_specs_from_resolutions(verified or resolutions)
    merged = dict(p.boards or {})
    for kind, entries in specs.items():
        merged.setdefault(kind, [])
        for e in entries:
            if e not in merged[kind]:
                merged[kind].append(e)

    import yaml
    prof_out = {
        "name": f"{p.name}-discovered",
        "boards": merged,
        "filters": p.filters or [{"name": "criteria", **p.criteria_raw}],
    }
    if p.judge_rubric:
        prof_out["judge_rubric"] = p.judge_rubric
    prof_path = outdir / "profile.discovered.yaml"
    prof_path.write_text(yaml.safe_dump(prof_out, sort_keys=False))

    print(f"leads: {len(leads)} from {len(p.discover)} source(s); "
          f"companies: {len(companies)}; resolved: {len(resolutions)} "
          f"({len(verified)} title-verified)")
    print(f"report -> {outdir}/companies.json")
    print(f"merged profile -> {prof_path}")

    if args.fetch:
        from .discover import merge_specs
        merge_specs(p, specs)
        from .pipeline import run_pipeline
        res = run_pipeline(p)
        (outdir / "raw_jobs.json").write_text(
            json.dumps([j.to_dict() for j in res["jobs"]], indent=1))
        (outdir / "matches.json").write_text(
            json.dumps(_rows(res["matches"]), indent=1))
        print(f"fetched {len(res['jobs'])} jobs; matched {len(res['matches'])} "
              f"-> {outdir}/matches.json")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jobhunt",
        description="Fetch and match engineering jobs from pluggable job boards.")
    ap.add_argument("--profile", "-p", required=True, help="profile YAML path")
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="fetch all boards to JSON")
    f.add_argument("--out", default="raw_jobs.json")
    f.set_defaults(fn=cmd_fetch)

    m = sub.add_parser("match", help="run the filter pipeline on an existing raw_jobs.json")
    m.add_argument("--jobs", default="raw_jobs.json")
    m.add_argument("--out", default="matches.json")
    m.add_argument("-v", "--verbose", action="store_true")
    m.set_defaults(fn=cmd_match)

    r = sub.add_parser("run", help="fetch + filter in one pass")
    r.add_argument("--outdir", default="out")
    r.set_defaults(fn=cmd_run)

    b = sub.add_parser("boards", help="probe every configured board (exit 1 if any dead)")
    b.set_defaults(fn=cmd_boards)

    d = sub.add_parser("discover",
        help="scrape public aggregator boards, resolve companies to their "
             "first-party ATS boards, write a merged profile")
    d.add_argument("--outdir", default="discovered")
    d.add_argument("--fetch", action="store_true",
                   help="also fetch + match the resolved boards in this pass")
    d.set_defaults(fn=cmd_discover)

    pl = sub.add_parser("plugins", help="list registered boards/filters/judges")
    pl.set_defaults(fn=cmd_plugins)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
