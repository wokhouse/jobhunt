"""Pipeline: boards -> filter stages -> dedupe -> results."""
from .boards.base import Board  # noqa: F401
from . import boards as _boards  # noqa: F401 (registers built-in boards)
from .filters.base import Filter  # noqa: F401
from . import filters as _filters  # noqa: F401 (registers built-in filters)
from .matcher import dedupe
from .models import Job
from .registry import BOARDS, FILTERS, JUDGES, load_plugins


def build_stages(profile) -> list[Filter]:
    """Instantiate filter stages from profile.filters (ordered list).

    Each entry: {name: <registered filter>, ...its config...}.
    Defaults to [criteria] when absent. 'judge' is shorthand for llm_judge.
    """
    load_plugins()
    specs = profile.filters or [{"name": "criteria", **profile.criteria_raw}]
    stages = []
    for spec in specs:
        spec = dict(spec)
        name = spec.pop("name")
        if name == "judge":
            name = "llm_judge"
        cls = FILTERS.get(name)
        if cls is None:
            raise KeyError(f"unknown filter {name!r}; registered: {sorted(FILTERS)}")
        stages.append(cls(spec, profile=profile))
    return stages


def build_boards(profile) -> list[Board]:
    load_plugins()
    boards = []
    for name, cfg in (profile.boards or {}).items():
        cls = BOARDS.get(name)
        if cls is None:
            raise KeyError(f"unknown board {name!r}; registered: {sorted(BOARDS)}")
        boards.append(cls(cfg))
    return boards


def run_pipeline(profile, *, fetch_only=False, match_only=False,
                 raw_jobs: list[Job] | None = None) -> dict:
    """Returns {jobs, matches, rejected, per_board}."""
    jobs: list[Job] = []
    per_board: dict[str, int] = {}
    if not match_only:
        for board in build_boards(profile):
            got = board.fetch()
            per_board[board.name] = per_board.get(board.name, 0) + len(got)
            jobs.extend(got)
    else:
        jobs = raw_jobs or []
        per_board["(from cache)"] = len(jobs)

    jobs = dedupe(jobs)
    if fetch_only:
        return {"jobs": jobs, "matches": [], "rejected": {}, "per_board": per_board}

    rejected: dict[str, str] = {}
    current = jobs
    for stage in build_stages(profile):
        current, verdicts = stage.filter(current)
        rejected.update(verdicts)
    return {"jobs": jobs, "matches": current, "rejected": rejected,
            "per_board": per_board}
