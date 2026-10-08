"""Discovery: public job boards -> company leads -> first-party ATS boards.

A Source scrapes a public aggregator board (Remotive, Himalayas, ...) and
returns Leads: (company, role) pairs. The resolver then locates each
company's own ATS board (Greenhouse, Lever, Ashby, ...) so jobs come from
the first-party source, not the aggregator.

Third-party sources register via the 'jobhunt.sources' entry-point group.
"""
from .base import Lead, Source, slugify  # noqa: F401
from .remotive import RemotiveSource
from .himalayas import HimalayasSource
from .jobicy import JobicySource
from .weworkremotely import WwrSource  # noqa: F401
