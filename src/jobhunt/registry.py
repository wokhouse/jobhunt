"""Plugin registry for boards, filters, and judges.

Built-ins register via decorators at import time. Third-party packages
register via entry points (see README):

    [project.entry-points."jobhunt.boards"]
    myboard = "my_pkg.jobhunt_plugin:MyBoard"
"""
from importlib.metadata import entry_points

BOARDS: dict[str, type] = {}
FILTERS: dict[str, type] = {}
JUDGES: dict[str, type] = {}
SOURCES: dict[str, type] = {}


def register_board(name: str):
    def deco(cls):
        cls.name = name
        BOARDS[name] = cls
        return cls
    return deco


def register_filter(name: str):
    def deco(cls):
        cls.name = name
        FILTERS[name] = cls
        return cls
    return deco


def register_judge(name: str):
    def deco(cls):
        cls.name = name
        JUDGES[name] = cls
        return cls
    return deco


def register_source(name: str):
    def deco(cls):
        cls.name = name
        SOURCES[name] = cls
        return cls
    return deco


def load_plugins() -> None:
    """Load third-party plugins registered via entry points."""
    for group, table in (
        ("jobhunt.boards", BOARDS),
        ("jobhunt.filters", FILTERS),
        ("jobhunt.judges", JUDGES),
        ("jobhunt.sources", SOURCES),
    ):
        try:
            for ep in entry_points(group=group):
                table[ep.name] = ep.load()
        except Exception:
            pass
