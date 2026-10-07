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
    print("boards:", ", ".join(sorted(BOARDS)))
    print("filters:", ", ".join(sorted(FILTERS)))
    print("judges:", ", ".join(sorted(JUDGES)))
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

    pl = sub.add_parser("plugins", help="list registered boards/filters/judges")
    pl.set_defaults(fn=cmd_plugins)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
