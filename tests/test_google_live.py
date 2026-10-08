"""Live smoke test for the Google Careers board. Skipped unless RUN_LIVE=1.

Google retired its public JSON API; this board scrapes the AF_initDataCallback
JSON embedded in the hosted results pages. See jobhunt.boards.google.
"""
import os

import pytest

from jobhunt.boards.google import GoogleBoard

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE") != "1", reason="set RUN_LIVE=1 to hit live APIs")


def test_google_live():
    jobs = GoogleBoard({"search": "software engineer", "max_jobs": 30}).fetch()
    assert len(jobs) > 0
    assert all(j.title and j.url.startswith("http") for j in jobs[:5])
    assert all("careers/applications/jobs/results" in j.url for j in jobs[:5])
    # list-page records carry the full description, so content should be populated
    assert any(len(j.content) > 100 for j in jobs)


def test_google_location_filter_live():
    jobs = GoogleBoard(
        {"search": "software engineer", "locations": ["United States"],
         "max_jobs": 20}).fetch()
    assert len(jobs) > 0
    assert all(j.location for j in jobs[:5])
