"""Tests for the Lawrences adapter. Calendar and lot-page tests use trimmed copies of real pages
(fixtures/lawrences/). The catalogue (list of lots) page was never saved: those tests use a small SYNTHETIC page."""
import os
import unittest
from datetime import date

from collector.sources import get_adapter
from collector.sources.lawrences import LawrencesAdapter, tidy_caps
from collector.tagger import NotArt, tag
from collector.tests.fakes import FakeFetcher
from collector.validate import validate_lot

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "lawrences")
CAL = "https://auctions.lawrences.co.uk/en/calendar"
TODAY = date(2026, 11, 25)
HOUSE = {"id": "lawrences", "name": "Lawrences", "website": "https://www.lawrences.co.uk", "crawl_delay": 3,
         "content_policy": "full"}
LOT27 = "https://www.lawrences.co.uk/sales/fine-art-sales/fs190721/view-lot/27/"
LOT1194 = "https://www.lawrences.co.uk/sales/fine-art-sales/fs170119/view-lot/1194/"


def fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


def adapter(pages=None):
    a = LawrencesAdapter(FakeFetcher(pages))
    a.today_override = TODAY
    return a


class CalendarTests(unittest.TestCase):  # REAL page
    def test_registered(self):
        self.assertIs(get_adapter("lawrences"), LawrencesAdapter)

    def test_sales_with_dates_and_multi_day_merge(self):
        sales = adapter().parse_calendar(fixture("calendar.html"), CAL)
        got = {s["title"]: (s["date"], s["end_date"]) for s in sales}
        self.assertEqual(got, {
            "A Large Private Collection of Trains": ("2026-12-10", None),
            "Winter 20th Century Art & Design Sale": ("2026-12-11", None),
            "Winter Fine Art": ("2027-02-09", "2027-02-10"),        # two boxes (Tue 9 + Wed 10 Feb) = one sale
            "Summer Fine Art Sale": ("2027-06-15", "2027-06-16"),
        })

    def test_year_is_the_one_whose_weekday_matches(self):
        self.assertEqual(adapter()._resolve_day("Friday", 11, "December"), date(2026, 12, 11))
        self.assertEqual(adapter()._resolve_day("Tuesday", 9, "February"), date(2027, 2, 9))
        self.assertIsNone(adapter()._resolve_day("Monday", 11, "December"))  # no such weekday in range

    def test_event_link_only_when_the_page_exists(self):
        sales = {s["title"]: s for s in adapter().parse_calendar(fixture("calendar.html"), CAL)}
        self.assertEqual(sales["A Large Private Collection of Trains"]["url"],
                         "https://auctions.lawrences.co.uk/en/events/1342-a-large-private-collection-of-trains")
        self.assertIsNone(sales["Winter Fine Art"]["url"])

    def test_list_sales_keeps_art_sales_only(self):
        sales = adapter({CAL: fixture("calendar.html")}).list_sales(dict(HOUSE, calendar_urls=[CAL]))
        self.assertEqual([(s["id"], s["title"], s["date"], s["end_date"]) for s in sales], [
            ("fs111226", "Winter 20th Century Art & Design Sale", "2026-12-11", None),
            ("fs090227", "Winter Fine Art", "2027-02-09", "2027-02-10"),
            ("fs150627", "Summer Fine Art Sale", "2027-06-15", "2027-06-16")])


class LotPageTests(unittest.TestCase):  # REAL pages
    def test_artist_lot(self):
        raw = adapter().parse_lot(fixture("lot_fs190721_27.html"), LOT27)
        self.assertEqual((raw["lot_number"], raw["artist_text"], raw["title"], raw["estimate_text"], raw["image_url"],
                          raw["sale_date"]),
                         ("27", "DAME MAGDALENE ODUNDO (BORN 1950)", "Terracotta Vessel, 1985", "£5000 - £7000",
                          "https://dp0wuijufr9x2.cloudfront.net/law/FS190721/27.jpg?v=2", "2021-07-19"))
        self.assertIn("a large coil built terracotta vessel", raw["description"])

    def test_headline_on_its_own_line(self):
        raw = adapter().parse_lot(fixture("lot_fs170119_1194.html"), LOT1194)
        self.assertEqual((raw["lot_number"], raw["title"], raw["estimate_text"]),
                         ("1194", "A Victorian Diamond Necklace, Converting to a Tiara", "£10000 - £15000"))
        self.assertNotIn("artist_text", raw)
        self.assertEqual(raw["image_url"], "https://dp0wuijufr9x2.cloudfront.net/law/FS170119/1194.jpg?v=2")

    def test_tags_into_a_valid_lot_and_jewellery_is_skipped(self):
        sale = {"id": "fs190721", "title": "19th/20th Century & Ceramics", "date": "2026-12-11", "end_date": None}
        lot = tag(adapter().parse_lot(fixture("lot_fs190721_27.html"), LOT27), HOUSE, sale)
        self.assertEqual((lot["id"], lot["artist"], lot["artist_dates"], lot["estimate_low"], lot["estimate_high"]),
                         ("lawrences-fs190721-27", "Magdalene Odundo", "b.1950", 5000, 7000))
        self.assertEqual(validate_lot(lot), [])
        with self.assertRaises(NotArt):
            tag(adapter().parse_lot(fixture("lot_fs170119_1194.html"), LOT1194), HOUSE, sale)

    def test_tidy_caps_only_changes_shouted_text(self):
        self.assertEqual(tidy_caps("TERRACOTTA VESSEL, 1985"), "Terracotta Vessel, 1985")
        self.assertEqual(tidy_caps("Harbour at St Ives"), "Harbour at St Ives")


