"""One-off probe: which job platforms are reachable from a GitHub runner?

Run by .github/workflows/probe.yml. Prints status, size and content previews.
No secrets are used. Designed so one bad endpoint never kills the probe.
"""

import json
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

BASE_HEADERS = {
    "User-Agent": UA,
    "Accept": "*/*",
    "Accept-Language": "en-HK,en;q=0.9",
}


def show(name, status, size, extra, body):
    preview = body[:160].decode("utf-8", "ignore").replace("\n", " ").replace("\r", " ")
    print(f"{name:34} {status!s:>7} {size:>8}B {extra[:38]:38} :: {preview}", flush=True)


def read_safe(fn, n=600):
    try:
        return fn(n)
    except Exception:
        return b""


def fetch(name, url, method="GET", headers=None, body=None, timeout=14, full=False):
    h = dict(BASE_HEADERS)
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read(None if full else 300000)
            show(name, r.status, len(data),
                 f"{time.time()-started:.1f}s {r.headers.get('content-type','')[:20]}", data)
            return data
    except urllib.error.HTTPError as e:
        data = read_safe(e.read)
        show(name, f"HTTP{e.code}", len(data), f"{time.time()-started:.1f}s", data)
        return data
    except Exception as e:
        show(name, "ERR", 0, type(e).__name__, str(e).encode()[:140])
        return b""


def curl_cffi_test(name, url):
    try:
        from curl_cffi import requests as creq
        r = creq.get(url, impersonate="chrome", timeout=15,
                     headers={"Accept-Language": "en-HK,en;q=0.9"})
        show(name, r.status_code, len(r.content), "curl_cffi", r.content[:160])
    except Exception as e:
        show(name, "ERR", 0, f"curl_cffi {type(e).__name__}", str(e).encode()[:140])


def cloudscraper_test(name, url):
    try:
        import cloudscraper
        s = cloudscraper.create_scraper()
        r = s.get(url, timeout=20, headers={"Accept-Language": "en-HK,en;q=0.9"})
        show(name, r.status_code, len(r.content), "cloudscraper", r.content[:160])
    except Exception as e:
        show(name, "ERR", 0, f"cloudscraper {type(e).__name__}", str(e).encode()[:140])


