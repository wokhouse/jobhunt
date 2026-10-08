"""We Work Remotely — public RSS feeds per job category.

Feed: https://weworkremotely.com/categories/remote-<category>-jobs.rss
The item description often links straight to the company's ATS posting,
so the resolver can skip probing when the ATS URL is already present.
"""
import re

from ..http import get
from ..registry import register_source
from .base import Lead, Source, slugify

ATS_IN_DESC = re.compile(
    r'href="(https?://[^"]*(?:greenhouse\.io|lever\.co|ashbyhq\.com|'
    r'workable\.com|rippling\.com|myworkdayjobs\.com)[^"]*)"', re.I)
TITLE_COMPANY = re.compile(r"^([A-Za-z0-9 .&'-]+?)(?: is hiring|:|\s+-\s+|\s+\()")


@register_source("weworkremotely")
class WwrSource(Source):
    def leads(self) -> list[Lead]:
        cat = self.config.get("category", "programming")
        feed = self.config.get(
            "feed", f"https://weworkremotely.com/categories/remote-{cat}-jobs.rss")
        xml = get(feed, raw=True, tries=2)
        if not xml:
            return []
        out: list[Lead] = []
        for item in re.findall(r"<item>(.*?)</item>", xml, re.S)[: self.max_leads]:
            tm = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", item, re.S)
            lm = re.search(r"<link>(.*?)</link>", item, re.S)
            if not tm or not lm:
                continue
            title = tm.group(1).strip()
            link = lm.group(1).strip()
            ats = ATS_IN_DESC.search(item)
            cm = TITLE_COMPANY.search(title)
            name = (cm.group(1) if cm else title.split()[0]).strip()
            if not name:
                continue
            out.append(Lead(
                source="weworkremotely",
                company=slugify(name),
                company_display=name,
                title=title,
                url=ats.group(1) if ats else link,
                location="Remote",
            ))
        return out
