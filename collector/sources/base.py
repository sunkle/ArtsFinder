"""Adapter base class. Adapters ONLY fetch (through the fetcher) and parse. No cleaning:
tagger.py does that.

sale dict : {"id": str, "title": str, "date": "YYYY-MM-DD", "url": str}
raw_lot   : {"lot_number", "title", "lot_url"            (required)
             "artist_text", "description", "medium_detail", "estimate_text",
             "dimensions", "date_made_text", "image_url"  (optional, as found on the page)}
"""
import os


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
