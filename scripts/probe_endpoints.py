"""One-off probe: which job platforms are reachable from a GitHub runner?

Run by .github/workflows/probe.yml. Prints status, size and a content preview for
each candidate endpoint. No secrets are used.
"""

import json
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
    preview = body[:150].decode("utf-8", "ignore").replace("\n", " ").replace("\r", " ")
    print(f"{name:34} {status!s:>5} {size:>8}B {extra[:42]:42} :: {preview}", flush=True)


def fetch(name, url, method="GET", headers=None, body=None, timeout=14):
    h = dict(BASE_HEADERS)
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read(300000)
            show(name, r.status, len(data),
                 f"{time.time()-started:.1f}s {r.headers.get('content-type','')[:22]}", data)
    except urllib.error.HTTPError as e:
        data = e.read(600)
        show(name, f"HTTP{e.code}", len(data),
             f"{time.time()-started:.1f}s", data)
    except Exception as e:
        show(name, "ERR", 0, type(e).__name__, str(e).encode()[:150])


def curl_cffi_test(name, url):
    try:
        from curl_cffi import requests as creq
        r = creq.get(url, impersonate="chrome", timeout=15,
                     headers={"Accept-Language": "en-HK,en;q=0.9"})
        show(name, r.status_code, len(r.content), "curl_cffi chrome", r.content[:150])
    except Exception as e:
        show(name, "ERR", 0, f"curl_cffi {type(e).__name__}", str(e).encode()[:150])


def cloudscraper_test(name, url):
    try:
        import cloudscraper
        s = cloudscraper.create_scraper()
        r = s.get(url, timeout=20, headers={"Accept-Language": "en-HK,en;q=0.9"})
        show(name, r.status_code, len(r.content), "cloudscraper", r.content[:150])
    except Exception as e:
        show(name, "ERR", 0, f"cloudscraper {type(e).__name__}", str(e).encode()[:150])


