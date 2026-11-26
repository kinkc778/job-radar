import json
import logging
import re
import time
from urllib.parse import quote_plus

from ..httpclient import get_text
from ..models import Job
from ..util import clean, employment_type, html_to_text

log = logging.getLogger("jobscan")

BASE = "https://jobs.ctgoodjobs.hk"
SEARCH = BASE + "/jobs?q={q}"
JOB_ID_RE = re.compile(r"/job/(\d+)")
LDJSON_RE = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S)


def _ld_blocks(html: str):
    for raw in LDJSON_RE.findall(html):
        try:
            yield json.loads(raw)
        except Exception:
            continue


def collect(queries: list[str], pages: int = 1, session=None) -> list[Job]:
    jobs: dict[str, Job] = {}
    failures = 0
    consecutive = 0

    for q in queries:
        for page in range(1, pages + 1):
            url = SEARCH.format(q=quote_plus(q))
            if page > 1:
                url += f"&page={page}"
            try:
                if session is not None:
                    html = session.goto(url, wait_selector='a[href*="/job/"]', retries=1)
                    session.polite_pause(0.8, 1.8)
                else:
                    html = get_text(url, timeout=30)
                    time.sleep(0.4)
                consecutive = 0
            except Exception as e:
                failures += 1
                consecutive += 1
                log.warning("ctgoodjobs: search '%s' failed: %s", q, str(e)[:120])
                if consecutive >= 3:
                    log.error("ctgoodjobs: 3 consecutive failures - stopping this source")
                    raise RuntimeError("ctgoodjobs blocked / unavailable") from e
                continue

            found = 0
            for block in _ld_blocks(html):
                if not isinstance(block, dict) or block.get("@type") != "ItemList":
                    continue
                for item in block.get("itemListElement", []):
                    link = item.get("url", "")
                    name = clean(item.get("name", ""))
                    m = JOB_ID_RE.search(link)
                    if not m:
                        continue
                    jid = m.group(1)
                    if jid in jobs:
                        continue
                    jobs[jid] = Job(
                        source="ctgoodjobs",
                        external_id=jid,
                        title=name,
                        company="",
                        url=link.split("?")[0],
                        location="Hong Kong",
                        employment_type=employment_type(name),
                    )
                    found += 1
            log.info("ctgoodjobs: '%s' p%d -> %d cards", q, page, found)

    if failures and not jobs:
        raise RuntimeError(f"ctgoodjobs: all {failures} searches failed")
    return list(jobs.values())


def enrich(jobs: list[Job], limit: int = 30, session=None) -> int:
    done = 0
    for job in jobs[:limit]:
        try:
            if session is not None:
                html = session.goto(job.url,
                                    wait_selector='script[type="application/ld+json"]',
                                    retries=1)
                session.polite_pause(0.7, 1.5)
            else:
                html = get_text(job.url, timeout=30)
        except Exception as e:
            log.warning("ctgoodjobs: detail failed for %s: %s", job.external_id, str(e)[:100])
            continue

        posting = None
        for block in _ld_blocks(html):
            if isinstance(block, dict) and block.get("@type") == "JobPosting":
                posting = block
                break
        if not posting:
            continue

        job.title = clean(posting.get("title") or job.title)
        org = posting.get("hiringOrganization") or {}
        job.company = clean(org.get("name") or job.company) or "Unknown company"

        locs = posting.get("jobLocation") or []
        if isinstance(locs, dict):
            locs = [locs]
        parts = []
        for loc in locs[:2]:
            addr = (loc or {}).get("address") or {}
            bits = [addr.get("addressLocality"), addr.get("addressRegion")]
            s = ", ".join([b for b in bits if b])
            if s:
                parts.append(s)
        if parts:
            job.location = "; ".join(parts)

        desc = posting.get("description") or ""
        job.jd = html_to_text(desc)
        job.employment_type = employment_type(job.title, posting.get("employmentType", "") or "")

        salary = posting.get("baseSalary") or {}
        val = salary.get("value") or {}
        if isinstance(val, dict):
            lo, hi = val.get("minValue"), val.get("maxValue")
            single = val.get("value")
            if isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
                job.salary = f"HK${int(lo):,} - {int(hi):,}"
            elif isinstance(single, (int, float)):
                job.salary = f"HK${int(single):,}"
        if job.salary.lower() in ("n/a", "none"):
            job.salary = ""

        job.posted = clean(str(posting.get("datePosted") or ""))[:10]
        job.posted_at = job.posted
        valid = posting.get("validThrough")
        if valid and "-" in str(valid):
            job.extra["valid_through"] = str(valid)[:10]
        done += 1
        if session is None:
            time.sleep(0.3)
    return done
