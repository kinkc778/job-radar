"""Build the static job board payload from scored jobs.

The board is a plain static site (docs/) with no backend. This module keeps a
cumulative archive in data/board_jobs.json and writes docs/data/jobs.js, which
the page loads as a normal script so it works from file:// and from Pages.
"""

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone

from .config import Config
from .models import Job
from .util import hk_now, iso_now, parse_iso, relative_to_date, truncate

log = logging.getLogger("jobscan")

ARCHIVE_FILE = "board_jobs.json"
ANALYSIS_FIELDS = ("why_match", "gaps", "seniority_fit")


def _path(cfg: Config):
    return cfg.data_dir / ARCHIVE_FILE


def load_archive(cfg: Config) -> dict:
    p = _path(cfg)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            data.setdefault("jobs", {})
            return data
        except Exception as e:
            log.warning("board archive unreadable (%s); starting fresh", e)
    return {"version": 1, "jobs": {}}


def _save(cfg: Config, data: dict):
    p = _path(cfg)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def _sanitize(cfg: Config, data: dict):
    """The board may be hosted publicly: drop CV-derived analysis if configured."""
    if cfg.board_include_analysis:
        return
    for entry in data["jobs"].values():
        for field in ANALYSIS_FIELDS:
            entry.pop(field, None)


def _backfill_dates(data: dict):
    """Fill posted_at for older entries that only have relative text or epoch ms."""
    for entry in data["jobs"].values():
        if entry.get("posted_at") or not entry.get("posted"):
            continue
        raw = str(entry["posted"]).strip()
        if re.fullmatch(r"\d{10,13}", raw):
            ms = int(raw)
            if len(raw) == 10:
                ms *= 1000
            try:
                entry["posted_at"] = datetime.fromtimestamp(
                    ms / 1000, tz=timezone.utc
                ).strftime("%Y-%m-%d")
                continue
            except (ValueError, OSError):
                pass
        entry["posted_at"] = relative_to_date(raw)


def _prune(cfg: Config, data: dict):
    cutoff = parse_iso(iso_now()) - timedelta(days=cfg.board_keep_days)
    dropped = 0
    for key in list(data["jobs"]):
        entry = data["jobs"][key]
        seen = parse_iso(entry.get("last_seen") or entry.get("first_seen") or "")
        if seen and seen < cutoff:
            del data["jobs"][key]
            dropped += 1
    if len(data["jobs"]) > cfg.board_max_jobs:
        ranked = sorted(
            data["jobs"].items(),
            key=lambda kv: (kv[1].get("last_seen", ""), kv[1].get("score", 0)),
        )
        for key, _ in ranked[: len(data["jobs"]) - cfg.board_max_jobs]:
            del data["jobs"][key]
            dropped += 1
    if dropped:
        log.info("board: pruned %d old entries", dropped)


def update_archive(cfg: Config, jobs: list[Job]) -> tuple[dict, int, int]:
    data = load_archive(cfg)
    now = iso_now()
    added = updated = 0
    for job in jobs:
        if job.score < cfg.board_min_score or job.extra.get("expired"):
            continue
        prev = data["jobs"].get(job.key)
        entry = job.to_public_dict()
        entry["key"] = job.key
        entry["jd"] = truncate(job.jd, 1500)
        entry["first_seen"] = (prev or {}).get("first_seen", now)
        entry["last_seen"] = now
        data["jobs"][job.key] = entry
        if prev:
            updated += 1
        else:
            added += 1
    _sanitize(cfg, data)
    _backfill_dates(data)
    _prune(cfg, data)
    _save(cfg, data)
    return data, added, updated


def write_site(cfg: Config, data: dict | None = None) -> int:
    data = data if data is not None else load_archive(cfg)
    jobs = sorted(
        data["jobs"].values(),
        key=lambda j: (j.get("first_seen", ""), j.get("score", 0)),
        reverse=True,
    )
    meta = {
        "generated_at": iso_now(),
        "generated_hkt": hk_now().strftime("%d %b %Y, %H:%M"),
        "count": len(jobs),
        "min_score": cfg.board_min_score,
    }
    payload = (
        "window.JOB_META = " + json.dumps(meta, ensure_ascii=False) + ";\n"
        "window.JOBS = " + json.dumps(jobs, ensure_ascii=False) + ";\n"
    )
    # never let embedded data terminate a script tag
    payload = payload.replace("</", "<\\/")

    out_dir = cfg.docs_dir / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "jobs.js"
    tmp = out.with_suffix(".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, out)
    log.info("board: wrote %d jobs to %s", len(jobs), out.relative_to(cfg.root))
    return len(jobs)


def export_only(cfg: Config) -> int:
    data = load_archive(cfg)
    _sanitize(cfg, data)
    _backfill_dates(data)
    _save(cfg, data)
    return write_site(cfg, data)
