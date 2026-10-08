import json
import time
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (jobhunt/0.1; +https://github.com/wokhouse/jobhunt)"}


def get(url: str, *, method: str = "GET", body: dict | None = None,
        params: dict | None = None,
        headers: dict | None = None, timeout: int = 15,
        tries: int = 3, raw: bool = False):
    """Fetch a URL with retries and linear backoff. Returns None on failure.

    JSON is parsed unless raw=True (RSS/HTML sources pass raw=True).
    """
    hdrs = dict(UA)
    if headers:
        hdrs.update(headers)
    if params:
        from urllib.parse import urlencode
        url = f"{url}{'&' if '?' in url else '?'}{urlencode(params)}"
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        hdrs.setdefault("Content-Type", "application/json")
        hdrs.setdefault("Accept", "application/json")
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                text = r.read().decode(errors="replace")
                return text if raw else json.loads(text)
        except Exception:
            if attempt < tries - 1:
                time.sleep(1.0 * (attempt + 1))
    return None
