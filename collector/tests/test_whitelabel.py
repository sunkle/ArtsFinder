"""Tests for the white-label catalogue adapter, using trimmed copies of real pages (fixtures/whitelabel/).
Every expected value below was read off the real page."""
import os
import unittest

from collector import run
from collector.fetcher import FetchError
from collector.sources import get_adapter
from collector.sources.whitelabel import WhiteLabelAdapter
from collector.tagger import NotArt, tag
from collector.validate import validate_lot

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "whitelabel")
TODAY = "2026-11-25"


def fixture(name):
    with open(os.path.join(FIX, name + ".html"), encoding="utf-8") as f:
        return f.read()


class FakeFetcher:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def get(self, url, crawl_delay=0):
        self.calls.append(url)
        if url not in self.pages:
            raise FetchError("HTTP 404 for " + url)
        return self.pages[url]


def adapter():
    return WhiteLabelAdapter(None)


def sales_of(calendar, base, house=None):
    house = dict({"id": "x", "website": base, "calendar_urls": [base]}, **(house or {}))
    return WhiteLabelAdapter(FakeFetcher({base: fixture(calendar)})).list_sales(house)


def short(sales):
    return [(s["title"], s["date"], s["end_date"], len(s["urls"])) for s in sales]


class RegistryTests(unittest.TestCase):
    def test_registered(self):
        self.assertIs(get_adapter("whitelabel"), WhiteLabelAdapter)


class CalendarTests(unittest.TestCase):
    def test_gardiner_cards_and_multi_day_sale(self):
        cards = adapter().parse_calendar(fixture("calendar_gardiner"), "https://auctions.gardinerhoulgate.co.uk/")
        self.assertEqual(len(cards), 9)  # 9 "Upcoming Auctions" on the real page, one card per sale day
        first = cards[1]
        self.assertEqual((first["title"], first["date"], first["auction"], first["day"]),
                         ("Antiques, Silver, Paintings & Works of Art", "2026-11-26",
                          "a4d31ec5cbfc79aa9ce2cbed987c6b56", "63b778f7668dabe928d3800924a99077"))
        self.assertEqual(first["url"], "https://auctions.gardinerhoulgate.co.uk/catalogue/a4d31ec5cbfc79aa9ce2cbed987c6b56/"
                                       "63b778f7668dabe928d3800924a99077/antiques-silver-paintings-works-of-art/")
        sales = {s["title"]: s for s in WhiteLabelAdapter.group_sales(cards)}
        guitar = sales["The Guitar Auction - Four Day Sale - Including Memorabilia & Audio Equipment"]
        self.assertEqual((guitar["date"], guitar["end_date"], len(guitar["urls"]), guitar["id"]),
                         ("2026-12-08", "2026-12-11", 4, "6819b37ceb"))
        self.assertEqual(len(sales), 6)

    def test_default_filter_keeps_art_sales_only(self):
        # (the Guitar Auction passes the default filter: its summary line says "Artist Associated Guitars";
        # a house that does not want it says so with sale_exclude)
        sales = sales_of("calendar_gardiner", "https://auctions.gardinerhoulgate.co.uk/", {"sale_exclude": "guitar"})
        self.assertEqual(short(sales), [("Antiques, Silver, Paintings & Works of Art", "2026-11-26", None, 1)])

    def test_hansons_filter_uses_title_and_summary_line_per_day(self):
        sales = sales_of("calendar_hansons", "https://auctions.hansonsauctioneers.co.uk/auctions/",
                         {"sale_exclude": r"\bcomedy\b"})
        got = {s["title"]: s for s in sales}
        # "Pre Christmas Sale" has two days on one auction id: only the 28 Nov day (summary "fine arts ...") is art
        pre = got["Pre Christmas Sale"]
        self.assertEqual((pre["date"], pre["end_date"], len(pre["urls"])), ("2026-11-28", None, 1))
        derby = next(s for s in sales if s["title"].startswith("Two Day Christmas Derbyshire Fine Art Sale"))
        self.assertEqual((derby["date"], derby["end_date"], len(derby["urls"])), ("2026-12-03", "2026-12-04", 2))
        self.assertTrue(any(s["title"].startswith("Holloways Christmas Jewellery, Silver, Fine Arts") for s in sales))
        timed = next(s for s in sales if s["title"].startswith("Hertfordshire - Royston, a Timed Sale"))
        self.assertEqual(timed["date"], "2027-02-05")  # card says "Ends Fri 5th February 2027"
        titles = " | ".join(s["title"] for s in sales)
        for dropped in ("Comedy", "Historica", "Medals", "London November", "Library", "Cornwall", "Fine Jewellery, Watches"):
            self.assertNotIn(dropped, titles)
        self.assertEqual(len(sales), 4)

    def test_mellors_main_site_calendar_has_a_different_layout(self):
        cards = adapter().parse_calendar(fixture("calendar_mellors_main"), "https://mellorsandkirk.com/auction-calendar/")
        self.assertEqual([(c["title"], c["date"]) for c in cards],
                         [("Fine Art, Antiques & Collectors Sale", "2026-12-01"),
                          ("Fine Art, Antiques & Collectors Sale", "2026-12-02")])
        self.assertTrue(cards[0]["summary"].startswith("Day 1 of our 2 day Auction [Lots 1-491]"))
        sale, = WhiteLabelAdapter.group_sales(cards)
        self.assertEqual((sale["id"], sale["date"], sale["end_date"]), ("2b61520a6e", "2026-12-01", "2026-12-02"))
        self.assertEqual([u.split("/")[5][:6] for u in sale["urls"]], ["4f177e", "6d0808"])

    def test_trevanion_two_day_sale(self):
        sales = sales_of("calendar_trevanion", "https://auctions.trevanion.com/auctions/")
        self.assertEqual(short(sales), [("The December Fine Art & Antiques Auction", "2026-12-02", "2026-12-03", 2)])

    def test_unreadable_calendar_gives_no_sales_and_no_crash(self):
        house = {"id": "x", "website": "https://x.test", "calendar_urls": ["https://x.test/gone"]}
        self.assertEqual(WhiteLabelAdapter(FakeFetcher({})).list_sales(house), [])


