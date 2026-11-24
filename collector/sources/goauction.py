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
import json
import logging
import re
from datetime import date
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit

from ..fetcher import FetchError
from .base import Adapter
from .htmlutil import parse, parse_date, parse_date_range

log = logging.getLogger("collector.goauction")
DEFAULT_NEW_LOT_PAGES = 150
_EST_IN_LISTING = re.compile(r"(?:estimate|est\.?)\s*:?\s*(£\s*[\d,]+(?:\s*[-–]\s*£?\s*[\d,]+)?)", re.I)

# Sales whose title does not match are skipped (jewellery, watches, stamps, coins, ...).
ART_SALE = (r"\b(art|arts|artists?|paintings?|pictures?|prints?|drawings?|watercolou?rs?|sculptures?|"
            r"pottery|contemporary|modern|british|scottish|cornish|impressionist|illustrations?)\b")
# Link texts that are buttons, not titles ("View catalogue", "Remind me", ...): every word is in this set.
GENERIC_WORDS = set("view more detail details catalogue catalog browse bid now register remind me read see click "
                    "here online live enter info information lots lot auction sale to the all full this go".split())

_AU = re.compile(r"(?:^|[?&])au=(\d+)")
_LOT_ID = re.compile(r"(?:^|[?&])lot=(\d+)")
_SLUG_LOT_NO = re.compile(r"/lot-(\d+[a-z]?)(?:-|/|$)", re.I)
_LOT_NO_TEXT = re.compile(r"\blot\s*(?:no\.?|number|#)?\s*:?\s*(\d+[A-Za-z]?)\b", re.I)
_LIFE_DATES = re.compile(r"\(\s*(?:[A-Za-z.]+\s+)?(?:b\.\s*|born\s+|fl\.?\s*)?\d{4}\s*(?:[-–—]\s*\d{4})?\s*\)\s*$")

# label (case-insensitive, whole label) -> raw_lot field. Order matters (first hit wins per field).
LABELS = {
    "estimate_text": r"estimate(?:\s*\(gbp\))?|guide price|est\.?",
    "medium_detail": r"medium|materials?|media|technique",
    "dimensions": r"dimensions?|size|image size|overall size|measurements?|sight size",
    "framed": r"framed(?: size| dimensions?)?|frame size",
    "artist_text": r"artist|maker|creator|painter|sculptor",
    "description": r"description|details|catalogue note|lot details",
    "date_made_text": r"date made|date of work|year made|year|circa|dated",
    "auction_date": r"auction date|sale date|date of sale",
}
_LABEL_RX = {f: re.compile(r"^(?:" + rx + r")\b", re.I) for f, rx in LABELS.items()}
_ANY_LABEL = re.compile(r"^(?:" + "|".join(LABELS.values()) + r")\s*(?::|$)", re.I)


# ---- small helpers ------------------------------------------------------------------------
def _clean_url(base, href):
    parts = urlsplit(urljoin(base, href.strip()))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def _query_id(url, rx):
    m = rx.search(urlsplit(url).query)
    return m.group(1) if m else None


def _slug_title(url):
    slug = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"[-_]+", " ", slug).strip().title()


def _is_generic(text):
    words = re.findall(r"[a-z0-9']+", (text or "").lower())
    return not re.search(r"[a-z]{3}", (text or "").lower()) or all(w in GENERIC_WORDS for w in words)


def _ancestors(node):
    while node.parent is not None:
        node = node.parent
        yield node


def _as_int(v):
    try:
        f = float(str(v).replace(",", "").replace("£", ""))
        return int(round(f))
    except (TypeError, ValueError):
        return None


def month_strings(today, count):
    year, month, out = today.year, today.month, []
    for _ in range(max(1, count)):
        out.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


