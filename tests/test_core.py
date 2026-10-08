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


def test_slugify_and_lead():
    from jobhunt.sources.base import Lead, slugify
    assert slugify("Hinge Health") == "hinge-health"
    assert slugify("  Acme.io ") == "acme-io"
    lead = Lead(source="remotive", company="dremio", company_display="Dremio",
                title="Senior Software Engineer", url="https://remotive/x")
    assert lead.company == "dremio"


BUILTIN_LISTING = """
<html><head><script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
 {"@type":"Organization","name":"Built In"},
 {"@type":"ItemList","itemListElement":[
   {"@type":"ListItem","position":1,"name":"Frontend Engineer",
    "url":"https://www.builtinsf.com/job/frontend-engineer/12345"},
   {"@type":"ListItem","position":2,"name":"Full Stack Engineer",
    "url":"https://www.builtinsf.com/job/full-stack-engineer/67890"},
   {"@type":"ListItem","position":3,"name":"Built In Home",
    "url":"https://www.builtinsf.com/jobs"}
 ]}
]}</script></head><body>jobs</body></html>
"""

BUILTIN_DETAIL = """
<html><head><script type="application/ld+json">
{"@context":"https://schema.org","@type":"JobPosting",
 "title":"Frontend Engineer",
 "datePosted":"2026-10-01",
 "hiringOrganization":{"@type":"Organization","name":"Hinge Health"},
 "jobLocation":{"@type":"Place","address":{
   "@type":"PostalAddress","addressLocality":"San Francisco",
   "addressRegion":"CA"}},
 "baseSalary":{"@type":"MonetaryAmount","value":{
   "@type":"QuantitativeValue","minValue":150000,"maxValue":200000}}
}</script></head><body>job</body></html>
"""


def test_builtin_parse_listing():
    from jobhunt.sources.builtin import parse_listing
    items = parse_listing(BUILTIN_LISTING)
    # only '/job/' entries are kept
    assert [i["title"] for i in items] == ["Frontend Engineer", "Full Stack Engineer"]
    assert all("/job/" in i["url"] for i in items)
    assert items[0]["url"] == "https://www.builtinsf.com/job/frontend-engineer/12345"


def test_builtin_parse_detail():
    from jobhunt.sources.builtin import parse_detail
    d = parse_detail(BUILTIN_DETAIL)
    assert d["company"] == "Hinge Health"
    assert d["title"] == "Frontend Engineer"
    assert d["location"] == "San Francisco, CA"


def test_builtin_parse_detail_skips_companyless():
    from jobhunt.sources.builtin import parse_detail
    assert parse_detail("<html>no ld+json here</html>") is None
    assert parse_detail(
        '<script type="application/ld+json">'
        '{"@type":"JobPosting","title":"X"}</script>') is None


def test_builtin_city_allowlist_and_slug():
    from jobhunt.sources.builtin import BuiltinSource
    import pytest
    assert BuiltinSource({"city": "nyc"}).host == "builtinnyc.com"
    assert BuiltinSource({}).host == "builtinsf.com"
    with pytest.raises(ValueError):
        BuiltinSource({"city": "atlantis"})


def test_builtin_registered():
    import jobhunt.sources  # noqa: F401
    from jobhunt.registry import SOURCES
    assert "builtin" in SOURCES


WAAS_SEARCH = """
{"jobs": [
  {"id": 1, "title": "Software Engineer - Backend", "companyName": "Mason",
   "companySlug": "mason", "location": "Seattle, WA"},
  {"id": 2, "title": "Senior Frontend Engineer", "companyName": "Mason",
   "companySlug": "mason", "location": "Seattle, WA"},
  {"id": 3, "title": "Founding Full Stack Engineer", "companyName": "Hive",
   "companySlug": "hive", "location": "SF"},
  {"id": 4, "title": "Sales Account Executive", "companyName": "Hive",
   "companySlug": "hive", "location": "SF"},
  {"id": 5, "title": "No company here", "companySlug": "ghost"}
]}
"""


def test_waas_parse_jobs():
    import json
    from jobhunt.sources.waas import parse_jobs
    rows = parse_jobs(json.loads(WAAS_SEARCH))
    # entries with no companyName are dropped
    assert [r["company"] for r in rows] == ["mason", "mason", "hive", "hive"]
    assert rows[0]["display"] == "Mason"
    assert parse_jobs(None) == [] and parse_jobs({}) == []


def test_waas_pick_title():
    from jobhunt.sources.waas import pick_title
    titles = ["Software Engineer - Backend", "Senior Frontend Engineer"]
    assert pick_title(titles, "frontend engineer") == "Senior Frontend Engineer"
    # tie on query tokens -> shortest title wins
    assert pick_title(["Software Engineer", "Software Engineer II"],
                      "engineer") == "Software Engineer"
    # no query tokens -> shortest title
    assert pick_title(["A very long title here", "Short"], "") == "Short"


