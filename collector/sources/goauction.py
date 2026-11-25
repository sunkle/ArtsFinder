"""Adapter for the GoAuction platform (Lay's, McTear's, Anderson & Garland, Mallams, Halls).

Written WITHOUT seeing real pages (see docs/SOURCES.md), so it is deliberately forgiving: every
step tries several patterns and a missing piece gives None, never a crash. Run the workflow with
"diagnose" ticked to save real sample pages (diagnose/<house>/), then tighten the patterns here.

URL patterns (SOURCES.md):  sale   /auction/details/<slug>/?au=<id>[&pn=<page>]
                            lot    /auction/lot/<slug>/?lot=<id>[&au=<id>]

houses.json options for a house using this adapter:
  calendar_urls     pages that list the sales (required). "{month}" is replaced by YYYY-MM for this
                    month and the next few (calendar_months, default 3), e.g. McTear's ?m={month}
  sale_include      regex a sale title must match to be collected (default: art words, see ART_SALE)
  sale_exclude      regex that removes a sale (optional)
  max_pages         pages of lots to read per sale (default 40)
  max_new_lot_pages lot pages to fetch per run for lots not seen before (default 150). Known lots
                    (same ?lot=<id> in the previous data/lots.json) are reused without a request, so a
                    big sale fills in over several nights.
  max_lots_per_sale stop after this many lots (optional; each lot is one request, so 700 lots at
                    10 s is about two hours)
"""
import logging
import re
from datetime import date
from urllib.parse import parse_qs, urlsplit

from ..fetcher import FetchError
from .base import Adapter, sale_wanted
from .htmlutil import ancestors, card_of, clean_url, is_generic, parse, parse_date, parse_date_range, slug_title
from .lotpage import _LOT_NO_TEXT, _SLUG_LOT_NO, LotPageMixin

log = logging.getLogger("collector.goauction")
_EST_IN_LISTING = re.compile(r"(?:estimate|est\.?)\s*:?\s*(£\s*[\d,]+(?:\s*[-–]\s*£?\s*[\d,]+)?)", re.I)

_AU = re.compile(r"(?:^|[?&])au=(\d+)")
_LOT_ID = re.compile(r"(?:^|[?&])lot=(\d+)")


# ---- small helpers ------------------------------------------------------------------------
def _query_id(url, rx):
    m = rx.search(urlsplit(url).query)
    return m.group(1) if m else None


def month_strings(today, count):
    year, month, out = today.year, today.month, []
    for _ in range(max(1, count)):
        out.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


