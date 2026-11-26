import html
from datetime import datetime

from .config import Config
from .models import Job
from .util import truncate

FONT = ("-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,"
        "'PingFang HK','Microsoft JhengHei',sans-serif")
INK = "#111827"
MUTED = "#6b7280"
LINE = "#e5e7eb"
BG = "#f3f4f6"


def esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


def _nl2br(s) -> str:
    return esc(s).replace("\n", "<br>")


def _score_colors(score: int):
    if score >= 85:
        return "#047857", "#ecfdf5"
    if score >= 70:
        return "#1d4ed8", "#eff6ff"
    return "#b45309", "#fffbeb"


def _chip(text: str, tone: str = "grey") -> str:
    tones = {
        "grey": ("#f3f4f6", "#374151"),
        "blue": ("#eff6ff", "#1d4ed8"),
        "green": ("#ecfdf5", "#047857"),
        "amber": ("#fffbeb", "#b45309"),
        "violet": ("#f5f3ff", "#6d28d9"),
    }
    bg, fg = tones.get(tone, tones["grey"])
    return (f'<span style="display:inline-block;background:{bg};color:{fg};'
            f'font-size:11px;font-weight:600;padding:3px 8px;border-radius:999px;'
            f'margin:0 4px 4px 0;white-space:nowrap">{esc(text)}</span>')


def _family_tone(family: str) -> str:
    return {
        "Data Engineering": "blue",
        "Data Science": "violet",
        "Data Analytics / BI": "green",
        "AI / ML Engineering": "amber",
        "Solution Engineering": "grey",
    }.get(family, "grey")


def _card(job: Job, cfg: Config) -> str:
    fg, bg = _score_colors(job.score)
    title = esc(job.title)
    url = esc(job.url)
    meta = " &nbsp;·&nbsp; ".join(
        [esc(x) for x in [job.company, job.location] if x]
    )
    sub = " &nbsp;·&nbsp; ".join(
        [esc(x) for x in [job.salary, job.posted, job.employment_type] if x]
    )

    chips = _chip(job.role_family or "Role", _family_tone(job.role_family))
    if job.employment_type:
        chips += _chip(job.employment_type, "green" if job.employment_type != "Full-time" else "grey")
    if job.source:
        chips += _chip(job.source, "grey")
    if job.priority == "high":
        chips += _chip("High priority", "amber")

    why = ""
    if job.why_match:
        items = "".join(
            f'<li style="margin:0 0 4px 0;color:#065f46">{esc(x)}</li>'
            for x in job.why_match
        )
        why = (f'<div style="margin-top:12px"><div style="font-size:10.5px;'
               f'letter-spacing:1.2px;text-transform:uppercase;color:{MUTED};'
               f'font-weight:700;margin-bottom:5px">Why it fits</div>'
               f'<ul style="margin:0;padding-left:18px;font-size:13px;line-height:1.5">{items}</ul></div>')

    gaps = ""
    if job.gaps:
        items = "".join(
            f'<li style="margin:0 0 4px 0;color:#92400e">{esc(x)}</li>'
            for x in job.gaps
        )
        gaps = (f'<div style="margin-top:10px"><div style="font-size:10.5px;'
                f'letter-spacing:1.2px;text-transform:uppercase;color:{MUTED};'
                f'font-weight:700;margin-bottom:5px">Watch out</div>'
                f'<ul style="margin:0;padding-left:18px;font-size:13px;line-height:1.5">{items}</ul></div>')

    jd = ""
    if job.jd:
        excerpt = truncate(job.jd, 850)
        jd = (f'<div style="margin-top:14px;padding:10px 12px;background:#f9fafb;'
              f'border-left:3px solid #d1d5db;border-radius:0 6px 6px 0;'
              f'font-size:12.5px;line-height:1.55;color:#4b5563">'
              f'<div style="font-size:10.5px;letter-spacing:1.2px;text-transform:uppercase;'
              f'color:#9ca3af;font-weight:700;margin-bottom:4px">JD snapshot</div>'
              f'{_nl2br(excerpt)}</div>')

    summary = job.summary or truncate(job.jd, 220)

    return f"""
<div style="background:#ffffff;border:1px solid {LINE};border-radius:12px;
     padding:18px 18px 16px;margin:0 0 14px 0">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">
    <tr>
      <td width="58" valign="top" style="padding-right:12px">
        <div style="width:52px;height:52px;background:{bg};border-radius:12px;text-align:center;
             padding-top:7px;box-sizing:border-box">
          <div style="font-size:19px;font-weight:800;color:{fg};line-height:1.1">{job.score}</div>
          <div style="font-size:9px;font-weight:700;letter-spacing:.6px;color:{fg};opacity:.8;
               text-transform:uppercase">match</div>
        </div>
      </td>
      <td valign="top">
        <a href="{url}" style="font-size:17px;font-weight:700;color:{INK};text-decoration:none;
           line-height:1.35">{title}</a>
        <div style="font-size:12.5px;color:{MUTED};margin-top:3px">{meta}</div>
        {f'<div style="font-size:12px;color:#9ca3af;margin-top:2px">{sub}</div>' if sub else ''}
        <div style="margin-top:9px">{chips}</div>
      </td>
    </tr>
  </table>
  {f'<div style="font-size:13.5px;line-height:1.6;color:#374151;margin-top:12px">{esc(summary)}</div>' if summary else ''}
  {why}
  {gaps}
  {jd}
  <div style="margin-top:16px">
    <a href="{url}" style="display:inline-block;background:#111827;color:#ffffff;
       font-size:13px;font-weight:600;padding:9px 16px;border-radius:8px;
       text-decoration:none">Apply / view posting &rarr;</a>
    <span style="font-size:11.5px;color:#9ca3af;margin-left:10px">
      {esc(job.verdict)} &nbsp;·&nbsp; scored by {esc(job.scored_by or 'model')}
    </span>
  </div>
</div>"""


