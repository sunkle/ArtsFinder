import json
import os
import tempfile
import unittest

from collector.probe_deep import classify_link, deep_house, pick_links, run_deep, same_site, host_allowed

HOME = """<html><body>
<a href="/calendar">Auction calendar</a>
<a href="/forthcoming-auctions">Forthcoming</a>
<a href="/auctions/12/general-sale">General sale</a>
<a href="https://bid.example.co.uk/catalogue/55">Pictures and Paintings sale</a>
<a href="https://example.easyliveauction.com/catalogue/9">Online</a>
<a href="https://www.the-saleroom.com/en-gb/auction-catalogues/example/catalogue-id-1">Saleroom</a>
<a href="https://other.com/catalogue/1">Elsewhere</a>
<a href="/lot/1001">Lot 1001</a>
<a href="/privacy">Privacy</a>
<a href="/catalogue.pdf">PDF</a>
</body></html>"""


def pad(s):
    return "<html><body>" + s + "<p>" + "Auction lots with estimate details and catalogue. " * 12 + "</p></body></html>"


class LinkTests(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(classify_link("https://x.co.uk/lot/55"), "lot")
        self.assertEqual(classify_link("https://x.co.uk/catalogue?lotid=3"), "lot")
        self.assertEqual(classify_link("https://x.co.uk/calendar"), "calendar")
        self.assertEqual(classify_link("https://x.co.uk/x", "Forthcoming auctions"), "calendar")
        self.assertEqual(classify_link("https://x.co.uk/catalogue/55"), "sale")
        self.assertEqual(classify_link("https://x.co.uk/privacy-policy"), None)
        self.assertEqual(classify_link("https://x.co.uk/about"), None)
        self.assertEqual(classify_link("https://x.co.uk/a.pdf", "Catalogue"), None)

    def test_hosts(self):
        self.assertTrue(same_site("bid.example.co.uk", "example.co.uk"))
        self.assertFalse(same_site("other.com", "example.co.uk"))
        self.assertTrue(host_allowed("example.easyliveauction.com", "example.co.uk"))
        self.assertFalse(host_allowed("evil.com", "example.co.uk"))

    def test_pick_links(self):
        got = pick_links(HOME, "https://www.example.co.uk/", "example.co.uk")
        self.assertEqual(got["calendar"], ["https://www.example.co.uk/calendar", "https://www.example.co.uk/forthcoming-auctions"])
        self.assertEqual(got["lot"], ["https://www.example.co.uk/lot/1001"])
        self.assertEqual(got["sale"][0], "https://bid.example.co.uk/catalogue/55")  # art-sounding first
        self.assertIn("https://example.easyliveauction.com/catalogue/9", got["sale"])
        flat = sum(got.values(), [])
        self.assertFalse(any("other.com" in u or "privacy" in u or ".pdf" in u for u in flat))

    def test_seen_skipped(self):
        got = pick_links(HOME, "https://www.example.co.uk/", "example.co.uk", seen={"https://www.example.co.uk/lot/1001"})
        self.assertEqual(got["lot"], [])


class FakeFetcher:
    def __init__(self, pages):
        self.pages, self.asked = pages, []

    def get(self, url):
        from collector.fetcher import FetchError
        self.asked.append(url)
        if url not in self.pages:
            raise FetchError("404 " + url)
        return self.pages[url]

    def close(self):
        pass


class DeepTests(unittest.TestCase):
    def setUp(self):
        self.pages = {
            "https://www.example.co.uk/": pad(HOME),
            "https://www.example.co.uk/calendar": pad("<a href='/lot/7'>Lot 7</a>"),
            "https://www.example.co.uk/forthcoming-auctions": pad(""),
            "https://bid.example.co.uk/catalogue/55": pad("".join(f"<a href='/lot/{i}'>Lot {i}</a>" for i in range(20, 26))),
            "https://example.easyliveauction.com/catalogue/9": pad("<a href='/lot/9'>lot</a>"),
        }
        self.house = {"id": "ex", "house": "Ex", "url": "https://www.example.co.uk/"}

    def test_saves_capped_pages_with_comment(self):
        import time
        with tempfile.TemporaryDirectory() as d:
            f = FakeFetcher(self.pages)
            saved, note = deep_house(self.house, f, d, time.monotonic() + 60)
            kinds = [k for _, _, k in saved]
            self.assertEqual(kinds[0], "home")
            self.assertLessEqual(kinds.count("calendar"), 2)
            self.assertLessEqual(kinds.count("sale"), 2)
            self.assertLessEqual(kinds.count("lot"), 3)
            self.assertLessEqual(len(saved), 8)
            self.assertEqual(saved[0][0], "01-home.html")
            with open(os.path.join(d, "ex", saved[0][0]), encoding="utf-8") as fh:
                self.assertTrue(fh.readline().startswith("<!-- source: https://www.example.co.uk/"))
            self.assertFalse(any("the-saleroom" in u or "other.com" in u for u in f.asked))

    def test_challenge_stops_house(self):
        import time
        self.pages["https://www.example.co.uk/calendar"] = "<html><title>Just a moment...</title><body>Checking</body></html>"
        with tempfile.TemporaryDirectory() as d:
            f = FakeFetcher(self.pages)
            saved, note = deep_house(self.house, f, d, time.monotonic() + 60)
            self.assertIn("challenge", note)
            self.assertEqual([k for _, _, k in saved], ["home"])
            self.assertNotIn("https://bid.example.co.uk/catalogue/55", f.asked)

    def test_run_deep_only_ok_and_index(self):
        with tempfile.TemporaryDirectory() as d:
            rep = os.path.join(d, "report.json")
            with open(rep, "w") as fh:
                json.dump([dict(self.house, verdict="ok"), {"id": "no", "url": "https://n.com/", "verdict": "js_only"}], fh)
            rows = run_deep(rep, os.path.join(d, "out"), fetcher=FakeFetcher(self.pages))
            self.assertTrue(rows and all(r[0] == "ex" for r in rows))
            with open(os.path.join(d, "out", "index.md")) as fh:
                self.assertIn("01-home.html", fh.read())


if __name__ == "__main__":
    unittest.main()
