import json
import os
import tempfile
import unittest

from collector import run
from collector.fetcher import Fetcher
from collector.tests.test_validate import GOOD, HOUSE

TODAY = "2026-11-23"


def lot(house="lays", n="1", date="2026-12-03", collected="2026-11-23T02:00:00Z"):
    return dict(GOOD, id=f"{house}-1-{n}", house_id=house, lot_number=n, sale_date=date, collected_at=collected)


class ReuseTests(unittest.TestCase):
    def test_reuse_refreshes_estimate_and_dates_but_never_the_title(self):
        stored = lot(n="1", collected="2026-11-01T02:00:00Z")
        raw = {"_listing_title": "JOHN PIPER (1903-1992) Lot 1 New Title", "estimate_text": "£300 - £500"}
        out = run.reuse_stored(stored, raw, {"title": "New Sale", "date": "2026-12-09", "end_date": "2026-12-10"})
        self.assertEqual((out["estimate_low"], out["estimate_high"]), (300, 500))
        self.assertEqual(out["title"], GOOD["title"])  # the lot-page title is kept
        self.assertEqual((out["sale_title"], out["sale_date"], out["sale_end_date"], out["collected_at"]),
                         ("New Sale", "2026-12-09", "2026-12-10", "2026-11-01T02:00:00Z"))
        self.assertEqual(stored["title"], GOOD["title"])  # input not mutated

    def test_reuse_keeps_a_wider_end_date_found_on_a_lot_page(self):
        stored = dict(lot(n="1"), sale_end_date="2026-12-04")
        out = run.reuse_stored(stored, {}, {"title": "S", "date": "2026-12-03"})
        self.assertEqual(out["sale_end_date"], "2026-12-04")

    def test_reuse_without_listing_details_changes_nothing_else(self):
        stored = dict(lot(n="1"), sale_end_date=None)
        out = run.reuse_stored(stored, {}, {"title": stored["sale_title"], "date": stored["sale_date"]})
        self.assertEqual(out, stored)

    def test_collect_house_reuses_without_tagging(self):
        class Fake:
            def __init__(self, fetcher): self.stats = {"new": 0, "reused": 0, "deferred": 0}
            def list_sales(self, house): return [{"id": "1", "title": "S", "date": "2026-12-03", "url": "u"}]
            def list_lots(self, house, sale):
                self.stats["reused"] += 1
                return [{"lot_number": "1", "title": "t", "lot_url": "u", "_stored": stored}]
        stored = lot(n="1", collected="2026-11-01T02:00:00Z")
        from unittest import mock
        with mock.patch.object(run, "get_adapter", return_value=Fake):
            lots, rejected = run.collect_house({"id": "lays", "adapter": "x"}, None, TODAY, "now", previous=[stored])
        self.assertEqual((len(lots), rejected, lots[0]["collected_at"]), (1, 0, "2026-11-01T02:00:00Z"))


class MergeTests(unittest.TestCase):
    def test_fresh_replaces_old(self):
        out = run.merge_lots([lot(n="1")], {"lays": [lot(n="2")]}, {"lays"}, TODAY)
        self.assertEqual([l["id"] for l in out], ["lays-1-2"])

    def test_failed_house_keeps_yesterday_with_old_collected_at(self):
        old = lot(n="1", collected="2026-11-22T02:00:00Z")
        out = run.merge_lots([old], {}, {"lays"}, TODAY)
        self.assertEqual(out[0]["collected_at"], "2026-11-22T02:00:00Z")

    def test_empty_result_keeps_previous(self):
        out = run.merge_lots([lot(n="1")], {"lays": []}, {"lays"}, TODAY)
        self.assertEqual(len(out), 1)

    def test_past_sales_dropped_everywhere(self):
        out = run.merge_lots([lot(n="1", date="2026-11-01")], {"halls": [lot("halls", date="2026-11-22")]},
                             {"lays", "halls"}, TODAY)
        self.assertEqual(out, [])

    def test_today_is_kept(self):
        self.assertEqual(len(run.merge_lots([], {"lays": [lot(date=TODAY)]}, {"lays"}, TODAY)), 1)

    def test_multi_day_sale_kept_until_its_last_day(self):
        two_day = dict(lot(date="2026-11-22"), sale_end_date="2026-11-23")
        self.assertEqual(len(run.merge_lots([two_day], {}, {"lays"}, TODAY)), 1)           # on day 2
        self.assertEqual(run.merge_lots([two_day], {}, {"lays"}, "2026-11-24"), [])        # day after
        self.assertEqual(len(run.merge_lots([], {"lays": [two_day]}, {"lays"}, TODAY)), 1)

    def test_switched_off_house_removed(self):
        out = run.merge_lots([lot("halls")], {}, {"lays"}, TODAY)
        self.assertEqual(out, [])

    def test_duplicates_removed(self):
        out = run.merge_lots([], {"lays": [lot(n="1"), lot(n="1")]}, {"lays"}, TODAY)
        self.assertEqual(len(out), 1)

    def test_other_houses_unaffected_by_one_failure(self):
        out = run.merge_lots([lot("lays"), lot("halls", n="9")], {"halls": [lot("halls", n="10")]},
                             {"lays", "halls"}, TODAY)
        self.assertEqual(sorted(l["id"] for l in out), ["halls-1-10", "lays-1-1"])

    def test_output_validates(self):
        from collector.validate import validate_data
        out = run.build_output([HOUSE, dict(HOUSE, id="unused")], [lot()], "2026-11-23T02:00:00Z")
        self.assertEqual([h["id"] for h in out["houses"]], ["lays"])
        self.assertEqual(validate_data(out), [])


