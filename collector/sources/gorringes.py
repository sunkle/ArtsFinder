"""Adapter for Gorringe's (Lewes). Every reader below was written from real saved pages (diagnose run of
25 Nov 2026, kept trimmed in tests/fixtures/gorringes/): calendar, catalogue listing and one lot page.

VERIFIED (real pages)
  calendar    https://www.gorringes.co.uk/calendar (+ ?page=1 ...): one card per sale. Title (h4), date, and a
              hidden JSON block with startDate / endDate. A card has a "View Lots" button
              (https://auction.gorringes.co.uk/auction-catalog/<DDMMYY>) only once its catalogue is online.
  sale code   <DDMMYY> of the sale day, e.g. 011226 = 1 Dec 2026.
  lot URL     https://auction.gorringes.co.uk/auction-lot-detail/<Artist,-dates,-Title-start>&salelot=<code>+++++<n>+&refno=<refno>
              (seen in data/lots.json; note the & sits in the path, there is no ?).
  listing     https://auction.gorringes.co.uk/asp/searchresults.asp?st=D&sale_no=<code>&pg=<n>  (20 lots a page,
              "Page 1 of 29." in the pager; the "View Lots" page auction-catalog/<code> is the same listing).
              One <div class="lot-block"> per lot: <h4>Lot 1</h4>, <p> headline cut at ~45 characters, and
              <p class="estimate">Estimate: £400 - 600</p>. The link hrefs hold the lot URL (and a non-standard
              "&233;" for "é", which the site accepts as written).
  lot page    <div class="lot-header"> <h2>Lot 1 , headline</h2>, then one <p> whose lines (split by <br>) are:
              artist (French, 1857-1912) / title / description lines ... / £400-600. The picture is the
              a.zoomme link (/full/...); the <img src> uses backslashes and must not be used.

houses.json options:
  calendar_urls       default [<website>/calendar]
  max_calendar_pages  calendar pages to read (default 4)
  lots_url            listing URL template with {code} and {page} (default above)
  sale_include / sale_include_extra / sale_exclude, max_pages, max_new_lot_pages: see sources/base.py
"""
import json
import logging
import re
from urllib.parse import unquote, unquote_plus

from .base import Adapter, sale_wanted
from .htmlutil import ancestors, clean_url, first_estimate, page_links, parse, parse_date_range

log = logging.getLogger("collector.gorringes")

LOTS_URL = "https://auction.gorringes.co.uk/asp/searchresults.asp?st=D&sale_no={code}&pg={page}"
_CATALOG = re.compile(r"/auction-catalog/(\w+)", re.I)
_REFNO = re.compile(r"refno=(\d+)")
_SALELOT = re.compile(r"salelot=([^&]+)")
_SLUG = re.compile(r"/auction-lot-detail/([^&?]+)")
_SLUG_PARTS = re.compile(r"^(?P<artist>.+?),-(?P<dates>(?:c\.?-?)?\d{4}(?:-\d{4})?)(?:,-(?P<title>.*))?$")


def _has_class(node, name):
    return name in node.get("class").split()


