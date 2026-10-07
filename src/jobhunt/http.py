import json
import time
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (jobhunt/0.1; +https://github.com/wokhouse/jobhunt)"}


def get(url: str, *, method: str = "GET", body: dict | None = None,
        headers: dict | None = None, timeout: int = 15,
        tries: int = 3, sleep: float = 1.0):
    """Fetch JSON with retries and linear backoff. Returns None on failure."""
    hdrs = dict(UA)
    if headers:
        hdrs.update(headers)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        hdrs.setdefault("Content-Type", "application/json")
        hdrs.setdefault("Accept", "application/json")
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except Exception:
            if attempt < tries - 1:
                time.sleep(sleep * (attempt + 1))
    return None
