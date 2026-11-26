import json
import logging
import re
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import Config
from .models import Job
from .util import clean, truncate

log = logging.getLogger("jobscan")

ROLE_FAMILIES = [
    "Data Engineering",
    "Data Science",
    "Data Analytics / BI",
    "AI / ML Engineering",
    "Solution Engineering",
    "Other",
]

SYSTEM_PROMPT = """You are a strict technical recruiter in Hong Kong screening job ads for one candidate.
The candidate is a final-year undergraduate in AI & Information Engineering seeking FULL-TIME graduate / entry-level roles (0-2 years) in Hong Kong as a Data Engineer, Analytics Engineer, Data Scientist, Data Analyst, BI Analyst, AI/LLM Engineer, AI Agent Developer, Machine Learning Engineer or Solution Engineer. The candidate is NOT looking for internships.

Score the fit from 0 to 100 using this calibration:
- 90-100: near-perfect; the candidate clearly meets almost every requirement today.
- 75-89: strong fit; meets most core requirements, realistic to get an interview.
- 60-74: plausible stretch; meets some requirements but has a visible gap.
- 40-59: weak; the role is adjacent or demands more experience.
- 0-39: poor; wrong discipline, wrong seniority, or not in Hong Kong.

Rules:
- Most job ads should score below 55. Do not inflate.
- Penalise hard: 3+ years of professional experience required, senior/lead/manager titles, non-HK locations, roles that are mainly sales or support, PhD requirements, internships.
- Reward: Python/SQL/PySpark/dbt/Azure/Databricks, ETL/ELT, RAG/LLM/AI agents, data modelling, BI, cloud data platforms, fresh-graduate or graduate-programme openings.
- The candidate is still a student. Graduate programmes and entry-level roles are a good fit, not a downgrade.
- If the job description is thin, judge from the title and say so in the summary.

Return ONLY a JSON object with these keys:
score: integer 0-100
verdict: one short phrase (e.g. "Strong fit", "Good stretch", "Too senior")
role_family: one of "Data Engineering", "Data Science", "Data Analytics / BI", "AI / ML Engineering", "Solution Engineering", "Other"
summary: 2-3 sentences on what the role actually does day to day
why_match: array of up to 3 short strings citing concrete evidence from the candidate's CV
gaps: array of up to 2 short strings naming what the candidate lacks for this role
seniority_fit: one of "entry", "stretch", "too senior"
priority: one of "high", "medium", "low"
"""

SKILL_PATTERNS = {
    "Python": r"\bpython\b",
    "SQL": r"\bsql\b",
    "PySpark": r"\b(py?spark)\b",
    "Databricks": r"\bdatabricks\b",
    "Azure": r"\bazure\b",
    "dbt": r"\bdbt\b",
    "ETL/ELT": r"\b(etl|elt)\b",
    "data modelling": r"\b(data model|dimensional|star schema|data warehouse)\w*",
    "Power BI": r"\b(power bi|tableau)\b",
    "Airflow": r"\bairflow\b",
    "Kafka": r"\bkafka\b",
    "Machine learning": r"\b(machine learning|scikit|ml model)\b",
    "LLM": r"\b(llm|large language model)\b",
    "RAG": r"\b(rag|retrieval[- ]augmented)\b",
    "AI agents": r"\b(ai agent|agentic|langchain|llamaindex)\b",
    "Prompt engineering": r"\bprompt engineering\b",
    "Vector DB": r"\b(vector database|chromadb|pinecone|faiss|milvus|weaviate)\b",
    "Docker": r"\bdocker\b",
    "Git": r"\bgit\b",
    "AWS": r"\baws\b",
    "GCP": r"\b(gcp|bigquery)\b",
    "MongoDB": r"\bmongo(db)?\b",
    "Java": r"\bjava\b",
    "Django": r"\bdjango\b",
}


def cv_brief(cfg: Config) -> str:
    p = cfg.cv
    lines = [
        f"Name: {p.get('name')}",
        f"Headline: {p.get('headline')}",
        "Target roles: " + ", ".join(p.get("target_roles", [])),
        "Target location: " + p.get("target_location", "Hong Kong"),
        "Seniority: " + p.get("seniority", ""),
        "",
        "Education:",
    ]
    lines += [f"- {e}" for e in p.get("education", [])]
    lines += ["", "Experience:"]
    lines += [f"- {e}" for e in p.get("experience", [])]
    lines += ["", "Skills:"]
    for group, items in (p.get("skills") or {}).items():
        lines.append(f"- {group}: {', '.join(items)}")
    lines += ["", "Note: " + p.get("candidate_notes", "")]
    return "\n".join(lines)


