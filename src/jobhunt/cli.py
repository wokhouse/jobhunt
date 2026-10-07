"""jobhunt CLI: fetch boards, match against a profile, verify links."""
import argparse
import json
import sys
from pathlib import Path

from .fetchers import fetch_all
from .matcher import dedupe, evaluate
from .profile import Profile


def _load_jobs(path: Path) -> list[dict]:
    return json.loads(path.read_text())


def cmd_fetch(args) -> int:
    p = Profile.load(args.profile)
    jobs = fetch_all(p.boards, getattr(p, "workday_specs", None))
    out = Path(args.out)
    out.write_text(json.dumps([j.to_dict() for j in jobs], indent=1))
    boards = len({(j.source, j.company) for j in jobs})
    print(f"fetched {len(jobs)} jobs from {boards} boards -> {out}")
    return 0


def cmd_match(args) -> int:
    p = Profile.load(args.profile)
    raw = _load_jobs(Path(args.jobs))
    from .models import Job
    jobs2 = []
    for j in raw:
        jobs2.append(Job(
            source=j.get("source", ""), company=j.get("company", ""),
            id=j.get("id", ""), title=j.get("title", ""), url=j.get("url", ""),
            location=j.get("location", ""), updated=j.get("updated", ""),
            content=j.get("content", ""), extra=j.get("extra", {})))
    jobs2 = dedupe(jobs2)
    verdicts = [evaluate(j, p.criteria) for j in jobs2]
    passed = [v for v in verdicts if v.passed]
    out = Path(args.out)
    rows = []
    for v in passed:
        d = v.job.to_dict()
        d.pop("content", None)
        d["salary"] = list(v.salary) if v.salary else None
        d["min_years"] = v.min_years
        rows.append(d)
    out.write_text(json.dumps(rows, indent=1))
    print(f"matched {len(passed)} / {len(verdicts)} jobs -> {out}")
    if args.verbose:
        for v in verdicts:
            if not v.passed:
                print(f"REJECT {v.job.company}: {v.job.title} :: {'; '.join(v.reasons)}",
                      file=sys.stderr)
    return 0


def cmd_run(args) -> int:
    p = Profile.load(args.profile)
    jobs = fetch_all(p.boards, getattr(p, "workday_specs", None))
    jobs = dedupe(jobs)
    verdicts = [evaluate(j, p.criteria) for j in jobs]
    passed = [v for v in verdicts if v.passed]
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "raw_jobs.json").write_text(
        json.dumps([j.to_dict() for j in jobs], indent=1))
    rows = []
    for v in passed:
        d = v.job.to_dict()
        d.pop("content", None)
        d["salary"] = list(v.salary) if v.salary else None
        d["min_years"] = v.min_years
        rows.append(d)
    (outdir / "matches.json").write_text(json.dumps(rows, indent=1))
    print(f"fetched {len(jobs)} jobs; matched {len(passed)} -> {outdir}/matches.json")
    return 0


def cmd_boards(args) -> int:
    """Probe each configured board slug; report job counts or DEAD."""
    p = Profile.load(args.profile)
    bad = 0
    for ats, slugs in p.boards.items():
        for slug in slugs:
            from .fetchers import FETCHERS
            fn = FETCHERS.get(ats)
            if not fn:
                print(f"{ats} {slug}: unknown ATS")
                continue
            jobs = fn(slug)
            status = f"{len(jobs)} jobs" if jobs else "DEAD/EMPTY"
            if not jobs:
                bad += 1
            print(f"{ats} {slug}: {status}")
    for spec in getattr(p, "workday_specs", []):
        from .fetchers import workday
        jobs = workday({**spec, "max_jobs": 20})
        status = f"{len(jobs)} jobs (sampled)" if jobs else "DEAD/EMPTY"
        if not jobs:
            bad += 1
        print(f"workday {spec.get('tenant')}/{spec.get('site')}: {status}")
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jobhunt",
        description="Fetch and match engineering jobs from public ATS boards.")
    ap.add_argument("--profile", "-p", required=True, help="profile YAML path")
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="fetch all boards to JSON")
    f.add_argument("--out", default="raw_jobs.json")
    f.set_defaults(fn=cmd_fetch)

    m = sub.add_parser("match", help="score an existing raw_jobs.json against the profile")
    m.add_argument("--jobs", default="raw_jobs.json")
    m.add_argument("--out", default="matches.json")
    m.add_argument("-v", "--verbose", action="store_true")
    m.set_defaults(fn=cmd_match)

    r = sub.add_parser("run", help="fetch + match in one pass")
    r.add_argument("--outdir", default="out")
    r.set_defaults(fn=cmd_run)

    b = sub.add_parser("boards", help="probe every board slug (exit 1 if any dead)")
    b.set_defaults(fn=cmd_boards)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
