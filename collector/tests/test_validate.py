import copy
import json
import os
import unittest

from collector.schema import CONTENT_POLICIES
from collector.sources import ADAPTERS
from collector.validate import validate_data, validate_lot

GOOD = {
    "id": "lays-1-2", "house_id": "lays", "sale_title": "Fine Art", "sale_date": "2026-12-03", "lot_number": "2",
    "title": "Harbour", "artist": "John Piper", "artist_dates": "1903-1992", "attribution_note": None,
    "type": "Painting", "medium": "Oil", "medium_detail": "oil on canvas", "year_made": 1952,
    "date_made_text": "c.1950", "estimate_low": 800, "estimate_high": 1200, "dimensions": "40 x 50cm",
    "description": "text", "image_url": None, "lot_url": "https://x.test/2", "collected_at": "2026-11-23T02:00:00Z",
}
HOUSE = {"id": "lays", "name": "David Lay", "town": "Penzance", "region": "South West", "website": "https://x.test"}


def data(**lot_changes):
    lot = dict(GOOD, **lot_changes)
    return {"generated_at": "2026-11-23T02:00:00Z", "schema_version": 1, "houses": [HOUSE], "lots": [lot]}


class ValidateTests(unittest.TestCase):
    def test_good_lot(self):
        self.assertEqual(validate_lot(GOOD), [])
        self.assertEqual(validate_data(data()), [])

    def test_bad_values(self):
        bad = [
            {"type": "Painting "}, {"medium": "Oils"}, {"sale_date": "03/12/2026"}, {"sale_date": "2026-13-45"},
            {"year_made": "1952"}, {"year_made": True}, {"estimate_low": 2000}, {"estimate_low": 12.5},
            {"description": "x" * 301}, {"lot_url": "ftp://x"}, {"lot_url": ""}, {"collected_at": "yesterday"},
            {"id": "other-1-2"}, {"image_url": 5},
            {"sale_end_date": "2026-12-03"}, {"sale_end_date": "2026-12-02"}, {"sale_end_date": "4 Dec"},
            {"attribution_note": "Probably by"},
        ]
        for change in bad:
            with self.subTest(change=change):
                self.assertTrue(validate_lot(dict(GOOD, **change)))

    def test_end_date_and_attribution_ok(self):
        self.assertEqual(validate_lot(dict(GOOD, sale_end_date="2026-12-04", attribution_note="Ascribed to")), [])
        self.assertEqual(validate_lot(dict(GOOD, sale_end_date=None)), [])

    def test_missing_and_unknown_fields(self):
        lot = copy.deepcopy(GOOD)
        del lot["title"]
        self.assertTrue(validate_lot(lot))
        self.assertTrue(validate_lot(dict(GOOD, surprise=1)))

    def test_attribution_note_optional(self):
        lot = dict(GOOD)
        del lot["attribution_note"]
        self.assertEqual(validate_lot(lot), [])

    def test_file_level(self):
        d = data()
        d["schema_version"] = 2
        self.assertTrue(validate_data(d))
        d = data()
        d["lots"].append(copy.deepcopy(d["lots"][0]))
        self.assertTrue(any("duplicate" in e for e in validate_data(d)))
        d = data(house_id="ghost", id="ghost-1-2")
        self.assertTrue(any("not in houses" in e for e in validate_data(d)))
        self.assertTrue(validate_data([]))

    def test_houses_json_is_well_formed(self):
        path = os.path.join(os.path.dirname(__file__), "..", "houses.json")
        with open(path) as fh:
            houses = json.load(fh)["houses"]
        keys = {"id", "name", "town", "region", "website", "adapter", "enabled", "crawl_delay", "disabled_reason",
                "content_policy"}
        optional = {"calendar_urls", "calendar_months", "sale_include", "sale_include_extra", "sale_exclude", "max_pages", "max_lots_per_sale", "max_new_lot_pages", "keep_existing_lots"}
        for h in houses:
            self.assertEqual(set(h) - optional, keys, h["id"])
            if h["adapter"] in ("goauction", "whitelabel"):
                self.assertTrue(h["calendar_urls"], h["id"])
            if h["adapter"] is None:
                self.assertFalse(h["enabled"], h["id"])  # no adapter planned: must be switched off
            else:
                self.assertIn(h["adapter"], ADAPTERS, h["id"])
            self.assertIn(h["content_policy"], CONTENT_POLICIES, h["id"])
            self.assertGreaterEqual(h["crawl_delay"], 3)
            self.assertEqual(bool(h["enabled"]), h["disabled_reason"] is None, h["id"])
        self.assertEqual(len({h["id"] for h in houses}), len(houses))
        for h in houses:  # keep_existing_lots only makes sense on a house that is switched off
            self.assertFalse(h.get("keep_existing_lots") and h["enabled"], h["id"])

    def test_houses_json_follows_the_terms_review(self):
        """User decision 25 Nov 2026 (SPEC.md, docs/RULES.md): terms forbid -> not collected, reason quoted."""
        path = os.path.join(os.path.dirname(__file__), "..", "houses.json")
        with open(path) as fh:
            by_id = {h["id"]: h for h in json.load(fh)["houses"]}
        enabled = {i for i, h in by_id.items() if h["enabled"]}
        self.assertEqual(enabled, {"hansons", "fieldings", "peterfrancis", "gorringes", "lawrences", "duggleby",
                                   "rogersjones", "morphets"})
        for i in enabled:
            self.assertEqual(by_id[i]["content_policy"], "full", i)
        for i in ("mellorskirk", "trevanion", "serrell", "morganevans", "gardinerhoulgate", "rosss"):
            self.assertFalse(by_id[i]["enabled"], i)
            self.assertIn("RULES.md", by_id[i]["disabled_reason"], i)
            self.assertFalse(by_id[i].get("keep_existing_lots"), i)
        for i in ("lays", "gildings", "andersonandgarland", "mallams", "mctears", "halls"):
            self.assertFalse(by_id[i]["enabled"], i)
            self.assertIn("bot challenge", by_id[i]["disabled_reason"], i)
            self.assertTrue(by_id[i]["keep_existing_lots"], i)
        self.assertEqual({by_id[i]["adapter"] for i in ("gorringes", "lawrences", "duggleby", "rogersjones")},
                         {"gorringes", "lawrences", "duggleby", "rogersjones"})


if __name__ == "__main__":
    unittest.main()
