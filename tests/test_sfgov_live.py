"""Live smoke test for the SmartRecruiters board, targeting the City and
County of San Francisco. Skipped unless RUN_LIVE=1.

Platform verdict: careers.sfgov.org does not resolve; the live SF portal
careers.sf.gov runs on SmartRecruiters (company CityAndCountyOfSanFrancisco1),
not NeoGov. See jobhunt.boards.smartrecruiters.
"""
import os

import pytest

from jobhunt.boards.smartrecruiters import SmartRecruitersBoard

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE") != "1", reason="set RUN_LIVE=1 to hit live APIs")

COMPANY = "CityAndCountyOfSanFrancisco1"


def test_sfgov_smartrecruiters_live():
    jobs = SmartRecruitersBoard([{"company": COMPANY, "max_jobs": 30}]).fetch()
    assert len(jobs) > 0
    assert all(j.title and j.url.startswith("http") for j in jobs[:5])
    assert all("jobs.smartrecruiters.com" in j.url for j in jobs[:5])
    # location and content come from the list payload + per-job detail fetch
    assert any(j.location for j in jobs)
    assert any(len(j.content) > 100 for j in jobs)


def test_sfgov_keyword_filter_live():
    jobs = SmartRecruitersBoard(
        [{"company": COMPANY, "q": "engineer", "max_jobs": 15}]).fetch()
    assert len(jobs) > 0
    assert any("engineer" in j.title.lower() for j in jobs)
