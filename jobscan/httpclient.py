import json
import random
import time
import urllib.error
import urllib.request

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class FetchError(Exception):
    pass


def request(
    url: str,
    headers: dict | None = None,
    data: bytes | None = None,
    timeout: int = 30,
    retries: int = 3,
    backoff: float = 1.6,
) -> bytes:
    h = {
        "User-Agent": UA,
        "Accept": "*/*",
        "Accept-Language": "en-HK,en;q=0.9",
    }
    if headers:
        h.update(headers)

    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=h, data=data)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (400, 401, 403, 404):
                raise FetchError(f"HTTP {e.code} for {url}") from e
            if attempt == retries - 1:
                break
        except Exception as e:  # timeouts, DNS, resets
            last = e
            if attempt == retries - 1:
                break
        time.sleep(backoff ** attempt + random.random())

    raise FetchError(f"fetch failed for {url}: {last}")


def get_json(url: str, headers: dict | None = None, **kw):
    h = {"Accept": "application/json"}
    if headers:
        h.update(headers)
    body = request(url, headers=h, **kw)
    try:
        return json.loads(body)
    except Exception as e:
        raise FetchError(f"invalid JSON from {url}: {e}") from e


def get_text(url: str, headers: dict | None = None, **kw) -> str:
    return request(url, headers=headers, **kw).decode("utf-8", "ignore")