def linkedin():
    url = ("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
           "?keywords=data%20engineer&location=Hong%20Kong&f_TPR=r604800&start=0")
    html = fetch("linkedin.guest.search", url, full=True).decode("utf-8", "ignore")
    ids = re.findall(r"jobs/view/(\d+)", html)
    titles = re.findall(r'base-search-card__title[^>]*>\s*([^<]+)', html)
    print(f"   linkedin cards: ids={len(set(ids))} titles={titles[:4]}", flush=True)
    if ids:
        jid = ids[0]
        detail = fetch(f"linkedin.guest.detail",
                       f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{jid}", full=True)
        d = detail.decode("utf-8", "ignore")
        m = re.search(r'show-more-less-html__markup[^>]*>(.*?)</div>', d, re.S)
        txt = re.sub(r"<[^>]+>", " ", m.group(1)) if m else ""
        print(f"   linkedin detail {jid}: bytes={len(d)} jd={len(re.sub(r'\\s+',' ',txt))}", flush=True)


def oracle():
    url = ("https://jpmc.fa.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
           "?onlyData=true&finder=findReqs;siteNumber=CX_1001,facetsList=LOCATIONS%3BWORK_LOCATIONS,"
           "limit=50,sortBy=POSTING_DATES_DESC,keyword=data")
    data = fetch("oracle.jpm.list", url, full=True)
    try:
        d = json.loads(data)
        items = d["items"][0]
        reqs = items.get("requisitionList", [])
        print(f"   oracle total={items.get('TotalJobsCount')} returned={len(reqs)}", flush=True)
        for r in reqs[:5]:
            print(f"   - {r.get('Title','')[:60]} | {r.get('PrimaryLocation','')} | {r.get('PostedDate')}", flush=True)
        hk = [r for r in reqs if "hong kong" in str(r.get("PrimaryLocation", "")).lower()]
        if hk:
            rid = hk[0].get("Id")
            fetch("oracle.jpm.detail",
                  ("https://jpmc.fa.oraclecloud.com/hcmRestApi/resources/latest/"
                   f"recruitingCEJobRequisitionDetails?expand=all&onlyData=true&finder=ById;requisitionId={rid},"
                   "siteNumber=CX_1001"), full=True)
    except Exception as e:
        print("   oracle parse err", e, flush=True)


def talent():
    html = fetch("talent.hk", "https://hk.talent.com/jobs?k=data+engineer", full=True).decode("utf-8", "ignore")
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        print("   talent: no __NEXT_DATA__", flush=True)
        return
    try:
        d = json.loads(m.group(1))
        txt = json.dumps(d)
        print(f"   talent next_data bytes={len(txt)} jobish={txt.lower().count('jobtitle')} "
              f"hits={txt.lower().count('data engineer')}", flush=True)
    except Exception as e:
        print("   talent parse err", e, flush=True)


def html_api_hints(name, url):
    html = fetch(name, url, full=True).decode("utf-8", "ignore")
    urls = sorted(set(re.findall(r"https?://[^\"'\\s]+", html)))
    api = [u for u in urls if "/api" in u or "api." in u][:8]
    print(f"   {name} api hints: {api}", flush=True)


def smartrecruiters():
    for slug in ["McDonalds", "Visa", "Mastercard", "Accenture", "IBM", "Cognizant",
                 "Infosys", "Wipro", "Capgemini", "EY", "KPMG", "HSBC", "Manulife",
                 "Prudential", "Zurich", "Allianz", "AXA", "DHL", "Maersk", "Unilever"]:
        try:
            data = fetch(f"sr.{slug}", f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100",
                         full=True)
            d = json.loads(data)
            content = d.get("content", [])
            hk = [j for j in content if "hong kong" in json.dumps(j.get("location") or {}).lower()]
            if hk:
                print(f"   SR {slug}: total={d.get('totalFound')} hk={len(hk)} :: "
                      f"{[j.get('name','')[:40] for j in hk[:4]]}", flush=True)
        except Exception:
            pass


def workday():
    for tenant in ["hkex", "mtr", "cathaypacific", "manulife", "aia", "sc", "ms",
                   "swirepacific", "clp", "hanglung", "bochk", "pwc", "deloitte",
                   "kpmg", "ey", "hsbc"]:
        url = f"https://{tenant}.wd3.myworkdayjobs.com/"
        try:
            req = urllib.request.Request(url, headers=BASE_HEADERS)
            with urllib.request.urlopen(req, timeout=12) as r:
                final = r.geturl()
                data = r.read(2000)
                show(f"wd.{tenant}", r.status, len(data), f"final={final[:60]}", data)
        except urllib.error.HTTPError as e:
            show(f"wd.{tenant}", f"HTTP{e.code}", 0, "", b"")
        except Exception as e:
            show(f"wd.{tenant}", "ERR", 0, type(e).__name__, str(e).encode()[:80])


def main():
    print("== platform probes ==", flush=True)
    tasks = [
        ("linkedin", linkedin),
        ("oracle", oracle),
        ("talent", talent),
        ("sr", smartrecruiters),
        ("html.labour", lambda: html_api_hints("labour", "https://www1.jobs.gov.hk/0/en/")),
        ("html.jijis", lambda: html_api_hints("jijis", "https://www.jijis.org.hk/")),
        ("html.efc", lambda: html_api_hints("efc", "https://www.efinancialcareers.hk/search?q=data%20engineer")),
    ]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fn): name for name, fn in tasks}
        for f in as_completed(futures):
            pass

    print("\n== bypass attempts ==", flush=True)
    curl_cffi_test("jobsdb.curl_cffi", "https://hk.jobsdb.com/jobs?keywords=data%20engineer")
    curl_cffi_test("ctg.curl_cffi", "https://jobs.ctgoodjobs.hk/jobs?q=data+engineer")
    cloudscraper_test("jobsdb.cloudscraper", "https://hk.jobsdb.com/jobs?keywords=data%20engineer")
    cloudscraper_test("ctg.cloudscraper", "https://jobs.ctgoodjobs.hk/jobs?q=data+engineer")

    print("\n== workable ==", flush=True)
    for acct in ["bowtie", "welab", "preface", "airwallex", "lalamove", "wearepreface"]:
        fetch(f"workable.{acct}", f"https://apply.workable.com/api/v3/accounts/{acct}/jobs",
              method="POST", headers={"Content-Type": "application/json"}, body=b"{}")

    print("\n== workday ==", flush=True)
    workday()


if __name__ == "__main__":
    main()
