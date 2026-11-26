import json
import logging
import os
from datetime import timedelta

from .models import Job
from .util import iso_now, parse_iso

log = logging.getLogger("jobscan")


class State:
    def __init__(self, path):
        self.path = path
        self.data = {"version": 1, "jobs": {}, "runs": []}
        if path.exists():
            try:
                self.data = json.loads(path.read_text(encoding="utf-8"))
                self.data.setdefault("jobs", {})
                self.data.setdefault("runs", [])
            except Exception as e:
                log.warning("state file unreadable (%s); starting fresh", e)
        self._xkeys = {v.get("xkey") for v in self.data["jobs"].values() if v.get("xkey")}

    # ---------- queries ----------
    def is_seen(self, job: Job) -> bool:
        return job.key in self.data["jobs"] or job.xkey in self._xkeys

    def queued_backfill(self, min_score: int, days: int, limit: int):
        cutoff = parse_iso(iso_now()) - timedelta(days=days)
        rows = []
        for key, v in self.data["jobs"].items():
            if v.get("status") != "queued" or int(v.get("score") or 0) < min_score:
                continue
            ts = parse_iso(v.get("first_seen", ""))
            if ts and ts < cutoff:
                continue
            rows.append(dict(v, key=key))
        rows.sort(key=lambda r: -int(r.get("score") or 0))
        return rows[:limit]

    # ---------- mutation ----------
    def mark(self, job: Job, status: str):
        now = iso_now()
        entry = self.data["jobs"].get(job.key)
        if entry is None:
            entry = {
                "first_seen": now,
                "title": job.title,
                "company": job.company,
                "url": job.url,
                "source": job.source,
                "xkey": job.xkey,
            }
            self.data["jobs"][job.key] = entry
            self._xkeys.add(job.xkey)
        entry.update(
            {
                "last_seen": now,
                "status": status,
                "score": int(job.score or 0),
                "role_family": job.role_family,
                "location": job.location,
                "salary": job.salary,
                "employment_type": job.employment_type,
            }
        )

    def mark_backfill_emailed(self, key: str):
        if key in self.data["jobs"]:
            self.data["jobs"][key]["status"] = "emailed"
            self.data["jobs"][key]["emailed_at"] = iso_now()

    def record_run(self, summary: dict):
        self.data["runs"].append(summary)
        self.data["runs"] = self.data["runs"][-60:]

    def prune(self, days: int = 120):
        cutoff = parse_iso(iso_now()) - timedelta(days=days)
        drop = []
        for key, v in self.data["jobs"].items():
            ts = parse_iso(v.get("last_seen") or v.get("first_seen") or "")
            if ts and ts < cutoff:
                drop.append(key)
        for key in drop:
            v = self.data["jobs"].pop(key, None)
            if v and v.get("xkey"):
                self._xkeys.discard(v["xkey"])
        if drop:
            log.info("state: pruned %d old entries", len(drop))

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)
        log.info("state: saved %d jobs to %s", len(self.data["jobs"]), self.path.name)
