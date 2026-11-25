"""Deep probe: save real calendar, sale and lot pages from houses the first probe marked `ok`.

Usage (repo root):
  python3 -m collector.probe --deep --only-verdict ok --report probe/report.json

Per house it saves up to 8 pages (home, <=2 calendar, <=2 sale, <=3 lot) as
probe-deep/<house>/<NN>-<kind>.html, with the source URL in a leading comment. It uses the same
polite Fetcher as everything else (robots.txt on every host, honest UA, >=3 s delay, never-fetch
list). It never tries to get past a challenge: if one appears the house is left alone.
"""
import json
import logging
import os
import re
import shutil
import time
from urllib.parse import urljoin, urlsplit

from .fetcher import Fetcher, FetchError
from .probe import SKIP_WORDS, classify_page, parse

log = logging.getLogger("collector.probe_deep")

LIMITS = {"calendar": 2, "sale": 2, "lot": 3}
LOT_RE = re.compile(r"/lots?/|/lot-|lot[-_=]?\d|lotid|/item/|/lot\?", re.I)
CALENDAR_RE = re.compile(r"calendar|forthcoming|upcoming|future|auction[-_ ]?dates|all[-_ ]auctions|"
                         r"auction[-_ ]?list|our[-_ ]auctions|^/?auctions?/?$", re.I)
SALE_RE = re.compile(r"catalogue|catalog|view[-_ ]?auction|auction[-_/ ]?(details|info|id)?[-_/=]?\d|"
                     r"/sales?/|/auction/[^/?#]+|[?&](sale|auction)(_?id)?=|\bsale\b|\bauction\b", re.I)
ART_RE = re.compile(r"picture|painting|fine[-_ ]?art|\bart\b|print|modern|contemporary|watercolou?r|drawing", re.I)
# Hosted catalogue platforms a house may link to from its own site (robots.txt still applies).
PLATFORM_SUFFIXES = ("easyliveauction.com", "bidpath.com")


def _site(url):
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def same_site(host, house_host):
    return host == house_host or host.endswith("." + house_host) or house_host.endswith("." + host)


def host_allowed(host, house_host):
    """Own site, own sub-host (bid.x.co.uk), or a white-label catalogue platform."""
    return same_site(host, house_host) or any(host == s or host.endswith("." + s) for s in PLATFORM_SUFFIXES)


def classify_link(url, label=""):
    """Return 'lot', 'calendar', 'sale' or None for a link."""
    if SKIP_WORDS.search(url):
        return None
    path = urlsplit(url).path + ("?" + urlsplit(url).query if urlsplit(url).query else "")
    if LOT_RE.search(path):
        return "lot"
    if CALENDAR_RE.search(label) or CALENDAR_RE.search(path):
        return "calendar"
    if SALE_RE.search(path) or SALE_RE.search(label):
        return "sale"
    return None


def pick_links(html, base, house_host, seen=()):
    """Return {'calendar': [...], 'sale': [...], 'lot': [...]} of absolute URLs, best first.
    Sales whose link text or URL suggests art come first."""
    out = {"calendar": [], "sale": [], "lot": []}
    done = set(seen)
    scored = {"sale": []}
    for i, (href, label) in enumerate(parse(html).links):
        url = urljoin(base, href).split("#")[0]
        if url in done or urlsplit(url).scheme not in ("http", "https"):
            continue
        if not host_allowed(_site(url), house_host):
            continue
        kind = classify_link(url, label)
        if not kind:
            continue
        done.add(url)
        if kind == "sale":
            scored["sale"].append((0 if ART_RE.search(label) or ART_RE.search(url) else 1, i, url))
        else:
            out[kind].append(url)
    out["sale"] = [u for _, _, u in sorted(scored["sale"])]
    return out


def save_page(folder, n, kind, url, html):
    os.makedirs(folder, exist_ok=True)
    name = f"{n:02d}-{kind}.html"
    with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
        f.write(f"<!-- source: {url} -->\n{html}")
    return name


def deep_house(house, fetcher, out_dir, deadline, house_cap=180):
    """Save pages for one house. Returns (saved [(file,url,kind)], note)."""
    started = time.monotonic()
    folder = os.path.join(out_dir, house["id"])
    house_host = _site(house["url"])
    saved, tried = [], set()

    def over():
        return time.monotonic() > deadline or time.monotonic() - started > house_cap

    def grab(url, kind):
        """Fetch+save one page. Returns html, or None; raises StopIteration on a challenge."""
        tried.add(url)
        try:
            html = fetcher.get(url)
        except FetchError as e:
            log.info("  skip %s (%s)", url, str(e)[:80])
            return None
        if classify_page(html)[0] == "bot_challenge":
            raise StopIteration(url)
        saved.append((save_page(folder, len(saved) + 1, kind, url, html), url, kind))
        return html

    pool = {"calendar": [], "sale": [], "lot": []}

    def add(html, base):
        for k, urls in pick_links(html, base, house_host, tried).items():
            pool[k] += [u for u in urls if u not in pool[k]]

    try:
        home = grab(house["url"], "home")
        if home is None:
            return saved, "home page not fetched"
        add(home, house["url"])
        counts = {"calendar": 0, "sale": 0, "lot": 0}
        for kind in ("calendar", "sale", "lot"):
            while pool[kind] and counts[kind] < LIMITS[kind] and not over():
                url = pool[kind].pop(0)
                if url in tried:
                    continue
                html = grab(url, kind)
                if html is None:
                    continue
                counts[kind] += 1
                add(html, url)  # new links: lots from sales, sales from calendars
        note = "ok" if not over() else "time cap reached"
    except StopIteration as e:
        note = f"bot challenge at {e}: house left alone"
    return saved, note


def render_index(rows):
    lines = ["# Deep probe", "", "| House | File | Kind | URL |", "|---|---|---|---|"]
    for house, file, url, kind in rows:
        lines.append(f"| {house} | {house}/{file} | {kind} | {url} |")
    return "\n".join(lines) + "\n"


def run_deep(report_path, out_dir, only_verdict="ok", budget_min=30, house_cap=180, only=None, fetcher=None):
    with open(report_path, encoding="utf-8") as f:
        reports = json.load(f)
    houses = [r for r in reports if r.get("verdict") == only_verdict and (not only or r["id"] == only)]
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)
    own = fetcher is None
    fetcher = fetcher or Fetcher()
    deadline = time.monotonic() + budget_min * 60
    rows = []
    for h in houses:
        if time.monotonic() > deadline:
            log.info("%s -> not probed: time budget used", h["id"])
            continue
        try:
            saved, note = deep_house(h, fetcher, out_dir, deadline, house_cap)
        except Exception as e:  # one house must never stop the run
            saved, note = [], f"{type(e).__name__}: {e}"[:120]
        rows += [(h["id"], f, u, k) for f, u, k in saved]
        log.info("%s -> %d pages saved (%s)", h["id"], len(saved), note)
    with open(os.path.join(out_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write(render_index(rows))
    if own:
        fetcher.close()
    return rows
