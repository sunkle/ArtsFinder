"""Adapter for Gorringe's (Lewes). Calendar and catalogue-search page were read from real saved pages
(tests/fixtures/gorringes/); the lot listing and lot pages were NOT saved, so those two readers are written
defensively from the lot URLs and earlier notes (docs/SOURCES.md) and marked UNVERIFIED below.

VERIFIED (real pages)
  calendar    https://www.gorringes.co.uk/calendar (+ ?page=1 ...): one card per sale. Title (h4), date, and a
              hidden JSON block with startDate / endDate. A card has a "View Lots" button
              (https://auction.gorringes.co.uk/auction-catalog/<DDMMYY>) only once its catalogue is online.
  sale code   <DDMMYY> of the sale day, e.g. 011226 = 1 Dec 2026.
  lot URL     https://auction.gorringes.co.uk/auction-lot-detail/<Artist,-dates,-Title-start>&salelot=<code>+++++<n>+&refno=<refno>
              (seen in data/lots.json; note the & sits in the path, there is no ?).
UNVERIFIED (not saved; from docs/SOURCES.md)
  listing     https://auction.gorringes.co.uk/asp/searchresults.asp?st=D&sale_no=<code>&pg=<n>  (20 lots a page)
  lot page    read by the shared generic reader (lotpage.py); artist falls back to the lot URL.

houses.json options:
  calendar_urls       default [<website>/calendar]
  max_calendar_pages  calendar pages to read (default 4)
  lots_url            listing URL template with {code} and {page} (default above)
  sale_include / sale_include_extra / sale_exclude, max_pages, max_new_lot_pages: see sources/base.py
"""
import json
import logging
import re
from urllib.parse import unquote, unquote_plus, urljoin

from .base import Adapter, sale_wanted
from .htmlutil import ancestors, card_of, clean_url, first_estimate, page_links, parse, parse_date_range
from .lotpage import LotPageMixin

log = logging.getLogger("collector.gorringes")

LOTS_URL = "https://auction.gorringes.co.uk/asp/searchresults.asp?st=D&sale_no={code}&pg={page}"
_CATALOG = re.compile(r"/auction-catalog/(\w+)", re.I)
_REFNO = re.compile(r"refno=(\d+)")
_SALELOT = re.compile(r"salelot=([^&]+)")
_SLUG = re.compile(r"/auction-lot-detail/([^&?]+)")
_SLUG_PARTS = re.compile(r"^(?P<artist>.+?),-(?P<dates>(?:c\.?-?)?\d{4}(?:-\d{4})?)(?:,-(?P<title>.*))?$")


def _has_class(node, name):
    return name in node.get("class").split()


