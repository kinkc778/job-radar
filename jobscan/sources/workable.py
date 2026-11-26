"""Workable global job search (jobs.workable.com).

The public API accepts a Hong Kong location filter and returns full HTML descriptions,
requirements, company and posting date — no detail fetch needed. Works from datacenter IPs.
"""

import logging
import time
from urllib.parse import quote

from ..httpclient import get_json
from ..models import Job
from ..util import clean, employment_type, html_to_text

log = logging.getLogger("jobscan")

SEARCH = "https://jobs.workable.com/api/v1/jobs?query={q}&location=Hong%20Kong"


def collect(queries: list[str]) -> list[Job]:
    jobs: dict[str, Job] = {}
    failures = 0

    for q in queries:
        url = SEARCH.format(q=quote(q))
        try:
            data = get_json(url)
        except Exception as e:
            failures += 1
            log.warning("workable: '%s' failed: %s", q, str(e)[:110])
            continue

        found = 0
        for rec in data.get("jobs") or []:
            jid = str(rec.get("id") or "")
            if not jid or jid in jobs:
                continue
            loc = rec.get("location") or {}
            location = clean(", ".join(
                x for x in [loc.get("city"), loc.get("subregion"), loc.get("countryName")] if x
            )) or "Hong Kong"
            if "hong kong" not in location.lower():
                continue

            title = clean(rec.get("title", ""))
            company = clean((rec.get("company") or {}).get("title", "")) or "Unknown company"
            jd = "\n\n".join(filter(None, [
                html_to_text(rec.get("description", "")),
                html_to_text(rec.get("requirementsSection", "")),
            ]))
            posted = clean(str(rec.get("created") or ""))[:10]

            jobs[jid] = Job(
                source="workable",
                external_id=jid,
                title=title,
                company=company,
                url=rec.get("url", ""),
                location=location,
                posted=posted,
                posted_at=posted,
                jd=jd,
                employment_type=rec.get("employmentType") or employment_type(title, jd[:300]),
                classification=clean(rec.get("department", "")),
                extra={"query": q, "workplace": rec.get("workplace", "")},
            )
            found += 1

        log.info("workable: '%s' -> %d HK roles (of %d)", q, found, len(data.get("jobs") or []))
        time.sleep(0.4)

    if failures and not jobs:
        raise RuntimeError(f"workable: all {failures} queries failed")
    return list(jobs.values())
