import os
import unittest
from datetime import date

from collector.fetcher import FetchError
from collector.sources import get_adapter
from collector.sources.goauction import GoAuctionAdapter, month_strings
from collector.sources.htmlutil import parse_date, parse_date_range
from collector.tagger import tag
from collector.validate import validate_lot

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "goauction")
BASE = "https://www.davidlay.co.uk"
HOUSE = {"id": "lays", "name": "David Lay", "website": BASE, "crawl_delay": 10,
         "calendar_urls": [BASE + "/"]}


def fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


class FakeFetcher:
    """pages: url -> html. A missing url raises FetchError, like a 404."""

    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def get(self, url, crawl_delay=0):
        self.calls.append(url)
        if url not in self.pages:
            raise FetchError("HTTP 404 for " + url)
        return self.pages[url]


SALE_URL = BASE + "/auction/details/cornish-art-fine-art--studio-pottery/?au=566"
PAGE2 = SALE_URL + "&pn=2&g=1"
LOT1 = BASE + "/auction/lot/lot-1---john-piper-1903-1992/?lot=9001&au=566"
LOT2 = BASE + "/auction/lot/lot-2---unknown/?lot=9002&au=566"
LOT49 = BASE + "/auction/lot/lot-49---anon/?lot=9049&au=566"


class DateTests(unittest.TestCase):
    def test_formats(self):
        for text, want in [("Thu 26 Nov 2026", "2026-11-26"), ("3rd December 2026", "2026-12-03"),
                           ("9-10 Dec 2026", "2026-12-09"), ("December 3, 2026", "2026-12-03"),
                           ("03/12/2026", "2026-12-03"), ("2026-12-03", "2026-12-03"),
                           ("28 Dec - 3 Jan 2027", "2026-12-28"), ("no date", None), ("31 Foo 2026", None)]:
            with self.subTest(text=text):
                self.assertEqual(parse_date(text), want)

    def test_ranges(self):
        for text, want in [("26-27 Nov 2026", ("2026-11-26", "2026-11-27")), ("Thu 26 Nov 2026", ("2026-11-26", None)),
                           ("9–10 Dec 2026", ("2026-12-09", "2026-12-10")), ("26 & 27 Nov 2026", ("2026-11-26", "2026-11-27")),
                           ("28 Dec - 3 Jan 2027", ("2026-12-28", "2027-01-03")), ("none", (None, None))]:
            with self.subTest(text=text):
                self.assertEqual(parse_date_range(text), want)

    def test_month_strings_wrap_the_year(self):
        self.assertEqual(month_strings(date(2026, 11, 5), 3), ["2026-11", "2026-12", "2027-01"])


