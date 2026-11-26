import re

from .config import Config
from .models import Job
from .util import norm

TITLE_WEIGHTS = [
    (r"data engineer", 10),
    (r"analytics engineer", 10),
    (r"data scientist", 9),
    (r"machine learning", 9),
    (r"\bml\b", 8),
    (r"ai agent", 10),
    (r"\bai\b", 8),
    (r"llm", 8),
    (r"data analyst", 8),
    (r"business intelligence", 7),
    (r"\bbi\b", 6),
    (r"solution engineer", 7),
    (r"forward deployed", 8),
    (r"mlops", 8),
    (r"data platform", 7),
    (r"etl", 6),
    (r"graduate|trainee|intern", 4),
    (r"engineer", 3),
]


def is_hong_kong(job: Job, cfg: Config) -> bool:
    loc = f"{job.location} {job.extra.get('workplace', '')}"
    return bool(cfg.location_re.search(loc))


def title_relevant(job: Job, cfg: Config) -> tuple[bool, str]:
    """Return (relevant, reason). Only relevant jobs are remembered in state."""
    title = job.title or ""
    if cfg.blocked_re.search(title):
        return False, "blocked"
    if not cfg.include_re.search(title):
        return False, "no_match"
    if cfg.exclude_re.search(title):
        return False, "too_senior"
    if not cfg.include_internships and re.search(
        r"(?i)\b(intern|internship|placement|co-?op|summer (analyst|associate|programme|program))\b"
        r"|實習|实习",
        title,
    ):
        return False, "internship"
    return True, "ok"


def quick_score(job: Job) -> float:
    title = (job.title or "").lower()
    score = 0.0
    for pattern, weight in TITLE_WEIGHTS:
        if re.search(pattern, title):
            score = max(score, weight) if weight >= 8 else score + weight * 0.4
    if "graduate" in title or "intern" in title:
        score += 2
    if any(w in title for w in ("hong kong", "hk")):
        score += 1
    return score


def dedupe_jobs(jobs: list[Job]) -> list[Job]:
    seen_keys, seen_x, out = set(), set(), []
    for j in jobs:
        if j.key in seen_keys or j.xkey in seen_x:
            continue
        seen_keys.add(j.key)
        seen_x.add(j.xkey)
        out.append(j)
    return out


def sanitize_title(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "")).strip()


def cross_key(company: str, title: str) -> str:
    return f"{norm(company)}|{norm(title)}"


SOURCE_RANK = {"jobsdb": 3, "greenhouse": 3, "lever": 3, "ctgoodjobs": 2, "ashby": 2}


def _group_key(job: Job) -> str:
    company = (job.company or "").strip().lower()
    if company in ("", "unknown", "unknown company"):
        return job.key  # never merge two anonymous postings
    return job.xkey


def dedupe_enriched(jobs: list[Job]) -> tuple[list[Job], list[Job]]:
    """Merge same company+title twins now that enrichment has revealed companies."""
    groups: dict[str, list[Job]] = {}
    for job in jobs:
        groups.setdefault(_group_key(job), []).append(job)
    kept: list[Job] = []
    dupes: list[Job] = []
    for group in groups.values():
        group.sort(key=lambda j: (len(j.jd), SOURCE_RANK.get(j.source, 0)), reverse=True)
        kept.append(group[0])
        dupes.extend(group[1:])
    return kept, dupes
