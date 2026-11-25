"""Tests for the Gorringe's adapter. Calendar, catalogue listing and lot page tests use trimmed copies of real
pages (fixtures/gorringes/, diagnose run of 25 Nov 2026); the listing is also checked against the 11 lots collected
by hand in data/lots.json. Only the second listing page is derived (the first page with other lot numbers)."""
import json
import os
import re
import unittest

from collector.sources import get_adapter
from collector.sources.gorringes import GorringesAdapter
from collector.tagger import parse_estimate, tag
from collector.tests.fakes import FakeFetcher
from collector.validate import validate_lot

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "gorringes")
CAL = "https://www.gorringes.co.uk/calendar"
HOUSE = {"id": "gorringes", "name": "Gorringe's", "website": "https://www.gorringes.co.uk", "crawl_delay": 10,
         "content_policy": "full"}


def fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


# --- the real lot URLs of lots.json (Gorringe's sale 011226) ---
def lot_url(slug, number, refno):
    return f"https://auction.gorringes.co.uk/auction-lot-detail/{slug}&salelot=011226{'+' * (6 - len(str(number)))}{number}+&refno={refno}"


GRANT = lot_url("Duncan-Grant,-1885-1978,-'Wrestlers'", 20, 90216814)
SICKERT = lot_url("Walter-Richard-Sickert,-1860-1942,-A-head-and-shoulders-port", 2, 90206208)
BEVAN = lot_url("Robert-Polhill-Bevan,-1865-1925,-'Cumberland-Market'", 6, 90206192)
LIST_URL = "https://auction.gorringes.co.uk/asp/searchresults.asp?st=D&sale_no=011226&pg={}"


class CalendarTests(unittest.TestCase):  # REAL pages
    def setUp(self):
        self.a = GorringesAdapter(None)
        self.p1 = self.a.parse_calendar(fixture("calendar_p1.html"), CAL)
        self.p2 = self.a.parse_calendar(fixture("calendar_p2.html"), CAL + "?page=1")

    def test_registered(self):
        self.assertIs(get_adapter("gorringes"), GorringesAdapter)

    def test_ten_cards_on_the_first_page_nine_on_the_second(self):
        self.assertEqual((len(self.p1), len(self.p2)), (10, 9))

    def test_art_and_design_sale(self):
        sale = self.p1[1]
        self.assertEqual((sale["id"], sale["title"], sale["date"], sale["end_date"], sale["url"]),
                         ("011226", "Art & Design Post 1880", "2026-12-01", None,
                          "https://auction.gorringes.co.uk/auction-catalog/011226"))

    def test_only_sales_with_a_catalogue_have_a_url(self):
        self.assertEqual([s["id"] for s in self.p1 if s["url"]], ["301126", "011226"])
        self.assertTrue(all(s["url"] is None for s in self.p2))

    def test_sale_without_catalogue_gets_ddmmyy_id(self):
        fine_art = next(s for s in self.p2 if s["title"] == "Fine Art & Interiors")
        self.assertEqual((fine_art["id"], fine_art["date"]), ("020327", "2027-03-02"))

    def test_catalogue_search_page_uses_the_same_sale_codes(self):
        html = fixture("cataloguesearch.html")
        for code in ("301126", "011226"):
            self.assertIn(f'<option value="{code} ">', html)
            self.assertIn(f"Sale {code}, ", html)

    def test_list_sales_follows_the_pager_and_keeps_art_sales_only(self):
        pages = {CAL: fixture("calendar_p1.html"), CAL + "?page=1": fixture("calendar_p2.html")}
        sales = GorringesAdapter(FakeFetcher(pages)).list_sales(dict(HOUSE, calendar_urls=[CAL]))
        self.assertEqual([(s["title"], s["date"]) for s in sales],
                         [("Art & Design Post 1880", "2026-12-01"), ("Fine Art & Interiors", "2027-03-02")])

    def test_multi_day_sale_end_date_from_the_calendar_json(self):
        # the real card says startDate == endDate; a two-day sale would carry a later endDate
        html = re.sub(r'("startDate":"2026-12-01",\s*)"endDate":"2026-12-01"', r'\1"endDate":"2026-12-02"',
                      fixture("calendar_p1.html"))
        sale = next(s for s in self.a.parse_calendar(html, CAL) if s["id"] == "011226")
        self.assertEqual((sale["date"], sale["end_date"]), ("2026-12-01", "2026-12-02"))


