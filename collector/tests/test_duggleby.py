"""Tests for the David Duggleby adapter.

The real saved pages are JavaScript shells, so the REAL-page tests check that the endpoints, request fields and
field names the adapter relies on are the ones written in that JavaScript (fixtures/duggleby/). The JSON answers
themselves were never saved: the answer tests use SYNTHETIC JSON shaped by those field names."""
import json
import os
import unittest

from collector.sources import get_adapter
from collector.sources.duggleby import AUCTIONS_PAGE, LOTS_PAGE, DugglebyAdapter
from collector.tagger import tag
from collector.tests.fakes import FakeFetcher
from collector.validate import validate_lot

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "duggleby")
SITE = "https://www.davidduggleby.com"
AUCTIONS_API, LOTS_API = SITE + "/api/Auctions/GetMoreAuctions", SITE + "/api/Auctions/FilterBidItems"
HOUSE = {"id": "duggleby", "name": "David Duggleby", "website": SITE, "crawl_delay": 3, "content_policy": "full",
         "sale_include_extra": "antiques?|interiors|collectors?"}


def fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


AUCTION = {"AuctionName": "Modern Art", "SubTitle": "null", "AuctionDate": "03/12/2026", "FDTimed": "False",
           "FDstarttime": "11:00", "FDvenue": "Online & Live Broadcast from Duggleby Stephenson of York",
           "auctionLink": "/auctions/2787/Modern-Art/", "description": "Bold ideas ...", "image": "/files/x.jpg"}
JEWELS = dict(AUCTION, AuctionName="Jewellery & Watches", auctionLink="/auctions/2790/Jewellery/", AuctionDate="04/12/2026")
ANTIQUES = dict(AUCTION, AuctionName="Antiques & Interiors", auctionLink="/auctions/2791/Antiques/", AuctionDate="10/12/2026")


def item(no, number, text, est="£200 - £300", link=None, thumb="/files/lots/%s.jpg"):
    return {"ItemNo": no, "ItemAuction": 2787, "ItemLotNo": number, "ItemLotA": "", "ItemCat": "2",
            "ItemDescription": text, "ItemDescriptionTruncated": text[:60], "ItemEstimateText": est,
            "ItemLink": link or f"/auctions/2787/Modern-Art/lot/{number}/", "ItemThumbnail": thumb % no}


class RealPageTests(unittest.TestCase):
    def test_registered(self):
        self.assertIs(get_adapter("duggleby"), DugglebyAdapter)

    def test_auction_list_endpoint_and_fields_match_the_page_script(self):
        js = fixture("auctions_page.html")
        self.assertIn("fetch('/api/Auctions/GetMoreAuctions'", js)
        self.assertIn("{ pageIndex: page, pageSize: pageSize, ClientNo: clientNo }", js)
        self.assertIn("const pageSize = 20;", js)
        self.assertEqual(AUCTIONS_PAGE, 20)

    def test_lot_list_endpoint_and_request_fields_match_the_page_script(self):
        js = fixture("sale_page.html")
        self.assertIn("fetch('/api/Auctions/FilterBidItems'", js)
        for field in ("AuctionNo", "SearchText", "Sort", "Page", "ClientNo", "PageSize", "Preview", "Filters", "FilterType", "Values"):
            self.assertIn(field + ":", js)
        self.assertIn("const pageSize = 800;", js)
        self.assertEqual(LOTS_PAGE, 800)
        for field in ("ItemNo", "ItemLotNo", "ItemLotA", "ItemDescription", "ItemEstimateText", "ItemThumbnail"):
            self.assertIn("item." + field, js)

    def test_real_sale_page_text_matches_the_modern_art_sale(self):
        self.assertIn("Thursday 03 December 2026", fixture("sale_page.html"))
        sale = DugglebyAdapter.parse_auction(AUCTION, SITE)
        self.assertEqual((sale["id"], sale["date"]), ("2787", "2026-12-03"))


