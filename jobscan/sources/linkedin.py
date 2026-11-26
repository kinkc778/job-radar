"""LinkedIn public guest endpoints (no login).

The guest search endpoint returns HTML cards and is reachable from GitHub runners,
unlike JobsDB/Indeed. Detail pages expose the full JD in the markup block.
"""

import logging
import re
import time
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from ..httpclient import get_text
from ..models import Job
from ..util import clean, employment_type

log = logging.getLogger("jobscan")

SEARCH = ("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
          "?keywords={q}&location=Hong%20Kong&f_TPR=r604800&start={start}")
DETAIL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{jid}"
JOB_URL = "https://www.linkedin.com/jobs/view/{jid}"
ID_RE = re.compile(r"/jobs/view/[^?#]*?(\d+)(?:[?#]|$)")


def collect(queries: list[str], pages: int = 2) -> list[Job]:
    jobs: dict[str, Job] = {}
    failures = 0
    consecutive = 0

    for q in queries:
        for page in range(pages):
            url = SEARCH.format(q=quote_plus(q), start=page * 10)
            try:
                html = get_text(url, headers={"Accept": "text/html,application/xhtml+xml"})
                consecutive = 0
            except Exception as e:
                failures += 1
                consecutive += 1
                log.warning("linkedin: search '%s' p%d failed: %s", q, page + 1, str(e)[:110])
                if consecutive >= 3:
                    log.error("linkedin: 3 consecutive failures - stopping this source")
                    raise RuntimeError("linkedin blocked / unavailable") from e
                continue

            soup = BeautifulSoup(html, "html.parser")
            found = 0
            for li in soup.select("li"):
                title_el = li.select_one(".base-search-card__title")
                link = li.select_one("a.base-card__full-link") or li.select_one("a[href*='/jobs/view/']")
                if not title_el or not link:
                    continue
                m = ID_RE.search(link.get("href", ""))
                if not m:
                    continue
                jid = m.group(1)
                if jid in jobs:
                    continue

                title = clean(title_el.get_text(" ", strip=True))
                company_el = li.select_one(".base-search-card__subtitle")
                company = clean(company_el.get_text(" ", strip=True)) if company_el else "LinkedIn"
                loc_el = li.select_one(".job-search-card__location")
                location = clean(loc_el.get_text(" ", strip=True)) if loc_el else "Hong Kong"
                time_el = li.select_one("time")
                posted = clean(time_el.get("datetime", ""))[:10] if time_el else ""

                jobs[jid] = Job(
                    source="linkedin",
                    external_id=jid,
                    title=title,
                    company=company,
                    url=JOB_URL.format(jid=jid),
                    location=location,
                    posted=posted,
                    posted_at=posted,
                    employment_type=employment_type(title),
                    extra={"query": q},
                )
                found += 1

            log.info("linkedin: '%s' p%d -> %d cards", q, page + 1, found)
            time.sleep(1.0)

    if failures and not jobs:
        raise RuntimeError(f"linkedin: all {failures} searches failed")
    return list(jobs.values())


def enrich(jobs: list[Job], limit: int = 30) -> int:
    done = 0
    for job in jobs[:limit]:
        try:
            html = get_text(DETAIL.format(jid=job.external_id),
                            headers={"Accept": "text/html"})
        except Exception as e:
            log.warning("linkedin: detail failed for %s: %s", job.external_id, str(e)[:110])
            continue

        soup = BeautifulSoup(html, "html.parser")
        body = soup.select_one(".show-more-less-html__markup")
        if body:
            job.jd = body.get_text("\n", strip=True)

        title_el = soup.select_one(".top-card-layout__title") or soup.select_one(".topcard__title")
        if title_el:
            job.title = clean(title_el.get_text(" ", strip=True)) or job.title
        company_el = (soup.select_one(".topcard__org-name-link")
                      or soup.select_one(".top-card-layout__second-subline a"))
        if company_el:
            job.company = clean(company_el.get_text(" ", strip=True)) or job.company
        loc_el = soup.select_one(".topcard__flavor--bullet")
        if loc_el:
            job.location = clean(loc_el.get_text(" ", strip=True)) or job.location

        if job.jd:
            job.employment_type = employment_type(job.title, job.jd[:400])
            done += 1
        time.sleep(1.0)
    return done