class GorringesAdapter(LotPageMixin, Adapter):
    # ---------- sales ----------
    def list_sales(self, house):
        found = {}
        urls = house.get("calendar_urls") or [house["website"].rstrip("/") + "/calendar"]
        for cal_url in urls:
            refs = self.crawl_pages(house, cal_url, self._calendar_page, kind="calendar",
                                    max_pages=house.get("max_calendar_pages", 4))
            for sale in refs:
                found.setdefault(sale["id"], sale)
        sales = [s for s in found.values() if sale_wanted(house, s["title"])]
        return sorted(sales, key=lambda s: (s["date"], s["id"]))

    def _calendar_page(self, html, url):
        root = parse(html)
        return self.parse_calendar(html, url), page_links(root, url, ("page",))

    def parse_calendar(self, html, base_url):
        """One dict per sale card: id, title, date, end_date, url (catalogue, or None while not online)."""
        root = parse(html)
        title_nodes = root.find_all("h4", lambda n: _has_class(n, "calendar-card__title"))
        sales = []
        for title in title_nodes:
            card = title
            for node in ancestors(title):
                if len(node.find_all("h4", lambda n: _has_class(n, "calendar-card__title"))) > 1:
                    break
                card = node
            start, end = self._dates(card)
            if not start:
                log.info("gorringes: sale card without a date skipped: %s", title.text())
                continue
            link = next((a.get("href") for a in card.find_all("a") if _has_class(a, "btn-lots")), "")
            m = _CATALOG.search(link)
            code = m.group(1) if m else start[8:10] + start[5:7] + start[2:4]
            sales.append({"id": code, "title": title.text(), "date": start, "end_date": end,
                          "url": clean_url(base_url, link) if m else None})
        return sales

    @staticmethod
    def _dates(card):
        """From the hidden calendar-reminder JSON (startDate / endDate); else from the visible date text."""
        for n in card.iter():
            if _has_class(n, "atcb"):
                try:
                    data = json.loads(n.raw_text())
                    start, end = data.get("startDate"), data.get("endDate")
                    if start:
                        return start, end if end and end > start else None
                except ValueError:
                    pass
        node = next((n for n in card.iter() if _has_class(n, "calendar-card__date")), card)
        return parse_date_range(node.text())

    # ---------- lots of one sale ----------
    def list_lots(self, house, sale):
        if not sale.get("url"):
            return []  # catalogue not online yet
        self.diagnose_fetch(house, "catalog", sale["url"])  # the verified "View Lots" page auction-catalog/<code>
        template = house.get("lots_url") or LOTS_URL
        code = sale["id"]
        first = template.format(code=code, page=1)

        def parse_page(html, url):
            refs, pages = self.parse_listing(html, url)
            page = int(re.search(r"[?&]pg=(\d+)", url).group(1)) if re.search(r"[?&]pg=(\d+)", url) else 1
            nxt = template.format(code=code, page=page + 1)
            return refs, pages + ([nxt] if refs and nxt not in pages else [])

        refs = self.crawl_pages(house, first, parse_page)
        return self.fetch_lots(house, refs, lambda lot: self._refno(lot.get("lot_url")), self.parse_lot)

    @staticmethod
    def _refno(url):
        m = _REFNO.search(url or "")
        return m.group(1) if m else None

    @staticmethod
    def _lot_no(url):
        m = _SALELOT.search(url or "")
        parts = unquote_plus(m.group(1)).split() if m else []
        return parts[-1] if len(parts) > 1 else ""

    @staticmethod
    def _slug(url):
        """'.../Duncan-Grant,-1885-1978,-'Wrestlers'&salelot=..' -> ('Duncan Grant', '1885-1978', "'Wrestlers'")."""
        m = _SLUG.search(url or "")
        if not m:
            return None
        parts = _SLUG_PARTS.match(unquote(m.group(1)))
        if not parts:
            return None
        clean = lambda s: (s or "").replace("-", " ").strip()  # noqa: E731
        return clean(parts.group("artist")), parts.group("dates").replace("c.-", "c."), clean(parts.group("title")).strip("'")

    def parse_listing(self, html, base_url):
        """UNVERIFIED listing reader: every lot-detail link with its card's text. -> (refs, other page urls)."""
        root = parse(html)
        refs = {}
        for a in root.find_all("a"):
            href = a.get("href")
            if "salelot=" not in href or "refno=" not in href:
                continue
            url = clean_url(base_url, href)
            ref_id = self._refno(url)
            if ref_id in refs:
                continue
            lines = card_of(a, lambda h: self._refno(h) if "salelot=" in h else None).lines()
            slug = self._slug(url)
            title = self._card_title(lines, slug)
            ref = {"id": ref_id, "url": url, "lot_number": self._lot_no(url), "title": title}
            estimate = first_estimate(lines)
            if estimate:
                ref["estimate_text"] = estimate
            refs[ref_id] = ref
        return list(refs.values()), page_links(root, base_url, ("pg",))

    @staticmethod
    def _card_title(lines, slug):
        """The card's own text when it has any, else the (truncated) title in the URL."""
        skip = re.compile(r"^(lot\s*\d|estimate|£|bid\b|view\b|add\b|track\b|sold\b)", re.I)
        artist = slug[0].lower() if slug else ""
        texts = [l for l in lines if not skip.match(l) and not re.fullmatch(r"[\d\s,.-]+", l)
                 and not l.lower().startswith(artist or "\0")]
        return max(texts, key=len) if texts else (slug[2] if slug else "")

    # ---------- one lot page (UNVERIFIED: generic reader + the lot URL) ----------
    def parse_lot(self, html, url, house=None):
        raw = super().parse_lot(html, url, house)
        raw["lot_number"] = self._lot_no(url) or raw.get("lot_number") or ""
        slug = self._slug(url)
        if slug and not raw.get("artist_text"):
            raw["artist_text"] = f"{slug[0]} ({slug[1]})"
        if not raw.get("image_url"):
            for img in parse(html).find_all("img"):
                if "_Catalog_" in img.get("src"):
                    raw["image_url"] = urljoin(url, img.get("src"))
                    break
        return {k: v for k, v in raw.items() if v not in (None, "")}