class CollectHouseTests(unittest.TestCase):
    def test_example_adapter_end_to_end_with_mock_network(self):
        page = ('<div class="lot" data-lot="7"><a href="/lot/7">Harbour</a><span class="est">£1k-1.5k</span>'
                '<img src="https://x.test/7.jpg"></div><div class="lot" data-lot="8"><a href="/lot/8"></a></div>')
        net = {"https://x.test/sale": page.encode(), "https://x.test/robots.txt": b""}

        def opener(req, timeout):
            return net[req.full_url], None

        f = Fetcher(opener=opener, sleep=lambda s: None)
        self.addCleanup(f.close)
        house = {"id": "lays", "adapter": "example_html", "crawl_delay": 3, "sale_id": "s1", "sale_title": "Fine Art",
                 "sale_date": "2026-12-03", "sales_url": "https://x.test/sale"}
        lots, rejected = run.collect_house(house, f, TODAY, "2026-11-23T02:00:00Z")
        self.assertEqual((len(lots), rejected), (1, 1))  # lot 8 has no title: rejected, run carries on
        self.assertEqual((lots[0]["estimate_low"], lots[0]["estimate_high"]), (1000, 1500))
        self.assertEqual(lots[0]["lot_url"], "https://x.test/lot/7")

    def test_sale_still_running_is_fetched_but_ended_one_is_not(self):
        page = '<div class="lot" data-lot="7"><a href="/lot/7">Harbour</a></div>'
        net = {"https://x.test/sale": page.encode(), "https://x.test/robots.txt": b""}
        f = Fetcher(opener=lambda r, t: (net[r.full_url], None), sleep=lambda s: None)
        self.addCleanup(f.close)
        house = {"id": "lays", "adapter": "example_html", "crawl_delay": 3, "sale_id": "s1",
                 "sale_title": "Fine Art", "sale_date": "2026-11-22", "sale_end_date": "2026-11-23", "sales_url": "https://x.test/sale"}
        lots, _ = run.collect_house(house, f, TODAY, "2026-11-23T02:00:00Z")
        self.assertEqual((len(lots), lots[0]["sale_end_date"]), (1, "2026-11-23"))
        self.assertEqual(run.collect_house(house, f, "2026-11-24", "now"), ([], 0))

    def test_past_sale_not_fetched(self):
        f = Fetcher(opener=lambda r, t: self.fail("network used"), sleep=lambda s: None)
        self.addCleanup(f.close)
        house = {"id": "lays", "adapter": "example_html", "crawl_delay": 3, "sale_id": "s1",
                 "sale_date": "2026-01-01", "sales_url": "https://x.test/sale"}
        self.assertEqual(run.collect_house(house, f, TODAY, "now"), ([], 0))


class MainTests(unittest.TestCase):
    def test_failing_house_does_not_stop_run_and_keeps_old_data(self):
        with tempfile.TemporaryDirectory() as d:
            houses = os.path.join(d, "houses.json")
            out = os.path.join(d, "data", "lots.json")
            os.makedirs(os.path.dirname(out))
            with open(houses, "w") as fh:
                json.dump({"houses": [dict(HOUSE, adapter="nonsense", enabled=True, crawl_delay=3)]}, fh)
            future = lot(date="2099-01-01")
            with open(out, "w") as fh:
                json.dump(run.build_output([HOUSE], [future], "2026-11-22T02:00:00Z"), fh)
            with self.assertLogs("collector", level="INFO"):
                self.assertEqual(run.main(["--houses", houses, "--out", out]), 0)
            with open(out) as fh:
                self.assertEqual(json.load(fh)["lots"][0]["id"], future["id"])

    def _run_with(self, house_changes):
        with tempfile.TemporaryDirectory() as d:
            houses = os.path.join(d, "houses.json")
            out = os.path.join(d, "lots.json")
            with open(houses, "w") as fh:
                json.dump({"houses": [dict(HOUSE, adapter="nonsense", crawl_delay=3, **house_changes)]}, fh)
            with open(out, "w") as fh:
                json.dump(run.build_output([HOUSE], [lot(date="2099-01-01")], "2026-11-22T02:00:00Z"), fh)
            with self.assertLogs("collector", level="INFO"):
                run.main(["--houses", houses, "--out", out])
            with open(out) as fh:
                return json.load(fh)["lots"]

    def test_keep_existing_lots_survives_a_house_with_no_adapter(self):
        self.assertEqual(len(self._run_with({"enabled": False, "keep_existing_lots": True})), 1)

    def test_plain_disabled_house_loses_its_lots(self):
        self.assertEqual(self._run_with({"enabled": False}), [])


if __name__ == "__main__":
    unittest.main()