class Scorer:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.base_url = (cfg.llm_base_url or "").rstrip("/")
        self.model = cfg.llm_model
        self.api_key = cfg.llm_key
        self.url = f"{self.base_url}/chat/completions" if self.base_url else ""
        needs_key = "api.deepseek.com" in self.base_url
        self.disabled = not self.base_url or (needs_key and not self.api_key)
        self._lock = threading.Lock()
        self._done = 0
        self._failed = 0
        self._ok = 0
        self.cv = cv_brief(cfg)
        if self.disabled:
            log.warning("no usable LLM endpoint/key - heuristic scorer only")
        else:
            log.info("scoring with %s", self.model)

    # ---------- public ----------
    def score_many(self, jobs: list[Job]) -> list[Job]:
        if not jobs:
            return jobs
        workers = max(1, min(self.cfg.scoring_workers, len(jobs)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(self._score_one, j): j for j in jobs}
            for fut in as_completed(futures):
                job = futures[fut]
                try:
                    fut.result()
                except Exception as e:
                    log.warning("scoring crashed for %s: %s", job.title, str(e)[:120])
                    self._apply_heuristic(job, error=str(e))
                with self._lock:
                    self._done += 1
                    if self._done % 5 == 0 or self._done == len(jobs):
                        log.info("scored %d/%d jobs (%d api fallbacks)",
                                 self._done, len(jobs), self._failed)
        return jobs

    # ---------- internals ----------
    def _score_one(self, job: Job):
        if self.disabled:
            self._apply_heuristic(job)
            return
        try:
            result = self._call_llm(job)
            self._apply_result(job, result, "deepseek")
            with self._lock:
                self._ok += 1
        except DisabledError:
            self._apply_heuristic(job)
        except Exception as e:
            with self._lock:
                self._failed += 1
                if self._failed >= 8 and self._ok == 0:
                    self.disabled = True
                    log.error("LLM endpoint failing consistently - heuristic for the rest of this run")
            log.warning("scoring failed (%s) - heuristic fallback for '%s'",
                        str(e)[:110], job.title[:60])
            self._apply_heuristic(job)

    def _call_llm(self, job: Job) -> dict:
        jd = truncate(job.jd or job.extra.get("teaser", ""), 7000)
        user = (
            "CANDIDATE\n"
            f"{self.cv}\n\n"
            "JOB\n"
            f"Title: {job.title}\n"
            f"Company: {job.company}\n"
            f"Location: {job.location}\n"
            f"Employment type: {job.employment_type}\n"
            f"Salary: {job.salary or 'not stated'}\n"
            f"Description:\n{jd}\n\n"
            "Score the fit and return the JSON object."
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            "temperature": 0.1,
            "max_tokens": self.cfg.llm_max_output,
            "stream": False,
        }
        if self.cfg.llm_json_mode:
            payload["response_format"] = {"type": "json_object"}
        if self.cfg.llm_reasoning:
            payload["reasoning_effort"] = self.cfg.llm_reasoning

        minimal = {
            "model": self.model,
            "messages": payload["messages"],
            "max_tokens": self.cfg.llm_max_output,
        }

        last = None
        for attempt in range(3):
            try:
                status, body = self._post(payload)
            except Exception as e:
                last = e
                time.sleep(1.5 * (attempt + 1))
                continue

            if status == 200:
                try:
                    return self._parse_response(body)
                except Exception as e:
                    last = e
                    log.debug("unparseable LLM response: %s | %s", e, body[:200])
                    time.sleep(1.0)
                    continue
            if status in (401, 403):
                self.disabled = True
                raise DisabledError(f"auth failed: HTTP {status}")
            if status == 400:
                last = RuntimeError(body[:200])
                if payload is not minimal:
                    log.debug("LLM rejected optional params; retrying minimal payload")
                    payload = minimal
                    continue
                raise last
            if status == 429 or status >= 500:
                last = RuntimeError(f"HTTP {status}: {body[:160]}")
                time.sleep(2 * (attempt + 1))
                continue
            raise RuntimeError(f"HTTP {status}: {body[:160]}")

        raise RuntimeError(f"LLM request failed: {last}")

    def _post(self, payload: dict) -> tuple[int, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.llm_timeout) as r:
                return r.status, r.read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "ignore")

    @staticmethod
    def _parse_response(body: str) -> dict:
        data = json.loads(body)
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        if not content and isinstance(message.get("reasoning_content"), str):
            content = message["reasoning_content"]
        if not content:
            raise ValueError(f"empty content (finish={choice.get('finish_reason')})")
        return Scorer._parse_json(content)

    @staticmethod
    def _parse_json(text: str) -> dict:
        t = (text or "").strip()
        t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.M).strip()
        start, end = t.find("{"), t.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("no JSON object in response")
        d = json.loads(t[start : end + 1])
        d["score"] = max(0, min(100, int(round(float(d.get("score", 0))))))
        return d

    def _apply_result(self, job: Job, d: dict, by: str):
        job.score = int(d.get("score", 0))
        job.verdict = clean(str(d.get("verdict", "")))[:80]
        rf = str(d.get("role_family", "Other"))
        job.role_family = rf if rf in ROLE_FAMILIES else "Other"
        job.summary = clean(str(d.get("summary", "")))[:600]
        job.why_match = [clean(str(x))[:180] for x in (d.get("why_match") or [])][:3]
        job.gaps = [clean(str(x))[:180] for x in (d.get("gaps") or [])][:2]
        job.seniority_fit = clean(str(d.get("seniority_fit", "")))[:20]
        job.priority = clean(str(d.get("priority", "")))[:10]
        job.scored_by = by

    def _apply_heuristic(self, job: Job, error: str = ""):
        text = f"{job.title}\n{job.jd or job.extra.get('teaser', '')}".lower()
        title = (job.title or "").lower()
        score = 28.0

        title_points = []
        if re.search(r"data engineer|analytics engineer", title):
            title_points.append(25)
        if re.search(r"data scientist|machine learning|\bml\b|\bai\b|llm|ai agent", title):
            title_points.append(22)
        if re.search(r"data analyst|business intelligence|\bbi\b", title):
            title_points.append(18)
        if re.search(r"solution engineer|forward deployed", title):
            title_points.append(15)
        if re.search(r"technology|digital", title):
            title_points.append(10)
        score += max(title_points) if title_points else 6

        hits = [name for name, pat in SKILL_PATTERNS.items() if re.search(pat, text)]
        score += min(len(hits), 8) * 3.0

        if re.search(r"\b(5|6|7|8|9|10)\+?\s*years?", text):
            score -= 25
        elif re.search(r"\b(3|4)\+?\s*years?", text):
            score -= 15
        elif re.search(r"\b2\+?\s*years?", text):
            score -= 5

        if re.search(r"\b(phd|doctorate)\b", text):
            score -= 20
        if re.search(r"\b(intern|internship)\b", text):
            score -= 10
        if re.search(r"\b(fresh graduate|graduate programme|graduate program|final[- ]year)\b", text):
            score += 10
        if re.search(r"\b(graduate|trainee)\b", text):
            score += 5
        if re.search(r"hong kong", f"{job.location}".lower()):
            score += 8

        job.score = max(0, min(98, int(round(score))))
        job.verdict = "Heuristic fit"
        if re.search(r"data engineer|etl|pipeline|databricks|spark", title + " " + text):
            job.role_family = "Data Engineering"
        elif re.search(r"machine learning|\bml\b|llm|ai agent|\bai\b", title + " " + text):
            job.role_family = "AI / ML Engineering"
        elif re.search(r"data scientist|statistic|model", title + " " + text):
            job.role_family = "Data Science"
        elif re.search(r"data analyst|business intelligence|\bbi\b|dashboard", title + " " + text):
            job.role_family = "Data Analytics / BI"
        elif "solution" in title:
            job.role_family = "Solution Engineering"
        else:
            job.role_family = "Other"

        src = job.jd or job.extra.get("teaser", "")
        first = re.split(r"(?<=[.!?])\s+", clean(src))
        job.summary = truncate(" ".join(first[:2]), 260) if src else "No description available."
        job.why_match = [f"Experience with {h}" for h in hits[:3]]
        job.gaps = []
        m = re.search(r"\b([3-9]|10)\+?\s*years?", text)
        if m:
            job.gaps.append(f"Ad asks for {m.group(1)}+ years of experience")
        if error:
            job.gaps.append("AI scoring unavailable - heuristic used")
        job.seniority_fit = "stretch" if job.score < 70 else "entry"
        job.priority = "high" if job.score >= 80 else ("medium" if job.score >= 65 else "low")
        job.scored_by = "heuristic"


class DisabledError(Exception):
    pass