BASE = "https://www.lawrences.co.uk/sales/fine-art-sales/"


def catalogue(*lots):
    """SYNTHETIC catalogue page: one div per lot (number, SHOUTED title, estimate) plus a paging link."""
    cards = "".join(f'<div class="lot"><a href="/sales/fine-art-sales/fs090227/view-lot/{n}/"><img src="/i.jpg"></a>'
                    f"<h4>Lot {n}</h4><p>{t}</p><p>£{e}</p></div>" for n, t, e in lots)
    return f'<html><body>{cards}<a href="?page=2">2</a></body></html>'


class LotsTests(unittest.TestCase):  # SYNTHETIC catalogue; lot pages are the real ones
    sale = {"id": "fs090227", "title": "Winter Fine Art", "date": "2026-12-11", "end_date": None, "days": ["2026-12-11"]}

    def pages(self):
        url = BASE + "fs111226/"
        a, b = BASE + "fs111226/view-lot/27/", BASE + "fs111226/view-lot/28/"
        return {url: catalogue((27, "DAME MAGDALENE ODUNDO (BORN 1950) - TERRACOTTA VESSEL, 1985", "5000 - £7000")).replace("fs090227", "fs111226"),
                url + "?page=2": "<html></html>",
                a: fixture("lot_fs190721_27.html")}

    def test_listing_reader(self):
        refs, pages = adapter().parse_listing(self.pages()[BASE + "fs111226/"], BASE + "fs111226/")
        self.assertEqual([(r["id"], r["lot_number"], r["title"], r["estimate_text"]) for r in refs],
                         [("fs111226-27", "27", "Dame Magdalene Odundo (Born 1950) - Terracotta Vessel, 1985", "£5000 - £7000")])
        self.assertEqual(pages, [BASE + "fs111226/?page=2"])

    def test_lots_come_from_the_catalogue_of_each_day_and_new_lots_are_read(self):
        fetcher = FakeFetcher(self.pages())
        a = LawrencesAdapter(fetcher)
        a.today_override = TODAY
        lots = a.list_lots(HOUSE, dict(self.sale, id="fs111226"))
        self.assertEqual([(l["lot_number"], l["title"]) for l in lots], [("27", "Terracotta Vessel, 1985")])
        self.assertEqual(a.stats["new"], 1)

    def test_known_lot_is_reused_without_a_request(self):
        fetcher = FakeFetcher(self.pages())
        a = LawrencesAdapter(fetcher)
        a.today_override = TODAY
        a.previous_lots = [{"lot_url": BASE + "fs111226/view-lot/27/", "lot_number": "27", "title": "Terracotta Vessel, 1985"}]
        lots = a.list_lots(HOUSE, dict(self.sale, id="fs111226"))
        self.assertNotIn(BASE + "fs111226/view-lot/27/", fetcher.calls)
        self.assertIn("_stored", lots[0])

    def test_sale_far_ahead_is_not_looked_for_yet(self):
        fetcher = FakeFetcher({})
        a = LawrencesAdapter(fetcher)
        a.today_override = TODAY
        far = {"id": "fs150627", "title": "Summer Fine Art Sale", "date": "2027-06-15", "end_date": None, "days": ["2027-06-15"]}
        self.assertEqual(a.list_lots(HOUSE, far), [])
        self.assertEqual(fetcher.calls, [])

    def test_catalogue_not_online_gives_no_lots_and_no_crash(self):
        a = adapter({})
        self.assertEqual(a.list_lots(HOUSE, dict(self.sale, id="fs111226")), [])


if __name__ == "__main__":
    unittest.main()