# ---- the adapter ----------------------------------------------------------------------------
class GoAuctionAdapter(Adapter):
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
                    if _is_generic(old["title"]) and not _is_generic(sale["title"]):
                        old["title"] = sale["title"]
        sales = [self._with_date(house, s) for s in found.values() if self._wanted(house, s)]
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
            href = _clean_url(base_url, a.get("href"))
            au = _query_id(href, _AU)
            container = self._container(a, au)
            start, end = parse_date_range(a.text())
            if not start:
                start, end = parse_date_range(container.text())
            title = a.text()
            if _is_generic(title):
                title = self._heading(container) or _slug_title(href)
            sale = {"id": au, "title": re.sub(r"\s+", " ", title).strip(), "date": start, "end_date": end, "url": href}
            old = sales.setdefault(au, sale)
            if old is not sale:
                if not old["date"]:
                    old["date"], old["end_date"] = sale["date"], sale["end_date"]
                if _is_generic(old["title"]) or old["title"] == _slug_title(old["url"]):
                    old["title"] = sale["title"]
        return list(sales.values())

    @staticmethod
    def _container(link, au):
        """Smallest ancestor that holds a date and no other sale: the 'card' this link belongs to."""
        best = link
        for node in _ancestors(link):
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
                if t and not _is_generic(t):
                    return t
        return None

    @staticmethod
    def _wanted(house, sale):
        include = re.compile(house.get("sale_include") or ART_SALE, re.I)
        exclude = house.get("sale_exclude")
        title = sale["title"]
        ok = bool(include.search(title)) and not (exclude and re.search(exclude, title, re.I))
        if not ok:
            log.info("%s: skipping sale %r (title does not look like art)", house["id"], title)
        return ok

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
        cap = 2 if self.diagnosing else house.get("max_lots_per_sale")
        budget = house.get("max_new_lot_pages", DEFAULT_NEW_LOT_PAGES)
        known = self._known_lots()
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
            raw = self.parse_lot(html, ref["url"], house)
            raw["lot_number"] = raw["lot_number"] or ref["lot_number"]
            raw["title"] = raw.get("title") or ref["title"]
            if raw["lot_number"] and raw["title"]:
                lots.append(raw)
        return lots

    def _known_lots(self):
        """Previous lots by GoAuction lot id (taken from the ?lot=<id> in their stored lot_url)."""
        if not hasattr(self, "_known"):
            self._known = {}
            for lot in self.previous_lots or ():
                lot_id = _query_id(lot.get("lot_url") or "", _LOT_ID)
                if lot_id:
                    self._known[lot_id] = lot
        return self._known

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
        """Text of the smallest ancestor holding only this lot's link (a listing 'card')."""
        lot_id = _query_id(link.get("href"), _LOT_ID)
        best = link
        for node in _ancestors(link):
            ids = {_query_id(a.get("href"), _LOT_ID) for a in node.find_all("a")} - {None}
            if ids - {lot_id}:
                break
            best = node
        return best.text()

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
            url = _clean_url(base_url, href)
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
                if text and not _is_generic(text) and len(text) > len(ref["title"]):
                    ref["title"] = text
                    ref["lot_number"] = ref["lot_number"] or (_LOT_NO_TEXT.search(text) or [None, ""])[1]
            elif (parts.netloc == host and "pn=" in parts.query and _query_id(url, _AU) in (sale_id, None)
                  and "/auction/" in parts.path.lower()):
                pages.append(url)
        return list(lots.values()), pages

    # ---------- one lot page ----------
    def parse_lot(self, html, url, house=None):
        """Lot page -> raw_lot. Order of trust: JSON-LD, labelled fields, og:/meta tags, visible text."""
        root = parse(html)
        meta = self._meta(root)
        ld = self._json_ld(root)
        lines = self._main_lines(root)
        labelled = self._labelled(lines)
        raw = {"lot_url": url}

        raw["title"] = self._clean_title(
            ld.get("name") or self._first_text(root, "h1") or meta.get("og:title") or self._first_text(root, "title"),
            house)
        raw["lot_number"] = (self._lot_number(lines, raw["title"], url)) or ""
        raw["title"] = re.sub(r"^\s*lot\s*\d+[A-Za-z]?\s*[-–—:.]*\s*", "", raw["title"] or "", flags=re.I).strip()

        creator = ld.get("creator") or ld.get("artist")
        creator = creator.get("name") if isinstance(creator, dict) else creator
        raw["artist_text"] = labelled.get("artist_text") or creator or self._artist_class(root) \
            or self._artist_heading(lines, raw["title"])
        raw["medium_detail"] = labelled.get("medium_detail")
        raw["estimate_text"] = labelled.get("estimate_text")
        offers = ld.get("offers")
        offers = offers[0] if isinstance(offers, list) and offers else offers
        offers = offers if isinstance(offers, dict) else {}
        if not raw["estimate_text"]:
            low = _as_int(offers.get("lowPrice") or offers.get("price"))
            high = _as_int(offers.get("highPrice") or offers.get("price"))
            if low is not None:
                raw["estimate_low"], raw["estimate_high"] = low, high if high is not None else low
        raw["dimensions"] = labelled.get("dimensions") or labelled.get("framed")
        raw["date_made_text"] = labelled.get("date_made_text")
        # The lot's own sale day(s), when shown. The tagger only uses it to widen a sale's end date.
        raw["sale_date"], raw["sale_end_date"] = parse_date_range(labelled.get("auction_date"))
        raw["description"] = (labelled.get("description") or ld.get("description") or meta.get("og:description")
                              or meta.get("description") or self._visible_summary(lines, raw["title"]))
        image = ld.get("image")
        image = image[0] if isinstance(image, list) and image else image
        image = image.get("url") if isinstance(image, dict) else image
        raw["image_url"] = image or meta.get("og:image") or self._stock_image(root)
        if raw["image_url"]:
            raw["image_url"] = _clean_url(url, raw["image_url"])
        return {k: v for k, v in raw.items() if v not in (None, "")}

    # -- extraction pieces --
    @staticmethod
    def _meta(root):
        out = {}
        for m in root.find_all("meta"):
            key = (m.get("property") or m.get("name")).lower()
            if key and m.get("content"):
                out.setdefault(key, m.get("content").strip())
        return out

    @staticmethod
    def _json_ld(root):
        """First schema.org Product/artwork object found in any ld+json block ({} if none)."""
        def walk(obj):
            if isinstance(obj, list):
                for o in obj:
                    yield from walk(o)
            elif isinstance(obj, dict):
                yield obj
                yield from walk(obj.get("@graph", []))
        for s in root.find_all("script", lambda n: "ld+json" in n.get("type").lower()):
            try:
                data = json.loads(s.raw_text())
            except ValueError:
                continue
            for obj in walk(data):
                kind = obj.get("@type")
                kinds = kind if isinstance(kind, list) else [kind]
                if any(str(k) in ("Product", "VisualArtwork", "CreativeWork", "Offer") for k in kinds):
                    return obj
        return {}

    @staticmethod
    def _first_text(root, tag):
        for n in root.find_all(tag):
            if n.text():
                return n.text()
        return None

    @staticmethod
    def _clean_title(title, house):
        title = re.sub(r"\s+", " ", title or "").strip()
        if house and house.get("name"):
            title = re.sub(r"\s*[|–—-]\s*" + re.escape(house["name"]) + r"\s*$", "", title, flags=re.I)
        return title

    @staticmethod
    def _main_lines(root):
        """Visible text lines, without navigation/header/footer chrome where the page marks it."""
        return root.lines(skip={"nav", "footer"})

    @staticmethod
    def _labelled(lines):
        """'Label: value' on one line, or 'Label' alone with the value on the next line(s).
        Without a colon only an estimate may carry its value ('Estimate £800 - £1,200')."""
        out = {}
        for i, line in enumerate(lines):
            for field, rx in _LABEL_RX.items():
                m = rx.match(line)
                if not m or field in out:
                    continue
                rest = line[m.end():].strip()
                if not rest:  # label alone: the value is on the next line(s)
                    parts = []
                    for follow in lines[i + 1:i + 6]:
                        if _ANY_LABEL.match(follow):
                            break
                        parts.append(follow)
                        if field != "description":
                            break
                    value = " ".join(parts)
                elif rest[0] == ":" or (rest[0] in "–-" and rest[1:2].isspace()):
                    value = rest.lstrip(":–- ")
                elif field == "estimate_text" and re.match(r"[\d£]", rest):
                    value = rest
                else:
                    continue  # prose that merely starts with the word
                if value:
                    out[field] = value[:600]
        return out

    @staticmethod
    def _lot_number(lines, title, url):
        m = _SLUG_LOT_NO.search(urlsplit(url).path)
        if m:
            return m.group(1)
        for text in [title] + lines[:30]:
            hit = _LOT_NO_TEXT.search(text or "")
            if hit:
                return hit.group(1)
        return ""

    @staticmethod
    def _artist_class(root):
        for n in root.iter():
            if n.tag not in ("html", "body") and "artist" in (n.get("class") + " " + n.get("itemprop")).lower():
                t = n.text()
                if t and len(t) < 120 and len(n.lines()) <= 2:
                    return t
        return None

    @staticmethod
    def _artist_heading(lines, title):
        """A short line near the top ending in life dates, e.g. 'JOHN PIPER (1903-1992)'."""
        for line in lines[:60]:
            if line != title and len(line) < 90 and _LIFE_DATES.search(line) and not _ANY_LABEL.match(line) \
                    and not re.search(r"[£$]|\blot\b|\bestimate\b", line, re.I) and re.search(r"[A-Za-z]{3}", line):
                return line
        return None

    @staticmethod
    def _visible_summary(lines, title):
        keep = [l for l in lines if l != title and not _ANY_LABEL.match(l) and len(l) > 25]
        return " ".join(keep[:3])[:600] or None

    @staticmethod
    def _stock_image(root):
        for img in root.find_all("img"):
            src = img.get("src") or img.get("data-src")
            if src and "/stock/" in src:
                return src
        return None