class SalePageTests(unittest.TestCase):
    def test_gardiner_listing(self):
        refs, pages = adapter().parse_sale_page(fixture("sale_gardiner_p1"), "https://x.test/catalogue/a/b/c/")
        self.assertEqual(pages, 6)  # "of 6" pages of 60 lots (353 lots)
        self.assertEqual([(r["lot_number"], r["estimate_text"]) for r in refs],
                         [("601", "£450 - £650"), ("602", "£600 - £800"), ("603", "£250 - £350")])
        self.assertEqual(refs[0]["title"], "Paul Storr: George III silver twin-handl...")
        self.assertEqual(refs[0]["id"], "d9e49785466bce22190e0ba315d87f3f")
        self.assertTrue(refs[0]["url"].endswith("/antiques-silver-paintings-works-of-art-lot-601/"))

    def test_mellors_listing_drops_the_resale_rights_line(self):
        refs, pages = adapter().parse_sale_page(fixture("sale_mellors_day2"), "https://x.test/catalogue/a/b/c/")
        self.assertEqual([r["lot_number"] for r in refs], ["500", "501", "502", "503"])
        self.assertEqual(refs[0]["title"], "†Derek Carruthers (1935–2021) - Continuu...")
        self.assertEqual([r["estimate_text"] for r in refs], ["£100 - £150", "£100 - £200", "£100 - £200", "£100 - £150"])

    def test_sold_lots_show_hammer_not_estimate(self):
        refs, _ = adapter().parse_sale_page(fixture("sale_trevanion_past"), "https://x.test/catalogue/a/b/c/")
        self.assertEqual([r["lot_number"] for r in refs], ["1", "2"])
        self.assertNotIn("estimate_text", refs[0])

    def test_catalogue_without_lots_yet(self):
        self.assertEqual(adapter().parse_sale_page(fixture("sale_peterfrancis_empty"), "https://x.test/"), ([], 1))

    HANSONS_SALE = ("https://auctions.hansonsauctioneers.co.uk/catalogue/b15bae525138a9ecef8028f98e99b26e/"
                    "a4ea5662dfdd714dd24e999c0ecc040d/pre-christmas-sale/")

    def test_hansons_real_sale_page_has_no_lots_in_the_html(self):
        """REAL page (diagnose 25 Nov 2026): the lot list is an Alpine.js template filled by auction_catalogue.js;
        the 'Catalogue coming soon...' text sits inside an unrendered <template> and says nothing."""
        html = fixture("sale_hansons_pre_christmas")
        self.assertEqual(adapter().parse_sale_page(html, self.HANSONS_SALE), ([], 1))
        self.assertIn("lots loaded by script", WhiteLabelAdapter.no_lots_reason(html))
        self.assertNotIn("not yet online", WhiteLabelAdapter.no_lots_reason(html))

    def test_empty_sale_page_logs_the_reason_once(self):
        house = {"id": "hansons", "crawl_delay": 3}
        a = WhiteLabelAdapter(FakeFetcher({self.HANSONS_SALE: fixture("sale_hansons_pre_christmas")}))
        with self.assertLogs("collector.whitelabel", "WARNING") as logs:
            self.assertEqual(a.lot_refs(house, self.HANSONS_SALE), [])
        self.assertEqual(len(logs.output), 1)
        self.assertIn("lots loaded by script", logs.output[0])

    def test_reason_when_the_page_says_the_catalogue_is_coming_soon(self):
        html = "<html><body><p>Catalogue coming soon...</p></body></html>"
        self.assertEqual(WhiteLabelAdapter.no_lots_reason(html), "catalogue not yet online")
        self.assertIn("not recognised", WhiteLabelAdapter.no_lots_reason("<html><body>hello</body></html>"))

    def test_page_url(self):
        self.assertEqual(WhiteLabelAdapter.page_url("https://x.test/catalogue/a/b/c/", 1), "https://x.test/catalogue/a/b/c/")
        self.assertEqual(WhiteLabelAdapter.page_url("https://x.test/catalogue/a/b/c/", 3), "https://x.test/catalogue/a/b/c/?currentPageNo=3")


