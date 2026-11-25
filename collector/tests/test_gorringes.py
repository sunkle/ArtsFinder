"""Tests for the Gorringe's adapter. The calendar and catalogue-search tests use trimmed copies of real pages
(fixtures/gorringes/); the lot listing and lot page were never saved, so those tests use small SYNTHETIC pages
built from real lot URLs in data/lots.json and are marked as such."""
import os
import re
import unittest

from collector.sources import get_adapter
from collector.sources.gorringes import GorringesAdapter
from collector.tagger import tag
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


def listing(*lots):
    """SYNTHETIC listing page: one div per lot with artist, title, estimate."""
    cards = "".join(f'<div class="lot"><a href="{u}"><img src="/thumb/{n}.jpg"></a><p>{a}</p><p>{t}</p><p>Estimate £{e}</p></div>'
                    for u, n, a, t, e in lots)
    return f"<html><body>{cards}</body></html>"


def lot_page(title, medium, est):
    """SYNTHETIC lot page in the generic label layout."""
    return (f"<html><head><title>{title} - Gorringe's</title></head><body><h1>{title}</h1>"
            f"<p>Medium: {medium}</p><p>Estimate: {est}</p><p>Dimensions: 25 x 19cm</p>"
            f'<img src="/full/814/90216814_Catalog_gp7gr94oiH.JPG"></body></html>')


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


class LotsTests(unittest.TestCase):  # SYNTHETIC listing and lot pages (unverified layouts)
    def pages(self):
        return {
            LIST_URL.format(1): listing((GRANT, 20, "Duncan Grant (1885-1978)", "Wrestlers", "1,000 - £1,500"),
                                        (SICKERT, 2, "Walter Richard Sickert (1860-1942)", "A head and shoulders portrait sketch of a woman", "300 - £500")),
            LIST_URL.format(2): listing((BEVAN, 6, "Robert Polhill Bevan (1865-1925)", "Cumberland Market", "300 - £500")),
            GRANT: lot_page("Wrestlers", "Pencil on paper", "£1,000 - £1,500"),
            SICKERT: lot_page("A head and shoulders portrait sketch of a woman", "Pencil on paper", "£300 - £500"),
            BEVAN: lot_page("Cumberland Market", "Soft pencil on paper", "£300 - £500"),
        }

    def sale(self):
        return {"id": "011226", "title": "Art & Design Post 1880", "date": "2026-12-01", "end_date": None,
                "url": "https://auction.gorringes.co.uk/auction-catalog/011226"}

    def test_listing_reader(self):
        refs, _ = GorringesAdapter(None).parse_listing(self.pages()[LIST_URL.format(1)], LIST_URL.format(1))
        self.assertEqual([(r["id"], r["lot_number"], r["estimate_text"]) for r in refs],
                         [("90216814", "20", "£1,000 - £1,500"), ("90206208", "2", "£300 - £500")])
        self.assertEqual(refs[0]["title"], "Wrestlers")

    def test_all_pages_are_read_and_stop_when_a_page_is_empty(self):
        fetcher = FakeFetcher(dict(self.pages(), **{LIST_URL.format(3): listing()}))
        lots = GorringesAdapter(fetcher).list_lots(HOUSE, self.sale())
        self.assertEqual([l["lot_number"] for l in lots], ["20", "2", "6"])
        self.assertEqual([u for u in fetcher.calls if "searchresults" in u], [LIST_URL.format(n) for n in (1, 2, 3)])

    def test_raw_lot_tags_into_a_valid_lot(self):
        lots = GorringesAdapter(FakeFetcher(self.pages())).list_lots(HOUSE, self.sale())
        lot = tag(lots[0], HOUSE, self.sale())
        self.assertEqual((lot["artist"], lot["artist_dates"], lot["title"], lot["type"], lot["estimate_low"],
                          lot["estimate_high"]), ("Duncan Grant", "1885-1978", "Wrestlers", "Work on paper", 1000, 1500))
        self.assertEqual(lot["id"], "gorringes-011226-20")
        self.assertEqual(validate_lot(lot), [])

    def test_known_lots_are_not_fetched_again(self):
        fetcher = FakeFetcher(self.pages())
        adapter = GorringesAdapter(fetcher)
        adapter.previous_lots = [{"lot_url": GRANT, "lot_number": "20", "title": "Wrestlers"}]
        lots = adapter.list_lots(HOUSE, self.sale())
        self.assertNotIn(GRANT, fetcher.calls)
        self.assertIn(SICKERT, fetcher.calls)
        self.assertEqual((adapter.stats["reused"], adapter.stats["new"]), (1, 2))
        self.assertIn("_stored", lots[0])

    def test_sale_without_catalogue_has_no_lots(self):
        self.assertEqual(GorringesAdapter(FakeFetcher()).list_lots(HOUSE, dict(self.sale(), url=None)), [])


if __name__ == "__main__":
    unittest.main()