class LotUrlTests(unittest.TestCase):  # REAL lot URLs
    def test_lot_number_and_refno(self):
        self.assertEqual(GorringesAdapter._lot_no(GRANT), "20")
        self.assertEqual(GorringesAdapter._lot_no(SICKERT), "2")
        self.assertEqual(GorringesAdapter._refno(GRANT), "90216814")

    def test_artist_dates_and_title_start_from_the_slug(self):
        self.assertEqual(GorringesAdapter._slug(GRANT), ("Duncan Grant", "1885-1978", "Wrestlers"))
        self.assertEqual(GorringesAdapter._slug(SICKERT), ("Walter Richard Sickert", "1860-1942", "A head and shoulders port"))


class RealCatalogueFakeFetcher(FakeFetcher):
    """Serves the real lot page for every lot-detail URL (the other 39 lots are not saved)."""

    def get(self, url, crawl_delay=0):
        if "/auction-lot-detail/" in url:
            self.calls.append(url)
            return fixture("lot_011226_1.html")
        return super().get(url, crawl_delay)


SALE = {"id": "011226", "title": "Art & Design Post 1880", "date": "2026-12-01", "end_date": None,
        "url": "https://auction.gorringes.co.uk/auction-catalog/011226"}
LOT1 = lot_url("Th&233;odore-Rivi&232;re,-French-1857-1912,-An-elegant-you", 1, 90215475)


def stored_lots():
    """The 11 Gorringe's lots collected by hand earlier (data/lots.json, real data)."""
    path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "lots.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [l for l in (data["lots"] if isinstance(data, dict) else data) if l["house_id"] == "gorringes"]


class ListingTests(unittest.TestCase):  # REAL page: auction-catalog/011226 (page 1 of 29)
    def setUp(self):
        self.html = fixture("catalog_011226_p1.html")
        self.refs, _ = GorringesAdapter(None).parse_listing(self.html, SALE["url"])

    def test_twenty_lots_numbered_1_to_20(self):
        self.assertEqual([r["lot_number"] for r in self.refs], [str(n) for n in range(1, 21)])

    def test_first_lot(self):
        first = self.refs[0]
        self.assertEqual((first["id"], first["title"], first["estimate_text"]),
                         ("90215475", "Théodore Rivière, French 1857-1912, An elegan", "£400 - 600"))
        self.assertEqual(first["url"], LOT1)

    def test_title_is_the_card_text_not_a_button(self):
        self.assertTrue(self.refs[1]["title"].startswith("Walter Richard Sickert, 1860-1942"))
        self.assertFalse(any("Bid" in r["title"] for r in self.refs))

    def test_page_count_ignores_the_old_pager_in_a_comment(self):
        self.assertIn("Page 1 of 32", self.html)  # the page really holds both
        self.assertEqual(GorringesAdapter.page_count(self.html), 29)
        self.assertIsNone(GorringesAdapter.page_count("<p>no pager</p>"))

    def test_matches_the_eleven_lots_collected_by_hand(self):
        by_id = {r["id"]: r for r in self.refs}
        stored = stored_lots()
        self.assertEqual(len(stored), 11)
        for lot in stored:
            ref = by_id[GorringesAdapter._refno(lot["lot_url"])]
            self.assertEqual(ref["lot_number"], lot["lot_number"], lot["title"])
            self.assertEqual(ref["url"], lot["lot_url"], lot["title"])
            self.assertEqual(parse_estimate(ref["estimate_text"]), (lot["estimate_low"], lot["estimate_high"]), lot["title"])
            # the listing headline is cut at ~45 characters but names the artist (often with Sir / RA added)
            self.assertIn(lot["artist"].split()[-1], ref["title"], lot["title"])


