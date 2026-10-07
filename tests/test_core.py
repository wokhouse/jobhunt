import textwrap

from jobhunt.models import Job
from jobhunt.matcher import dedupe, title_similarity
from jobhunt.profile import Profile
from jobhunt.registry import BOARDS, FILTERS, load_plugins
from jobhunt.util import parse_salary_range, parse_min_years, strip_tags
from jobhunt.filters.criteria import CriteriaFilter, _age_days


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


def test_criteria_filter_pass():
    f = CriteriaFilter({"title_include": ["engineer"], "locations": ["san francisco"],
                        "max_years_required": 6, "min_salary": 200000,
                        "any_of_terms": ["typescript"]})
    kept, rejected = f.filter([make_job()])
    assert kept and not rejected


def test_criteria_filter_reject_years():
    f = CriteriaFilter({"max_years_required": 2})
    kept, rejected = f.filter([make_job()])
    assert not kept
    assert any("years" in v for v in rejected.values())


def test_criteria_filter_reject_title():
    f = CriteriaFilter({"title_exclude": ["senior product"]})
    kept, rejected = f.filter([make_job()])
    assert not kept


def test_criteria_filter_reject_location():
    f = CriteriaFilter({"locations": ["london"]})
    kept, rejected = f.filter([make_job()])
    assert not kept


def test_criteria_filter_default_engineer_gate():
    # no explicit title_include: non-engineer titles are rejected by default
    f = CriteriaFilter({})
    kept, rejected = f.filter([make_job(title="Sales Account Executive")])
    assert not kept


def test_age_days():
    assert _age_days("Posted Today") == 0
    assert _age_days("3 Days Ago") == 3
    assert _age_days("") is None


def test_dedupe():
    a = make_job(id="1", url="https://x/1")
    b = make_job(id="2", url="https://x/1")
    c = make_job(id="3", url="https://x/2", title="Senior Product Engineer ")
    d = make_job(id="4", url="https://x/3", title="Staff Frontend Engineer")
    kept = dedupe([a, b, c, d])
    assert [j.id for j in kept] == ["1", "4"]


def test_title_similarity():
    assert title_similarity("Senior Product Engineer", "Product Engineer, Senior") == 1.0
    assert title_similarity("Careers", "Senior Product Engineer") < 0.5


def test_registry_builtin():
    load_plugins()
    for name in ("greenhouse", "lever", "ashby", "workable", "rippling", "workday"):
        assert name in BOARDS
    assert "criteria" in FILTERS and "llm_judge" in FILTERS


def test_registry_custom_plugin():
    from jobhunt.registry import register_board, register_filter
    from jobhunt.boards.base import Board
    from jobhunt.filters.base import Filter

    @register_board("dummy")
    class DummyBoard(Board):
        def fetch(self):
            return [make_job()]

    @register_filter("keep_all")
    class KeepAll(Filter):
        def filter(self, jobs):
            return jobs, {}

    load_plugins()
    assert "dummy" in BOARDS and "keep_all" in FILTERS


def test_profile_load_new_and_legacy(tmp_path):
    p = tmp_path / "p.yaml"
    p.write_text(textwrap.dedent("""
        name: t
        boards:
          greenhouse: [stripe]
          workday:
            - tenant: salesforce
              site: External_Career_Site
              host: wd12
        filters:
          - name: criteria
            min_salary: 100000
          - name: llm_judge
            base_url: http://localhost:8080/v1
            min_score: 7
        judge_rubric: product engineer, SF or remote
    """))
    prof = Profile.load(p)
    assert prof.boards["workday"][0]["tenant"] == "salesforce"
    assert prof.filters[0]["min_salary"] == 100000
    assert prof.filters[1]["name"] == "llm_judge"
    assert prof.judge_rubric.startswith("product engineer")

    legacy = tmp_path / "l.yaml"
    legacy.write_text(textwrap.dedent("""
        boards:
          greenhouse: [stripe]
        criteria:
          min_salary: 100000
    """))
    prof2 = Profile.load(legacy)
    assert prof2.filters[0]["name"] == "criteria"
    assert prof2.filters[0]["min_salary"] == 100000


def test_pipeline_match_only(tmp_path):
    from jobhunt.pipeline import run_pipeline
    p = tmp_path / "p.yaml"
    p.write_text(textwrap.dedent("""
        boards: {}
        filters:
          - name: criteria
            locations: ["san francisco"]
    """))
    prof = Profile.load(p)
    res = run_pipeline(prof, match_only=True,
                       raw_jobs=[make_job(), make_job(id="2", url="https://x/2",
                                                      title="Sales Director",
                                                      location="London")])
    assert len(res["matches"]) == 1
