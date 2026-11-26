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


_WORD_NUM = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12,
}

_UNIT_DAYS = {
    "minute": 0, "min": 0, "m": 0,
    "hour": 0, "hr": 0, "h": 0,
    "day": 1, "d": 1,
    "week": 7, "wk": 7, "w": 7,
    "month": 30, "mo": 30,
    "year": 365, "yr": 365, "y": 365,
}


def relative_age_days(text: str):
    """Best-effort parse of board text like 'Listed 3d ago' or 'two hours ago'."""
    t = (text or "").lower().strip()
    if not t:
        return None
    if re.search(r"\b(just|today|new)\b", t):
        return 0
    if "yesterday" in t:
        return 1

    m = re.search(
        r"\b(\d+)\s*\+?\s*(minutes?|mins?|hours?|hrs?|days?|weeks?|wks?|months?|mos?"
        r"|years?|yrs?|m|h|d|w|y)\b",
        t,
    )
    if m:
        n = int(m.group(1))
        unit = m.group(2).rstrip("s")
        if unit in ("minute", "min"):
            return 0
        if unit in ("hour", "hr"):
            return 0
        if unit == "day":
            return n
        if unit in ("week", "wk"):
            return n * 7
        if unit == "month":
            return n * 30
        if unit in ("year", "yr"):
            return n * 365
        return n * _UNIT_DAYS.get(unit, 1)

    m = re.search(
        r"\b(a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
        r"\s+(minute|hour|day|week|month|year)s?\b",
        t,
    )
    if m:
        n = _WORD_NUM[m.group(1)]
        return n * _UNIT_DAYS[m.group(2)]

    return None


def relative_to_date(text: str) -> str:
    """'Listed 3d ago' -> '2026-11-23' (HKT). Empty when unparseable."""
    days = relative_age_days(text)
    if days is None:
        return ""
    return (hk_now() - timedelta(days=days)).strftime("%Y-%m-%d")


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
