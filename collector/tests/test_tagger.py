import unittest

from collector.tagger import (AFTER_NOTE, RULES, classify, is_reproduction, clean_text, parse_artist, parse_dimensions, parse_estimate, parse_year, tag, NotArt)
from collector.validate import validate_lot

HOUSE = {"id": "lays"}
SALE = {"id": "1234", "title": "Fine Art", "date": "2026-12-03"}


def raw(**kw):
    base = {"lot_number": "56", "title": "Harbour", "lot_url": "https://example.com/lot/56"}
    base.update(kw)
    return base


class ArtistTests(unittest.TestCase):
    CASES = [
        ("JOHN PIPER (1903-1992)", ("John Piper", "1903-1992", None)),
        ("John Piper (1903-1992)", ("John Piper", "1903-1992", None)),
        ("John Piper (British 1903–1992)", ("John Piper", "1903-1992", None)),
        ("ATTRIBUTED TO LOUIS WAIN (1860-1939)", ("Louis Wain", "1860-1939", "Attributed to")),
        ("Circle of Thomas Gainsborough", ("Thomas Gainsborough", None, "Circle of")),
        ("After L.S. LOWRY (1887-1976)", ("L.S. Lowry", "1887-1976", "After")),
        ("AFTER JOHN CONSTABLE", ("John Constable", None, "After")),
        ("Manner of David Cox", ("David Cox", None, "Manner of")),
        ("PIPER, John (1903-1992)", ("John Piper", "1903-1992", None)),
        ("WILLIAM McTAGGART (1835-1910)", ("William McTaggart", "1835-1910", None)),
        ("PADDY O'BRIEN (b.1950)", ("Paddy O'Brien", "b.1950", None)),
        ("VINCENT VAN GOGH", ("Vincent van Gogh", None, None)),
        ("Terry Frost, R.A. (1915-2003)", ("Terry Frost", "1915-2003", None)),
        ("British School, 19th Century", (None, None, None)),
        ("Unknown artist", (None, None, None)),
        ("", (None, None, None)),
        # real catalogue strings from the v0.2 review
        ("§ John TUNNARD", ("John Tunnard", None, None)),
        ("§ John TUNNARD (1900-1971)", ("John Tunnard", "1900-1971", None)),
        ("Munnings PRA", ("Munnings", None, None)),
        ("Sir Alfred MUNNINGS PRA (1878-1959)", ("Alfred Munnings", "1878-1959", None)),
        ("Pears RI ROI RSMA", ("Pears", None, None)),
        ("Robert JONES (1943)", ("Robert Jones", "b.1943", None)),
        ("Andrew LANYON (b.1943)", ("Andrew Lanyon", "b.1943", None)),
        ("Andrew LANYON (1947-)", ("Andrew Lanyon", "b.1947", None)),
        ("BB", ("BB", None, None)),
        ("Ascribed to John SMITH (1800-1870)", ("John Smith", "1800-1870", "Ascribed to")),
        ("ASCRIBED TO JAN VAN GOYEN", ("Jan van Goyen", None, "Ascribed to")),
        ("In the manner of David Cox", ("David Cox", None, "Manner of")),
        ("Harold HARVEY R.A. R.W.S.", ("Harold Harvey", None, None)),
    ]

    def test_cases(self):
        for text, expected in self.CASES:
            with self.subTest(text=text):
                got = parse_artist(text)
                self.assertEqual(got, expected)

    def test_unstripped_honours_keep_capitals_not_title_case(self):
        # an unknown trailing mark must not become "Ra"; a known one in the middle stays upper-case
        self.assertEqual(parse_artist("John SMITH RWS Junior")[0], "John Smith RWS Junior")

    def test_after_is_detectable(self):
        lot = tag(raw(artist_text="After SALVADOR DALI (1904-1989)"), HOUSE, SALE)
        self.assertEqual(lot["attribution_note"], "After")
        self.assertEqual(lot["artist"], "Salvador Dali")

    def test_artist_from_description_lead(self):
        lot = tag(raw(description="JOHN PIPER (1903-1992) Harbour, oil on board, dated 1952"), HOUSE, SALE)
        self.assertEqual((lot["artist"], lot["artist_dates"]), ("John Piper", "1903-1992"))
        self.assertEqual(lot["year_made"], 1952)  # not 1903 or 1992


