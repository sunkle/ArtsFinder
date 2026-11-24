import os
import unittest

from collector.probe import classify_page, detect_platform, find_links, render_markdown

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "probe")


def pad(s, n=300):
    return s + "<p>" + "Fine art and antiques sale with many interesting items. " * (n // 50 + 1) + "</p>"


class ProbeTests(unittest.TestCase):
    def test_real_challenge_page(self):
        with open(os.path.join(FIX, "lays_challenge.html"), encoding="utf-8") as f:
            html = f.read()
        self.assertEqual(classify_page(html)[0], "bot_challenge")
        self.assertEqual(detect_platform(html), "goauction/bidpath")

    def test_cloudflare(self):
        html = "<html><title>Just a moment...</title><body>Checking your browser</body></html>"
        self.assertEqual(classify_page(html)[0], "bot_challenge")

    def test_tiny_script_page(self):
        self.assertEqual(classify_page("<html><script>x=1</script></html>")[0], "bot_challenge")

    def test_js_only(self):
        html = "<html><head><title>Shop</title></head><body><div id='root'></div>" \
               + "<script src='a.js'></script>" * 3 + "<!--" + "x" * 7000 + "--></body></html>"
        self.assertEqual(classify_page(html)[0], "js_only")

    def test_ok(self):
        html = pad("<html><body><h1>Upcoming auctions</h1><a href='/lot/1'>Lot 1</a>")
        self.assertEqual(classify_page(html)[0], "ok")

    def test_readable_but_no_auction_words(self):
        html = "<html><body><p>" + "Welcome to our family bakery serving bread daily. " * 6 + "</p></body></html>"
        self.assertEqual(classify_page(html)[0], "no_auction_links")

    def test_platforms(self):
        self.assertEqual(detect_platform("<script src='https://x.easyliveauction.com/a.js'>"), "easylive")
        self.assertEqual(detect_platform("<a href='https://www.the-saleroom.com/x'>"), "atg/the-saleroom")
        self.assertEqual(detect_platform("<link href='/wp-content/a.css'>"), "wordpress")
        self.assertEqual(detect_platform("<p>hi</p>"), "custom")

    def test_find_links(self):
        html = ("<a href='/auctions'>Auctions</a><a href='/calendar'>Calendar</a><a href='/catalogue/9'>More</a>"
                "<a href='/lot/55'>Lot</a><a href='https://other.com/auction'>x</a><a href='/login'>Login</a>"
                "<a href='/brochure.pdf'>Sale PDF</a>")
        auction, lot = find_links(html, "https://www.example.co.uk/")
        self.assertEqual(auction, ["https://www.example.co.uk/auctions", "https://www.example.co.uk/calendar"])
        self.assertEqual(lot, ["https://www.example.co.uk/lot/55"])

    def test_report_table(self):
        md = render_markdown([{"house": "A|B", "region": "R", "verdict": "ok", "platform": "custom",
                               "pages": ["u"], "note": "n|m"}])
        self.assertIn("| A|B |", md.replace("A|B", "A|B"))
        self.assertIn("ok: 1", md)


if __name__ == "__main__":
    unittest.main()
