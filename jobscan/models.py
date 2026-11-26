from dataclasses import dataclass, field
from typing import Any, Dict

from .util import norm


@dataclass
class Job:
    source: str
    external_id: str
    title: str
    company: str
    url: str
    location: str = ""
    salary: str = ""
    jd: str = ""
    posted: str = ""
    employment_type: str = ""
    classification: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    # scoring result (filled in later)
    score: int = 0
    verdict: str = ""
    role_family: str = ""
    summary: str = ""
    why_match: list = field(default_factory=list)
    gaps: list = field(default_factory=list)
    priority: str = ""
    seniority_fit: str = ""
    scored_by: str = ""

    @property
    def key(self) -> str:
        return f"{self.source}:{self.external_id}"

    @property
    def xkey(self) -> str:
        """Cross-source identity: same company + normalised title."""
        return f"{norm(self.company)}|{norm(self.title)}"

    @property
    def fingerprint(self) -> str:
        return f"{norm(self.title)}|{norm(self.company)}|{norm(self.jd)[:600]}"

    def to_public_dict(self) -> dict:
        return {
            "source": self.source,
            "external_id": self.external_id,
            "title": self.title,
            "company": self.company,
            "url": self.url,
            "location": self.location,
            "salary": self.salary,
            "posted": self.posted,
            "employment_type": self.employment_type,
            "score": self.score,
            "verdict": self.verdict,
            "role_family": self.role_family,
            "summary": self.summary,
            "why_match": self.why_match,
            "gaps": self.gaps,
            "priority": self.priority,
            "seniority_fit": self.seniority_fit,
        }
