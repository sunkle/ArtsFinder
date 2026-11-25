"""Tests for the Rogers Jones adapter. The sales list uses a trimmed copy of the real forthcoming-sales page
(fixtures/rogersjones/). The catalogue and lot pages of the bidding site were never saved: those tests use small
SYNTHETIC pages."""
import os
import unittest

from collector.sources import get_adapter
from collector.sources.rogersjones import RogersJonesAdapter
from collector.tagger import tag
from collector.tests.fakes import FakeFetcher
from collector.validate import validate_lot

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "rogersjones")
CAL = "https://www.rogersjones.co.uk/en/forthcoming-sales"
CATALOGUE = "https://auctions.rogersjones.co.uk/auctions/7713/rogers10663"
HOUSE = {"id": "rogersjones", "name": "Rogers Jones", "website": "https://www.rogersjones.co.uk", "crawl_delay": 3,
         "content_policy": "full", "sale_include_extra": "monthly|welsh|charity"}
U1 = "5b14b1c8-c71f-4a55-a620-ad5000ef157a"  # the lot-details id seen on the real Welsh Sale page
U2 = "0f9d4b1e-6c1a-4d0e-9a35-5d1d6a2f7c11"


def fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


class CalendarTests(unittest.TestCase):  # REAL page
    def setUp(self):
        self.all = RogersJonesAdapter(None).parse_calendar(fixture("forthcoming_sales.html"), CAL)
        self.sales = {s["title"]: s for s in self.all if s["title"] != "Chester Monthly" or s["date"] == "2026-12-01"}

    def test_registered(self):
        self.assertIs(get_adapter("rogersjones"), RogersJonesAdapter)

    def test_nine_sales_with_dates(self):
        self.assertEqual(len(self.all), 9)
        self.assertEqual(self.sales["Chester Monthly"]["date"], "2026-12-01")
        self.assertEqual(self.sales["City Hospice Charity Auction"]["date"], "2026-12-09")
        self.assertEqual(self.sales["The Club House"]["date"], "2027-03-04")

    def test_timed_sale_end_date_is_its_date(self):
        self.assertEqual(self.sales["Luxury Reload"]["date"], "2026-11-24")

    def test_catalogue_link_only_for_sales_with_browse_and_bid(self):
        chester = self.sales["Chester Monthly"]
        self.assertEqual((chester["id"], chester["url"]), ("rogers10663", CATALOGUE))
        self.assertEqual(chester["page"], "https://www.rogersjones.co.uk/en/sales/2026/12/1/chester-monthly")
        self.assertIsNone(self.sales["City Hospice Charity Auction"]["url"])
        self.assertIsNone(self.sales["Luxury Reload"]["url"])  # only a "Results" button: finished

    def test_far_ahead_label_is_removed(self):
        self.assertEqual(self.sales["The Welsh Sale"]["date"], "2027-04-18")
        self.assertNotIn("Further ahead: The Welsh Sale", self.sales)

    def test_list_sales_keeps_art_and_monthly_sales(self):
        sales = RogersJonesAdapter(FakeFetcher({CAL: fixture("forthcoming_sales.html")})).list_sales(dict(HOUSE, calendar_urls=[CAL]))
        self.assertEqual([(s["title"], s["date"]) for s in sales], [
            ("Chester Monthly", "2026-12-01"), ("City Hospice Charity Auction", "2026-12-09"),
            ("Colwyn Bay Monthly", "2027-01-12"), ("Cardiff Monthly", "2027-01-19"),
            ("Chester Monthly", "2027-01-26"), ("The Welsh Sale", "2027-04-18")])


def catalogue_page(*lots, more=""):
    """SYNTHETIC catalogue page: one div per lot."""
    cards = "".join(f'<div class="lot"><a href="/auctions/7713/rogers10663/lot-details/{u}"><img src="/i.jpg"></a>'
                    f"<p>Lot {n}</p><h3>{t}</h3><p>Estimate £{e}</p></div>" for u, n, t, e in lots)
    return f"<html><body>{cards}{more}</body></html>"


def lot_page(artist, title, medium, est):
    return (f"<html><head><title>{title} | Rogers Jones</title></head><body><h1>{title}</h1><p>Artist: {artist}</p><p>Medium: {medium}</p>"
            f"<p>Estimate: {est}</p></body></html>")


class LotsTests(unittest.TestCase):  # SYNTHETIC
    sale = {"id": "rogers10663", "title": "Chester Monthly", "date": "2026-12-01", "end_date": None, "url": CATALOGUE}
    L1 = f"https://auctions.rogersjones.co.uk/auctions/7713/rogers10663/lot-details/{U1}"
    L2 = f"https://auctions.rogersjones.co.uk/auctions/7713/rogers10663/lot-details/{U2}"

    def pages(self):
        return {CATALOGUE: catalogue_page((U1, 101, "Sir Kyffin Williams RA (1918-2006), Anglesey Landscape", "5,000 - £8,000"),
                                          more='<a href="?page=2">2</a>'),
                CATALOGUE + "?page=2": catalogue_page((U2, 102, "Donald McIntyre (1923-2009), Boats", "2,000 - £3,000")),
                self.L1: lot_page("Sir Kyffin Williams RA (1918-2006)", "Anglesey Landscape", "Oil on canvas", "£5,000 - £8,000"),
                self.L2: lot_page("Donald McIntyre (1923-2009)", "Boats", "Acrylic on board", "£2,000 - £3,000")}

    def test_listing_reader(self):
        refs, pages = RogersJonesAdapter(None).parse_listing(self.pages()[CATALOGUE], CATALOGUE)
        self.assertEqual([(r["id"], r["lot_number"], r["estimate_text"]) for r in refs], [(U1, "101", "£5,000 - £8,000")])
        self.assertEqual(refs[0]["url"], self.L1)
        self.assertEqual(pages, [CATALOGUE + "?page=2"])

    def test_pages_are_followed_and_lots_read(self):
        fetcher = FakeFetcher(self.pages())
        a = RogersJonesAdapter(fetcher)
        lots = a.list_lots(HOUSE, self.sale)
        self.assertEqual([l["lot_number"] for l in lots], ["101", "102"])
        self.assertEqual(a.stats["new"], 2)

    def test_raw_lot_tags_into_a_valid_lot(self):
        lot = tag(RogersJonesAdapter(FakeFetcher(self.pages())).list_lots(HOUSE, self.sale)[0], HOUSE, self.sale)
        self.assertEqual((lot["id"], lot["artist"], lot["medium"], lot["estimate_low"], lot["estimate_high"]),
                         ("rogersjones-rogers10663-101", "Kyffin Williams", "Oil", 5000, 8000))
        self.assertEqual(validate_lot(lot), [])

    def test_known_lots_are_reused(self):
        fetcher = FakeFetcher(self.pages())
        a = RogersJonesAdapter(fetcher)
        a.previous_lots = [{"lot_url": self.L1, "lot_number": "101", "title": "Anglesey Landscape"}]
        a.list_lots(HOUSE, self.sale)
        self.assertNotIn(self.L1, fetcher.calls)
        self.assertIn(self.L2, fetcher.calls)

    def test_sale_without_catalogue_has_no_lots(self):
        self.assertEqual(RogersJonesAdapter(FakeFetcher()).list_lots(HOUSE, dict(self.sale, url=None)), [])


if __name__ == "__main__":
    unittest.main()
