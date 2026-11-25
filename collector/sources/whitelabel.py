"""Adapter for the white-label catalogue platform shared by Gardiner Houlgate, Fieldings, Mellors & Kirk,
Trevanion, Peter Francis and Hansons (auctions.hansonsauctioneers.co.uk). Written from real saved pages
(tests/fixtures/whitelabel/).

URL patterns (the two long hex strings are opaque ids):
  sale (one day)  /catalogue/<auction>/<day>/<slug>/            ?currentPageNo=<n>   (60 lots a page)
  lot             /catalogue/lot/<lot>/<day>/<slug>-lot-<number>/

A multi-day sale is one <auction> id with several <day> ids, each listed as its own card on the calendar and
each with its own lot pages. We turn the cards into ONE sale (first day .. last day) that remembers its day
pages in sale["urls"].

houses.json options for a house using this adapter:
  calendar_urls     pages that list the sales (required): e.g. https://auctions.<house>/ or .../auctions/
  sale_include      regex a sale card (title + summary line) must match (default: art words, base.ART_SALE).
                    Mixed "fine art & antiques" sales should match; the tagger drops the non-art lots.
  sale_exclude      regex that removes a sale card (optional)
  max_pages         pages of 60 lots to read per sale day (default 40)
  max_new_lot_pages lot pages fetched per run for lots not seen before (default 150; known lots are reused)
"""
import logging
import re
from urllib.parse import urlsplit

from ..fetcher import FetchError
from ..tagger import classify, is_non_art
from .base import Adapter, sale_wanted
from .htmlutil import ancestors, card_of, clean_url, is_generic, parse, parse_date, parse_date_range, slug_title

log = logging.getLogger("collector.whitelabel")

_HEX = r"([0-9a-f]{32})"
_SALE_PATH = re.compile(r"^/catalogue/" + _HEX + "/" + _HEX + r"/[^/]+/?$", re.I)
_LOT_PATH = re.compile(r"^/catalogue/lot/" + _HEX + "/" + _HEX + r"/[^/]*?-lot-(\d+[a-z]?)/?$", re.I)
_LOT_LINE = re.compile(r"^lot\s+(\d+[A-Za-z]?)$", re.I)
_ESTIMATE_LINE = re.compile(r"^estimate\s*(£.*)$", re.I)
# Lines of a listing card that are not the lot's title.
_CARD_JUNK = re.compile(r"^(lot\s+\d|estimate|hammer|starting bid|current bid|fees\b|watch lot|sold\b|unsold|withdrawn|£)", re.I)
_RESALE = re.compile(r"^artist resale rights apply\s*[-–:]*\s*", re.I)
_SALE_ID_LEN = 10

# "Name - Title" / "Name: Title" at the start of a description: the left part must look like an artist
# (life dates, or 2-5 capitalised words, optionally after an attribution phrase and a dagger).
_NAME_WORD = r"(?:[A-Z][A-Za-z'’.\-]*|de|van|von|le|la|of|the)"
_ARTIST_TITLE = re.compile(
    r"^[†*\s]*(?P<artist>(?:(?:Attributed to|Circle of|After|Manner of|Follower of|School of|Style of)\s+)?"
    r"(?:[A-Z][A-Za-z'’.\-]*\s+){1,4}" + _NAME_WORD + r"?(?:\s*\(\s*(?:b\.\s*)?\d{4}(?:\s*[-–]\s*\d{4})?\s*\))?)"
    r"\s*(?:\s[-–]\s|:\s)\s*(?P<title>\S.*)$")


