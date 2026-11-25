"""Adapter for David Duggleby (and Duggleby Stephenson of York, which share the site).

The saved pages (tests/fixtures/duggleby/) are empty shells ("Loading Auction...", "Loading Lots..."): the real
lists are fetched by the page's own JavaScript from two JSON endpoints. Their addresses, the request bodies and
the field names below were read from that JavaScript, so they are VERIFIED AS CODE but no real JSON answer was
ever saved: field names are UNVERIFIED against a live answer and every access is forgiving (missing = None).

  sales   POST /api/Auctions/GetMoreAuctions  {pageIndex, pageSize: 20, ClientNo: null}  -> [auction, ...]
          auction: AuctionName, SubTitle, AuctionDate ("dd/mm/yyyy"), auctionLink ("/auctions/2787/Modern-Art/"),
                   FDTimed ("True"/"False"), FDstarttime, FDvenue, description, image
  lots    POST /api/Auctions/FilterBidItems {AuctionNo, SearchText, Sort: "lowLotNo", Page (from 1), ClientNo: 0,
          PageSize: 800, Preview: false, Filters: [{FilterType, Values: []}, ...]} -> {FilteredBidItems: [item, ...]}
          item: ItemNo, ItemLotNo, ItemLotA, ItemDescription, ItemDescriptionTruncated, ItemEstimateText,
                ItemThumbnail, ItemLink, ItemCat
The lot list already holds lot number, description, estimate, link and picture, so no lot page is read (nothing
to fetch incrementally: one request per 800 lots).

houses.json options:
  auctions_api / lots_api   endpoint URLs (default: <website>/api/Auctions/GetMoreAuctions and .../FilterBidItems)
  sale_include / sale_include_extra / sale_exclude: see sources/base.py (matched against sale name + sub-title)
"""
import logging
import re
from datetime import datetime
from urllib.parse import urljoin

from .base import Adapter, sale_wanted
from .whitelabel import WhiteLabelAdapter

log = logging.getLogger("collector.duggleby")

AUCTIONS_PATH = "/api/Auctions/GetMoreAuctions"
LOTS_PATH = "/api/Auctions/FilterBidItems"
AUCTIONS_PAGE = 20
LOTS_PAGE = 800
MAX_AUCTION_PAGES = 50
FILTER_TYPES = ("category", "subcategory", "type", "material", "age", "price", "maker", "availability", "company")
_AUCTION_NO = re.compile(r"/auctions/(\d+)(?:/|$)")
# "JOHN PIPER (1903-1992), Harbour at Dusk, ..." / "John Piper (1903-1992) Harbour ...": artist with life dates first.
_ARTIST_LEAD = re.compile(r"^(?P<artist>(?:(?:Attributed to|Circle of|After|Manner of|Follower of|School of|Style of)\s+)?"
                          r"(?:[A-Z][\w'’.\-]*\s+){1,4}\(\s*(?:b\.\s*|born\s+|fl\.?\s*)?\d{4}(?:\s*[-–]\s*\d{4})?\s*\))"
                          r"[\s,:\-–]*(?P<rest>\S.*)$")


def _text(value):
    """JSON strings like 'null' or None -> ''."""
    value = "" if value is None else str(value).strip()
    return "" if value.lower() == "null" else value


class DugglebyAdapter(Adapter):
    # ---------- sales ----------
    def list_sales(self, house):
        api = house.get("auctions_api") or urljoin(house["website"], AUCTIONS_PATH)
        found, page = {}, 0
        while page < MAX_AUCTION_PAGES:
            rows = self.fetch_json(house, api, {"pageIndex": page, "pageSize": AUCTIONS_PAGE, "ClientNo": None},
                                   kind="calendar.json")
            if not isinstance(rows, list) or not rows:
                break
            for row in rows:
                sale = self.parse_auction(row, house["website"])
                if sale and sale_wanted(house, sale["title"], sale["subtitle"]):
                    found.setdefault(sale["id"], sale)
            if len(rows) < AUCTIONS_PAGE or self.diagnosing:
                break
            page += 1
        return sorted(found.values(), key=lambda s: (s["date"], s["id"]))

    @staticmethod
    def parse_auction(row, website):
        """One JSON auction -> sale dict, or None without a number or a date."""
        link = _text(row.get("auctionLink"))
        m = _AUCTION_NO.search(link)
        try:
            day = datetime.strptime(_text(row.get("AuctionDate")), "%d/%m/%Y").date()
        except ValueError:
            return None
        if not m:
            return None
        return {"id": m.group(1), "title": _text(row.get("AuctionName")), "subtitle": _text(row.get("SubTitle")),
                "date": day.isoformat(), "end_date": None, "url": urljoin(website, link),
                "timed": _text(row.get("FDTimed")).lower() == "true", "venue": _text(row.get("FDvenue"))}

    # ---------- lots ----------
    def list_lots(self, house, sale):
        api = house.get("lots_api") or urljoin(house["website"], LOTS_PATH)
        lots, seen, page = [], set(), 1
        max_pages = 1 if self.diagnosing else house.get("max_pages", 40)
        while page <= max_pages:
            answer = self.fetch_json(house, api, {
                "AuctionNo": int(sale["id"]), "SearchText": "", "Sort": "lowLotNo", "Page": page, "ClientNo": 0,
                "PageSize": LOTS_PAGE, "Preview": False,
                "Filters": [{"FilterType": f, "Values": []} for f in FILTER_TYPES]}, kind="sale.json")
            items = answer.get("FilteredBidItems") if isinstance(answer, dict) else None
            if not items:
                break
            new = [i for i in items if _text(i.get("ItemNo")) not in seen]
            for item in new:
                seen.add(_text(item.get("ItemNo")))
                raw = self.parse_item(item, sale, house["website"])
                if raw:
                    lots.append(raw)
            if len(items) < LOTS_PAGE or not new:
                break
            page += 1
        if self.diagnosing:  # the HTML sale page and one real lot page, to see what the site really serves
            self.diagnose_fetch(house, "catalog", sale["url"])
            link = next((l["lot_url"] for l in lots if l.get("lot_url") != sale["url"]), None)
            self.diagnose_fetch(house, "lot", link)
        return lots

    @staticmethod
    def parse_item(item, sale, website):
        """One JSON lot -> raw_lot (None if it has no number or description)."""
        number = _text(item.get("ItemLotNo")) + _text(item.get("ItemLotA"))
        description = _text(item.get("ItemDescription")) or _text(item.get("ItemDescriptionTruncated"))
        if not (number and description):
            return None
        headline = WhiteLabelAdapter._headline(description)  # first clause = the title-ish part
        artist, title = WhiteLabelAdapter._split_artist(headline)
        lead = None if artist else _ARTIST_LEAD.match(description)
        if lead:
            artist, title = lead.group("artist"), WhiteLabelAdapter._headline(lead.group("rest"))
        link = _text(item.get("ItemLink"))
        raw = {"lot_number": number, "title": title or headline, "description": description,
               "lot_url": urljoin(website, link) if link else sale["url"],
               "estimate_text": _text(item.get("ItemEstimateText")) or None,
               "image_url": urljoin(website, _text(item.get("ItemThumbnail"))) if _text(item.get("ItemThumbnail")) else None}
        if artist:
            raw["artist_text"] = artist
        return {k: v for k, v in raw.items() if v}
