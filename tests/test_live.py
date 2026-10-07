"""Live smoke test: hits real public ATS APIs. Skipped unless RUN_LIVE=1."""
import os
import pytest

from jobhunt.fetchers import greenhouse, lever, ashby, workable, rippling, workday

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE") != "1", reason="set RUN_LIVE=1 to hit live APIs")


def test_greenhouse_live():
    jobs = greenhouse("stripe")
    assert len(jobs) > 0
    assert all(j.url.startswith("http") and j.title for j in jobs[:5])


def test_ashby_live():
    jobs = ashby("openai")
    assert len(jobs) > 0


def test_lever_live():
    jobs = lever("dexterity")
    assert len(jobs) > 0


def test_workable_live():
    jobs = workable("raydar")
    assert len(jobs) > 0


def test_rippling_live():
    jobs = rippling("positron")
    assert len(jobs) > 0
    assert any(len(j.content) > 100 for j in jobs)


def test_workday_live():
    jobs = workday({"tenant": "salesforce", "site": "External_Career_Site",
                    "host": "wd12", "search": "full stack", "max_jobs": 40})
    assert len(jobs) > 0
    assert "myworkdayjobs.com" in jobs[0].url
