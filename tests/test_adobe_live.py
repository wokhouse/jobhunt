"""Live test for Adobe's first-party board. Skipped unless RUN_LIVE=1.

Adobe runs on Workday at adobe.wd5.myworkdayjobs.com, site
'external_experienced'. The built-in 'workday' board covers it with no
board-specific code. Example profile config (equivalent to the spec below):

    boards:
      workday:
        - tenant: adobe
          host: wd5
          site: external_experienced
          terms: ["software engineer", "full stack"]
          max_jobs: 60
"""
import os

import pytest

from jobhunt.boards.workday import WorkdayBoard

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE") != "1", reason="set RUN_LIVE=1 to hit live APIs")

ADOBE_SPEC = {
    "tenant": "adobe",
    "host": "wd5",
    "site": "external_experienced",
    "terms": ["software engineer", "full stack"],
    "max_jobs": 60,
}


def test_adobe_live():
    jobs = WorkdayBoard(ADOBE_SPEC).fetch()
    assert len(jobs) > 0
    assert all("myworkdayjobs.com" in j.url for j in jobs)
    assert any("adobe.wd5.myworkdayjobs.com" in j.url for j in jobs)
    # Normalized fields must be populated on real postings.
    sample = [j for j in jobs if j.title and j.location and j.content]
    assert sample, "expected postings with title, location, and content"
    for j in sample[:5]:
        assert j.url.startswith("http")