class CalendarTests(unittest.TestCase):
    def setUp(self):
        self.adapter = GoAuctionAdapter(FakeFetcher({}))
        self.sales = {s["id"]: s for s in self.adapter.parse_calendar(fixture("calendar.html"), BASE + "/")}

    def test_finds_sales_once_each(self):
        self.assertEqual(sorted(self.sales), ["1005", "566", "570", "999"])  # not the lot link

    def test_title_date_and_url(self):
        s = self.sales["566"]
        self.assertEqual((s["title"], s["date"]), ("Cornish Art, Fine Art & Studio Pottery", "2026-11-26"))
        self.assertEqual(s["url"], SALE_URL)

    def test_date_after_the_link(self):
        self.assertEqual(self.sales["570"]["date"], "2026-12-03")

    def test_generic_link_text_falls_back_to_slug(self):
        s = self.sales["1005"]
        self.assertEqual((s["title"], s["date"]), ("The Art Auction", "2026-12-09"))
        self.assertNotIn("#", s["url"])

    def test_two_day_sale_gets_an_end_date(self):
        html = '<div><h3>Cornish Art</h3><p>26-27 Nov 2026</p><a href="/auction/details/x/?au=7">View</a></div>'
        sale = self.adapter.parse_calendar(html, BASE + "/")[0]
        self.assertEqual((sale["date"], sale["end_date"]), ("2026-11-26", "2026-11-27"))
        self.assertIsNone(self.sales["566"]["end_date"])

    def test_missing_date_is_none(self):
        self.assertIsNone(self.sales["999"]["date"])

    def test_list_sales_filters_non_art_and_reads_undated_sale_page(self):
        pages = {BASE + "/": fixture("calendar.html"),
                 BASE + "/auction/details/undated-modern-art-sale?au=999": "<h1>Sale</h1><p>Starts 17 Dec 2026</p>"}
        sales = {s["id"]: s for s in GoAuctionAdapter(FakeFetcher(pages)).list_sales(HOUSE)}
        self.assertEqual(sorted(sales), ["1005", "566", "999"])  # jewellery dropped
        self.assertEqual(sales["999"]["date"], "2026-12-17")

    def test_house_can_override_sale_filter(self):
        house = dict(HOUSE, sale_include="jewellery")
        sales = GoAuctionAdapter(FakeFetcher({BASE + "/": fixture("calendar.html")})).list_sales(house)
        self.assertEqual([s["id"] for s in sales], ["570"])

    def test_failed_calendar_page_is_skipped_not_fatal(self):
        house = dict(HOUSE, calendar_urls=[BASE + "/gone", BASE + "/"])
        sales = GoAuctionAdapter(FakeFetcher({BASE + "/": fixture("calendar.html")})).list_sales(house)
        self.assertTrue(sales)

    def test_month_placeholder(self):
        house = dict(HOUSE, calendar_urls=["https://x.test/cal?m={month}"], calendar_months=2)
        urls = GoAuctionAdapter(FakeFetcher({})).calendar_pages(house, today=date(2026, 12, 1))
        self.assertEqual(urls, ["https://x.test/cal?m=2026-12", "https://x.test/cal?m=2027-01"])


class SalePageTests(unittest.TestCase):
    def test_lot_links_and_pagination(self):
        lots, pages = GoAuctionAdapter(None).parse_sale_page(fixture("sale_p1.html"), SALE_URL, "566")
        self.assertEqual([l["id"] for l in lots], ["9001", "9002"])
        self.assertEqual(lots[0]["lot_number"], "1")
        self.assertEqual(lots[0]["title"], "Lot 1 Harbour at St Ives")
        self.assertEqual(lots[0]["url"], LOT1)
        self.assertIn(PAGE2, pages)
        self.assertFalse([p for p in pages if "au=777" in p])  # another sale's pager

    def test_lot_refs_follow_pages_without_looping(self):
        pages = {SALE_URL: fixture("sale_p1.html"), PAGE2: fixture("sale_p2.html"),
                 SALE_URL + "&pn=1&g=1": fixture("sale_p1.html")}
        fetcher = FakeFetcher(pages)
        refs = GoAuctionAdapter(fetcher).lot_refs(HOUSE, {"id": "566", "url": SALE_URL})
        self.assertEqual([r["id"] for r in refs], ["9001", "9002", "9049"])
        self.assertEqual(len(fetcher.calls), len(set(fetcher.calls)))  # no page fetched twice


