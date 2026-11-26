import logging
import random
import time

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

log = logging.getLogger("jobscan")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

BLOCK_MARKERS = (
    "Attention Required! | Cloudflare",
    "Just a moment...",
    "cf-browser-verification",
    "challenge-platform",
    "Enable JavaScript and cookies to continue",
)

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['en-HK', 'en', 'zh-HK']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
"""


class BlockedError(Exception):
    pass


class BrowserSession:
    """One Chromium instance shared by all browser-based sources."""

    def __init__(self, headless: bool = True, channel: str | None = "chrome"):
        self.headless = headless
        self.channel = channel
        self._pw = None
        self._browser = None
        self._ctx = None
        self.page = None

    def __enter__(self):
        self._pw = sync_playwright().start()
        args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ]
        launch_kwargs = dict(headless=self.headless, args=args)

        if self.channel:
            try:
                self._browser = self._pw.chromium.launch(
                    channel=self.channel, **launch_kwargs
                )
                log.info("browser: launched %s (headless=%s)", self.channel, self.headless)
            except Exception as e:
                log.warning("browser: channel %s unavailable (%s); using bundled chromium",
                            self.channel, str(e)[:120])
                self._browser = None
        if self._browser is None:
            self._browser = self._pw.chromium.launch(**launch_kwargs)
            log.info("browser: launched bundled chromium (headless=%s)", self.headless)

        self._ctx = self._browser.new_context(
            user_agent=UA,
            locale="en-HK",
            timezone_id="Asia/Hong_Kong",
            viewport={"width": 1366, "height": 900},
            extra_http_headers={
                "Accept-Language": "en-HK,en;q=0.9",
                "sec-ch-ua": '"Chromium";v="131", "Not_A Brand";v="24", "Google Chrome";v="131"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
            },
        )
        self._ctx.add_init_script(STEALTH_JS)
        self.page = self._ctx.new_page()
        self.page.set_default_timeout(45000)
        return self

    def goto(self, url: str, wait_selector: str | None = None, retries: int = 1) -> str:
        last_err = None
        for attempt in range(retries + 1):
            try:
                self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
                if wait_selector:
                    self.page.wait_for_selector(wait_selector, timeout=15000)
                time.sleep(0.6 + random.random() * 0.8)
                html = self.page.content()
                if self._is_blocked(html):
                    raise BlockedError("cloudflare challenge")
                return html
            except (BlockedError, PWTimeout) as e:
                last_err = e
                if attempt < retries:
                    pause = 6 + random.random() * 3
                    log.warning("browser: %s on %s - retrying in %.0fs",
                                type(e).__name__, url, pause)
                    time.sleep(pause)
        raise BlockedError(f"could not load {url}: {last_err}")

    @staticmethod
    def _is_blocked(html: str) -> bool:
        head = html[:6000]
        return any(m in head for m in BLOCK_MARKERS)

    def polite_pause(self, lo: float = 1.0, hi: float = 2.0):
        time.sleep(lo + random.random() * (hi - lo))

    def __exit__(self, *exc):
        try:
            if self._ctx:
                self._ctx.close()
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
