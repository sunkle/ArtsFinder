"""Polite probe: which auction houses allow honest automated access?

Usage (repo root):  python3 -m collector.probe [--out probe] [--only id] [--budget-min 25]

Uses collector.fetcher.Fetcher, so robots.txt, the honest User-Agent, 3 s+ delays and the
never-fetch list all apply. It NEVER tries to solve or bypass a challenge, CAPTCHA or bot check:
a challenge is recorded as `bot_challenge` and the house is left alone (no retry).
"""
import argparse
import json
import logging
import os
import re
import shutil
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from .fetcher import BlockedHost, Fetcher, FetchError, RobotsDisallowed

log = logging.getLogger("collector.probe")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

AUCTION_WORDS = re.compile(r"auction|catalogue|catalog|calendar|forthcoming|upcoming|sale", re.I)
LOT_WORDS = re.compile(r"/lots?/|/lot-|lot[-_=]?\d|lotid|/item/", re.I)
SKIP_WORDS = re.compile(r"\.(pdf|jpe?g|png|gif|zip)(\?|$)|^(mailto|tel|javascript):|login|register|cart|privacy|cookie|terms", re.I)

CHALLENGE_MARKERS = ("bpbc", "bp_challenge_token", "cf-challenge", "cf_chl", "just a moment",
                     "g-recaptcha", "h-captcha", "hcaptcha", "captcha", "javascript is required",
                     "enable javascript and cookies", "attention required", "access denied")


