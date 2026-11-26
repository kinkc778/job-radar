import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip("'\"")
        if k and k not in os.environ:
            os.environ[k] = v


_load_dotenv(ROOT / ".env")


class Config:
    def __init__(self, path: Path | None = None):
        self.path = path or (ROOT / "config.json")
        self.raw = json.loads(self.path.read_text(encoding="utf-8"))

        self.email_to = os.getenv("EMAIL_TO") or self.raw.get("email_to", "")
        self.timezone_offset = int(self.raw.get("timezone_offset_hours", 8))
        self.min_score = int(self.raw.get("min_score", 65))
        self.max_jobs_in_email = int(self.raw.get("max_jobs_in_email", 20))
        self.max_detail_fetches = int(self.raw.get("max_detail_fetches", 60))
        self.backfill_days = int(self.raw.get("backfill_days", 7))
        self.backfill_max = int(self.raw.get("backfill_max", 5))
        self.send_empty_report = bool(self.raw.get("send_empty_report", True))
        self.send_empty_hour = int(self.raw.get("send_empty_hour_hkt", 7))
        self.include_internships = bool(self.raw.get("include_internships", True))
        self.board_min_score = int(self.raw.get("board_min_score", 60))
        self.board_keep_days = int(self.raw.get("board_keep_days", 180))
        self.board_max_jobs = int(self.raw.get("board_max_jobs", 600))
        self.board_include_analysis = bool(self.raw.get("board_include_analysis", True))

        self.queries = list(self.raw.get("queries", []))
        self.sources = dict(self.raw.get("sources", {}))
        self.jobsdb = dict(self.raw.get("jobsdb", {}))
        self.ctgoodjobs = dict(self.raw.get("ctgoodjobs", {}))
        self.ats = dict(self.raw.get("ats", {}))

        self.include_re = re.compile(self.raw.get("title_include_regex", ".*"))
        self.exclude_re = re.compile(self.raw.get("title_exclude_regex", r"^\b$"))
        self.blocked_re = re.compile(self.raw.get("blocked_title_regex", r"^\b$"))
        self.location_re = re.compile(self.raw.get("location_regex", "hong kong"))

        self.cv_path = ROOT / "cv_profile.json"
        self.cv = json.loads(self.cv_path.read_text(encoding="utf-8"))

        self.root = ROOT
        self.data_dir = ROOT / "data"
        self.docs_dir = ROOT / "docs"
        self.reports_dir = ROOT / "reports"
        self.state_path = self.data_dir / "seen_jobs.json"
        self.data_dir.mkdir(exist_ok=True)
        self.reports_dir.mkdir(exist_ok=True)

        sc = self.raw.get("scoring", {})
        self.llm_base_url = (os.getenv("LLM_BASE_URL") or sc.get("base_url")
                             or "https://api.deepseek.com").rstrip("/")
        self.llm_model = os.getenv("LLM_MODEL") or sc.get("model") or "deepseek-chat"
        self.llm_key = (os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY", "")).strip()
        self.llm_reasoning = os.getenv("LLM_REASONING_EFFORT") or sc.get("reasoning_effort", "")
        self.llm_json_mode = bool(sc.get("json_mode", True))
        self.llm_timeout = int(sc.get("timeout_seconds", 90))
        self.llm_max_output = int(sc.get("max_output_tokens", 2048))
        self.scoring_workers = int(os.getenv("SCORING_WORKERS", "4"))

        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_pass = os.getenv("SMTP_PASS", "")
        self.email_from = os.getenv("EMAIL_FROM") or self.smtp_user

        self.headless = os.getenv("HEADLESS", "1") not in ("0", "false", "False")
        self.chrome_channel = os.getenv("CHROME_CHANNEL", "chrome")
        self.dry_run = os.getenv("DRY_RUN", "") in ("1", "true", "True")

    def enabled_sources(self):
        return [k for k, v in self.sources.items() if v]
