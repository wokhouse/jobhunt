# jobhunt

Fetch and match jobs from public ATS boards. No API keys for boards — every
job comes from the company's own public job-board API. Optional discovery
scrapes public aggregator boards only to FIND companies; the jobs still come
from each company's first-party board.

Everything is a plugin: **boards** (job sources), **sources** (aggregator
scrapers for discovery), **filters** (match stages), and an optional **LLM
judge** stage. Built-ins register in-process; third parties register via pip
entry points. New job boards merge in without touching the core.

```
discover: public boards ──> company leads ──> first-party ATS resolution
                                                    │
boards ──> dedupe ──> filter stage 1 ──> filter stage 2 ──> ... ──> matches
                       (criteria)         (llm_judge, optional)
```

Built-in boards:

| Board      | Endpoint                                              |
|------------|-------------------------------------------------------|
| Greenhouse | `boards-api.greenhouse.io/v1/boards/{slug}/jobs`      |
| Lever      | `api.lever.co/v0/postings/{slug}`                     |
| Ashby      | `api.ashbyhq.com/posting-api/job-board/{slug}`        |
| Workable   | `apply.workable.com/api/v3/accounts/{slug}/jobs` (v1 widget fallback) |
| Rippling   | `api.rippling.com/platform/api/ats/v1/board/{slug}/jobs` |
| Workday    | `{tenant}.{host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` (POST) |

Built-in filters: `criteria` (keyword rules) and `llm_judge` (optional).
Built-in discovery sources: `remotive`, `himalayas`, `jobicy`, `weworkremotely`, `builtin`.

`builtin` scrapes the Built In network of city boards (builtinsf.com,
builtinnyc.com, and six more) for **company leads only** — jobs are always
fetched from the company's own ATS board later, never from Built In. Configure
it with `city` (one of `sf`, `nyc`, `austin`, `boston`, `chicago`, `dallas`,
`losangeles`, `seattle`; default `sf`) and the usual `search`/`max_leads`.

## Install

```bash
pip install jobhunt        # or: pip install git+https://github.com/wokhouse/jobhunt.git
```

## Quick start

1. Copy `examples/profile.example.yaml` and edit it. A profile has three parts:
   `boards` (what to watch), `filters` (ordered match stages), and
   `judge_rubric` (what the LLM judge optimizes for).

2. Fetch and match:

```bash
jobhunt -p my.yaml run --outdir out
# fetched 2015 jobs; matched 58 -> out/matches.json
```

Other commands:

```bash
jobhunt -p my.yaml boards          # probe every board; exit 1 if any is dead
jobhunt -p my.yaml fetch --out raw_jobs.json
jobhunt -p my.yaml match --jobs raw_jobs.json -v   # -v prints rejection reasons
jobhunt -p my.yaml plugins         # list registered boards/filters/judges/sources
jobhunt -p my.yaml discover --fetch  # scrape public boards, resolve companies, fetch
```

## Discovery: find companies you don't know yet

You cannot pre-list every company. The `discover:` block scrapes public
aggregator boards for (company, role) leads, then resolves each company to
its **first-party ATS board** and pulls jobs from there — the aggregator is
used only to find companies, never as the job source.

```yaml
discover:
  remotive:            # free JSON APIs, no keys
    search: "software engineer"
    max_leads: 60
  himalayas:
    search: "frontend engineer"
  weworkremotely:      # RSS per category
    category: programming
```

Built-in sources: `remotive`, `himalayas`, `jobicy`, `weworkremotely`, `builtin`.
`search` is any career field keyword — tech is the default focus, but
"nurse", "designer", or "accountant" works the same way.

Resolution order per company: probe Greenhouse → Ashby → Lever → Workable →
Rippling APIs with the company slug; if no slug hits, fetch the company's
own careers page and parse ATS links (including Workday tenants). A
resolution is **title-verified** when a job on the resolved board matches
the lead's role, which prevents slug squatting (someone else's board under
the same name).

```bash
jobhunt -p my.yaml discover --outdir discovered
# leads: 62 from 3 source(s); companies: 42; resolved: 17 (6 title-verified)
# report -> discovered/companies.json      (company -> ATS, slug, evidence)
# merged profile -> discovered/profile.discovered.yaml
jobhunt -p discovered/profile.discovered.yaml run --outdir out2
```

Add `--fetch` to fetch + match the resolved boards in the same pass. The
merged profile is a normal jobhunt profile: static `boards:` entries and
discovered ones coexist, and re-running discovery is idempotent (no
duplicate slugs).

## Profile schema

