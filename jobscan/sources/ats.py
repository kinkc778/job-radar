import logging
import time
from datetime import datetime, timezone

from ..config import Config
from ..httpclient import get_json
from ..models import Job
from ..util import clean, employment_type, html_to_text

log = logging.getLogger("jobscan")

DISPLAY = {
    "binance": "Binance",
    "okx": "OKX",
    "bybit": "Bybit",
    "flexport": "Flexport",
    "mongodb": "MongoDB",
    "lalamove": "Lalamove",
}


def _company(slug: str, kind: str) -> str:
    return DISPLAY.get(slug.lower(), slug.replace("-", " ").title())


def _hk(text: str, cfg: Config) -> bool:
    return bool(cfg.location_re.search(text or ""))


def _greenhouse(slug: str, cfg: Config) -> list[Job]:
    data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=false")
    out = []
    for j in data.get("jobs", []):
        loc = clean((j.get("location") or {}).get("name", ""))
        if not _hk(loc, cfg):
            continue
        title = clean(j.get("title", ""))
        out.append(Job(
            source="greenhouse",
            external_id=f"{slug}:{j.get('id')}",
            title=title,
            company=_company(slug, "greenhouse"),
            url=j.get("absolute_url", ""),
            location=loc,
            posted=clean(str(j.get("updated_at") or ""))[:10],
            posted_at=clean(str(j.get("updated_at") or ""))[:10],
            employment_type=employment_type(title),
            extra={"board": slug, "gh_id": j.get("id")},
        ))
    return out


def _lever(slug: str, cfg: Config) -> list[Job]:
    postings = get_json(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    out = []
    for p in postings:
        cats = p.get("categories") or {}
        loc = clean(cats.get("location", ""))
        if not _hk(loc, cfg):
            continue
        title = clean(p.get("text", ""))
        parts = [p.get("descriptionPlain") or ""]
        for lst in p.get("lists") or []:
            parts.append(f"\n{lst.get('text', '')}\n")
            parts.append(html_to_text(lst.get("content", "")))
        jd = "\n".join(x for x in parts if x).strip()
        created = p.get("createdAt")
        posted = ""
        if isinstance(created, (int, float)):
            posted = datetime.fromtimestamp(created / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        out.append(Job(
            source="lever",
            external_id=f"{slug}:{p.get('id')}",
            title=title,
            company=_company(slug, "lever"),
            url=p.get("hostedUrl", ""),
            location=loc,
            jd=jd,
            posted=posted,
            posted_at=posted,
            employment_type=employment_type(title, cats.get("commitment", "") or ""),
            classification=clean(cats.get("team", "")),
            extra={"board": slug, "commitment": cats.get("commitment", "")},
        ))
    return out


def _ashby(slug: str, cfg: Config) -> list[Job]:
    data = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    out = []
    for j in data.get("jobs", []):
        locs = [j.get("location") or ""]
        for sec in j.get("secondaryLocations") or []:
            if isinstance(sec, dict):
                locs.append(sec.get("location") or "")
        loc = "; ".join([clean(x) for x in locs if clean(x)])
        if not _hk(loc, cfg):
            continue
        title = clean(j.get("title", ""))
        jd = j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml", ""))
        out.append(Job(
            source="ashby",
            external_id=f"{slug}:{j.get('id')}",
            title=title,
            company=_company(slug, "ashby"),
            url=j.get("jobUrl") or j.get("applyUrl") or "",
            location=loc,
            jd=jd,
            posted=clean(str(j.get("publishedAt") or ""))[:10],
            posted_at=clean(str(j.get("publishedAt") or ""))[:10],
            employment_type=employment_type(title, j.get("employmentType") or ""),
            classification=clean(j.get("department") or ""),
            extra={"board": slug},
        ))
    return out


def collect(cfg: Config) -> list[Job]:
    jobs: list[Job] = []
    kinds = {
        "greenhouse": _greenhouse,
        "lever": _lever,
        "ashby": _ashby,
    }
    for kind, fn in kinds.items():
        for slug in cfg.ats.get(kind, []):
            try:
                found = fn(slug, cfg)
                jobs.extend(found)
                log.info("ats: %s/%s -> %d HK roles", kind, slug, len(found))
            except Exception as e:
                log.warning("ats: %s/%s failed: %s", kind, slug, str(e)[:120])
            time.sleep(0.3)
    return jobs


def enrich(jobs: list[Job], limit: int = 20) -> int:
    """Greenhouse list responses omit content; fetch the detail endpoint."""
    done = 0
    for job in jobs[:limit]:
        if job.source != "greenhouse" or not job.extra.get("gh_id"):
            continue
        slug = job.extra["board"]
        try:
            data = get_json(
                f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/"
                f"{job.extra['gh_id']}?questions=false"
            )
            content = data.get("content") or ""
            if content:
                job.jd = html_to_text(content)
        except Exception as e:
            log.warning("ats: greenhouse detail failed %s: %s", job.external_id, str(e)[:100])
            continue
        if job.jd:
            job.employment_type = employment_type(job.title, job.jd[:400])
        done += 1
        time.sleep(0.2)
    return done