def test_waas_registered():
    import jobhunt.sources  # noqa: F401
    from jobhunt.registry import SOURCES
    assert "waas" in SOURCES


HN_THREAD = """
{"children": [
  {"id": 1, "text": "PrairieLearn (Remote US) — Full-Stack Software Engineer — TypeScript<p>We build an assessment platform."},
  {"id": 2, "text": "<b>Acme Corp</b> | Senior Backend Engineer | Remote<p>We do things."},
  {"id": 3, "text": "<p>| — |</p>"},
  {"id": 4, "text": "Shepherd | ONSITE | San Francisco, CA<p>Autonomous underwriting.</p>"},
  {"id": 5, "text": ""}
]}
"""


def test_hn_clean_text():
    from jobhunt.sources.hn import clean_text
    t = clean_text("A &#x2F; B<p>line two</p>")
    assert t.startswith("A / B")
    assert "line two" in t
    # paragraph break keeps first line separate
    assert clean_text("Head<p>Body").split("\n")[0] == "Head"


def test_hn_parse_comment_strips_trailing_paren_and_url():
    from jobhunt.sources.hn import parse_comment
    p = parse_comment("Snout (YC S24) | Data Engineer | Remote")
    assert p["company"] == "Snout"
    assert p["title"] == "Data Engineer"
    p2 = parse_comment("Smarkets (https:&#x2F;&#x2F;www.smarkets.com) | Full Time")
    assert p2["company"] == "Smarkets"


def test_hn_parse_comment_company_and_role():
    from jobhunt.sources.hn import parse_comment
    p = parse_comment(
        "PrairieLearn (Remote US) — Full-Stack Software Engineer")
    assert p["company"] == "PrairieLearn"
    assert "Software Engineer" in p["title"]
    # leading bold wins over the first plain segment
    p2 = parse_comment("<b>Acme Corp</b> | Senior Backend Engineer | Remote")
    assert p2["company"] == "Acme Corp"
    assert p2["title"] == "Senior Backend Engineer"


def test_hn_parse_comment_skips_unparseable():
    from jobhunt.sources.hn import parse_comment
    assert parse_comment("") is None
    assert parse_comment("<p>| — |</p>") is None


def test_hn_parse_thread():
    import json
    from jobhunt.sources.hn import parse_thread
    posts = parse_thread(json.loads(HN_THREAD))
    # empty text and the companyless prose comment are skipped
    assert len(posts) == 3
    assert [p["company"] for p in posts] == ["PrairieLearn", "Acme Corp", "Shepherd"]
    assert all(p["company"] for p in posts)


def test_hn_registered():
    import jobhunt.sources  # noqa: F401
    from jobhunt.registry import SOURCES
    assert "hn" in SOURCES


def test_resolver_helpers():
    from jobhunt.resolver import core_title, norm_title, slug_ok, title_match
    assert norm_title("Senior Software Engineer, AI") == "senior software engineer ai"
    assert core_title("Senior Software Engineer") == "software engineer"
    assert core_title("Staff Software Engineer II") == "software engineer"
    assert slug_ok("hinge-health", "hinge-health", "Hinge Health")
    assert slug_ok("hippocraticai", "hippocratic-ai", "Hippocratic AI")
    assert slug_ok("stripe", "stripe", "Stripe")
    assert not slug_ok("acme", "stripe", "Stripe")
    jobs = [{"title": "Software Engineer II"}, {"title": "Sales Director"}]
    assert title_match("Senior Software Engineer", jobs)
    assert not title_match("Nurse Practitioner", jobs)


def test_board_specs_and_merge():
    from jobhunt.discover import board_specs_from_resolutions, merge_specs
    res = {
        "stripe": {"kind": "greenhouse", "slug": "stripe", "verified": True,
                   "board_jobs": 10, "leads": []},
        "salesforce": {"kind": "workday", "tenant": "salesforce", "host": "wd12",
                       "site": "External_Career_Site", "terms": ["full stack"],
                       "verified": True, "board_jobs": 5, "leads": []},
    }
    specs = board_specs_from_resolutions(res)
    assert specs["greenhouse"] == ["stripe"]
    assert specs["workday"][0]["tenant"] == "salesforce"

    class P:
        boards = {"greenhouse": ["elastic"]}
    p = P()
    added = merge_specs(p, specs)
    assert p.boards["greenhouse"] == ["elastic", "stripe"]
    assert added == {"greenhouse": 1, "workday": 1}
    # idempotent merge
    added2 = merge_specs(p, specs)
    assert added2 == {}


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
