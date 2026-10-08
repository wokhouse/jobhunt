import html
import re

MAX_CONTENT = 12000


def strip_tags(s: str) -> str:
    s = re.sub(r"<style.*?</style>", " ", s or "", flags=re.S)
    s = re.sub(r"<script.*?</script>", " ", s or "", flags=re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    return html.unescape(s)


def text_of(fragment: str) -> str:
    """Strip tags, unescape entities, collapse whitespace."""
    return re.sub(r"\s+", " ", html.unescape(strip_tags(fragment or ""))).strip()


def class_text(block: str, cls: str, tag: str = "span") -> str:
    """Text of the first <tag class="... cls ..."> in block. cls must appear
    as a whole class token (delimited by quote/space), so 'location' does not
    match 'job-location'."""
    m = re.search(r'<' + tag + r'[^>]*class="[^"]*?(?<=["\s])' + cls +
                  r'(?=["\s])[^"]*"[^>]*>(.*?)</' + tag + '>', block, re.S)
    return text_of(m.group(1)) if m else ""


_MONEY_RE = re.compile(r"\$\s*(\d[\d,]*)\s*(k|K)?")


def parse_salary_range(text: str) -> tuple[int, int] | None:
    """Return (min, max) of dollar amounts found in text, or None.

    Heuristic: scans all $ amounts in the posting body. Unrelated amounts
    (funding rounds, prices) can inflate the range; treat results as a signal,
    not a contract.
    """
    amounts = []
    for m in _MONEY_RE.finditer(text or ""):
        v = int(m.group(1).replace(",", ""))
        if m.group(2):
            v *= 1000
        if v >= 1000:  # ignore tiny amounts like $50
            amounts.append(v)
    if not amounts:
        return None
    return min(amounts), max(amounts)


_YEARS_RE = re.compile(
    r"(\d{1,2})\s*(?:\+|\s*(?:-|–|to)\s*\d{1,2}\s*\+?)?\s*years?", re.I)


def parse_min_years(text: str) -> int | None:
    """Smallest 'N years' requirement mentioned in the body, or None."""
    ms = _YEARS_RE.findall(text or "")
    if not ms:
        return None
    return min(int(a) for a in ms)
