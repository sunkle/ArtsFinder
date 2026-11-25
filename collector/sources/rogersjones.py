"""Adapter for Rogers Jones & Co (Colwyn Bay, Cardiff, Chester). The sales list was read from a real saved page
(tests/fixtures/rogersjones/); the bidding-site catalogue and lot pages were NOT saved, so they are UNVERIFIED.

VERIFIED (real pages)
  calendar    https://www.rogersjones.co.uk/en/forthcoming-sales : one box (div.sale) per sale with date
              ("Tue 1 December 2026 10:00 AM", or "Ends: ..." for timed sales), title, sub-heading (departments),
              saleroom, the sale page (/en/sales/YYYY/M/D/<slug>) and, once online, a "Browse & Bid" button to the
              catalogue https://auctions.rogersjones.co.uk/auctions/<n>/<code> ("Results" once finished). Sales
              still taking entries have no catalogue yet.
  lot link    https://auctions.rogersjones.co.uk/<...>/lot-details/<uuid> (seen on the Welsh Sale page)
UNVERIFIED (not saved)
  catalogue   lot links with /lot-details/<uuid>, card text for lot number / title / estimate, paging links
              (?page=n). Lot pages are read by the shared generic reader (lotpage.py, inherited parse_lot).

houses.json options:
  calendar_urls       default [<website>/en/forthcoming-sales]
  sale_include_extra  words that make a sale art (e.g. "monthly": the monthly sales hold pictures)
  sale_include / sale_exclude, max_pages, max_new_lot_pages: see sources/base.py
"""
import logging
import re
from urllib.parse import urlsplit

from ..fetcher import FetchError
from .base import Adapter, sale_wanted
from .htmlutil import card_of, clean_url, first_estimate, page_links, parse, parse_date_range
from .lotpage import LotPageMixin

log = logging.getLogger("collector.rogersjones")

_LOT_PATH = re.compile(r"/lot-details/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", re.I)
_BID_SITE = re.compile(r"auctions\.rogersjones\.co\.uk/auctions/(\d+)/(\w+)", re.I)
_LOT_LINE = re.compile(r"^lot\s*(?:no\.?|number|#)?\s*(\d+[A-Za-z]?)\b", re.I)
_SALE_PAGE = re.compile(r"/en/sales/(\d{4})/(\d{1,2})/(\d{1,2})/([\w-]+)", re.I)


def _has_class(node, name):
    return name in node.get("class").split()


class RogersJonesAdapter(LotPageMixin, Adapter):
    # ---------- sales ----------
    def list_sales(self, house):
        found = {}
        for cal_url in house.get("calendar_urls") or [house["website"].rstrip("/") + "/en/forthcoming-sales"]:
            try:
                html = self.fetch(house, cal_url)
            except FetchError as err:
                log.warning("%s: calendar page failed: %s", house["id"], err)
                continue
            self.snapshot(house, "calendar", cal_url, html)
            for sale in self.parse_calendar(html, cal_url):
                found.setdefault(sale["id"], sale)
        sales = [s for s in found.values() if sale_wanted(house, s["title"], s["summary"])]
        return sorted(sales, key=lambda s: (s["date"], s["id"]))

    def parse_calendar(self, html, base_url):
        """One dict per sale box: id, title, summary, location, date, end_date (None), url (catalogue or None),
        page (the sale's own page)."""
        root = parse(html)
        sales = []
        for box in root.find_all("div", lambda n: _has_class(n, "sale")):
            texts = {name: next((n.text() for n in box.iter() if _has_class(n, name)), "")
                     for name in ("date", "line", "subheading", "location")}
            texts["line"] = re.sub(r"^further ahead:\s*", "", texts["line"], flags=re.I)  # label on far-off sales
            start, _ = parse_date_range(texts["date"])
            if not (start and texts["line"]):
                continue
            hrefs = [clean_url(base_url, a.get("href")) for a in box.find_all("a") if a.get("href")]
            catalogue = None
            for a in box.find_all("a"):
                if _BID_SITE.search(a.get("href")) and "result" not in a.text().lower():
                    catalogue = clean_url(base_url, a.get("href"))
                    break
            page = next((h for h in hrefs if _SALE_PAGE.search(h)), None)
            m = _BID_SITE.search(catalogue or "")
            if m:
                sale_id = m.group(2).lower()
            else:
                p = _SALE_PAGE.search(page or "")
                sale_id = "-".join(p.groups()) if p else f"{start}-{texts['line']}".lower().replace(" ", "-")
            sales.append({"id": sale_id, "title": texts["line"], "summary": texts["subheading"],
                          "location": texts["location"], "date": start, "end_date": None, "url": catalogue,
                          "page": page})
        return sales

    # ---------- lots of one sale ----------
    def list_lots(self, house, sale):
        if not sale.get("url"):
            return []  # still taking entries: no catalogue yet
        refs = self.crawl_pages(house, sale["url"], self.parse_listing)
        return self.fetch_lots(house, refs, lambda lot: self._lot_key(lot.get("lot_url")), self.parse_lot)

    @staticmethod
    def _lot_key(url):
        m = _LOT_PATH.search(url or "")
        return m.group(1).lower() if m else None

    def parse_listing(self, html, base_url):
        """UNVERIFIED catalogue reader: every /lot-details/<uuid> link with its card's text."""
        root = parse(html)
        refs = {}
        for a in root.find_all("a"):
            url = clean_url(base_url, a.get("href") or "#")
            key = self._lot_key(url)
            if not key or key in refs:
                continue
            lines = card_of(a, self._lot_key).lines()
            number = next((m.group(1) for m in map(_LOT_LINE.match, lines) if m), "")
            texts = [l for l in lines if not _LOT_LINE.match(l) and not re.match(r"^(£|estimate|current|sold|view|bid)", l, re.I)
                     and not re.fullmatch(r"[\d\s,.]+", l)]
            ref = {"id": key, "url": url, "lot_number": number, "title": max(texts[:2], key=len) if texts else ""}
            estimate = first_estimate(lines)
            if estimate:
                ref["estimate_text"] = estimate
            refs[key] = ref
        pages = [u for u in page_links(root, base_url) if urlsplit(u).netloc == urlsplit(base_url).netloc]
        return list(refs.values()), pages
