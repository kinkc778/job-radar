"""Standard Chartered job RSS feed (SuccessFactors).

The careers site exposes a public RSS endpoint that accepts a keyword plus a Hong Kong
location filter and returns full HTML descriptions. Reachable from datacenter IPs.
"""

import logging
import re
import time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import quote

from ..config import Config
from ..httpclient import request
from ..models import Job
from ..util import clean, employment_type, html_to_text

log = logging.getLogger("jobscan")

FEED = ("https://jobs.standardchartered.com/services/rss/job/"
        "?locale=en_GB&keywords={kw}")
ID_RE = re.compile(r"/(\d+)/?(?:\?|$)")


def collect(cfg: Config) -> list[Job]:
    jobs: dict[str, Job] = {}
    failures = 0

    for q in cfg.queries:
        kw = quote(f"({q}) AND locationSearch:(Hong Kong)", safe="")
        try:
            body = request(FEED.format(kw=kw), headers={"Accept": "application/rss+xml"})
            root = ET.fromstring(body)
        except Exception as e:
            failures += 1
            log.warning("standardchartered: '%s' failed: %s", q, str(e)[:110])
            continue

        found = 0
        for item in root.findall(".//item"):
            title = clean(item.findtext("title", ""))
            link = (item.findtext("link", "") or "").split("?")[0]
            m = ID_RE.search(link)
            if not title or not m:
                continue
            jid = m.group(1)
            if jid in jobs:
                continue

            jd = html_to_text(item.findtext("description", ""))
            posted = ""
            pub = item.findtext("pubDate", "")
            if pub:
                try:
                    posted = parsedate_to_datetime(pub).strftime("%Y-%m-%d")
                except Exception:
                    posted = ""

            jobs[jid] = Job(
                source="standardchartered",
                external_id=jid,
                title=title,
                company="Standard Chartered",
                url=link,
                location="Hong Kong",
                posted=posted,
                posted_at=posted,
                jd=jd,
                employment_type=employment_type(title, jd[:300]),
            )
            found += 1

        log.info("standardchartered: '%s' -> %d roles", q, found)
        time.sleep(0.5)

    if failures and not jobs:
        raise RuntimeError(f"standardchartered: all {failures} queries failed")
    return list(jobs.values())