# ---- the adapter ----------------------------------------------------------------------------
class GoAuctionAdapter(LotPageMixin, Adapter):
    # ---------- sales ----------
    def calendar_pages(self, house, today=None):
        urls = []
        for url in house.get("calendar_urls") or [house["website"]]:
            if "{month}" in url:
                urls += [url.replace("{month}", m) for m in month_strings(today or date.today(), house.get("calendar_months", 3))]
            else:
                urls.append(url)
        return urls

    def list_sales(self, house):
        found = {}
        for cal_url in self.calendar_pages(house):
            try:
                text = self.fetch(house, cal_url)
            except FetchError as err:
                log.warning("%s: calendar page failed: %s", house["id"], err)
                continue
            self.snapshot(house, "calendar", cal_url, text)
            for sale in self.parse_calendar(text, cal_url):
                old = found.setdefault(sale["id"], sale)
                if old is not sale:  # same sale seen again (another link or page): fill gaps
                    if not old["date"]:
                        old["date"], old["end_date"] = sale["date"], sale["end_date"]
                    if is_generic(old["title"]) and not is_generic(sale["title"]):
                        old["title"] = sale["title"]
        sales = [self._with_date(house, s) for s in found.values() if sale_wanted(house, s["title"])]
        if self.diagnosing:
            sales = sales[:1]
        return sales

    def parse_calendar(self, html, base_url):
        """Sale links (/auction/details/...?au=<id>) with the nearest date and title."""
        root = parse(html)
        links = [a for a in root.find_all("a") if "/auction/details/" in a.get("href").lower()
                 and _query_id(a.get("href"), _AU)]
        sales = {}
        for a in links:
            href = clean_url(base_url, a.get("href"))
            au = _query_id(href, _AU)
            container = self._container(a, au)
            start, end = parse_date_range(a.text())
            if not start:
                start, end = parse_date_range(container.text())
            title = a.text()
            if is_generic(title):
                title = self._heading(container) or slug_title(href)
            sale = {"id": au, "title": re.sub(r"\s+", " ", title).strip(), "date": start, "end_date": end, "url": href}
            old = sales.setdefault(au, sale)
            if old is not sale:
                if not old["date"]:
                    old["date"], old["end_date"] = sale["date"], sale["end_date"]
                if is_generic(old["title"]) or old["title"] == slug_title(old["url"]):
                    old["title"] = sale["title"]
        return list(sales.values())

    @staticmethod
    def _container(link, au):
        """Smallest ancestor that holds a date and no other sale: the 'card' this link belongs to."""
        best = link
        for node in ancestors(link):
            others = {_query_id(a.get("href"), _AU) for a in node.find_all("a")
                      if "/auction/details/" in a.get("href").lower()} - {au, None}
            if others:
                break
            best = node
            if parse_date(node.text()):
                break
        return best

    @staticmethod
    def _heading(container):
        for n in container.iter():
            if n.tag in ("h1", "h2", "h3", "h4", "h5") or n.has_class("title"):
                t = n.text()
                if t and not is_generic(t):
                    return t
        return None

    def _with_date(self, house, sale):
        """No date on the calendar? Look on the sale page itself (it is fetched later anyway)."""
        if not sale["date"]:
            try:
                sale["date"], sale["end_date"] = parse_date_range(parse(self.fetch(house, sale["url"])).text())
            except FetchError as err:
                log.warning("%s: sale page failed: %s", house["id"], err)
        return sale

    # ---------- lots ----------
    def list_lots(self, house, sale):
        refs = self.lot_refs(house, sale)
        return self.fetch_lots(house, refs, lambda lot: _query_id(lot.get("lot_url") or "", _LOT_ID),
                               self.parse_lot, cap=house.get("max_lots_per_sale"))

    def lot_refs(self, house, sale):
        """Every lot link across the sale's pages: [{id, url, lot_number, title}] in page order."""
        max_pages = house.get("max_pages", 40)
        queue, seen_pages, refs = [sale["url"]], set(), {}
        while queue and len(seen_pages) < max_pages:
            url = queue.pop(0)
            if self._page_key(url) in seen_pages:
                continue
            seen_pages.add(self._page_key(url))
            try:
                html = self.fetch(house, url)
            except FetchError as err:
                log.warning("%s: sale page failed: %s", house["id"], err)
                break
            self.snapshot(house, "sale", url, html)
            new_lots, more_pages = self.parse_sale_page(html, url, sale["id"])
            new = [r for r in new_lots if r["id"] not in refs]
            for r in new:
                refs[r["id"]] = r
            if not new:
                break  # a page with nothing new means we are past the end (or looping)
            queue += [p for p in more_pages if self._page_key(p) not in seen_pages]
            if self.diagnosing:
                break
        return list(refs.values())

    @staticmethod
    def _card_text(link):
        """Text of the 'card' holding only this lot's link."""
        return card_of(link, lambda href: _query_id(href, _LOT_ID)).text()

    @staticmethod
    def _page_key(url):
        q = parse_qs(urlsplit(url).query)
        return (urlsplit(url).path.rstrip("/"), (q.get("au") or [""])[0], (q.get("pn") or ["1"])[0])

    def parse_sale_page(self, html, base_url, sale_id):
        """-> (lot refs on this page, urls of other pages of the same sale)."""
        root = parse(html)
        host = urlsplit(base_url).netloc
        lots, pages = {}, []
        for a in root.find_all("a"):
            href = a.get("href")
            if not href or href.startswith(("#", "javascript:", "mailto:")):
                continue
            url = clean_url(base_url, href)
            parts = urlsplit(url)
            lot_id = _query_id(url, _LOT_ID)
            if lot_id and "/auction/lot/" in parts.path.lower():
                ref = lots.setdefault(lot_id, {"id": lot_id, "url": url, "lot_number": "", "title": ""})
                if "estimate_text" not in ref:
                    est = _EST_IN_LISTING.search(self._card_text(a))
                    if est:
                        ref["estimate_text"] = est.group(1)
                m = _SLUG_LOT_NO.search(parts.path)
                ref["lot_number"] = ref["lot_number"] or (m.group(1) if m else "")
                text = a.text()
                if text and not is_generic(text) and len(text) > len(ref["title"]):
                    ref["title"] = text
                    ref["lot_number"] = ref["lot_number"] or (_LOT_NO_TEXT.search(text) or [None, ""])[1]
            elif (parts.netloc == host and "pn=" in parts.query and _query_id(url, _AU) in (sale_id, None)
                  and "/auction/" in parts.path.lower()):
                pages.append(url)
        return list(lots.values()), pages
