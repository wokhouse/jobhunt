"""Optional LLM judge stage.

Runs after keyword filters, on the survivors. Sends each job's title,
location, and a content excerpt to an OpenAI-compatible chat endpoint and
keeps only jobs the model scores at or above `min_score`.

Config:
  base_url   : default http://localhost:8080/v1  (any OpenAI-compatible server:
               vLLM, llama.cpp, Ollama /v1, OpenAI, Synthetic, ...)
  model      : model name the server expects
  api_key_env: NAME of the env var holding the key (never put the key in YAML)
  min_score  : keep jobs scored >= this (default 7)
  max_jobs   : judge at most this many jobs per run (default 200)
  excerpt    : content chars sent per job (default 2500)
  concurrency: parallel requests (default 4)

Prompt is built from profile.judge_rubric (free text describing what you want),
falling back to a generic rubric.
"""
import json
import os
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from ..models import Job
from ..registry import register_filter
from .base import Filter

DEFAULT_PROMPT = (
    "You are a strict job-match judge. Score how well this posting fits the "
    "candidate profile described below. Reply with ONLY a JSON object: "
    '{"score": 0-10, "reason": "one short sentence"}.'
)


def _endpoint(base: str) -> str:
    base = base.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


@register_filter("llm_judge")
class LLMJudge(Filter):
    def filter(self, jobs):
        c = self.config
        base = c.get("base_url", "http://localhost:8080/v1")
        model = c.get("model", "")
        key = os.environ.get(c.get("api_key_env", ""), "")
        min_score = int(c.get("min_score", 7))
        max_jobs = int(c.get("max_jobs", 200))
        excerpt = int(c.get("excerpt", 2500))
        conc = int(c.get("concurrency", 4))

        rubric = DEFAULT_PROMPT
        if self.profile is not None and getattr(self.profile, "judge_rubric", ""):
            rubric = DEFAULT_PROMPT + "\n\nCANDIDATE PROFILE:\n" + self.profile.judge_rubric

        to_judge, verdicts = jobs[:max_jobs], {}
        for j in jobs[max_jobs:]:
            verdicts[j.id] = f"not judged (over max_jobs={max_jobs})"

        def score(j: Job) -> tuple[Job, int, str]:
            user = (
                f"TITLE: {j.title}\nCOMPANY: {j.company}\nLOCATION: {j.location}\n"
                f"POSTING EXCERPT:\n{j.content[:excerpt]}"
            )
            body = {"messages": [{"role": "system", "content": rubric},
                                 {"role": "user", "content": user}],
                    "max_tokens": 1500, "temperature": 0}
            if model:
                body["model"] = model
            hdrs = {"Content-Type": "application/json"}
            if key:
                hdrs["Authorization"] = f"Bearer {key}"
            try:
                req = urllib.request.Request(
                    _endpoint(base), data=json.dumps(body).encode(),
                    headers=hdrs, method="POST")
                with urllib.request.urlopen(req, timeout=120) as r:
                    d = json.loads(r.read().decode())
                txt = d["choices"][0]["message"].get("content") or ""
                if not txt:
                    # reasoning models can exhaust max_tokens before emitting
                    # content; fall back to reasoning text
                    txt = d["choices"][0]["message"].get("reasoning_content") or ""
                m = re.search(r"\{.*?\}", txt, re.S)
                if not m:
                    return j, min_score, "judge error: no JSON in reply"
                obj = json.loads(m.group(0))
                if "score" not in obj:
                    return j, min_score, "judge error: no score field"
                return j, int(obj.get("score", 0)), str(obj.get("reason", ""))
            except Exception as e:
                # judge failure must not destroy the run: keep the job, note it
                return j, min_score, f"judge error: {e}"

        kept = []
        with ThreadPoolExecutor(max_workers=conc) as ex:
            for j, sc, reason in ex.map(score, to_judge):
                if sc >= min_score:
                    j.extra["judge"] = {"score": sc, "reason": reason}
                    kept.append(j)
                else:
                    verdicts[j.id] = f"llm judge {sc} < {min_score}: {reason}"
        return kept, verdicts