class LotPageTests(unittest.TestCase):  # REAL page: lot 1, Théodore Rivière
    def setUp(self):
        self.raw = GorringesAdapter(None).parse_lot(fixture("lot_011226_1.html"), LOT1, HOUSE)

    def test_fields(self):
        self.assertEqual(self.raw, {
            "lot_url": LOT1, "lot_number": "1", "artist_text": "Théodore Rivière (French, 1857-1912)",
            "title": "An elegant young woman seated in an intimate boudoir or salon",
            "estimate_text": "£400-600", "medium_detail": "signed lower right, oil on canvas",
            "description": "signed lower right, oil on canvas, 61cm x 49cm",
            "image_url": "https://auction.gorringes.co.uk/full/475/90215475_Catalog_AMxk2KEpzp.JPG"})

    def test_tags_into_a_valid_lot(self):
        """This lot used to be rejected as 'not artwork (type Other, no artist dates)': nothing was read from the page."""
        lot = tag(self.raw, HOUSE, SALE, collected_at="2026-11-25T00:00:00Z")
        self.assertEqual((lot["artist"], lot["artist_dates"], lot["type"], lot["medium"], lot["estimate_low"],
                          lot["estimate_high"], lot["dimensions"]),
                         ("Théodore Rivière", "1857-1912", "Painting", "Oil", 400, 600, "61 x 49cm"))
        self.assertEqual(lot["id"], "gorringes-011226-1")
        self.assertEqual(validate_lot(lot), [])

    def test_lot_without_an_artist_line_starts_with_its_title(self):
        html = ('<div class="lot-container"><h2> Lot 5 , A walnut chest</h2>'
                '<p><b>A walnut chest of drawers,</b><br />18th century,<br />£100-200<br /></p></div>')
        raw = GorringesAdapter(None).parse_lot(html, lot_url("A-walnut-chest", 5, 1))
        self.assertEqual((raw["title"], raw.get("artist_text"), raw["estimate_text"], raw["lot_number"]),
                         ("A walnut chest of drawers", None, "£100-200", "5"))


class LotsTests(unittest.TestCase):  # real listing page + real lot page
    def pages(self):
        page1 = fixture("catalog_011226_p1.html")
        page2 = page1.replace("refno=9", "refno=8")  # a second page with other lots
        return {LIST_URL.format(1): page1, LIST_URL.format(2): page2}

    def test_every_page_is_read_until_one_fails_or_adds_nothing(self):
        fetcher = RealCatalogueFakeFetcher(self.pages())
        lots = GorringesAdapter(fetcher).list_lots(HOUSE, SALE)
        listing_calls = [u for u in fetcher.calls if "searchresults" in u]
        self.assertEqual(listing_calls[:3], [LIST_URL.format(n) for n in (1, 2, 3)])  # 29 pages queued from the pager
        self.assertEqual(len(lots), 40)
        self.assertEqual([l["lot_number"] for l in lots[:3]], ["1", "2", "3"])

    def test_known_lots_are_not_fetched_again(self):
        fetcher = RealCatalogueFakeFetcher(self.pages())
        adapter = GorringesAdapter(fetcher)
        adapter.previous_lots = [{"lot_url": LOT1, "lot_number": "1", "title": "An elegant young woman"}]
        lots = adapter.list_lots(HOUSE, SALE)
        self.assertNotIn(LOT1, fetcher.calls)
        self.assertEqual((adapter.stats["reused"], adapter.stats["new"]), (1, 39))
        self.assertIn("_stored", lots[0])

    def test_sale_without_catalogue_has_no_lots(self):
        self.assertEqual(GorringesAdapter(FakeFetcher()).list_lots(HOUSE, dict(SALE, url=None)), [])


if __name__ == "__main__":
    unittest.main()
