"""The ONLY module that touches the network.

Polite by design: robots.txt, crawl-delay (never under min_delay), one request at a time,
2 retries with backoff, a per-run disk cache, and an honest User-Agent (never a browser).
"""
import hashlib
import os
import tempfile
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

MAX_BYTES = 5_000_000
RETRY_CODES = {429, 500, 502, 503, 504}


class FetchError(Exception):
    pass


class RobotsDisallowed(FetchError):
    pass


class BlockedHost(FetchError):
    pass


# Sites we must never fetch, whatever an adapter or houses.json says (their terms forbid it).
# A host matches if it equals an entry or is a subdomain of it.
BLOCKED_HOSTS = ("the-saleroom.com",)


def check_not_blocked(url):
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    for blocked in BLOCKED_HOSTS:
        if host == blocked or host.endswith("." + blocked):
            raise BlockedHost(f"{host} is on the never-fetch list (terms forbid automated access): {url}")


def user_agent(repo=None):
    repo = repo or os.environ.get("ARTS_FINDER_REPO") or "<owner>/arts-finder"
    return f"ArtsFinder-personal/0.1 (+https://github.com/{repo})"


def _urlopen(request, timeout):
    """Default opener: returns (body_bytes, charset_or_None). Tests swap this out."""
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return resp.read(MAX_BYTES), resp.headers.get_content_charset()


class Fetcher:
    def __init__(self, repo=None, min_delay=3.0, cache_dir=None, opener=_urlopen,
                 sleep=time.sleep, clock=time.monotonic, retries=2, backoff=2.0, timeout=30):
        self.ua = user_agent(repo)
        self.min_delay = max(3.0, float(min_delay))  # never below 3 s
        self.opener, self.sleep, self.clock = opener, sleep, clock
        self.retries, self.backoff, self.timeout = retries, backoff, timeout
        self._tmp = None
        if cache_dir is None:
            self._tmp = tempfile.TemporaryDirectory(prefix="arts-finder-cache-")
            cache_dir = self._tmp.name
        self.cache_dir = cache_dir
        self._last = {}    # host -> time of last request
        self._robots = {}  # origin -> (RobotFileParser, crawl_delay or 0)

    # ---- public -------------------------------------------------------
    def get(self, url, crawl_delay=0):
        """Return the page text. Raises FetchError / RobotsDisallowed / BlockedHost."""
        check_not_blocked(url)
        cached = self._cache_path(url)
        if os.path.exists(cached):
            with open(cached, encoding="utf-8") as f:
                return f.read()
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise FetchError(f"not an http(s) url: {url}")
        parser, robots_delay = self._robots_for(parts, crawl_delay)
        if not parser.can_fetch(self.ua, url):
            raise RobotsDisallowed(f"robots.txt disallows {url}")
        text = self._request(url, max(self.min_delay, float(crawl_delay or 0), robots_delay))
        with open(cached, "w", encoding="utf-8") as f:
            f.write(text)
        return text

    def close(self):
        if self._tmp:
            self._tmp.cleanup()
            self._tmp = None

    # ---- internals ----------------------------------------------------
    def _cache_path(self, url):
        return os.path.join(self.cache_dir, hashlib.sha256(url.encode()).hexdigest())

    def _robots_for(self, parts, crawl_delay):
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            parser = RobotFileParser()
            try:
                text = self._request(origin + "/robots.txt", max(self.min_delay, float(crawl_delay or 0)))
                parser.parse(text.splitlines())
            except FetchError as err:
                status = getattr(err, "status", None)
                if status in (404, 410):
                    parser.parse([])                    # no robots.txt: allowed
                else:
                    parser.parse(["User-agent: *", "Disallow: /"])  # refused/unreachable: stay away
            delay = parser.crawl_delay(self.ua)
            self._robots[origin] = (parser, float(delay or 0))
        return self._robots[origin]

    def _throttle(self, host, delay):
        wait = self._last.get(host, float("-inf")) + delay - self.clock()
        if wait > 0:
            self.sleep(wait)

    def _request(self, url, delay):
        check_not_blocked(url)
        host = urlsplit(url).netloc
        request = urllib.request.Request(url, headers={"User-Agent": self.ua})
        last_err = None
        for attempt in range(self.retries + 1):
            if attempt:
                self.sleep(self.backoff * 2 ** (attempt - 1))
            self._throttle(host, delay)
            try:
                body, charset = self.opener(request, self.timeout)
                self._last[host] = self.clock()
                return body.decode(charset or "utf-8", errors="replace")
            except urllib.error.HTTPError as err:
                self._last[host] = self.clock()
                last_err = FetchError(f"HTTP {err.code} for {url}")
                last_err.status = err.code
                if err.code not in RETRY_CODES:
                    raise last_err
            except (urllib.error.URLError, OSError) as err:
                self._last[host] = self.clock()
                last_err = FetchError(f"network error for {url}: {err}")
        raise last_err
