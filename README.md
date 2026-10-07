# jobhunt

Fetch and match engineering jobs from public ATS boards. No API keys, no
scraping of aggregator sites — every source is the company's own public
job-board API.

Supported boards:

| ATS        | Endpoint                                              |
|------------|-------------------------------------------------------|
| Greenhouse | `boards-api.greenhouse.io/v1/boards/{slug}/jobs`      |
| Lever      | `api.lever.co/v0/postings/{slug}`                     |
| Ashby      | `api.ashbyhq.com/posting-api/job-board/{slug}`        |
| Workable   | `apply.workable.com/api/v3/accounts/{slug}/jobs` (v1 widget fallback) |
| Rippling   | `api.rippling.com/platform/api/ats/v1/board/{slug}/jobs` |
| Workday    | `{tenant}.{host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` (POST) |

## Install

```bash
pip install jobhunt        # or: pip install git+https://github.com/wokhouse/jobhunt.git
```

## Quick start

1. Copy `examples/profile.example.yaml` and edit it. A profile has two parts:
   `boards` (which companies to watch) and `criteria` (what you accept).

2. Fetch and match:

```bash
jobhunt -p my.yaml run --outdir out
# fetched 4127 jobs; matched 38 -> out/matches.json
```

Other commands:

```bash
jobhunt -p my.yaml boards          # probe every slug; exit 1 if any board is dead
jobhunt -p my.yaml fetch --out raw_jobs.json
jobhunt -p my.yaml match --jobs raw_jobs.json -v   # -v prints rejection reasons
```

## Profile schema

```yaml
name: my-search
boards:
  greenhouse: [stripe, ramp]
  ashby: [openai, hex]
  lever: [dexterity]
  workable: [raydar]
  rippling: [positron]
  workday:
    - tenant: salesforce
      site: External_Career_Site
      host: wd12          # wd1/wd3/wd12... varies per tenant
      search: "full stack"
      max_jobs: 200

criteria:
  title_include: [engineer]          # lowercase substring match on title
  title_exclude: [manager, intern, sales]
  locations: [san francisco, remote] # substring match on location or body head; empty = any
  exclude_locations: [remote only]
  max_years_required: 6              # reject postings requiring more
  min_salary: 200000                 # posted range must reach it; unposted = pass with note
  require_terms: [typescript]        # all must appear in title+body
  any_of_terms: [react, next.js]     # at least one must appear
  exclude_terms: [clearance required]
  max_age_days: 45                   # drop stale postings when the board reports dates
```

Criteria are yours. The library ships no defaults: an empty `criteria` block
passes everything, which is useful when you only want the fetch layer.

## Python API

```python
from jobhunt.profile import Profile
from jobhunt.fetchers import fetch_all
from jobhunt.matcher import dedupe, evaluate

p = Profile.load("my.yaml")
jobs = dedupe(fetch_all(p.boards, getattr(p, "workday_specs", None)))
matches = [v for v in (evaluate(j, p.criteria) for j in jobs) if v.passed]
for v in matches:
    print(v.job.company, v.job.title, v.job.url)
```

Each fetcher returns normalized `Job` records: `source`, `company`, `id`,
`title`, `url`, `location`, `updated`, `content` (plain text, 12k cap).

## Notes on the boards

- **Workday**: the search key is `searchText`. `searchFor`, `search`, and
  `query` are accepted but silently ignored — they return the whole board.
  The API is rate-limited; the client retries with backoff. List results have
  no job body, so salary/term gates need the job page (not included here).
- **Ashby**: slugs are URL-encoded, so slugs with spaces (`hippocratic ai`)
  work. `isListed: false` postings are skipped.
- **Workable**: the v3 accounts API 404s for some accounts; the fetcher falls
  back to the v1 widget endpoint automatically.
- **Rippling**: the board endpoint returns a flat list with no descriptions;
  the fetcher pulls per-job detail pages concurrently.
- **Greenhouse** location strings are inconsistent (`Mountain View, California`
  vs `USA - Mountain View, CA`). Match on the city token.
- Salary parsing is a heuristic: it scans dollar amounts in the body. Treat
  `salary` in the output as a signal, not a guarantee.

## Tests

```bash
pip install -e ".[dev]" && pytest          # unit tests, no network
RUN_LIVE=1 pytest tests/test_live.py       # smoke test against real boards
```

## License

MIT
