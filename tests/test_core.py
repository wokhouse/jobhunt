import json
import textwrap

from jobhunt.models import Job
from jobhunt.matcher import evaluate, dedupe, title_similarity
from jobhunt.profile import Profile, Criteria
from jobhunt.util import parse_salary_range, parse_min_years, strip_tags


def make_job(**kw):
    base = dict(source="greenhouse", company="acme", id="gh-acme-1",
                title="Senior Product Engineer", url="https://x/1",
                location="San Francisco, CA", updated="2026-10-01T00:00:00.000Z",
                content="You have TypeScript and React experience. "
                        "Salary $200,000 - $260,000. 3+ years required.")
    base.update(kw)
    return Job(**base)


def test_salary_parse():
    assert parse_salary_range("make $180k - $240k") == (180000, 240000)
    assert parse_salary_range("no money here") is None


def test_years_parse():
    assert parse_min_years("5+ years experience, some 2+ years") == 2
    assert parse_min_years("no numbers") is None


def test_strip_tags():
    assert "hello" in strip_tags("<style>x</style><p>hello</p>")


def test_criteria_pass():
    c = Criteria(title_include=["engineer"], locations=["san francisco"],
                 max_years_required=6, min_salary=200000,
                 any_of_terms=["typescript"])
    v = evaluate(make_job(), c)
    assert v.passed, v.reasons
    assert v.salary == (200000, 260000)
    assert v.min_years == 3


def test_criteria_reject_years():
    c = Criteria(max_years_required=2)
    v = evaluate(make_job(), c)
    assert not v.passed
    assert any("experience" in r for r in v.reasons)


def test_criteria_reject_title():
    c = Criteria(title_exclude=["senior product"])
    v = evaluate(make_job(), c)
    assert not v.passed


def test_criteria_reject_location():
    c = Criteria(locations=["london"])
    v = evaluate(make_job(), c)
    assert not v.passed


def test_unposted_salary_passes_with_note():
    c = Criteria(min_salary=200000)
    v = evaluate(make_job(content="no salary listed here"), c)
    assert v.passed
    assert any("unposted" in r for r in v.reasons)


def test_dedupe():
    a = make_job(id="1", url="https://x/1")
    b = make_job(id="2", url="https://x/1")            # same URL
    c = make_job(id="3", url="https://x/2", title="Senior Product Engineer ")  # near-dup title
    d = make_job(id="4", url="https://x/3", title="Staff Frontend Engineer")
    kept = dedupe([a, b, c, d])
    assert [j.id for j in kept] == ["1", "4"]


def test_title_similarity():
    assert title_similarity("Senior Product Engineer", "Product Engineer, Senior") == 1.0
    assert title_similarity("Careers", "Senior Product Engineer") < 0.5


def test_profile_load(tmp_path):
    p = tmp_path / "p.yaml"
    p.write_text(textwrap.dedent("""
        name: t
        boards:
          greenhouse: [stripe]
          workday:
            - tenant: salesforce
              site: External_Career_Site
              host: wd12
        criteria:
          min_salary: 100000
    """))
    prof = Profile.load(p)
    assert prof.boards == {"greenhouse": ["stripe"]}
    assert prof.workday_specs[0]["tenant"] == "salesforce"
    assert prof.criteria.min_salary == 100000