class LotPageTests(unittest.TestCase):
    def parse(self, name, url=LOT1):
        return GoAuctionAdapter(None).parse_lot(fixture(name), url, HOUSE)

    def test_labelled_page(self):
        raw = self.parse("lot_labelled.html")
        self.assertEqual(raw["title"], "Harbour at St Ives")
        self.assertEqual(raw["lot_number"], "1")
        self.assertEqual(raw["artist_text"], "JOHN PIPER (1903-1992)")
        self.assertEqual(raw["medium_detail"], "Oil on canvas board, signed and dated 1952")
        self.assertEqual(raw["dimensions"], "40 x 50cm")  # image size, not framed
        self.assertEqual(raw["estimate_text"], "£800 - £1,200")
        self.assertTrue(raw["description"].startswith("A view of the harbour"))
        self.assertEqual(raw["image_url"], "https://davidlay.goauction.co.uk/stock/123-medium.jpg?v=2")
        self.assertEqual(raw["lot_url"], LOT1)

    def test_lot_page_auction_date_is_read(self):
        html = fixture("lot_labelled.html").replace("</body>", "<p>Auction date: 27 Nov 2026</p></body>")
        raw = GoAuctionAdapter(None).parse_lot(html, LOT1, HOUSE)
        self.assertEqual((raw["sale_date"], raw.get("sale_end_date")), ("2026-11-27", None))
        lot = tag(raw, {"id": "lays"}, {"id": "566", "title": "Cornish Art", "date": "2026-11-26"})
        self.assertEqual((lot["sale_date"], lot["sale_end_date"]), ("2026-11-26", "2026-11-27"))

    def test_labelled_page_tags_into_a_valid_lot(self):
        lot = tag(self.parse("lot_labelled.html"), {"id": "lays"}, {"id": "566", "title": "Cornish Art", "date": "2026-11-26"},
                  collected_at="2026-11-23T02:00:00Z")
        self.assertEqual(validate_lot(lot), [])
        self.assertEqual((lot["artist"], lot["medium"], lot["year_made"], lot["estimate_low"], lot["estimate_high"]),
                         ("John Piper", "Oil", 1952, 800, 1200))

    def test_json_ld_page(self):
        raw = self.parse("lot_jsonld.html", BASE + "/auction/lot/lot-7---x/?lot=7")
        self.assertEqual((raw["title"], raw["lot_number"]), ("Winter Hills", "7"))
        self.assertEqual(raw["artist_text"], "After JOHN CONSTABLE (1776-1837)")
        self.assertEqual((raw["estimate_low"], raw["estimate_high"]), (300, 500))
        self.assertEqual(raw["image_url"], BASE + "/stock/77-medium.jpg")
        self.assertEqual(raw["description"], "Watercolour of hills.")
        lot = tag(raw, {"id": "lays"}, {"id": "1", "date": "2026-12-01"})
        self.assertEqual(lot["attribution_note"], "After")

    def test_bare_page_uses_meta_and_visible_text(self):
        raw = GoAuctionAdapter(None).parse_lot(fixture("lot_bare.html"), BASE + "/auction/lot/anything/?lot=12",
                                               {"id": "andersonandgarland", "name": "Anderson & Garland"})
        self.assertEqual(raw["title"], "Winter Skiing Poster")  # site name stripped
        self.assertEqual(raw["lot_number"], "12")
        self.assertEqual(raw["estimate_text"], "£50-80")
        self.assertEqual(raw["description"], "A reproduction poster, framed.")
        self.assertNotIn("dimensions", raw)  # 'Size matters...' is prose, not a label
        self.assertNotIn("artist_text", raw)

    def test_garbage_does_not_crash(self):
        for html in ["", "<<<>>>", "<div><p>", "plain text", "<script type='application/ld+json'>[1,2,{]</script>"]:
            with self.subTest(html=html):
                self.assertIsInstance(self.parse_html(html), dict)

    def parse_html(self, html):
        return GoAuctionAdapter(None).parse_lot(html, LOT1, HOUSE)


