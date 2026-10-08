"""Hacker News monthly 'Who is hiring?' thread.

The newest thread is found through the Algolia story search, then its full
comment tree is fetched from the Algolia items API. Each top-level comment is
one company post; company and role are parsed from its leading segment.

Discovery source only: the evidence URL is the thread (news.ycombinator.com),
never a job URL. The resolver maps each company to its first-party ATS board.
"""
import html
import re

from ..http import get
from ..registry import register_source
from .base import Lead, Source, slugify

STORY_SEARCH = "https://hn.algolia.com/api/v1/search_by_date"
ITEMS = "https://hn.algolia.com/api/v1/items/{}"
THREAD_URL = "https://news.ycombinator.com/item?id={}"

LEAD_TAGS = re.compile(r"^<(b|i|em|strong)[^>]*>(.*?)</\1>", re.S | re.I)
SEG_SPLIT = re.compile(r"\s*[|—–]\s*")
ROLE_START = re.compile(
    r"^(?:founding |senior |staff |lead |principal |jr |junior )?"
    r"(engineer|developer|swe|software|full[- ]?stack|frontend|front-end|"
    r"backend|architect|designer|manager|scientist|sre|devops|data)\b", re.I)
ROLE_ANY = re.compile(
    r"\b(founding|senior|staff|lead|product|full[- ]?stack|frontend|backend|"
    r"machine learning|ml|platform|embedded|software|data)?\s*"
    r"(engineer|developer|swe|scientist|architect|designer)\b", re.I)


def clean_text(t: str) -> str:
    """HN comment HTML -> plain text; <p>/<br> become newlines so the first
    line stays separate from the body."""
    t = re.sub(r"</?p\b[^>]*>", "\n", t or "", flags=re.I)
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    return re.sub(r"[ \t]+", " ", t).strip()


def _clean_company(s: str) -> str:
    """Drop a trailing URL and trailing parenthetical ((Remote US), (YC S24))."""
    s = re.sub(r"\s*\(?https?://\S+\)?\s*$", "", s.strip())
    s = re.sub(r"\s*\([^)]*\)\s*$", "", s)
    return s.strip(" -")


def parse_comment(raw: str) -> dict | None:
    """One top-level comment -> {'company', 'title', 'text'} or None.

    Company is the leading bold/italic text if present, else the first
    segment of the first line. Returns None when no company parses.
    """
    if not raw:
        return None
    m = LEAD_TAGS.match(raw.strip())
    lead = m.group(2) if m else ""
    text = clean_text(raw)
    if not text:
        return None
    first = text.split("\n", 1)[0]
    segs = [s.strip() for s in SEG_SPLIT.split(first) if s.strip()]

    if lead:
        company = _clean_company(clean_text(lead))
    else:
        company = _clean_company(segs[0]) if segs else ""
    if not re.search(r"[A-Za-z0-9]", company):
        return None

    role = ""
    for s in segs[1:]:
        if ROLE_START.match(s):
            role = s
            break
    if not role:
        for s in segs[1:]:
            if ROLE_ANY.search(s):
                role = s
                break
    if not role:
        mm = ROLE_ANY.search(text)
        role = mm.group(0).strip() if mm else ""
    return {"company": company, "title": role[:80], "text": text}


def parse_thread(data) -> list[dict]:
    """Algolia items payload -> parsed top-level comments (company posts)."""
    out: list[dict] = []
    for child in (data or {}).get("children") or []:
        parsed = parse_comment(child.get("text") or "")
        if parsed:
            out.append(parsed)
    return out


@register_source("hn")
class HnSource(Source):
    def leads(self) -> list[Lead]:
        story = get(STORY_SEARCH, params={"query": '"Ask HN: Who is hiring?"',
                                          "tags": "story", "hitsPerPage": 1})
        hits = (story or {}).get("hits") or []
        if not hits:
            return []
        story_id = hits[0].get("objectID")
        thread = get(ITEMS.format(story_id))
        if not thread:
            return []
        url = THREAD_URL.format(story_id)

        terms = [w for w in (self.config.get("search") or "").lower().split()]
        out: list[Lead] = []
        for post in parse_thread(thread):
            if len(out) >= self.max_leads:
                break
            if terms and any(t not in post["text"].lower() for t in terms):
                continue
            out.append(Lead(
                source="hn",
                company=slugify(post["company"]),
                company_display=post["company"],
                title=post["title"],
                url=url,
            ))
        return out