class LotPageTests(unittest.TestCase):
    URL = "https://auctions.example.test/catalogue/lot/{}/{}/sale-lot-{}/"

    def lot(self, name, number="7"):
        return adapter().parse_lot(fixture("lot_" + name), self.URL.format("a" * 32, "b" * 32, number))

    def test_gardiner_lot_601(self):
        raw = self.lot("gardiner_601", "601")
        self.assertEqual((raw["lot_number"], raw["title"], raw["artist_text"], raw["estimate_text"], raw["sale_date"]),
                         ("601", "George III silver twin-handled cup with a gilded interior", "Paul Storr",
                          "£450 - £650", "2026-11-26"))
        self.assertIn("maker Paul Storr, London 1816, 4.4\" high, 298.9gm", raw["description"])
        self.assertEqual(raw["image_url"], "https://content.easyliveauction.com/auctions/images_lots/"
                                           "0EC4C634B6A8090C9EE1DC55C2B3AACC_gar02/1100464070_PREVIEW.JPG")  # not the og:image logo

    def test_mellors_painting_through_the_tagger(self):
        raw = self.lot("mellors_222", "222")
        self.assertEqual((raw["artist_text"], raw["title"], raw["sale_date"]),
                         ("British School", "Portrait of an Indian Dignitary", "2026-11-03"))
        self.assertNotIn("estimate_text", raw)  # sale over: the page shows the hammer price, not an estimate
        lot = tag(raw, {"id": "mellorskirk"}, {"id": "2b61520a6e", "title": "Fine Art", "date": "2026-11-03"})
        self.assertEqual((lot["type"], lot["medium"], lot["dimensions"], lot["title"]),
                         ("Painting", "Oil", "24 x 20cm", "Portrait of an Indian Dignitary"))
        self.assertEqual(validate_lot(lot), [])

    def test_no_bold_lead_in_uses_first_clause_of_description(self):
        raw = self.lot("mellors_101", "101")
        self.assertEqual(raw["title"], "A Louis XVI ormolu cartel clock, J Baptiste Baillon")
        self.assertNotIn("artist_text", raw)

    def test_lot_number_comes_from_the_url(self):
        self.assertEqual(adapter().parse_lot(fixture("lot_peterfrancis_609"), self.URL.format("a" * 32, "b" * 32, "609a"))["lot_number"], "609a")
        raw = adapter().parse_lot(fixture("lot_peterfrancis_609"), "https://x.test/odd/")
        self.assertEqual(raw["lot_number"], "609")  # fallback: the "Lot 609" heading

    def test_other_houses(self):
        raw = self.lot("peterfrancis_609", "609")
        self.assertEqual((raw["title"], raw["sale_date"]), ("Art Deco design veneered walnut Bullseye cabinet with Bakelite handles", "2026-04-01"))
        raw = self.lot("fieldings_684", "684")
        self.assertEqual((raw["title"], raw["sale_date"]), ("A Macfarlane Lang advertising 'Engine' biscuit tin", "2025-11-13"))
        raw = self.lot("trevanion_1", "1")
        self.assertEqual(raw["sale_date"], "2023-02-15")

    def test_artist_split(self):
        split = WhiteLabelAdapter._split_artist
        self.assertEqual(split("†Derek Carruthers (1935–2021) - Continuum"), ("Derek Carruthers (1935–2021)", "Continuum"))
        self.assertEqual(split("Attributed to John Smith - Harbour at dusk"), ("Attributed to John Smith", "Harbour at dusk"))
        self.assertEqual(split("A pair of silver candlesticks - George III"), (None, "A pair of silver candlesticks - George III"))
        self.assertEqual(split("Victorian oil painting of a cottage"), (None, "Victorian oil painting of a cottage"))