def workday_root(name, tenant, node="wd3"):
    url = f"https://{tenant}.{node}.myworkdayjobs.com/"
    try:
        req = urllib.request.Request(url, headers=BASE_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as r:
            data = r.read(30000)
            final = r.geturl()
            show(name, r.status, len(data), f"final={final[:70]}", data)
    except urllib.error.HTTPError as e:
        show(name, f"HTTP{e.code}", 0, "", b"")
    except Exception as e:
        show(name, "ERR", 0, type(e).__name__, str(e).encode()[:120])


def main():
    print("== static platforms ==", flush=True)

    ctg_body = json.dumps({
        "pagingInputs": {"page": "1", "pageSize": "10", "pageOneSize": "10"},
        "sort": 2, "searchTypeId": "Y", "keyword": "data engineer",
        "jobIds": [], "jobcatareaIds": [], "companyIds": [], "industryIds": [],
        "employmentTypeIds": [], "locationIds": [], "educationIds": [], "gradeIds": [],
        "channelIds": [], "boostedJobIds": [], "boostedCompanyIds": [], "excludedJobIds": [],
    }).encode()

    tests = [
        ("jobsdb.api", "https://hk.jobsdb.com/api/jobsearch/v5/search?sitekey=HK-Main&sourcesystem=houston&keywords=data&page=1&pagesize=5"),
        ("jobsdb.html", "https://hk.jobsdb.com/jobs?keywords=data%20engineer"),
        ("ctgoodjobs.html", "https://jobs.ctgoodjobs.hk/jobs?q=data+engineer"),
        ("linkedin.guest", "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=data%20engineer&location=Hong%20Kong&start=0"),
        ("linkedin.html", "https://www.linkedin.com/jobs/search?keywords=data%20engineer&location=Hong%20Kong"),
        ("indeed.hk", "https://hk.indeed.com/jobs?q=data+engineer&l=Hong+Kong"),
        ("glassdoor.hk", "https://www.glassdoor.com/Job/hong-kong-data-engineer-jobs-SRCH_IL.0,9_IC2308631_KO10,23.htm"),
        ("efinancialcareers", "https://www.efinancialcareers.hk/search?q=data%20engineer"),
        ("jijis", "https://www.jijis.org.hk/"),
        ("labour.jobs.gov.hk", "https://www.jobs.gov.hk/"),
        ("hkstp.careers", "https://www.hkstp.org/careers/"),
        ("whub", "https://www.whub.io/jobs"),
        ("bing.jobs", "https://www.bing.com/jobs/search?q=data+engineer&l=Hong+Kong"),
        ("google.jobs", "https://www.google.com/search?q=data+engineer+hong+kong&ibp=htl;jobs"),
        ("careerjet.api", "https://public.api.careerjet.net/search?locale_code=en_HK&keywords=data+engineer&location=Hong+Kong&pagesize=20"),
        ("jooble.root", "https://jooble.org/api/"),
        ("talent.hk", "https://hk.talent.com/jobs?k=data+engineer"),
        ("jobrapido", "https://www.jobrapido.com/?w=data+engineer&l=Hong+Kong"),
        ("remotive", "https://remotive.com/api/remote-jobs?search=hong%20kong"),
        ("himalayas", "https://himalayas.app/jobs/api?limit=20&location=hong%20kong"),
        ("jobicy", "https://jobicy.com/api/v2/remote-jobs?count=20&geo=hong-kong"),
        ("remoteok", "https://remoteok.com/api"),
        ("weworkremotely.rss", "https://weworkremotely.com/categories/remote-programming-jobs.rss"),
        ("arbeitnow", "https://www.arbeitnow.com/api/job-board-api"),
        ("hn.algolia", "https://hn.algolia.com/api/v1/search?query=data%20engineer&tags=comment"),
        ("smartrecruiters.cathay", "https://api.smartrecruiters.com/v1/companies/Cathay/postings?limit=5"),
        ("smartrecruiters.pwc", "https://api.smartrecruiters.com/v1/companies/PwC/postings?limit=5"),
        ("smartrecruiters.deloitte", "https://api.smartrecruiters.com/v1/companies/Deloitte/postings?limit=5"),
        ("smartrecruiters.aia", "https://api.smartrecruiters.com/v1/companies/AIA/postings?limit=5"),
        ("oracle.jpmorgan", "https://jpmc.fa.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true&finder=findReqs;siteNumber=CX_1001,facetsList=LOCATIONS%3BWORK_LOCATIONS,limit=5,sortBy=POSTING_DATES_DESC,keyword=data"),
        ("goldman.higher", "https://higher.gs.com/api/v1/jobs?search=data&locations=Hong%20Kong&page=1"),
        ("bloomberg.api", "https://careers.bloomberg.com/api/jobs?page=1&search=data&location=Hong%20Kong"),
    ]

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fetch, name, url) for name, url in tests]
        for f in as_completed(futures):
            pass

    print("\n== POST / API variants ==", flush=True)
    fetch("ctgoodjobs.api.keyword", "https://api01.ctgoodjobs.hk/job/api/jobs/search",
          method="POST", headers={"Content-Type": "application/json", "Origin": "https://jobs.ctgoodjobs.hk",
                                  "Referer": "https://jobs.ctgoodjobs.hk/"}, body=ctg_body)
    fetch("ctgoodjobs.api.searchText", "https://api01.ctgoodjobs.hk/job/api/jobs/search",
          method="POST", headers={"Content-Type": "application/json", "Origin": "https://jobs.ctgoodjobs.hk",
                                  "Referer": "https://jobs.ctgoodjobs.hk/"},
          body=ctg_body.replace(b'"keyword": "data engineer"', b'"searchText": "data engineer"'))
    fetch("ctgoodjobs.api.bare", "https://api01.ctgoodjobs.hk/job/api/jobs/search",
          method="POST", headers={"Content-Type": "application/json"}, body=b"{}")

    print("\n== bypass attempts ==", flush=True)
    curl_cffi_test("jobsdb.curl_cffi", "https://hk.jobsdb.com/jobs?keywords=data%20engineer")
    curl_cffi_test("ctg.curl_cffi", "https://jobs.ctgoodjobs.hk/jobs?q=data+engineer")
    cloudscraper_test("jobsdb.cloudscraper", "https://hk.jobsdb.com/jobs?keywords=data%20engineer")
    cloudscraper_test("ctg.cloudscraper", "https://jobs.ctgoodjobs.hk/jobs?q=data+engineer")

    print("\n== workable ==", flush=True)
    for acct in ["bowtie", "welab", "preface", "airwallex", "lalamove"]:
        fetch(f"workable.{acct}", f"https://apply.workable.com/api/v3/accounts/{acct}/jobs",
              method="POST", headers={"Content-Type": "application/json"}, body=b"{}")

    print("\n== workday tenants ==", flush=True)
    for tenant in ["hkex", "mtr", "cathaypacific", "manulife", "aia", "sc", "ms",
                   "swirepacific", "clp", "hanglung", "bochk"]:
        workday_root(f"wd.{tenant}", tenant)


if __name__ == "__main__":
    main()
