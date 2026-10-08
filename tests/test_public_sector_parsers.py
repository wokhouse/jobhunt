"""Offline parser tests for the public-sector boards (no network).

Fixtures are real captured responses (2026-10-08):
  pageup_listing.html      jobs.sfsu.edu listing page 1
  uc_search.html           jobs.universityofcalifornia.edu advancedsearch (Berkeley)
  oracle_rows.json         Stanford Recruiting Cloud requisition rows
  smartrecruiters_postings.json  SF postings list page

These guard the HTML/JSON parsing against upstream markup drift without
needing RUN_LIVE.
"""
import json
import pathlib

from jobhunt.boards.pageup import _parse as pageup_parse
from jobhunt.boards.uc_systemwide import _parse as uc_parse
from jobhunt.boards.oracle_recruiting import _locations
from jobhunt.boards.smartrecruiters import _loc, _content

FX = pathlib.Path(__file__).parent / "fixtures"


def test_pageup_parse_fixture():
    rows = pageup_parse(FX.joinpath("pageup_listing.html").read_text(), "jobs.sfsu.edu")
    assert len(rows) == 40
    assert all(r["title"] and r["url"].startswith("https://jobs.sfsu.edu") for r in rows)
    assert sum(1 for r in rows if r["location"]) >= 35
    assert any(r["summary"] for r in rows)


def test_uc_parse_fixture():
    rows = uc_parse(FX.joinpath("uc_search.html").read_text())
    assert len(rows) >= 8
    assert all(r["title"] and r["url"] for r in rows)
    assert sum(1 for r in rows if r["location"]) >= 6


def test_oracle_locations_fixture():
    rows = json.loads(FX.joinpath("oracle_rows.json").read_text())
    assert len(rows) == 5
    for r in rows:
        assert "Stanford" in _locations(r)


def test_smartrecruiters_fixture():
    d = json.loads(FX.joinpath("smartrecruiters_postings.json").read_text())
    rows = d["content"]
    assert d["totalFound"] >= len(rows) > 0
    for r in rows:
        assert r["id"] and r["name"]
        assert _loc(r.get("location"))
