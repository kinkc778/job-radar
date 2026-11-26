"""Oracle HCM public job feeds (JPMorgan Chase by default).

The candidate-experience REST API is open and works from datacenter IPs. Filtering by
``location=Hong Kong`` returns the HK requisitions directly, and the list payload already
contains responsibility/qualification text, so no detail fetch is needed.
"""

import logging
from urllib.parse import quote_plus

from ..config import Config
from ..httpclient import get_json
from ..models import Job
from ..util import clean, employment_type, html_to_text

log = logging.getLogger("jobscan")

BASE = "https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
FINDER = (
    "?onlyData=true&expand=requisitionList.secondaryLocations"
    "&finder=findReqs;siteNumber={site},facetsList=LOCATIONS%3BWORK_LOCATIONS"
    ",limit=50,sortBy=POSTING_DATES_DESC,keyword={q},location=Hong%20Kong"
)


def collect(cfg: Config) -> list[Job]:
    conf = cfg.oracle
    host = conf.get("host", "jpmc.fa.oraclecloud.com")
    site = conf.get("site", "CX_1001")
    company = conf.get("company", "JPMorgan Chase")
    jobs: dict[str, Job] = {}
    failures = 0

    for q in cfg.queries:
        url = BASE.format(host=host) + FINDER.format(site=site, q=quote_plus(q))
        try:
            data = get_json(url)
        except Exception as e:
            failures += 1
            log.warning("oracle: '%s' failed: %s", q, str(e)[:110])
            continue

        items = (data.get("items") or [{}])[0]
        reqs = items.get("requisitionList") or []
        found = 0
        for r in reqs:
            rid = str(r.get("Id") or "")
            if not rid or rid in jobs:
                continue
            locs = [clean(r.get("PrimaryLocation", ""))]
            for sec in r.get("secondaryLocations") or []:
                if isinstance(sec, dict):
                    locs.append(clean(sec.get("Location", "")))
            location = "; ".join([x for x in locs if x])
            if "hong kong" not in location.lower():
                continue

            title = clean(r.get("Title", ""))
            parts = [
                r.get("ShortDescriptionStr", ""),
                r.get("ExternalResponsibilitiesStr", ""),
                r.get("ExternalQualificationsStr", ""),
            ]
            jd = "\n\n".join(html_to_text(p) for p in parts if p)
            posted = clean(str(r.get("PostedDate") or ""))[:10]

            jobs[rid] = Job(
                source="oracle",
                external_id=rid,
                title=title,
                company=company,
                url=(f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{rid}"),
                location=location,
                posted=posted,
                posted_at=posted,
                jd=jd,
                employment_type=employment_type(title, jd[:300]),
                classification=clean(r.get("JobFamily", "")),
                extra={"site": site, "query": q},
            )
            found += 1

        log.info("oracle: '%s' -> %d HK roles (of %d returned)", q, found, len(reqs))

    if failures and not jobs:
        raise RuntimeError(f"oracle: all {failures} queries failed")
    return list(jobs.values())
