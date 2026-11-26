import argparse
import logging
import sys
import time
from contextlib import ExitStack

from . import mailer, report, webexport
from .browser import BrowserSession
from .config import Config
from .models import Job
from .prefilter import dedupe_enriched, dedupe_jobs, quick_score, title_relevant
from .scoring import Scorer
from .sources import ats, ctgoodjobs, jobsdb
from .state import State
from .util import hk_now, iso_now

log = logging.getLogger("jobscan")


def _setup_logging(verbose: bool):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def run(cfg: Config, args) -> int:
    started = time.time()
    run_dt = hk_now()
    state = State(cfg.state_path)
    health: dict = {}
    raw: list[Job] = []

    enabled = cfg.enabled_sources()
    if args.sources:
        wanted = {s.strip() for s in args.sources.split(",") if s.strip()}
        cfg.sources = {k: (k in wanted) for k in cfg.sources}
        enabled = cfg.enabled_sources()
    log.info("sources enabled: %s", ", ".join(enabled) or "none")
    if not enabled:
        log.error("no sources enabled")
        return 1

    stack = ExitStack()
    session = None
    try:
        # ---------------- collect listings ----------------
        if "jobsdb" in enabled:
            try:
                session = stack.enter_context(
                    BrowserSession(headless=cfg.headless, channel=cfg.chrome_channel)
                )
                found = jobsdb.collect(
                    session,
                    cfg.queries,
                    pages=int(cfg.jobsdb.get("pages_per_query", 1)),
                    daterange=cfg.jobsdb.get("daterange_days", 14),
                )
                raw.extend(found)
                health["jobsdb"] = {"ok": True, "count": len(found)}
            except Exception as e:
                health["jobsdb"] = {"ok": False, "count": 0, "error": str(e)[:160]}
                log.error("jobsdb source failed: %s", str(e)[:200])

        if "ctgoodjobs" in enabled:
            try:
                found = ctgoodjobs.collect(
                    cfg.queries,
                    pages=int(cfg.ctgoodjobs.get("pages_per_query", 1)),
                    session=session,
                )
                raw.extend(found)
                health["ctgoodjobs"] = {"ok": True, "count": len(found)}
            except Exception as e:
                health["ctgoodjobs"] = {"ok": False, "count": 0, "error": str(e)[:160]}
                log.error("ctgoodjobs source failed: %s", str(e)[:200])

        if "ats" in enabled:
            try:
                found = ats.collect(cfg)
                raw.extend(found)
                health["ats"] = {"ok": True, "count": len(found)}
            except Exception as e:
                health["ats"] = {"ok": False, "count": 0, "error": str(e)[:160]}
                log.error("ats source failed: %s", str(e)[:200])

        if not raw:
            log.error("no listings collected from any source")
            if any(h.get("ok") for h in health.values()):
                pass
            else:
                return 1

        # ---------------- dedupe + filter ----------------
        unique = dedupe_jobs(raw)
        fresh = [j for j in unique if not state.is_seen(j)]
        log.info("collected %d listings (%d unique, %d new)", len(raw), len(unique), len(fresh))

        relevant: list[Job] = []
        for job in fresh:
            ok, why = title_relevant(job, cfg)
            if ok:
                relevant.append(job)
            elif why == "too_senior":
                state.mark(job, "filtered_senior")
        log.info("%d new listings pass the title filter", len(relevant))

        relevant.sort(key=lambda j: (-quick_score(j), 0 if j.jd else 1))

        # ---------------- choose what to enrich ----------------
        budget = int(args.limit or cfg.max_detail_fetches)
        hard_cap = int(budget * 1.5)
        caps = {
            "jobsdb": int(budget * 0.55),
            "ctgoodjobs": int(budget * 0.25),
            "greenhouse": budget - int(budget * 0.55) - int(budget * 0.25),
        }
        queues = {"jobsdb": [], "ctgoodjobs": [], "greenhouse": []}
        selected: list[Job] = []

        for job in relevant:
            if len(selected) >= hard_cap:
                break
            needs_detail = not job.jd
            if not needs_detail:
                selected.append(job)
                continue
            if job.source in queues:
                cap = caps.get(job.source, 0)
                if cap > 0:
                    caps[job.source] -= 1
                    queues[job.source].append(job)
                    selected.append(job)
                # otherwise leave it unseen: next run will pick it up
            else:
                selected.append(job)

        # ---------------- fetch JDs ----------------
        if session and queues["jobsdb"]:
            n = jobsdb.enrich(session, queues["jobsdb"], len(queues["jobsdb"]))
            log.info("jobsdb: fetched %d/%d JDs", n, len(queues["jobsdb"]))
        if queues["ctgoodjobs"]:
            n = ctgoodjobs.enrich(queues["ctgoodjobs"], len(queues["ctgoodjobs"]),
                                  session=session)
            log.info("ctgoodjobs: fetched %d/%d JDs", n, len(queues["ctgoodjobs"]))
        if queues["greenhouse"]:
            n = ats.enrich(queues["greenhouse"], len(queues["greenhouse"]))
            log.info("greenhouse: fetched %d/%d JDs", n, len(queues["greenhouse"]))
    finally:
        stack.close()

    # ---------------- finalise candidates ----------------
    today = run_dt.strftime("%Y-%m-%d")
    final: list[Job] = []
    for job in selected:
        if job.extra.get("expired"):
            state.mark(job, "expired")
            continue
        if job.extra.get("valid_through") and job.extra["valid_through"] < today:
            state.mark(job, "expired")
            continue
        if not job.jd and job.extra.get("teaser"):
            job.jd = job.extra["teaser"]
            job.extra["jd_partial"] = True
        if not job.jd:
            continue  # leave unseen so a later run can retry
        if not job.company:
            job.company = "Unknown company"
        final.append(job)

    # Company names resolve only after enrichment, so merge cross-source twins here.
    final, duplicates = dedupe_enriched(final)
    for dup in duplicates:
        state.mark(dup, "duplicate")
    if duplicates:
        log.info("merged %d cross-source duplicates", len(duplicates))

    log.info("scoring %d jobs", len(final))

    # ---------------- score ----------------
    scorer = Scorer(cfg)
    scorer.score_many(final)

    try:
        archive, added, updated = webexport.update_archive(cfg, final)
        total = webexport.write_site(cfg, archive)
        log.info("board: %d jobs on the board (%d new, %d refreshed)", total, added, updated)
    except Exception as e:
        log.warning("board export failed: %s", str(e)[:160])

    matched = [j for j in final if j.score >= cfg.min_score]
    matched.sort(key=lambda j: (-j.score, -quick_score(j)))
    top = matched[: cfg.max_jobs_in_email]

    # backfill from earlier queued matches (before we mark this run)
    backfill_rows = []
    if len(top) < 8:
        backfill_rows = state.queued_backfill(cfg.min_score, cfg.backfill_days,
                                              cfg.backfill_max)

    # ---------------- report + email ----------------
    model_label = (cfg.llm_model if not scorer.disabled
                   else "heuristic scorer (LLM endpoint unavailable)")
    stats = {
        "scanned": len(unique),
        "new": len(fresh),
        "candidates": len(relevant),
        "evaluated": len(final),
        "matched": len(matched),
        "elapsed": 0,
    }
    subject, html_body, text_body = report.build(
        top, backfill_rows, stats, health, cfg, run_dt, model_label
    )

    report_path = cfg.reports_dir / f"{run_dt:%Y-%m-%d_%H%M}.html"
    report_path.write_text(html_body, encoding="utf-8")
    log.info("report written: %s", report_path)

    heartbeat = (cfg.send_empty_report
                 and cfg.send_empty_hour <= run_dt.hour < cfg.send_empty_hour + 2)
    should_send = (not cfg.dry_run and not args.no_email and (top or heartbeat))
    sent = False
    if should_send:
        sent = mailer.send(cfg, subject, html_body, text_body)
    else:
        log.info("email skipped (dry-run/no-email/empty) - open the report file to inspect")

    # ---------------- persist state ----------------
    top_keys = {j.key for j in top}
    backfill_keys = {r["key"] for r in backfill_rows}
    for job in final:
        if job.key in top_keys:
            state.mark(job, "emailed" if sent else "queued")
        elif job.score >= cfg.min_score:
            state.mark(job, "queued")
        else:
            state.mark(job, "low_score")
    if sent:
        for key in backfill_keys:
            state.mark_backfill_emailed(key)

    stats["elapsed"] = int(time.time() - started)
    stats["emailed"] = len(top) if sent else 0
    stats["sent"] = sent
    state.record_run({
        "at": iso_now(),
        **{k: stats[k] for k in ("scanned", "new", "candidates", "evaluated",
                                "matched", "emailed", "elapsed")},
        "sources": {k: {"ok": v.get("ok"), "count": v.get("count", 0)}
                    for k, v in health.items()},
    })
    state.prune()
    state.save()
    _cleanup_reports(cfg)

    ok_sources = [k for k, v in health.items() if v.get("ok")]
    log.info("done in %ds - %d matched, %d emailed, sources ok: %s",
             stats["elapsed"], len(matched), len(top), ", ".join(ok_sources) or "none")

    if not ok_sources:
        log.error("all sources failed")
        return 1
    return 0


