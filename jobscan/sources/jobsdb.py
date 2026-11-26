import logging
import re
import time
from urllib.parse import quote, urljoin, urlparse

from bs4 import BeautifulSoup

from ..browser import BrowserSession
from ..models import Job
from ..util import clean, employment_type

log = logging.getLogger("jobscan")

BASE = "https://hk.jobsdb.com"
SEARCH = BASE + "/jobs?keywords={q}&page={page}"
JOB_ID_RE = re.compile(r"/job/(\d+)")


def _text(node, sel: str) -> str:
    el = node.select_one(sel)
    return clean(el.get_text(" ", strip=True)) if el else ""


def _norm_url(href: str, job_id: str) -> str:
    if job_id:
        return f"{BASE}/job/{job_id}"
    if not href:
        return ""
    return urljoin(BASE, urlparse(href)._replace(query="", fragment="").geturl())


def collect(session: BrowserSession, queries: list[str], pages: int = 1,
            daterange: int | None = 14) -> list[Job]:
    jobs: dict[str, Job] = {}
    failures = 0
    consecutive = 0

    for qi, q in enumerate(queries):
        for page in range(1, pages + 1):
            url = SEARCH.format(q=quote(q), page=page)
            if daterange:
                url += f"&daterange={daterange}"
            started = time.time()
            try:
                html = session.goto(url, wait_selector='article[data-automation="normalJob"]',
                                    retries=1)
                consecutive = 0
            except Exception as e:
                failures += 1
                consecutive += 1
                log.warning("jobsdb: search '%s' failed: %s", q, str(e)[:140])
                if consecutive >= 3:
                    log.error("jobsdb: 3 consecutive failures - stopping this source")
                    raise RuntimeError("jobsdb blocked / unavailable") from e
                continue

            soup = BeautifulSoup(html, "html.parser")
            cards = soup.select('article[data-automation="normalJob"]')
            log.info("jobsdb: '%s' p%d -> %d cards in %.1fs",
                     q, page, len(cards), time.time() - started)
            for card in cards:
                title_el = card.select_one('[data-automation="jobTitle"]')
                if not title_el:
                    continue
                jid = card.get("data-job-id") or ""
                if not jid:
                    m = JOB_ID_RE.search(title_el.get("href", ""))
                    jid = m.group(1) if m else ""
                if not jid or jid in jobs:
                    continue
                title = clean(title_el.get_text(" ", strip=True))
                href = title_el.get("href", "")
                location = _text(card, '[data-automation="jobLocation"]')
                company = _text(card, '[data-automation="jobCompany"]')
                salary = _text(card, '[data-automation="jobSalary"]')
                posted = _text(card, '[data-automation="jobListingDate"]')
                teaser = _text(card, '[data-automation="jobShortDescription"]')
                classification = _text(card, '[data-automation="jobClassification"]')

                jobs[jid] = Job(
                    source="jobsdb",
                    external_id=jid,
                    title=title,
                    company=company,
                    url=_norm_url(href, jid),
                    location=location,
                    salary=salary,
                    posted=posted,
                    employment_type=employment_type(title, teaser),
                    classification=classification,
                    extra={"teaser": teaser, "query": q},
                )
            session.polite_pause(1.2, 2.6)

    if failures and not jobs:
        raise RuntimeError(f"jobsdb: all {failures} searches failed")
    return list(jobs.values())


def enrich(session: BrowserSession, jobs: list[Job], limit: int = 60) -> int:
    """Fetch full JDs from detail pages, one at a time, politely."""
    done = 0
    for job in jobs[:limit]:
        url = f"{BASE}/job/{job.external_id}"
        try:
            html = session.goto(url, wait_selector='[data-automation="jobAdDetails"]',
                                retries=1)
        except Exception as e:
            log.warning("jobsdb: detail failed for %s: %s", job.external_id, str(e)[:120])
            continue

        soup = BeautifulSoup(html, "html.parser")
        body = soup.select_one('[data-automation="jobAdDetails"]')
        if body is None:
            continue
        jd = body.get_text("\n", strip=True)
        if not jd:
            continue

        low = jd.lower()
        if ("no longer advertised" in low or "this job has expired" in low
                or "job has been withdrawn" in low):
            job.extra["expired"] = True
            continue

        job.jd = jd
        job.title = _text(soup, '[data-automation="job-detail-title"]') or job.title
        job.company = _text(soup, '[data-automation="advertiser-name"]') or job.company
        job.location = _text(soup, '[data-automation="job-detail-location"]') or job.location
        job.salary = _text(soup, '[data-automation="job-detail-salary"]') or job.salary
        job.classification = (_text(soup, '[data-automation="job-detail-classifications"]')
                              or job.classification)
        work_type = _text(soup, '[data-automation="job-detail-work-type"]')
        job.employment_type = employment_type(job.title, f"{work_type} {jd[:400]}")
        job.posted = job.posted or ""
        done += 1
        session.polite_pause(1.0, 2.2)
    return done
