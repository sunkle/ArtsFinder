"""Adapter base class. Adapters ONLY fetch (through the fetcher) and parse. No cleaning:
tagger.py does that.

sale dict : {"id": str, "title": str, "date": "YYYY-MM-DD", "url": str}
raw_lot   : {"lot_number", "title", "lot_url"            (required)
             "artist_text", "description", "medium_detail", "estimate_text",
             "dimensions", "date_made_text", "image_url"  (optional, as found on the page)}
"""
import logging
import os
import re

from ..fetcher import FetchError

DEFAULT_NEW_LOT_PAGES = 150
log = logging.getLogger("collector.sources")

# Sales whose title does not match are skipped (jewellery, watches, stamps, coins, ...). Shared by all adapters;
# a house can override it with `sale_include` / `sale_exclude` (regexes) in houses.json.
ART_SALE = (r"\b(art|arts|artists?|paintings?|pictures?|prints?|drawings?|watercolou?rs?|sculptures?|"
            r"pottery|contemporary|modern|british|scottish|cornish|impressionist|illustrations?)\b")


def sale_wanted(house, *texts):
    """True if the sale (title and any summary text) passes the house's sale_include / sale_exclude."""
    text = " ".join(t for t in texts if t)
    include = re.compile(house.get("sale_include") or ART_SALE, re.I)
    exclude = house.get("sale_exclude")
    ok = bool(include.search(text)) and not (exclude and re.search(exclude, text, re.I))
    if not ok:
        log.info("%s: skipping sale %r (does not look like art)", house["id"], text[:80])
    return ok


class Adapter:
    previous_lots = ()   # this house's lots from the last data/lots.json (set by run.py) for incremental runs
    diagnose_dir = None  # set by run.py --diagnose: a folder to save sample pages in (and keep the run small)

    def __init__(self, fetcher):
        self.fetcher = fetcher
        self._snapshots = set()
        self.stats = {"new": 0, "reused": 0, "deferred": 0}  # lot pages fetched / taken from last run / postponed

    @property
    def diagnosing(self):
        return bool(self.diagnose_dir)

    def snapshot(self, house, kind, url, text):
        """In --diagnose mode save the FIRST page of each kind ('calendar', 'sale', 'lot') as diagnose/<house>/<kind>.html."""
        if not self.diagnose_dir or kind in self._snapshots:
            return
        self._snapshots.add(kind)
        folder = os.path.join(self.diagnose_dir, house["id"])
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, kind + ".html"), "w", encoding="utf-8") as f:
            f.write(f"<!-- fetched from {url} -->\n{text}")

    def fetch(self, house, url):
        """Get a page, applying this house's crawl_delay. The only way adapters read the web."""
        return self.fetcher.get(url, crawl_delay=house.get("crawl_delay", 0))

    def list_sales(self, house):
        """Return the upcoming sales: a list of sale dicts."""
        raise NotImplementedError

    def list_lots(self, house, sale):
        """Return the lots of one sale: a list of raw_lot dicts."""
        raise NotImplementedError

    # ---- incremental lot fetching, shared by every adapter that reads one page per lot ----
    def known_lots(self, key_of):
        """Previous lots of this house by platform lot key: {key: stored lot}. key_of(stored lot) -> key or None."""
        if not hasattr(self, "_known"):
            self._known = {}
            for lot in self.previous_lots or ():
                key = key_of(lot)
                if key:
                    self._known[key] = lot
        return self._known

    def fetch_lots(self, house, refs, key_of, parse_lot, cap=None):
        """Turn listing refs into raw lots, politely and incrementally.

        refs: [{"id": platform lot key, "url", "lot_number", "title", optional "estimate_text"}] in page order.
        key_of(stored lot) -> the platform key of a lot already in last night's data/lots.json.
        parse_lot(html, url, house) -> raw_lot dict.
        A known lot is reused without a request. A new one costs one request, up to house["max_new_lot_pages"]
        (default 150) per run across all sales; the rest wait for the next night."""
        cap = 2 if self.diagnosing else cap
        budget = house.get("max_new_lot_pages", DEFAULT_NEW_LOT_PAGES)
        known = self.known_lots(key_of)
        lots = []
        for ref in refs[:cap] if cap else refs:
            stored = known.get(ref["id"])
            if stored and not self.diagnosing:
                self.stats["reused"] += 1
                lots.append({"lot_number": stored["lot_number"], "title": stored["title"], "lot_url": ref["url"],
                             "estimate_text": ref.get("estimate_text"), "_stored": stored,
                             "_listing_title": ref["title"]})
                continue
            if self.stats["new"] >= budget:
                self.stats["deferred"] += 1
                continue
            self.stats["new"] += 1
            try:
                html = self.fetch(house, ref["url"])
            except FetchError as err:
                # Not stored: a listing-only lot has no medium or artist and would be "known" (never re-fetched).
                log.warning("%s: lot page failed (%s): lot left out, tried again next run", house["id"], err)
                continue
            self.snapshot(house, "lot", ref["url"], html)
            raw = parse_lot(html, ref["url"], house)
            raw["lot_number"] = raw.get("lot_number") or ref["lot_number"]
            raw["title"] = raw.get("title") or ref["title"]
            if not raw.get("estimate_text") and not raw.get("estimate_low") and ref.get("estimate_text"):
                raw["estimate_text"] = ref["estimate_text"]  # the lot page shows no estimate (e.g. sale over)
            if raw["lot_number"] and raw["title"]:
                lots.append(raw)
        return lots