class _Page(HTMLParser):
    """Collects visible text length, links, script count and empty-app-root hints."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text, self.links, self.scripts = [], [], 0
        self.app_roots, self._skip, self._stack = [], 0, []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "noscript"):
            self._skip += 1
            self.scripts += tag == "script"
        elif tag == "title":
            self._in_title = True
        elif tag == "a" and a.get("href"):
            self.links.append((a["href"], ""))
        if tag in ("div", "main", "section") and (a.get("id") or "").lower() in (
                "root", "app", "__next", "__nuxt", "app-root", "svelte"):
            self.app_roots.append(a["id"])

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if not self._skip and data.strip():
            self.text.append(data.strip())
            if self.links and not self.links[-1][1]:
                self.links[-1] = (self.links[-1][0], data.strip())


def parse(html):
    p = _Page()
    try:
        p.feed(html)
    except Exception:  # broken markup: keep what we have
        pass
    return p


def detect_platform(html):
    low = html.lower()
    if "bpbc" in low or "bidpath" in low or "goauction" in low or "bp_challenge" in low:
        return "goauction/bidpath"
    if "easylive" in low or "easyliveauction" in low or "easy-live" in low:
        return "easylive"
    if "the-saleroom" in low or "thesaleroom" in low or "atgmedia" in low or "auction-technology-group" in low:
        return "atg/the-saleroom"
    if "wp-content" in low or "wp-includes" in low or 'content="wordpress' in low:
        return "wordpress"
    return "custom"


def classify_page(html):
    """Return (verdict, note) for one fetched page: ok / bot_challenge / js_only / no_auction_links."""
    low = html.lower()
    page = parse(html)
    text = " ".join(page.text)
    for m in CHALLENGE_MARKERS:
        if m in low and (m not in ("captcha", "access denied") or len(text) < 600):
            return "bot_challenge", f"challenge marker '{m}'"
    if page.scripts and len(text) < 100 and len(html) < 6000:
        return "bot_challenge", "tiny HTML with a script and no content"
    if len(text) < 80 or (page.app_roots and len(text) < 300):
        return "js_only", "page has no readable text (rendered by JavaScript)" if not page.app_roots \
            else f"empty app root #{page.app_roots[0]}"
    if re.search(r"\blots?\b|auction|catalogue|estimate", text, re.I):
        return "ok", f"{len(text)} chars of text"
    return "no_auction_links", "readable page without auction/lot wording"


def find_links(html, base, limit_auction=2, limit_lot=1):
    """Pick up to 2 auction-looking and 1 lot-looking same-site links."""
    host = (urlsplit(base).hostname or "").removeprefix("www.")
    auction, lot, seen = [], [], set()
    for href, label in parse(html).links:
        if SKIP_WORDS.search(href):
            continue
        url = urljoin(base, href).split("#")[0]
        h = (urlsplit(url).hostname or "").removeprefix("www.")
        if url in seen or not (h == host or h.endswith("." + host) or host.endswith("." + h)) \
                or urlsplit(url).scheme not in ("http", "https"):
            continue
        seen.add(url)
        if LOT_WORDS.search(url):
            lot.append(url)
        elif AUCTION_WORDS.search(url) or AUCTION_WORDS.search(label):
            auction.append(url)
    return auction[:limit_auction], lot[:limit_lot]


def probe_house(house, fetcher, deadline, save_dir=None):
    """Probe one house. Returns a report dict."""
    rep = {"id": house["id"], "house": house["name"], "region": house["region"], "url": house["url"],
           "verdict": "error", "platform": "custom", "pages": [], "note": ""}
    started = time.monotonic()
    saved = []

    def over():
        return time.monotonic() > deadline or time.monotonic() - started > HOUSE_CAP

    def fetch(url):
        rep["pages"].append(url)
        return fetcher.get(url)

    try:
        origin = "{0.scheme}://{0.netloc}".format(urlsplit(house["url"]))
        fetcher._robots_for(urlsplit(origin), 0)           # records robots.txt (polite, cached)
        rep["pages"].append(origin + "/robots.txt")
        home = fetch(house["url"])
    except RobotsDisallowed as e:
        rep.update(verdict="robots_disallow", note=str(e)[:120])
        return rep
    except BlockedHost as e:
        rep.update(verdict="error", note=str(e)[:120])
        return rep
    except FetchError as e:
        rep.update(verdict="error", note=str(e)[:120])
        return rep
    rep["platform"] = detect_platform(home)
    verdict, note = classify_page(home)
    if verdict in ("bot_challenge", "js_only"):
        rep.update(verdict=verdict, note=note + " (home page)")
        return rep
    pages = [(house["url"], home, verdict, note)]
    auction_links, lot_links = find_links(home, house["url"])
    if not auction_links and not lot_links:
        rep.update(verdict="no_auction_links", note="no auction/catalogue/lot links on the home page")
        return rep
    blocked_by = None
    for url in auction_links + lot_links:
        if over():
            rep["note"] = "time cap reached"
            break
        try:
            html = fetch(url)
        except RobotsDisallowed:
            blocked_by = blocked_by or "robots_disallow"
            continue
        except FetchError as e:
            blocked_by = blocked_by or "error"
            rep["note"] = str(e)[:100]
            continue
        v, n = classify_page(html)
        pages.append((url, html, v, n))
        if v == "bot_challenge":                                # never retry, stop touching this house
            rep["platform"] = detect_platform(html) if rep["platform"] == "custom" else rep["platform"]
            rep.update(verdict="bot_challenge", note=n)
            return rep
        if lot_links and url == lot_links[0] and url not in auction_links and v == "ok" and not rep.get("lot_ok"):
            rep["lot_ok"] = True
        if rep["platform"] == "custom":
            rep["platform"] = detect_platform(html)
    good = [p for p in pages if p[2] == "ok"]
    if good:
        rep.update(verdict="ok", note=f"{len(good)} of {len(pages)} pages had auction/lot content")
        if save_dir:
            os.makedirs(save_dir, exist_ok=True)
            for i, (url, html, _, _) in enumerate(good[:1]):
                with open(os.path.join(save_dir, f"page{i + 1}.html"), "w", encoding="utf-8") as f:
                    f.write(f"<!-- fetched from {url} -->\n{html}")
    else:
        kinds = {p[2] for p in pages}
        rep["verdict"] = "js_only" if "js_only" in kinds else (blocked_by or "no_auction_links")
        rep["note"] = rep["note"] or "no fetched page had auction/lot content"
    rep.pop("lot_ok", None)
    return rep


HOUSE_CAP = 240  # seconds per house


def render_markdown(reports):
    rows = ["| House | Region | Verdict | Platform | Pages | Note |", "|---|---|---|---|---|---|"]
    for r in reports:
        note = (r["note"] or "").replace("|", "/")
        rows.append(f"| {r['house']} | {r['region']} | {r['verdict']} | {r['platform']} | {len(r['pages'])} | {note} |")
    counts = {}
    for r in reports:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    summary = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
    return f"# House probe\n\n{summary}\n\n" + "\n".join(rows) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "probe"))
    ap.add_argument("--only")
    ap.add_argument("--budget-min", type=float, default=25)
    ap.add_argument("--deep", action="store_true", help="save sale and lot pages from houses in --report")
    ap.add_argument("--only-verdict", default="ok")
    ap.add_argument("--report", default=os.path.join(ROOT, "probe", "report.json"))
    ap.add_argument("--houses", default=os.path.join(ROOT, "collector", "probe_houses.json"))
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.deep:
        from .probe_deep import run_deep
        out = args.out if args.out != os.path.join(ROOT, "probe") else os.path.join(ROOT, "probe-deep")
        budget = args.budget_min if args.budget_min != 25 else 30
        run_deep(args.report, out, args.only_verdict, budget, only=args.only)
        return
    with open(args.houses, encoding="utf-8") as f:
        houses = json.load(f)
    if args.only:
        houses = [h for h in houses if h["id"] == args.only]
    if os.path.isdir(args.out):
        shutil.rmtree(args.out)
    os.makedirs(args.out)
    fetcher = Fetcher()
    deadline = time.monotonic() + args.budget_min * 60
    reports = []
    for h in houses:
        if time.monotonic() > deadline:
            reports.append({"id": h["id"], "house": h["name"], "region": h["region"], "url": h["url"],
                            "verdict": "error", "platform": "unknown", "pages": [], "note": "not probed: time budget used"})
            continue
        try:
            reports.append(probe_house(h, fetcher, deadline, os.path.join(args.out, h["id"])))
        except Exception as e:  # one house must never stop the run
            reports.append({"id": h["id"], "house": h["name"], "region": h["region"], "url": h["url"],
                            "verdict": "error", "platform": "unknown", "pages": [], "note": f"{type(e).__name__}: {e}"[:120]})
        log.info("%s -> %s", h["id"], reports[-1]["verdict"])
    with open(os.path.join(args.out, "report.json"), "w", encoding="utf-8") as f:
        json.dump(reports, f, indent=1)
    with open(os.path.join(args.out, "report.md"), "w", encoding="utf-8") as f:
        f.write(render_markdown(reports))
    fetcher.close()


if __name__ == "__main__":
    main()