class WhiteLabelAdapter(Adapter):
    # ---------- sales ----------
    def list_sales(self, house):
        cards = {}
        for cal_url in house.get("calendar_urls") or [house["website"]]:
            try:
                html = self.fetch(house, cal_url)
            except FetchError as err:
                log.warning("%s: calendar page failed: %s", house["id"], err)
                continue
            self.snapshot(house, "calendar", cal_url, html)
            for card in self.parse_calendar(html, cal_url):
                cards.setdefault((card["auction"], card["day"]), card)
        wanted = [c for c in cards.values() if sale_wanted(house, c["title"], c["summary"])]
        sales = self.group_sales(wanted)
        return sales[:1] if self.diagnosing else sales

    def parse_calendar(self, html, base_url):
        """One dict per sale card (= per sale DAY): auction, day, url, title, summary, date."""
        root = parse(html)
        found = {}
        for a in root.find_all("a"):
            href = a.get("href")
            if not href or href.startswith(("#", "javascript:", "mailto:")):
                continue
            url = clean_url(base_url, href)
            m = _SALE_PATH.match(urlsplit(url).path)
            if not m:
                continue
            key = (m.group(1).lower(), m.group(2).lower())
            card = self._card(a, key)
            date, _ = parse_date_range(self._date_text(card) or card.text())
            title = self._title(card) or next((t.text() for t in card.find_all("a") if not is_generic(t.text())), "") \
                or slug_title(url)
            entry = {"auction": key[0], "day": key[1], "url": url, "date": date, "title": title,
                     "summary": self._summary(card)}
            old = found.setdefault(key, entry)
            if old is not entry and not old["date"]:
                old.update(date=entry["date"])
        cards = [c for c in found.values() if c["date"]]
        for c in found.values():
            if not c["date"]:
                log.info("whitelabel: sale card without a date skipped: %s", c["title"])
        return cards

    @staticmethod
    def _key_of(href):
        m = _SALE_PATH.match(urlsplit(href or "").path)
        return (m.group(1).lower(), m.group(2).lower()) if m else None

    def _card(self, link, key):
        """Smallest ancestor holding a date and no other sale card (the box one sale day sits in)."""
        best = link
        for node in ancestors(link):
            others = {self._key_of(a.get("href")) for a in node.find_all("a")} - {key, None}
            if others:
                break
            best = node
            if parse_date(node.text()):
                break
        return best

    @staticmethod
    def _date_text(card):
        for n in card.iter():
            if n.has_class("auction-date") or n.has_class("date-content"):
                return n.text()
        return None

    @staticmethod
    def _title(card):
        for n in card.iter():
            if n.tag != "a" and (n.has_class("auction-title") or n.has_class("sale-title")
                                 or (n.tag == "span" and "title" in n.get("class").split())):
                text = n.text()
                if text and not is_generic(text):
                    return text
        return None

    @staticmethod
    def _summary(card):
        for n in card.iter():
            if n.has_class("auction-summary") or "lead-type" in n.get("class").split():
                return n.text()
        return ""

    @staticmethod
    def group_sales(cards):
        """Day cards -> sales: one per <auction> id, dated first day .. last day, with every day page in `urls`."""
        by_auction = {}
        for c in sorted(cards, key=lambda c: (c["date"], c["url"])):
            by_auction.setdefault(c["auction"], []).append(c)
        sales = []
        for auction, days in by_auction.items():
            first, last = days[0]["date"], days[-1]["date"]
            sales.append({"id": auction[:_SALE_ID_LEN], "title": days[0]["title"], "date": first,
                          "end_date": last if last > first else None, "url": days[0]["url"],
                          "urls": [d["url"] for d in days]})
        return sorted(sales, key=lambda s: (s["date"], s["id"]))

    # ---------- lots of one sale ----------
    def list_lots(self, house, sale):
        refs = []
        for day_url in sale.get("urls") or [sale["url"]]:
            refs += self.lot_refs(house, day_url)
        return self.fetch_lots(house, self._worth_fetching(refs), self._stored_key, self.parse_lot)

    @staticmethod
    def _stored_key(stored):
        m = _LOT_PATH.match(urlsplit(stored.get("lot_url") or "").path)
        return m.group(1).lower() if m else None

    def _worth_fetching(self, refs):
        """Drop lots whose listing title already says jewellery, a watch, a vase ... (saves a request each).
        Same rule as the tagger's, so nothing the tagger would keep is lost; known lots are never dropped."""
        known = self.known_lots(self._stored_key)
        keep = []
        for ref in refs:
            typ, _ = classify(ref["title"])
            if ref["id"] not in known and ref["title"] and is_non_art(typ, ref["title"], None, ""):
                log.debug("whitelabel: lot %s not fetched (%s)", ref["lot_number"], ref["title"])
                continue
            keep.append(ref)
        return keep

    def lot_refs(self, house, day_url):
        """Every lot of one sale day: [{id, url, lot_number, title, estimate_text?}] over all pages."""
        refs, pages, page = {}, 1, 1
        max_pages = house.get("max_pages", 40)
        while page <= min(pages, max_pages):
            url = self.page_url(day_url, page)
            try:
                html = self.fetch(house, url)
            except FetchError as err:
                log.warning("%s: sale page failed: %s", house["id"], err)
                break
            self.snapshot(house, "sale", url, html)
            found, pages_seen = self.parse_sale_page(html, url)
            new = [r for r in found if r["id"] not in refs]
            for r in new:
                refs[r["id"]] = r
            if not new:
                break  # nothing new: past the end (or a page that ignores the page number)
            pages = max(pages, pages_seen)
            page += 1
            if self.diagnosing:
                break
        return list(refs.values())

    @staticmethod
    def page_url(day_url, page):
        if page == 1:
            return day_url
        return day_url + ("&" if "?" in day_url else "?") + f"currentPageNo={page}"

    def parse_sale_page(self, html, base_url):
        """-> (lot refs on this page in order, number of pages of this sale day)."""
        root = parse(html)
        refs = {}
        key_of = lambda href: (self._lot_key(href))  # noqa: E731
        for a in root.find_all("a"):
            url = clean_url(base_url, a.get("href") or "#")
            m = _LOT_PATH.match(urlsplit(url).path)
            if not m:
                continue
            ref = refs.setdefault(m.group(1).lower(), {"id": m.group(1).lower(), "url": url,
                                                       "lot_number": m.group(3), "title": ""})
            if ref["title"] or "estimate_text" in ref:
                continue  # card already read through its first link
            lines = card_of(a, key_of).lines()
            ref["title"] = self._card_title(lines)
            for line in lines:
                est = _ESTIMATE_LINE.match(line)
                if est:
                    ref["estimate_text"] = est.group(1)
        pages = [int(n.get("data-value")) for n in root.find_all(test=lambda n: n.get("data-param") == "currentPageNo")
                 if n.get("data-value").isdigit()]
        return list(refs.values()), max(pages, default=1)

    @staticmethod
    def _lot_key(href):
        m = _LOT_PATH.match(urlsplit(href or "").path)
        return m.group(1).lower() if m else None

    @staticmethod
    def _card_title(lines):
        for line in lines:
            if _CARD_JUNK.match(line):
                continue
            line = _RESALE.sub("", line).strip()
            if line:
                return line
        return ""

    # ---------- one lot page ----------
    def parse_lot(self, html, url, house=None):
        """Lot page -> raw_lot. The page has no separate artist/medium/dimensions fields: they are in the
        description, which the tagger reads. Estimate is absent once a sale is over (the page shows the hammer)."""
        root = parse(html)
        lines = root.lines(skip={"nav", "footer"})
        m = _LOT_PATH.match(urlsplit(url).path)
        raw = {"lot_url": url, "lot_number": m.group(3) if m else self._lot_number(lines)}

        desc_node = next((p for p in root.find_all("p") if "translate" in p.get("class").split()), None)
        description = desc_node.text() if desc_node else ""
        bold = next((s.text() for s in desc_node.find_all("strong") if s.text()), "") if desc_node else ""
        headline = bold.strip(" ,;:") or self._headline(description or self._h1(root))
        artist, title = self._split_artist(headline)
        raw["title"] = title
        if artist:
            raw["artist_text"] = artist
        raw["description"] = description or None

        info = next((n for n in root.iter() if "lot-information" in n.get("class").split()), None)
        info_lines = info.lines() if info else []
        for i, line in enumerate(info_lines[:-1]):
            if line.lower() == "estimate":
                raw["estimate_text"] = info_lines[i + 1]
                break

        image = next((n.get("src") for n in root.find_all("img") if n.has_class("main-image") and n.get("src")), None)
        if image:
            raw["image_url"] = clean_url(url, image)
        for i, line in enumerate(lines):
            if line.lower().startswith("auction date"):
                raw["sale_date"], raw["sale_end_date"] = parse_date_range(" ".join(lines[i:i + 4]))
                break
        return {k: v for k, v in raw.items() if v not in (None, "")}

    @staticmethod
    def _lot_number(lines):
        for line in lines:
            m = _LOT_LINE.match(line)
            if m:
                return m.group(1)
        return ""

    @staticmethod
    def _h1(root):
        h1 = next((n.text() for n in root.find_all("h1") if n.text()), "")
        return h1.rstrip(".").rstrip("…").strip()

    @staticmethod
    def _headline(text, limit=100):
        """No bold lead-in on the page: the first clause of the description, at most `limit` characters."""
        text = (text or "").strip()
        clause = re.split(r",\s|;\s|\.\s", text, maxsplit=1)[0]
        if 8 <= len(clause) <= limit:
            return clause
        if len(text) <= limit:
            return text
        return text[:limit].rsplit(" ", 1)[0]

    @staticmethod
    def _split_artist(headline):
        """'Derek Carruthers (1935-2021) - Continuum' -> ('Derek Carruthers (1935-2021)', 'Continuum').
        No artist-like start: (None, headline)."""
        m = _ARTIST_TITLE.match(headline or "")
        if m and not is_generic(m.group("title")):
            return m.group("artist").strip(), m.group("title").strip()
        return None, headline