class ListLotsTests(unittest.TestCase):
    DAY = "https://auctions.mellorsandkirk.com/catalogue/2b61520a6ee59c76ed4a44b187267890/6d0808242845d9a724247bb4d43cabe3/fine-art-antiques-collectors-sale/"
    HOUSE = {"id": "mellorskirk", "name": "Mellors & Kirk", "website": "https://mellorsandkirk.com", "crawl_delay": 3}
    SALE = {"id": "2b61520a6e", "title": "Fine Art", "date": "2026-12-01", "end_date": "2026-12-02", "url": DAY, "urls": [DAY]}

    def pages(self):
        page1 = fixture("sale_mellors_day2")
        page2 = page1.replace("a98a3b41765e85c955131353b6700fce", "f" * 32).replace("lot-500/", "lot-510/")
        return {self.DAY: page1, self.DAY + "?currentPageNo=2": page2, self.DAY + "?currentPageNo=3": page2}

    def test_pages_are_followed_until_nothing_new(self):
        fetcher = FakeFetcher(self.pages())
        refs = WhiteLabelAdapter(fetcher).lot_refs(self.HOUSE, self.DAY)
        self.assertEqual([r["lot_number"] for r in refs], ["500", "501", "502", "503", "510"])
        self.assertEqual(fetcher.calls, [self.DAY, self.DAY + "?currentPageNo=2", self.DAY + "?currentPageNo=3"])

    def test_known_lots_are_reused_and_new_ones_are_capped(self):
        fetcher = FakeFetcher(dict(self.pages(), **{
            "https://auctions.mellorsandkirk.com/catalogue/lot/0b643c70e7a7d2bdb3f768efeeafc0a9/6d0808242845d9a724247bb4d43cabe3/fine-art-antiques-collectors-sale-lot-501/": fixture("lot_mellors_222")}))
        stored = {"lot_number": "500", "title": "Continuum", "lot_url": "https://auctions.mellorsandkirk.com/catalogue/lot/"
                  "A98A3B41765E85C955131353B6700FCE/6d0808242845d9a724247bb4d43cabe3/fine-art-antiques-collectors-sale-lot-500/"}
        ad = WhiteLabelAdapter(fetcher)
        ad.previous_lots = [stored]
        lots = ad.list_lots(dict(self.HOUSE, max_new_lot_pages=1), self.SALE)
        self.assertEqual((ad.stats["reused"], ad.stats["new"], ad.stats["deferred"]), (1, 1, 3))
        self.assertIs(lots[0]["_stored"], stored)
        self.assertEqual(lots[0]["estimate_text"], "£100 - £150")
        self.assertEqual(lots[1]["title"], "Portrait of an Indian Dignitary")
        self.assertEqual(len([c for c in fetcher.calls if "/catalogue/lot/" in c]), 1)

    def test_lots_whose_listing_title_says_jewellery_cost_no_request(self):
        day1 = "https://auctions.mellorsandkirk.com/catalogue/2b61520a6ee59c76ed4a44b187267890/4f177e56044f68c0321c00430764407b/fine-art-antiques-collectors-sale/"
        fetcher = FakeFetcher({day1: fixture("sale_mellors_day1"), day1 + "?currentPageNo=2": fixture("sale_mellors_day1")})
        lots = WhiteLabelAdapter(fetcher).list_lots(self.HOUSE, dict(self.SALE, url=day1, urls=[day1]))
        self.assertEqual(lots, [])  # lots 1-3 are rings
        self.assertFalse([c for c in fetcher.calls if "/catalogue/lot/" in c])

    def test_end_to_end_with_content_policy(self):
        calendar = "https://mellorsandkirk.com/auction-calendar/"
        day1 = self.DAY.replace("6d0808242845d9a724247bb4d43cabe3", "4f177e56044f68c0321c00430764407b")
        pages = {calendar: fixture("calendar_mellors_main"), day1: fixture("sale_mellors_day1"),
                 day1 + "?currentPageNo=2": fixture("sale_mellors_day1"), **self.pages()}
        lot_url = "https://auctions.mellorsandkirk.com/catalogue/lot/a98a3b41765e85c955131353b6700fce/6d0808242845d9a724247bb4d43cabe3/fine-art-antiques-collectors-sale-lot-500/"
        pages[lot_url] = fixture("lot_mellors_222")
        for policy, image in (("full", True), ("text_only", False)):
            with self.subTest(policy=policy):
                house = dict(self.HOUSE, adapter="whitelabel", calendar_urls=[calendar], content_policy=policy,
                             max_new_lot_pages=1)
                lots, rejected = run.collect_house(house, FakeFetcher(pages), TODAY, "2026-11-25T02:00:00Z")
                self.assertEqual(len(lots), 1)
                lot = lots[0]
                self.assertEqual((lot["id"], lot["sale_date"], lot["sale_end_date"], lot["estimate_low"], lot["estimate_high"]),
                                 ("mellorskirk-2b61520a6e-500", "2026-12-01", "2026-12-02", 100, 150))
                self.assertEqual((lot["artist"], lot["type"]), (None, "Painting"))  # "British School" = anonymous
                self.assertEqual(lot["lot_url"], lot_url)
                self.assertEqual(bool(lot["image_url"]), image)
                self.assertIn("oil on card", lot["description"])


class HeadlineTests(unittest.TestCase):
    def test_no_split_at_abbreviations_or_initials(self):
        cases = [("The Beatles - Sgt. Peppers Lonely Hearts Club Band PCS 7027, a rare copy", "The Beatles - Sgt. Peppers Lonely Hearts Club Band PCS 7027"),
                 ("John Piper - St. Ives harbour at dusk. Signed", "John Piper - St. Ives harbour at dusk"),
                 ("Mr. Punch and Dr. Who figures, boxed", "Mr. Punch and Dr. Who figures"),
                 ("J. M. W. Turner - Venice sunset. Framed", "J. M. W. Turner - Venice sunset")]
        for text, want in cases:
            with self.subTest(text=text):
                self.assertEqual(WhiteLabelAdapter._headline(text), want)

    def test_real_sentence_ends_still_split(self):
        self.assertEqual(WhiteLabelAdapter._headline("Harbour at dusk. Oil on canvas, signed"), "Harbour at dusk")
        self.assertEqual(WhiteLabelAdapter._headline("Harbour at dusk, oil on canvas"), "Harbour at dusk")


if __name__ == "__main__":
    unittest.main()
