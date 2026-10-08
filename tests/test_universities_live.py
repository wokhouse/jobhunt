"""Live smoke tests for the Bay Area university boards. Skipped unless RUN_LIVE=1.

Platform families covered:

* Oracle Recruiting Cloud -- Stanford, UCSF (``oracle_recruiting`` board)
* UC systemwide PeopleSoft -- Berkeley (``uc_systemwide`` board)
* PageUp / ClinchTalent -- San Francisco State (``pageup`` board)
* USF runs on Workday -- exercised through the existing ``workday`` board.

See jobhunt.boards.{oracle_recruiting,uc_systemwide,pageup}.
"""
import os

import pytest

from jobhunt.boards.oracle_recruiting import OracleRecruitingBoard
from jobhunt.boards.pageup import PageUpBoard
from jobhunt.boards.uc_systemwide import UcSystemwideBoard
from jobhunt.boards.workday import WorkdayBoard

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE") != "1", reason="set RUN_LIVE=1 to hit live APIs")


def test_stanford_live():
    """Stanford: Oracle Recruiting Cloud, site CX_1."""
    jobs = OracleRecruitingBoard({
        "host": "careersearch.stanford.edu", "site": "CX_1",
        "company": "Stanford", "terms": ["engineer"], "max_jobs": 10}).fetch()
    assert len(jobs) > 0
    assert all(j.title and j.url.startswith("http") for j in jobs)
    assert all(j.location for j in jobs[:3])
    assert any(len(j.content) > 100 for j in jobs)
    assert all("/hcmUI/CandidateExperience/en/sites/CX_1/job/" in j.url for j in jobs)


def test_ucsf_live():
    """UCSF: Oracle Recruiting Cloud, host iazuqy.fa.ocs.oraclecloud.com, site CX_1."""
    jobs = OracleRecruitingBoard({
        "host": "iazuqy.fa.ocs.oraclecloud.com", "site": "CX_1",
        "company": "UCSF", "terms": ["nurse"], "max_jobs": 10}).fetch()
    assert len(jobs) > 0
    assert all(j.title and j.url.startswith("http") for j in jobs)
    assert all(j.location for j in jobs[:3])
    assert any(len(j.content) > 100 for j in jobs)


def test_berkeley_live():
    """Berkeley: UC systemwide board (campus BK), full PeopleSoft detail."""
    jobs = UcSystemwideBoard({
        "campus": "BK", "company": "UC Berkeley",
        "search": "engineer", "detail": True, "max_jobs": 8}).fetch()
    assert len(jobs) > 0
    assert all(j.title and j.url.startswith("http") for j in jobs)
    assert all("universityofcalifornia.edu" in j.url for j in jobs)
    assert all(j.location for j in jobs[:3])


def test_sfsu_live():
    """San Francisco State: PageUp listing (CloudFront/AWS WAF may throttle)."""
    jobs = PageUpBoard({
        "host": "jobs.sfsu.edu", "company": "San Francisco State University",
        "pages": 2, "max_jobs": 40}).fetch()
    assert len(jobs) > 0
    assert all(j.title and j.url.startswith("http") for j in jobs)
    assert all("/en-us/job/" in j.url for j in jobs)
    assert all(j.location for j in jobs[:3])
    assert any(len(j.content) > 50 for j in jobs)


def test_usf_workday_live():
    """USF: runs on Workday (usfca.wd5); covered by the existing workday board."""
    jobs = WorkdayBoard([{
        "tenant": "usfca", "site": "USF_Staff", "host": "wd5",
        "terms": ["assistant"], "max_jobs": 20}]).fetch()
    assert len(jobs) > 0
    assert all("myworkdayjobs.com" in j.url for j in jobs)
    assert any(len(j.content) > 100 for j in jobs)
