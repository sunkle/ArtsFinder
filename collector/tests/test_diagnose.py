"""--diagnose must save one sale/catalogue page and one lot page per house, trying later sales when the first
has nothing, and never more than 6 pages."""
import os
import tempfile
import unittest

from collector import run
from collector.sources.base import DIAGNOSE_MAX_SAVED, Adapter
from collector.sources.duggleby import DugglebyAdapter
from collector.tests.fakes import FakeFetcher
from collector.tests.test_gorringes import CAL, GRANT, HOUSE, LIST_URL, fixture, listing, lot_page


class StubJsonFetcher:
    """Answers every POST with an HTML error page, like a site that wants a token."""
    def post_json(self, url, payload, crawl_delay=0, api_allowed=False):
        return "<html>403 token required</html>"


class DiagnoseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def saved(self, house_id):
        folder = os.path.join(self.tmp.name, house_id)
        return sorted(os.listdir(folder)) if os.path.isdir(folder) else []

    def test_gorringes_tries_the_next_sale_and_saves_calendar_catalogue_sale_and_lot(self):
        cat1, cat2 = "https://auction.gorringes.co.uk/auction-catalog/301126", "https://auction.gorringes.co.uk/auction-catalog/011226"
        pages = {CAL: fixture("calendar_p1.html"), cat1: "<p>cat1</p>", cat2: "<p>cat2</p>",
                 LIST_URL.format(1): listing((GRANT, 20, "Duncan Grant (1885-1978)", "Wrestlers", "1,000 - £1,500")),
                 GRANT: lot_page("Wrestlers", "Pencil on paper", "£1,000 - £1,500")}
        house = dict(HOUSE, adapter="gorringes", calendar_urls=[CAL], sale_include=".")
        fetcher = FakeFetcher(pages)
        # the sale 301126 listing is not saved (404), so the run has to carry on to sale 011226
        run.collect_house(house, fetcher, "2026-11-25", "now", diagnose_dir=self.tmp.name)
        self.assertEqual(self.saved("gorringes"), ["calendar.html", "catalog.html", "lot.html", "sale.html"])
        self.assertIn(LIST_URL.format(1), fetcher.calls)
        with open(os.path.join(self.tmp.name, "gorringes", "catalog.html"), encoding="utf-8") as f:
            self.assertIn(cat1, f.read().splitlines()[0])  # the verified "View Lots" page is saved

    def test_fetch_json_saves_the_raw_text_even_when_it_is_not_json(self):
        adapter = DugglebyAdapter(StubJsonFetcher())
        adapter.diagnose_dir = self.tmp.name
        self.assertIsNone(adapter.fetch_json({"id": "duggleby"}, "https://x.test/feed", {}, kind="calendar.json"))
        with open(os.path.join(self.tmp.name, "duggleby", "calendar.json"), encoding="utf-8") as f:
            self.assertIn("403 token required", f.read())

    def test_at_most_six_pages_are_saved_and_fetched(self):
        adapter = Adapter(FakeFetcher({f"https://x.test/{i}": "x" for i in range(30)}))
        adapter.diagnose_dir = self.tmp.name
        for i, kind in enumerate(("calendar", "sale", "catalog", "lot", "a", "b", "c", "d")):
            adapter.snapshot({"id": "h"}, kind, "u", "t")
        self.assertEqual(len(self.saved("h")), DIAGNOSE_MAX_SAVED)
        from collector.fetcher import FetchError
        with self.assertRaises(FetchError):
            for i in range(30):
                adapter.fetch({"id": "h"}, f"https://x.test/{i}")
        self.assertLessEqual(len(adapter.fetcher.calls), 10)

    def test_api_allowed_comes_from_the_house_config(self):
        seen = []

        class F:
            def post_json(self, url, payload, crawl_delay=0, api_allowed=False):
                seen.append(api_allowed)
                return "{}"
        DugglebyAdapter(F()).fetch_json({"id": "d"}, "https://x.test/api/x", {})
        DugglebyAdapter(F()).fetch_json({"id": "d", "api_allowed": True}, "https://x.test/api/x", {})
        self.assertEqual(seen, [False, True])


if __name__ == "__main__":
    unittest.main()
