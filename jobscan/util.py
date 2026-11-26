import hashlib
import html
import re
from datetime import datetime, timedelta, timezone


def norm(s: str) -> str:
    """Lowercase alphanumeric key used for duplicate detection."""
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def clean(s: str) -> str:
    s = (s or "").replace("​", "").replace("﻿", "").replace("‌", "")
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)([^*\n]+?)\*(?![\w*])", r"\1", s)
    return re.sub(r"\s+", " ", s).strip()


def html_to_text(h: str) -> str:
    if not h:
        return ""
    h = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", h)
    h = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</div>|</h\d>|</tr>", "\n", h)
    h = re.sub(r"(?i)<li[^>]*>", "\n- ", h)
    h = re.sub(r"<[^>]+>", " ", h)
    h = html.unescape(h)
    h = re.sub(r"\*\*(.+?)\*\*", r"\1", h)
    h = re.sub(r"[ ​‌﻿]", " ", h)
    h = h.replace(" ", " ")
    h = re.sub(r"[ \t]+", " ", h)
    h = re.sub(r"\n\s*\n+", "\n\n", h)
    return h.strip()


def truncate(s: str, n: int) -> str:
    s = clean(s)
    if len(s) <= n:
        return s
    cut = s[:n]
    if " " in cut[cut.rfind(" ", 0, n) :]:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,.;:") + " ..."


def digest(s: str, n: int = 16) -> str:
    return hashlib.sha1((s or "").encode("utf-8", "ignore")).hexdigest()[:n]


def hk_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=8)


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_iso(s: str):
    try:
        return datetime.fromisoformat((s or "").replace("Z", "+00:00"))
    except Exception:
        return None


def relative_age_days(text: str):
    """Best-effort parse of JobsDB-style 'Listed 3d ago' text."""
    t = (text or "").lower()
    m = re.search(r"(\d+)\s*(minute|hour|day|week|month)", t)
    if not m:
        if "just" in t or "today" in t:
            return 0
        return None
    n, unit = int(m.group(1)), m.group(2)
    return {
        "minute": 0,
        "hour": 0,
        "day": n,
        "week": n * 7,
        "month": n * 30,
    }[unit]


def employment_type(title: str, text: str = "") -> str:
    t = f"{title} {text[:600]}".lower()
    if re.search(r"\bintern(ship)?s?\b", t):
        return "Internship"
    if re.search(r"\b(graduate|trainee|management trainee|mt programme)\b", t):
        return "Graduate programme"
    if re.search(r"\bpart[- ]time\b", t):
        return "Part-time"
    if re.search(r"\b(contract|fixed[- ]term)\b", t):
        return "Contract"
    return "Full-time"
