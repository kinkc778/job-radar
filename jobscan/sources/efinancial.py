"""eFinancialCareers Hong Kong.

The Angular app ships its search results as a JSON state blob inside the page, which is
reachable from datacenter IPs. Each record carries title, company, HK location, salary,
posting date and a summary usable as the JD.
"""

import json
import logging
import re
import time
from urllib.parse import quote_plus

from ..httpclient import get_text
from ..models import Job
from ..util import clean, employment_type

log = logging.getLogger("jobscan")

BASE = "https://www.efinancialcareers.hk"
SEARCH = BASE + "/search?q={q}&page={page}"
JSON_SCRIPT_RE = re.compile(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', re.S)


def _walk(node, out: dict):
    if isinstance(node, dict):
        if "jobLocation" in node and "title" in node and "detailsPageUrl" in node:
            jid = str(node.get("id") or node.get("jobId") or "")
            if jid:
                out[jid] = node
        for value in node.values():
            _walk(value, out)
    elif isinstance(node, list):
        for value in node:
            _walk(value, out)


def _jobs_from(html: str) -> dict:
    found: dict = {}
    for raw in JSON_SCRIPT_RE.findall(html):
        if '"jobLocation"' not in raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        _walk(data, found)
    return found


def collect(queries: list[str], pages: int = 2) -> list[Job]:
    records: dict = {}
    failures = 0

    for q in queries:
        for page in range(1, pages + 1):
            url = SEARCH.format(q=quote_plus(q), page=page)
            try:
                html = get_text(url, headers={"Accept": "text/html"})
            except Exception as e:
                failures += 1
                log.warning("efinancial: '%s' p%d failed: %s", q, page, str(e)[:110])
                continue
            before = len(records)
            records.update(_jobs_from(html))
            log.info("efinancial: '%s' p%d -> %d new cards", q, page, len(records) - before)
            time.sleep(0.7)

    jobs: list[Job] = []
    for rec in records.values():
        loc = rec.get("jobLocation") or {}
        location = clean(loc.get("displayName") or loc.get("city") or "Hong Kong")
        if "hong kong" not in location.lower():
            continue
        title = clean(rec.get("title", ""))
        if not title:
            continue
        posted = clean(str(rec.get("postedDate") or ""))[:10]
        jd = clean(rec.get("summary", ""))
        salary = clean(rec.get("salary", ""))
        if salary.lower() in ("competitive", "negotiable"):
            salary = ""
        jobs.append(Job(
            source="efinancialcareers",
            external_id=str(rec.get("id") or rec.get("jobId")),
            title=title,
            company=clean(rec.get("companyName") or rec.get("fullCompanyName") or "Unknown company"),
            url=BASE + rec.get("detailsPageUrl", ""),
            location=location,
            salary=salary,
            posted=posted,
            posted_at=posted,
            jd=jd,
            employment_type=employment_type(title, rec.get("employmentType") or ""),
            classification=clean(", ".join(rec.get("sectors") or []) if isinstance(rec.get("sectors"), list) else ""),
        ))

    if failures and not records:
        raise RuntimeError(f"efinancial: all {failures} searches failed")
    return jobs