```yaml
name: my-search
boards:
  greenhouse: [stripe, elastic]
  ashby: [openai, hex]
  lever: [dexterity]
  workable: [raydar]
  rippling: [positron]
  workday:
    - tenant: salesforce
      site: External_Career_Site
      host: wd12          # wd1/wd3/wd12... varies per tenant
      terms: ["full stack", "frontend"]
      max_jobs: 200

filters:                  # ordered stages; omit for the default criteria stage
  - name: criteria
    title_include: [engineer]        # regex list on title
    title_exclude: [manager, intern, sales]
    locations: [san francisco, remote]  # substring on location; empty = any
    exclude_locations: []
    max_years_required: 6            # reject postings requiring more
    min_salary: 200000               # posted range must reach it
    any_of_terms: [react, next.js]   # at least one in title+body
    exclude_terms: [clearance required]
    max_age_days: 45

  - name: llm_judge                  # optional second stage
    base_url: http://localhost:8080/v1   # any OpenAI-compatible server
    model: my-model
    api_key_env: MY_API_KEY          # NAME of env var; never the key itself
    min_score: 7
    max_jobs: 200                    # judge at most N keyword survivors
    excerpt: 2500                    # content chars sent per job

judge_rubric: |
  Product engineer or full-stack engineer, mid-to-senior IC.
  SF Bay Area onsite or fully remote. TypeScript + React preferred.
```

A legacy top-level `criteria:` block still works and becomes a single
`criteria` stage.

With no `title_include`, the criteria stage applies a built-in engineering
gate: engineering titles pass, manager/sales/intern titles do not. Give
explicit `title_include`/`title_exclude` lists to override it.

## The LLM judge

The judge runs after keyword filters, on survivors only, so you pay for
tokens on maybe 200 jobs, not 10,000. It sends title, location, and a content
excerpt plus your `judge_rubric` to any OpenAI-compatible chat endpoint
(vLLM, llama.cpp, Ollama `/v1`, OpenAI, ...) and keeps jobs scored at or
above `min_score`. Scores and one-line reasons land in `extra.judge` in the
output JSON. If the judge endpoint is unreachable, jobs are kept with a
"judge error" note — a dead judge never empties your results.

## Writing a plugin

A board is one class:

```python
from jobhunt import register_board
from jobhunt.boards.base import Board
from jobhunt.models import Job

@register_board("myboard")
class MyBoard(Board):
    def fetch(self) -> list[Job]:
        # self.config is the YAML value under 'myboard:' in the profile
        return [Job(source="myboard", company="acme", id="acme-1",
                    title="...", url="https://...", location="...",
                    updated="...", content="...")]
```

A filter is one class:

```python
from jobhunt import register_filter
from jobhunt.filters.base import Filter

@register_filter("no_ai_hype")
class NoAiHype(Filter):
    def filter(self, jobs):
        kept, rejected = [], {}
        for j in jobs:
            if "synergy" in j.content.lower():
                rejected[j.id] = "ai hype"
            else:
                kept.append(j)
        return kept, rejected
```

Ship it in your own package and declare an entry point — `jobhunt plugins`
will show it, and profiles can reference it by name:

```toml
[project.entry-points."jobhunt.boards"]
myboard = "my_pkg.jobhunt_plugin:MyBoard"
```

Groups: `jobhunt.boards`, `jobhunt.filters`, `jobhunt.judges`.

## Python API

```python
from jobhunt.profile import Profile
from jobhunt.pipeline import run_pipeline

p = Profile.load("my.yaml")
res = run_pipeline(p)          # fetch + all filter stages
res["jobs"]                    # deduped raw jobs
res["matches"]                 # survivors (with judge scores in extra)
res["rejected"]                # {job_id: reason}
res["per_board"]               # {board_name: count}
```

All boards return normalized `Job` records: `source`, `company`, `id`,
`title`, `url`, `location`, `updated`, `content` (plain text, 12k cap),
`extra`.

## Notes on the boards

- **Workday**: the search key is `searchText`. `searchFor`, `search`, and
  `query` are accepted but silently ignored — they return the whole board.
  Some multi-word terms report `total: 0` while returning filler postings;
  the client treats that as "term unusable" and stops. The API is
  rate-limited; the client retries with backoff. List results have no job
  body, so the client fetches the CXS detail JSON per job.
- **Ashby**: slugs are URL-encoded, so slugs with spaces (`hippocratic ai`)
  work. `isListed: false` postings are skipped.
- **Workable**: the v3 accounts API 404s for some accounts; the board falls
  back to the v1 widget endpoint automatically.
- **Rippling**: the board endpoint returns a flat list with no descriptions;
  the board pulls per-job detail pages concurrently.
- **Greenhouse** location strings are inconsistent (`Mountain View, California`
  vs `USA - Mountain View, CA`). Match on the city token.
- Salary parsing is a heuristic: it scans dollar amounts in the body. Treat
  salary signals as a signal, not a guarantee.

## Tests

```bash
pip install -e ".[dev]" && pytest          # unit tests, no network
RUN_LIVE=1 pytest tests/test_live.py       # smoke test against real boards
```

## License

MIT