class EndToEndTests(unittest.TestCase):
    def pages(self):
        return {BASE + "/": fixture("calendar.html"), SALE_URL: fixture("sale_p1.html"),
                PAGE2: fixture("sale_p2.html"), SALE_URL + "&pn=1&g=1": fixture("sale_p1.html"),
                LOT1: fixture("lot_labelled.html"), LOT49: fixture("lot_bare.html")}  # LOT2 is a 404

    def test_lot_whose_page_fails_is_left_out_so_it_is_fetched_again_later(self):
        adapter = GoAuctionAdapter(FakeFetcher(self.pages()))
        lots = adapter.list_lots(HOUSE, {"id": "566", "url": SALE_URL})
        self.assertEqual([l["lot_number"] for l in lots], ["1", "49"])  # lot 2 is a 404: not stored as listing-only
        self.assertEqual(lots[1]["lot_number"], "49")  # URL slug wins over page text

    def test_max_lots_per_sale(self):
        adapter = GoAuctionAdapter(FakeFetcher(self.pages()))
        lots = adapter.list_lots(dict(HOUSE, max_lots_per_sale=1), {"id": "566", "url": SALE_URL})
        self.assertEqual(len(lots), 1)

    def test_diagnose_saves_first_page_of_each_kind(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            adapter = GoAuctionAdapter(FakeFetcher(self.pages()))
            adapter.diagnose_dir = tmp
            sales = adapter.list_sales(HOUSE)
            adapter.list_lots(HOUSE, sales[0])
            saved = sorted(os.listdir(os.path.join(tmp, "lays")))
            self.assertEqual(saved, ["calendar.html", "lot.html", "sale.html"])
            with open(os.path.join(tmp, "lays", "lot.html"), encoding="utf-8") as f:
                self.assertTrue(f.read().startswith("<!-- fetched from https://www.davidlay.co.uk/auction/lot/"))

    def stored(self, lot_id, number, title="Stored title"):
        return {"house_id": "lays", "lot_number": number, "title": title, "lot_url": f"{BASE}/auction/lot/x/?lot={lot_id}&au=566",
                "estimate_low": 1, "estimate_high": 2}

    def test_known_lots_are_not_fetched(self):
        fetcher = FakeFetcher(self.pages())
        adapter = GoAuctionAdapter(fetcher)
        adapter.previous_lots = [self.stored("9001", "1"), self.stored("9002", "2")]
        lots = adapter.list_lots(HOUSE, {"id": "566", "url": SALE_URL})
        self.assertEqual(adapter.stats, {"new": 1, "reused": 2, "deferred": 0})
        self.assertNotIn(LOT1, fetcher.calls)
        self.assertIn(LOT49, fetcher.calls)
        self.assertEqual([("_stored" in l) for l in lots], [True, True, False])

    def test_new_lot_cap_defers_the_rest(self):
        fetcher = FakeFetcher(self.pages())
        adapter = GoAuctionAdapter(fetcher)
        lots = adapter.list_lots(dict(HOUSE, max_new_lot_pages=1), {"id": "566", "url": SALE_URL})
        self.assertEqual(adapter.stats, {"new": 1, "reused": 0, "deferred": 2})
        self.assertEqual(len(lots), 1)
        self.assertEqual([c for c in fetcher.calls if "/auction/lot/" in c], [LOT1])

    def test_cap_is_shared_across_sales_and_known_lots_do_not_use_it(self):
        adapter = GoAuctionAdapter(FakeFetcher(self.pages()))
        adapter.previous_lots = [self.stored("9001", "1")]
        adapter.list_lots(dict(HOUSE, max_new_lot_pages=1), {"id": "566", "url": SALE_URL})
        self.assertEqual(adapter.stats, {"new": 1, "reused": 1, "deferred": 1})

    def test_listing_estimate_is_picked_up(self):
        html = ('<ul><li><a href="/auction/lot/lot-3---a/?lot=9003&au=566">Lot 3 Boats</a>'
                '<span>Estimate £200 - £300</span></li><li><a href="/auction/lot/lot-4---b/?lot=9004&au=566">Lot 4 Hills</a>'
                '<span>Estimate £5</span></li></ul>')
        lots, _ = GoAuctionAdapter(None).parse_sale_page(html, SALE_URL, "566")
        self.assertEqual(lots[0]["estimate_text"], "£200 - £300")
        self.assertEqual(lots[1]["estimate_text"], "£5")

    def test_registered(self):
        self.assertIs(get_adapter("goauction"), GoAuctionAdapter)


if __name__ == "__main__":
    unittest.main()
