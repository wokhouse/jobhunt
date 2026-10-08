"""Live smoke tests: hit real public ATS APIs. Skipped unless RUN_LIVE=1."""
import os
import pytest

from jobhunt.boards.ashby import AshbyBoard
from jobhunt.boards.greenhouse import GreenhouseBoard
from jobhunt.boards.lever import LeverBoard
from jobhunt.boards.rippling import RipplingBoard
from jobhunt.boards.workable import WorkableBoard
from jobhunt.boards.workday import WorkdayBoard

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE") != "1", reason="set RUN_LIVE=1 to hit live APIs")


def test_greenhouse_live():
    jobs = GreenhouseBoard(["stripe"]).fetch()
    assert len(jobs) > 0
    assert all(j.url.startswith("http") and j.title for j in jobs[:5])


def test_ashby_live():
    jobs = AshbyBoard(["openai"]).fetch()
    assert len(jobs) > 0


def test_lever_live():
    jobs = LeverBoard(["dexterity"]).fetch()
    assert len(jobs) > 0


def test_workable_live():
    jobs = WorkableBoard(["raydar"]).fetch()
    assert len(jobs) > 0


def test_rippling_live():
    jobs = RipplingBoard(["positron"]).fetch()
    assert len(jobs) > 0
    assert any(len(j.content) > 100 for j in jobs)


def test_workday_live():
    jobs = WorkdayBoard([{"tenant": "salesforce", "site": "External_Career_Site",
                          "host": "wd12", "terms": ["full stack"],
                          "max_jobs": 40}]).fetch()
    assert len(jobs) > 0
    assert "myworkdayjobs.com" in jobs[0].url


def test_sources_live():
    from jobhunt.sources import HimalayasSource, RemotiveSource, WwrSource
    r = RemotiveSource({"search": "software engineer", "max_leads": 10}).leads()
    h = HimalayasSource({"search": "frontend engineer", "max_leads": 10}).leads()
    w = WwrSource({"category": "programming", "max_leads": 10}).leads()
    assert len(r) > 0 and all(l.company and l.title for l in r)
    assert len(h) > 0 and all(l.company and l.title for l in h)
    assert len(w) > 0


def test_discover_resolve_live():
    """End-to-end: aggregator lead -> first-party ATS board resolution."""
    from jobhunt.discover import resolve_leads
    from jobhunt.sources.base import Lead
    leads = [
        Lead(source="test", company="pinterest", company_display="Pinterest",
             title="Machine Learning Engineer, Core Engineering",
             url="https://aggregator/x"),
        Lead(source="test", company="dremio", company_display="Dremio",
             title="Software Engineer - Query Execution",
             url="https://aggregator/y"),
    ]
    res = resolve_leads(leads)
    assert "pinterest" in res and res["pinterest"]["kind"] == "greenhouse"
    assert res["pinterest"]["verified"]
    assert "dremio" in res and res["dremio"]["kind"] == "greenhouse"
    assert res["dremio"]["verified"]