def _backfill(rows: list[dict]) -> str:
    if not rows:
        return ""
    tr = ""
    for r in rows:
        fg, _ = _score_colors(int(r.get("score") or 0))
        tr += (
            f'<tr>'
            f'<td style="padding:8px 0;font-size:13px;font-weight:700;color:{fg};width:38px">'
            f'{int(r.get("score") or 0)}</td>'
            f'<td style="padding:8px 8px;font-size:13px">'
            f'<a href="{esc(r.get("url"))}" style="color:{INK};text-decoration:none;font-weight:600">'
            f'{esc(r.get("title"))}</a>'
            f'<div style="font-size:11.5px;color:{MUTED}">{esc(r.get("company"))} · '
            f'{esc(r.get("location"))}</div></td>'
            f'</tr>'
        )
    return f"""
<div style="background:#ffffff;border:1px solid {LINE};border-radius:12px;padding:16px 18px;margin:18px 0 0 0">
  <div style="font-size:13px;font-weight:700;color:{INK};margin-bottom:6px">
    Still worth applying &mdash; high matches from earlier this week</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">
    {tr}
  </table>
</div>"""


def _sources_table(health: dict) -> str:
    if not health:
        return ""
    rows = ""
    for name, h in health.items():
        ok = h.get("ok")
        colour = "#047857" if ok else "#b91c1c"
        label = f'{h.get("count", 0)} listings' if ok else "failed"
        err = f' <span style="color:#9ca3af;font-size:11px">{esc(str(h.get("error", ""))[:90])}</span>' if h.get("error") else ""
        rows += (f'<tr><td style="padding:3px 0;font-size:12px;color:{MUTED}">{esc(name)}</td>'
                 f'<td style="padding:3px 0;font-size:12px;color:{colour};text-align:right">{label}{err}</td></tr>')
    return f"""
<div style="margin-top:22px;padding:14px 18px;border-top:1px solid {LINE}">
  <div style="font-size:10.5px;letter-spacing:1.2px;text-transform:uppercase;color:{MUTED};
       font-weight:700;margin-bottom:8px">Source health</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">{rows}</table>
</div>"""


def _stats_bar(stats: dict) -> str:
    cells = [
        ("scanned", stats.get("scanned", 0)),
        ("new", stats.get("new", 0)),
        ("matched", stats.get("matched", 0)),
    ]
    inner = ""
    for i, (label, value) in enumerate(cells):
        border = f"border-left:1px solid {LINE};" if i else ""
        inner += (f'<td style="text-align:center;padding:10px 4px;{border}">'
                  f'<div style="font-size:20px;font-weight:800;color:{INK}">{value}</div>'
                  f'<div style="font-size:10.5px;letter-spacing:1px;text-transform:uppercase;'
                  f'color:{MUTED};font-weight:600">{label}</div></td>')
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="border-collapse:collapse">{inner}</table>')