class SalesTests(unittest.TestCase):  # SYNTHETIC JSON
    def test_parse_auction(self):
        sale = DugglebyAdapter.parse_auction(AUCTION, SITE)
        self.assertEqual((sale["id"], sale["title"], sale["subtitle"], sale["date"], sale["url"], sale["timed"]),
                         ("2787", "Modern Art", "", "2026-12-03", SITE + "/auctions/2787/Modern-Art/", False))
        self.assertIsNone(DugglebyAdapter.parse_auction(dict(AUCTION, AuctionDate="soon"), SITE))
        self.assertIsNone(DugglebyAdapter.parse_auction(dict(AUCTION, auctionLink="/members/"), SITE))

    def test_list_sales_pages_until_a_short_page_and_keeps_art_sales(self):
        first = [dict(AUCTION, AuctionName="Sale %d" % i, auctionLink="/auctions/%d/x/" % (3000 + i)) for i in range(AUCTIONS_PAGE - 3)] \
            + [AUCTION, JEWELS, ANTIQUES]
        second = [dict(AUCTION, AuctionName="Fine Paintings", auctionLink="/auctions/2789/Fine-Paintings/", AuctionDate="04/12/2026")]
        fetcher = FakeFetcher(json_pages={AUCTIONS_API: lambda p: first if p["pageIndex"] == 0 else second if p["pageIndex"] == 1 else []})
        sales = DugglebyAdapter(fetcher).list_sales(HOUSE)
        self.assertEqual([(s["id"], s["title"], s["date"]) for s in sales],
                         [("2787", "Modern Art", "2026-12-03"), ("2789", "Fine Paintings", "2026-12-04"),
                          ("2791", "Antiques & Interiors", "2026-12-10")])
        self.assertEqual([p["pageIndex"] for _, p in fetcher.posts], [0, 1])
        self.assertEqual(fetcher.posts[0][1], {"pageIndex": 0, "pageSize": 20, "ClientNo": None})

    def test_unreadable_answer_gives_no_sales(self):
        self.assertEqual(DugglebyAdapter(FakeFetcher()).list_sales(HOUSE), [])


class LotsTests(unittest.TestCase):  # SYNTHETIC JSON
    sale = {"id": "2787", "title": "Modern Art", "date": "2026-12-03", "end_date": None, "url": SITE + "/auctions/2787/Modern-Art/"}
    ITEMS = [item(1, "1", "John Piper (1903-1992), Harbour at Dusk, oil on canvas, 40 x 50cm"),
             item(2, "2", "After David Hockney, Homage to Picasso, offset lithograph", est="£50 - £80"),
             item(3, "3", "A gold ring set with a diamond", est="£300 - £400")]

    def test_request_body_and_lots(self):
        fetcher = FakeFetcher(json_pages={LOTS_API: {"FilteredBidItems": self.ITEMS}})
        lots = DugglebyAdapter(fetcher).list_lots(HOUSE, self.sale)
        body = fetcher.posts[0][1]
        self.assertEqual((body["AuctionNo"], body["Page"], body["PageSize"], body["Sort"], body["ClientNo"], body["Preview"]),
                         (2787, 1, 800, "lowLotNo", 0, False))
        self.assertIn({"FilterType": "category", "Values": []}, body["Filters"])
        self.assertEqual([l["lot_number"] for l in lots], ["1", "2", "3"])
        first = lots[0]
        self.assertEqual((first["estimate_text"], first["lot_url"], first["image_url"]),
                         ("£200 - £300", SITE + "/auctions/2787/Modern-Art/lot/1/", SITE + "/files/lots/1.jpg"))

    def test_raw_lot_tags_into_a_valid_lot(self):
        fetcher = FakeFetcher(json_pages={LOTS_API: {"FilteredBidItems": self.ITEMS}})
        raw = DugglebyAdapter(fetcher).list_lots(HOUSE, self.sale)[0]
        lot = tag(raw, HOUSE, self.sale)
        self.assertEqual((lot["id"], lot["artist"], lot["artist_dates"], lot["medium"], lot["estimate_low"]),
                         ("duggleby-2787-1", "John Piper", "1903-1992", "Oil", 200))
        self.assertEqual(validate_lot(lot), [])

    def test_whole_run_through_the_collector(self):
        from collector import run
        fetcher = FakeFetcher(json_pages={AUCTIONS_API: [AUCTION], LOTS_API: {"FilteredBidItems": self.ITEMS}})
        lots, rejected = run.collect_house(dict(HOUSE, adapter="duggleby"), fetcher, "2026-11-25", "2026-11-25T00:00:00Z")
        self.assertEqual(([l["lot_number"] for l in lots], rejected), (["1", "2"], 1))  # the ring is not artwork

    def test_big_sale_is_read_page_by_page(self):
        many = [item(n, str(n), f"Artist {n} (1900-1950), Title {n}, oil on canvas") for n in range(1, LOTS_PAGE + 1)]
        tail = [item(LOTS_PAGE + 1, str(LOTS_PAGE + 1), "Last lot, watercolour")]
        fetcher = FakeFetcher(json_pages={LOTS_API: lambda p: {"FilteredBidItems": many if p["Page"] == 1 else tail}})
        lots = DugglebyAdapter(fetcher).list_lots(HOUSE, self.sale)
        self.assertEqual(len(lots), LOTS_PAGE + 1)
        self.assertEqual([p["Page"] for _, p in fetcher.posts], [1, 2])

    def test_missing_pieces_never_crash(self):
        self.assertIsNone(DugglebyAdapter.parse_item({"ItemNo": 9}, self.sale, SITE))
        raw = DugglebyAdapter.parse_item({"ItemNo": 9, "ItemLotNo": "5", "ItemLotA": "a", "ItemDescription": "Untitled"}, self.sale, SITE)
        self.assertEqual((raw["lot_number"], raw["lot_url"]), ("5a", self.sale["url"]))


if __name__ == "__main__":
    unittest.main()