class GorringesAdapter(Adapter):
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
            refs, _ = self.parse_listing(html, url)
            page = int(re.search(r"[?&]pg=(\d+)", url).group(1)) if re.search(r"[?&]pg=(\d+)", url) else 1
            total = self.page_count(html)
            # The pager says "Page 1 of 29": queue our own page URLs (the pager's links order the query differently).
            if total:
                more = [template.format(code=code, page=n) for n in range(page + 1, total + 1)] if page == 1 else []
            else:
                more = [template.format(code=code, page=page + 1)] if refs else []
            return refs, more

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

    @staticmethod
    def page_count(html):
        """'Page 1 of 29.' -> 29 (None when the pager is absent). The page also holds an old pager inside an
        HTML comment (another sale's, 32 pages): comments are ignored."""
        m = re.search(r"Page\s+\d+\s+of\s+(\d+)", re.sub(r"<!--.*?-->", "", html or "", flags=re.S))
        return int(m.group(1)) if m else None

    def parse_listing(self, html, base_url):
        """One lot-block per lot: -> (refs [{id, url, lot_number, title, estimate_text?}], other page urls)."""
        root = parse(html)
        refs = {}
        for block in root.find_all(test=lambda n: _has_class(n, "lot-block")):
            link = next((a for a in block.find_all("a") if "salelot=" in a.get("href") and "refno=" in a.get("href")
                         and "/auction-lot-detail/" in a.get("href")), None)
            if link is None:
                continue
            url = clean_url(base_url, link.get("href"))
            ref_id = self._refno(url)
            if ref_id in refs:
                continue
            slug = self._slug(url)
            body = next((n for n in block.iter() if _has_class(n, "lot-body")), block)
            paras = [p for p in body.find_all("p") if p.text()]
            est = next((p.text() for p in paras if _has_class(p, "estimate") and "£" in p.text()), "")
            headline = next((p.text() for p in paras if not _has_class(p, "estimate")), "")
            lot_no = self._lot_no(url)
            if not lot_no:
                m = re.match(r"lot\s+(\w+)", next((h.text() for h in body.find_all("h4")), ""), re.I)
                lot_no = m.group(1) if m else ""
            ref = {"id": ref_id, "url": url, "lot_number": lot_no, "title": headline or (slug[2] if slug else "")}
            figure = first_estimate([est])
            if figure:
                ref["estimate_text"] = figure
            refs[ref_id] = ref
        return list(refs.values()), page_links(root, base_url, ("pg",))

    # ---------- one lot page ----------
    _ARTIST_LINE = re.compile(r"\([^)]*\d{4}[^)]*\)\s*$")
    _PRICE_LINE = re.compile(r"^£\s*[\d,]+(?:\s*[-–]\s*£?\s*[\d,]+)?$")

    def parse_lot(self, html, url, house=None):
        """Lot page -> raw_lot, from the <p> under the lot heading (lines split by <br>):
        'Artist (French, 1857-1912)' / 'Title,' / description lines / '£400-600'. A lot without an artist line
        starts with its title. Dimensions are left to the tagger, which reads them from the description."""
        root = parse(html)
        raw = {"lot_url": url, "lot_number": self._lot_no(url)}
        container = next((n for n in root.iter() if _has_class(n, "lot-container")), root)
        heading = next((h.text() for h in container.find_all("h2")), "")
        para = next((p for p in container.find_all("p") if p.find_all("b") and len(p.lines()) >= 2), None)
        lines = para.lines() if para else []
        if lines and self._ARTIST_LINE.search(lines[0]):
            raw["artist_text"], lines = lines[0], lines[1:]
        estimate = next((l for l in reversed(lines) if self._PRICE_LINE.match(l)), None)
        if estimate:
            raw["estimate_text"] = estimate
            lines = [l for l in lines if l != estimate]
        if lines:
            raw["title"] = lines[0].strip(" ,;:").strip("'‘’\"“”").strip()
            detail = [l.strip(" ,;") for l in lines[1:]]
            raw["description"] = ", ".join(l for l in detail if l) or None
            raw["medium_detail"] = ", ".join(l for l in detail if l and not re.search(r"\d\s*(?:cm|mm|in)\b", l)) or None
        elif heading:  # no <p>: fall back to the heading 'Lot 1 , Artist, French 1857-1912, Title'
            raw["title"] = re.sub(r"^Lot\s+\w+\s*,\s*", "", heading).strip()
        if not raw["lot_number"]:
            m = re.match(r"Lot\s+(\w+)", heading)
            raw["lot_number"] = m.group(1) if m else ""
        slug = self._slug(url)
        if slug and slug[1] and not raw.get("artist_text") and not lines:
            raw["artist_text"] = f"{slug[0]} ({slug[1]})"
        zoom = next((a.get("href") for a in container.find_all("a") if a.has_class("zoomme") and a.get("href")), None)
        if zoom:
            raw["image_url"] = clean_url(url, zoom)
        return {k: v for k, v in raw.items() if v not in (None, "")}