def build(new_jobs: list[Job], backfill: list[dict], stats: dict, health: dict,
          cfg: Config, run_dt: datetime, model_label: str):
    date_label = run_dt.strftime("%A %d %B %Y")
    short_date = run_dt.strftime("%d %b")
    n = len(new_jobs)
    matched = stats.get("matched", 0)

    if n:
        headline = f"{n} new match{'es' if n != 1 else ''} in Hong Kong"
        subject = f"[Job Scan] {n} new AI/data role{'s' if n != 1 else ''} in HK · {short_date}"
    else:
        headline = "No new matches today"
        subject = f"[Job Scan] No new matches · {short_date}"

    cards = "".join(_card(j, cfg) for j in new_jobs)
    empty = ""
    if not new_jobs:
        empty = f"""
<div style="background:#ffffff;border:1px dashed #d1d5db;border-radius:12px;
     padding:28px 22px;text-align:center;margin-bottom:14px">
  <div style="font-size:15px;font-weight:700;color:{INK}">Nothing cleared the {cfg.min_score}-point bar today.</div>
  <div style="font-size:13px;color:{MUTED};line-height:1.6;margin-top:6px">
    The scanner checked {stats.get('scanned', 0)} live listings and scored {stats.get('evaluated', 0)}.
    New ads appear throughout the week, so tomorrow's run may surface roles posted after today.
  </div>
</div>"""

    body = f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(subject)}</title></head>
<body style="margin:0;padding:0;background:{BG};">
<div style="background:{BG};padding:24px 12px;">
<div style="max-width:640px;margin:0 auto;font-family:{FONT};">
  <div style="background:#0b1220;border-radius:14px 14px 0 0;padding:26px 24px 22px;">
    <div style="font-size:10.5px;letter-spacing:2.2px;text-transform:uppercase;color:#7c8ea8;font-weight:700">
      Daily job scan &nbsp;·&nbsp; Hong Kong
    </div>
    <div style="font-size:25px;line-height:1.2;font-weight:800;color:#ffffff;margin-top:8px">
      {esc(headline)}
    </div>
    <div style="font-size:12.5px;color:#9fb0c6;margin-top:6px">
      {esc(date_label)} &nbsp;·&nbsp; scored against your CV &nbsp;·&nbsp; threshold {cfg.min_score}/100
    </div>
  </div>
  <div style="background:#ffffff;border:1px solid {LINE};border-top:0;padding:6px 14px;">
    {_stats_bar(stats)}
  </div>
  <div style="margin-top:16px">
    {empty}
    {cards}
    {_backfill(backfill)}
  </div>
  {_sources_table(health)}
  <div style="padding:18px 4px 6px;text-align:center;font-size:11px;color:#9ca3af;line-height:1.7">
    Generated by <b>job_scanning</b> · {esc(model_label)} · {stats.get('elapsed', 0)}s<br>
    Tune queries, sources and the {cfg.min_score}-point threshold in <code>config.json</code>.
    Jobs you have already been sent are remembered in <code>data/seen_jobs.json</code>.
  </div>
</div>
</div>
</body></html>"""

    # plain text
    lines = [f"DAILY JOB SCAN — {date_label}", headline, ""]
    lines.append(f"Scanned {stats.get('scanned', 0)} · new {stats.get('new', 0)} · matched {matched}")
    lines.append("")
    for j in new_jobs:
        lines.append(f"[{j.score}] {j.title} — {j.company}")
        lines.append(f"      {j.location} | {j.employment_type} | {j.role_family}")
        if j.summary:
            lines.append(f"      {j.summary}")
        for w in j.why_match:
            lines.append(f"      + {w}")
        for g in j.gaps:
            lines.append(f"      ! {g}")
        lines.append(f"      Apply: {j.url}")
        lines.append("")
    if backfill:
        lines.append("STILL WORTH APPLYING")
        for r in backfill:
            lines.append(f"[{r.get('score')}] {r.get('title')} — {r.get('company')} | {r.get('url')}")
        lines.append("")
    lines.append("Sources: " + ", ".join(
        f"{k}={'ok' if v.get('ok') else 'fail'}({v.get('count', 0)})" for k, v in health.items()
    ))
    lines.append("")
    return subject, body, "\n".join(lines)
