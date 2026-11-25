"""Adapter for Lawrences of Crewkerne. Written from real saved pages (tests/fixtures/lawrences/).

VERIFIED (real pages)
  calendar    https://auctions.lawrences.co.uk/en/calendar (the Auctionet-hosted calendar, which
              https://lawrences.co.uk/auction-calendar/ shows). One box per sale DAY: month, day number, title
              and "Hammer auction . Friday 11 December" (no year: we find the year whose weekday matches). Two
              boxes with the same title on consecutive days are ONE sale (26-27 Feb style): sale_end_date.
  lot page    https://www.lawrences.co.uk/sales/fine-art-sales/fs<DDMMYY>/view-lot/<n>/  Sale name (h1), sale
              date, "Lot n", CAPITAL headline "ARTIST (BORN 1950) - TITLE, 1985" then description, estimate
              ("£5000 - £7000") and image (cloudfront, first gallery item).
UNVERIFIED (never saved, so guessed)
  catalogue   https://www.lawrences.co.uk/sales/fine-art-sales/fs<DDMMYY>/ ("Full Catalogue" link on every lot
              page; fs + day-month-year of the sale day, as in fs170119 = 17 Jan 2019). It is read for
              /view-lot/<n>/ links and ?page=n style paging links. A day whose catalogue is not online gives a
              404 which is logged and skipped.
  The Auctionet event pages (/en/events/<id>-<slug>) are not read: the saved calendar only links a trains sale.

houses.json options:
  calendar_urls       default [https://auctions.lawrences.co.uk/en/calendar]
  catalogue_base      default https://www.lawrences.co.uk
  catalogue_section   default fine-art-sales (the other section is general-sales)
  lookahead_days      only look for a catalogue this many days before the sale (default 45)
  sale_include / sale_include_extra / sale_exclude, max_pages, max_new_lot_pages: see sources/base.py
"""
import logging
import re
from datetime import date, timedelta
from urllib.parse import urlsplit

from ..fetcher import FetchError
from .base import Adapter, sale_wanted
from .htmlutil import (card_of, clean_url, first_estimate, meta_tags, page_links, parse, parse_date,
                       parse_date_range)

log = logging.getLogger("collector.lawrences")

CALENDAR_URL = "https://auctions.lawrences.co.uk/en/calendar"
CATALOGUE_BASE = "https://www.lawrences.co.uk"
_LOT_PATH = re.compile(r"^/sales/([^/]+)/(fs\d{6})/view-lot/(\d+[a-z]?)/?$", re.I)
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_META_DAY = re.compile(r"(" + "|".join(_WEEKDAYS) + r")\s+(\d{1,2})\s+([A-Za-z]+)", re.I)
_HEADLINE = re.compile(r"^(?P<head>[A-Z0-9][A-Z0-9 ,.'’()&/:;*\-–]*?)(?=\s+[a-z]|\s*$)")
_ARTIST_TITLE = re.compile(r"^(?P<artist>.+?\(\s*(?:born\s+|b\.\s*|fl\.?\s*)?\d{4}(?:\s*[-–]\s*\d{4})?\s*\))"
                           r"\s*[-–:]\s*(?P<title>.+)$", re.I)
_SMALL = {"a", "an", "and", "at", "by", "for", "from", "in", "of", "on", "or", "the", "to", "with"}


def _has_class(node, name):
    return name in node.get("class").split()


def tidy_caps(text):
    """'TERRACOTTA VESSEL, 1985' -> 'Terracotta Vessel, 1985' (only when the text is SHOUTED; mixed case is kept)."""
    letters = [c for c in text if c.isalpha()]
    if not letters or sum(c.isupper() for c in letters) < 0.8 * len(letters):
        return text
    words = text.lower().split(" ")
    return " ".join(w if (i and w in _SMALL) else re.sub(r"^([^a-z]*)([a-z])", lambda m: m.group(1) + m.group(2).upper(), w)
                    for i, w in enumerate(words))


def day_code(day):
    """date -> 'fs170119'."""
    return "fs" + day.strftime("%d%m%y")