def _cleanup_reports(cfg: Config, keep: int = 60):
    files = sorted(cfg.reports_dir.glob("*.html"))
    for f in files[:-keep]:
        try:
            f.unlink()
        except Exception:
            pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="jobscan", description="HK AI/data job scanner")
    parser.add_argument("--dry-run", action="store_true", help="scan and build the report, do not email")
    parser.add_argument("--no-email", action="store_true", help="same as --dry-run for sending")
    parser.add_argument("--sources", default="", help="comma list: jobsdb,ctgoodjobs,ats")
    parser.add_argument("--limit", type=int, default=0, help="max detail fetches this run")
    parser.add_argument("--headed", action="store_true", help="show the browser window")
    parser.add_argument("--include-interns", action="store_true",
                        help="include internships for this run (config default: excluded)")
    parser.add_argument("--export-only", action="store_true",
                        help="rebuild docs/data/jobs.js from the archive and exit")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    _setup_logging(args.verbose)
    cfg = Config()
    if args.dry_run:
        cfg.dry_run = True
    if args.headed:
        cfg.headless = False
    if args.include_interns:
        cfg.include_internships = True

    if args.export_only:
        n = webexport.export_only(cfg)
        log.info("board rebuilt with %d jobs", n)
        return 0

    log.info("job scan starting at %s (HKT)", hk_now().strftime("%Y-%m-%d %H:%M"))
    try:
        return run(cfg, args)
    except KeyboardInterrupt:
        log.warning("interrupted")
        return 130
    except Exception as e:
        log.exception("fatal: %s", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