class ReproductionRuleTests(unittest.TestCase):
    def test_rule_cases(self):
        cases = [
            (dict(title="Harbour", type="Painting"), False),
            (dict(title="Harbour", type="Print"), True),
            (dict(title="Harbour", type="Painting", attribution_note="After"), True),
            (dict(title="Harbour", type="Painting", attribution_note="Circle of"), False),
            (dict(title="Giclee of a harbour", type="Painting"), True),
            (dict(title="Harbour", type="Painting", description="A poster of a view"), True),
            (dict(title="Harbour", type="Painting", medium_detail="oil on canvas"), False),
        ]
        for lot, expected in cases:
            with self.subTest(lot=lot):
                self.assertEqual(is_reproduction(lot), expected)

    def test_after_note_comes_from_shared_rules(self):
        self.assertEqual(AFTER_NOTE, RULES["after_note"])
        self.assertEqual(parse_artist("AFTER JOHN CONSTABLE")[2], RULES["after_note"])

    def test_rules_file_is_the_one_tagger_loaded(self):
        import json, os
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        with open(os.path.join(root, "shared", "rules.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), RULES)


class ClassifyTests(unittest.TestCase):
    CASES = [
        ("oil on canvas", ("Painting", "Oil")),
        ("Oil on canvas board", ("Painting", "Oil")),
        ("oils on panel", ("Painting", "Oil")),
        ("acrylic on board", ("Painting", "Acrylic")),
        ("egg tempera on panel", ("Painting", "Tempera")),
        ("watercolour and pencil", ("Work on paper", "Watercolour")),
        ("pencil and watercolor heightened with white", ("Work on paper", "Watercolour")),
        ("gouache on paper", ("Work on paper", "Gouache")),
        ("pastel on paper", ("Work on paper", "Pastel")),
        ("pen and ink", ("Work on paper", "Pencil/Charcoal/Ink")),
        ("charcoal on paper", ("Work on paper", "Pencil/Charcoal/Ink")),
        ("mixed media on paper", ("Work on paper", "Mixed media")),
        ("mixed media on canvas", ("Painting", "Mixed media")),
        ("etching with aquatint, signed in pencil", ("Print", "Etching/Engraving")),
        ("lithograph in colours", ("Print", "Lithograph")),
        ("screenprint, numbered 12/75", ("Print", "Screenprint")),
        ("linocut printed in colours", ("Print", "Woodcut/Linocut")),
        ("giclee print on paper", ("Print", "Other")),
        ("gelatin silver print", ("Photograph", "Other")),
        ("patinated bronze on a marble base", ("Sculpture", "Bronze")),
        ("carved alabaster figure", ("Sculpture", "Stone/Marble")),
        ("welded steel", ("Sculpture", "Other metal")),
        ("stoneware vase", ("Other", "Ceramic")),
        ("something unfamiliar", ("Other", "Other")),
    ]

    def test_cases(self):
        for text, expected in self.CASES:
            with self.subTest(text=text):
                self.assertEqual(classify(text), expected)

    def test_medium_detail_beats_description(self):
        lot = tag(raw(medium_detail="oil on board", description="After a print by Hokusai"), HOUSE, SALE)
        self.assertEqual((lot["type"], lot["medium"]), ("Painting", "Oil"))

    def test_falls_back_to_description(self):
        lot = tag(raw(description="A watercolour of a harbour"), HOUSE, SALE)
        self.assertEqual(lot["medium"], "Watercolour")


class YearTests(unittest.TestCase):
    CASES = [
        ("signed and dated 1952", 1952),
        ("dated 12/3/1952 verso", 1952),
        ("signed and dated lower right 1948", 1948),
        ("c.1950", 1950),
        ("circa 1930", 1930),
        ("c. 1875", 1875),
        ("c.1950s", 1950),
        ("1950s", 1950),
        ("Harbour (1952)", 1952),
        ("no date at all", None),
        ("John Piper 1903-1992 oil on board", None),
    ]

    def test_cases(self):
        for text, expected in self.CASES:
            with self.subTest(text=text):
                self.assertEqual(parse_year(text)[0], expected)


class EstimateTests(unittest.TestCase):
    CASES = [
        ("£800-1,200", (800, 1200)),
        ("Est. 800 - 1200", (800, 1200)),
        ("£1k-1.5k", (1000, 1500)),
        ("£1-2k", (1000, 2000)),
        ("£800 - £1,200", (800, 1200)),
        ("Estimate: £2,000 to £3,000", (2000, 3000)),
        ("GBP 500-700", (500, 700)),
        ("£500", (500, 500)),
        ("£1,200-800", (800, 1200)),
        ("No estimate", (None, None)),
        ("", (None, None)),
        (None, (None, None)),
    ]

    def test_cases(self):
        for text, expected in self.CASES:
            with self.subTest(text=text):
                self.assertEqual(parse_estimate(text), expected)

    def test_raw_numbers_win(self):
        lot = tag(raw(estimate_low=100, estimate_high=200, estimate_text="£5-6"), HOUSE, SALE)
        self.assertEqual((lot["estimate_low"], lot["estimate_high"]), (100, 200))


class DimensionTests(unittest.TestCase):
    CASES = [
        ("40 x 50cm", "40 x 50cm"),
        ("40cm x 50cm", "40 x 50cm"),
        ("Canvas 61 x 91.5 cm (24 x 36in)", "61 x 91.5cm"),
        ("12 x 8 in", "12 x 8in"),
        ("no size", None),
    ]

    def test_cases(self):
        for text, expected in self.CASES:
            with self.subTest(text=text):
                self.assertEqual(parse_dimensions(text), expected)


class NonArtTests(unittest.TestCase):
    def skipped(self, **kw):
        try:
            tag(raw(**kw), HOUSE, SALE)
        except NotArt:
            return True
        return False

    def test_jewellery_and_pottery_are_skipped(self):
        for title, detail in [("A gold diamond ring", None), ("Studio pottery vase", None), ("Cartier wristwatch", None),
                              ("Lot of three brooches", "silver"), ("Large ceramic bowl", "glazed ceramic"),
                              ("A pendant necklace", None), ("Moorcroft jug", "earthenware")]:
            with self.subTest(title=title):
                self.assertTrue(self.skipped(title=title, medium_detail=detail))

    def test_art_with_a_non_art_word_in_the_title_is_kept(self):
        self.assertFalse(self.skipped(title="Still Life with Bowl of Fruit", medium_detail="oil on canvas"))
        self.assertFalse(self.skipped(title="The Ring", medium_detail="watercolour on paper"))

    def test_ceramic_sculpture_is_kept(self):
        self.assertFalse(self.skipped(title="Seated Figure", medium_detail="ceramic sculpture, glazed", artist_text="Jane DOE"))
        self.assertFalse(self.skipped(title="Bowl form", medium_detail="stoneware sculpture", artist_text="Jane DOE"))

    def test_a_brass_ring_is_not_rescued_by_being_metal(self):
        self.assertTrue(self.skipped(title="A brass ring", medium_detail="brass"))

    def test_keyword_list_is_in_the_shared_rules_file(self):
        self.assertIn("jewellery", RULES["non_art_words"])


class TagTests(unittest.TestCase):
    def test_full_lot_is_valid(self):
        lot = tag(raw(title="<b>Harbour at St Ives</b> &amp; boats", artist_text="JOHN PIPER (1903-1992)",
                      medium_detail="oil on canvas board, 40 x 50cm", estimate_text="£800-1,200",
                      description="Signed, dated 1952", image_url="https://example.com/i.jpg",
                      date_made_text="c.1950s"),
                  HOUSE, SALE, collected_at="2026-11-23T02:00:00Z")
        self.assertEqual(validate_lot(lot), [])
        self.assertEqual(lot["id"], "lays-1234-56")
        self.assertEqual(lot["title"], "Harbour at St Ives & boats")
        self.assertEqual((lot["year_made"], lot["date_made_text"]), (1950, "c.1950s"))
        self.assertEqual(lot["dimensions"], "40 x 50cm")

    def test_unknowns_are_none(self):
        lot = tag(raw(), HOUSE, SALE)
        for f in ("artist", "artist_dates", "attribution_note", "year_made", "estimate_low", "estimate_high",
                  "dimensions", "image_url", "medium_detail", "date_made_text"):
            self.assertIsNone(lot[f], f)
        self.assertEqual((lot["type"], lot["medium"]), ("Other", "Other"))
        self.assertEqual(validate_lot(lot), [])

    def test_description_truncated(self):
        lot = tag(raw(description="word " * 200), HOUSE, SALE)
        self.assertLessEqual(len(lot["description"]), 300)

    def test_missing_required_raises(self):
        for bad in ({"title": ""}, {"lot_url": ""}, {"lot_number": ""}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                tag(raw(**bad), HOUSE, SALE)

    def test_bad_sale_date_raises(self):
        with self.assertRaises(ValueError):
            tag(raw(), HOUSE, {"id": "1", "date": "3 Dec"})

    def test_one_day_sale_has_no_end_date_and_a_multi_day_sale_does(self):
        self.assertIsNone(tag(raw(), HOUSE, SALE)["sale_end_date"])
        lot = tag(raw(), HOUSE, dict(SALE, date="2026-11-26", end_date="2026-11-27"))
        self.assertEqual((lot["sale_date"], lot["sale_end_date"]), ("2026-11-26", "2026-11-27"))
        self.assertEqual(validate_lot(lot), [])

    def test_lot_page_date_can_widen_the_sale_end_but_not_move_the_start(self):
        lot = tag(raw(sale_date="2026-11-27"), HOUSE, dict(SALE, date="2026-11-26"))
        self.assertEqual((lot["sale_date"], lot["sale_end_date"]), ("2026-11-26", "2026-11-27"))

    def test_clean_text(self):
        self.assertEqual(clean_text(" a&nbsp;<br/>b \n c "), "a b c")


if __name__ == "__main__":
    unittest.main()