class LawrencesAdapter(Adapter):
    # ---------- sales ----------
    def list_sales(self, house):
        sales = []
        for cal_url in house.get("calendar_urls") or [CALENDAR_URL]:
            html = self._safe_fetch(house, cal_url)
            if html is None:
                continue
            self.snapshot(house, "calendar", cal_url, html)
            sales += self.parse_calendar(html, cal_url, house)
        sales = [s for s in sales if sale_wanted(house, s["title"])]
        return sorted(sales[:1] if self.diagnosing else sales, key=lambda s: (s["date"], s["id"]))

    def _safe_fetch(self, house, url):
        try:
            return self.fetch(house, url)
        except FetchError as err:
            log.warning("%s: page failed: %s", house["id"], err)
            return None

    def parse_calendar(self, html, base_url, house=None):
        """Day boxes -> sales: [{id, title, date, end_date, url, urls}]. Boxes of one event/title on consecutive
        days are merged."""
        root = parse(html)
        days = []
        for box in root.find_all(None, lambda n: _has_class(n, "calendar-event")):  # an <a> when it has a page
            heading = next((n.text() for n in box.iter() if _has_class(n, "calendar-event__heading")), "")
            meta = next((n.text() for n in box.iter() if _has_class(n, "calendar-event__meta")), "")
            m = _META_DAY.search(meta)
            if not (heading and m):
                continue
            day = self._resolve_day(m.group(1), int(m.group(2)), m.group(3))
            if not day:
                log.info("lawrences: could not date %r (%s)", heading, meta)
                continue
            link = box.get("href") or next((a.get("href") for a in box.find_all("a")), "")
            days.append({"title": heading, "day": day, "event": clean_url(base_url, link) if link else None})
        sales = []
        for d in sorted(days, key=lambda d: (d["title"], d["day"])):
            last = sales[-1] if sales else None
            if last and last["title"] == d["title"] and d["day"] - last["_days"][-1] <= timedelta(days=1):
                last["_days"].append(d["day"])
                last["event"] = last["event"] or d["event"]
            else:
                sales.append({"title": d["title"], "_days": [d["day"]], "event": d["event"]})
        out = []
        for s in sales:
            first, final = s["_days"][0], s["_days"][-1]
            out.append({"id": day_code(first), "title": s["title"], "date": first.isoformat(),
                        "end_date": final.isoformat() if final > first else None, "url": s["event"],
                        "days": [d.isoformat() for d in s["_days"]]})
        return out

    def _resolve_day(self, weekday, number, month_name):
        """'Friday', 11, 'December' -> the next such date whose weekday matches (the page shows no year)."""
        month = parse_date(f"1 {month_name} 2000")
        if not month:
            return None
        month = int(month[5:7])
        today = self.today()
        for year in (today.year, today.year + 1):  # the calendar shows the coming 12 months
            try:
                day = date(year, month, number)
            except ValueError:
                continue
            if _WEEKDAYS[day.weekday()] == weekday.lower() and day >= today - timedelta(days=7):
                return day
        return None

    # ---------- lots of one sale ----------
    def list_lots(self, house, sale):
        first = date.fromisoformat(sale["date"])
        if first - self.today() > timedelta(days=house.get("lookahead_days", 45)):
            log.info("lawrences: %s is too far ahead for a catalogue yet", sale["title"])
            return []
        base = house.get("catalogue_base", CATALOGUE_BASE).rstrip("/")
        section = house.get("catalogue_section", "fine-art-sales")
        refs = {}
        for day in sale.get("days") or [sale["date"]]:
            url = f"{base}/sales/{section}/{day_code(date.fromisoformat(day))}/"
            for ref in self.crawl_pages(house, url, self.parse_listing):
                refs.setdefault(ref["id"], ref)
        return self.fetch_lots(house, list(refs.values()), self._stored_key, self.parse_lot)

    @staticmethod
    def _lot_key(href):
        m = _LOT_PATH.match(urlsplit(href or "").path)
        return f"{m.group(2).lower()}-{m.group(3).lower()}" if m else None

    def _stored_key(self, stored):
        return self._lot_key(stored.get("lot_url"))

    def parse_listing(self, html, base_url):
        """UNVERIFIED catalogue reader: lot links with their card text. -> (refs, other page urls)."""
        root = parse(html)
        refs = {}
        for a in root.find_all("a"):
            url = clean_url(base_url, a.get("href") or "#")
            m = _LOT_PATH.match(urlsplit(url).path)
            if not m or self._lot_key(url) in refs:
                continue
            lines = card_of(a, self._lot_key).lines()
            number = m.group(3)
            texts = [l for l in lines if not re.match(r"^(lot\s*\d|£|estimate|sold|view|bid)", l, re.I)]
            ref = {"id": self._lot_key(url), "url": url, "lot_number": number,
                   "title": tidy_caps(texts[0]) if texts else ""}
            estimate = first_estimate(lines)
            if estimate:
                ref["estimate_text"] = estimate
            refs[ref["id"]] = ref
        return list(refs.values()), page_links(root, base_url)

    # ---------- one lot page (VERIFIED on two real pages) ----------
    def parse_lot(self, html, url, house=None):
        root = parse(html)
        meta = meta_tags(root)
        m = _LOT_PATH.match(urlsplit(url).path)
        raw = {"lot_url": url, "lot_number": m.group(3) if m else ""}

        content = next((n for n in root.find_all("div") if _has_class(n, "content-container")), None)
        lines = content.lines() if content else []
        text = " ".join(lines)
        if len(lines) > 1 and tidy_caps(lines[0]) != lines[0]:
            headline = lines[0]  # headline on a line of its own, description below
        else:  # one paragraph: the leading run of capitals is the headline
            head = _HEADLINE.match(text)
            headline = head.group("head").strip() if head else ""
        if not headline:  # no capital headline: the page title ("Title | Lawrences Auctioneers")
            headline = re.sub(r"\s*\|\s*Lawrences.*$", "", meta.get("og:title", "")).strip()
        split = _ARTIST_TITLE.match(headline)
        if split:
            raw["artist_text"], raw["title"] = split.group("artist").strip(), tidy_caps(split.group("title").strip())
        else:
            raw["title"] = tidy_caps(headline)
        raw["description"] = text if text else None

        prices = next((n for n in root.find_all("div") if _has_class(n, "lot-detail--prices")), None)
        if prices:
            raw["estimate_text"] = first_estimate(prices.lines()[:1])

        gallery = next((li.get("data-src") for li in root.find_all("li") if "cloudfront" in li.get("data-src")), None)
        raw["image_url"] = gallery or re.sub(r"^https?://[^/]+(?=https?://)", "", meta.get("og:image", "")) or None

        heading = next((n for n in root.find_all("div") if _has_class(n, "date-time-where")), None)
        if heading:
            raw["sale_date"], raw["sale_end_date"] = parse_date_range(heading.text())
        return {k: v for k, v in raw.items() if v not in (None, "")}

