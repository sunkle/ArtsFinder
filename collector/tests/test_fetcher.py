import unittest
import urllib.error

from collector.fetcher import BlockedHost, Fetcher, FetchError, RobotsDisallowed, user_agent


class FakeNet:
    """Stands in for the network. routes: url -> bytes | int (HTTP error code) | list of those (in order)."""

    def __init__(self, routes):
        self.routes, self.calls, self.times, self.agents = routes, [], [], []
        self.now = 0.0

    def clock(self):
        return self.now

    def sleep(self, secs):
        self.now += secs

    def opener(self, request, timeout):
        url = request.full_url
        self.calls.append(url)
        self.times.append(self.now)
        self.agents.append(request.get_header("User-agent"))
        item = self.routes.get(url, 404)
        if isinstance(item, list):
            item = item.pop(0)
        if isinstance(item, int):
            raise urllib.error.HTTPError(url, item, "err", {}, None)
        return item, None


_OPEN = []


def tearDownModule():
    for f in _OPEN:
        f.close()


def make(routes, **kw):
    net = FakeNet(routes)
    f = Fetcher(repo="me/arts-finder", opener=net.opener, sleep=net.sleep, clock=net.clock, **kw)
    _OPEN.append(f)
    return net, f



class FetcherTests(unittest.TestCase):
    def setUp(self):
        self._made = []

    def tearDown(self):
        for f in self._made:
            f.close()
    def test_the_saleroom_is_never_fetched(self):
        for url in ["https://www.the-saleroom.com/en-gb/auction-catalogues/x", "https://the-saleroom.com/",
                    "http://auction.the-saleroom.com/x", "https://WWW.THE-SALEROOM.COM./x"]:
            with self.subTest(url=url):
                net, f = make({})
                with self.assertRaises(BlockedHost):
                    f.get(url)
                self.assertEqual(net.calls, [])  # not even robots.txt

    def test_lookalike_host_is_not_blocked(self):
        net, f = make({"https://notthe-saleroom.com/robots.txt": b"", "https://notthe-saleroom.com/": b"ok"})
        self.assertEqual(f.get("https://notthe-saleroom.com/"), "ok")

    def test_honest_user_agent(self):
        net, f = make({"https://a.test/robots.txt": b"", "https://a.test/p": b"hi"})
        f.get("https://a.test/p")
        self.assertTrue(all(a == "ArtsFinder-personal/0.1 (+https://github.com/me/arts-finder)" for a in net.agents))
        self.assertNotIn("Mozilla", net.agents[0])
        self.assertIn("ArtsFinder-personal", user_agent())

    def test_robots_disallow_blocks(self):
        net, f = make({"https://a.test/robots.txt": b"User-agent: *\nDisallow: /private\n",
                       "https://a.test/private/x": b"secret", "https://a.test/ok": b"fine"})
        with self.assertRaises(RobotsDisallowed):
            f.get("https://a.test/private/x")
        self.assertEqual(f.get("https://a.test/ok"), "fine")
        self.assertNotIn("https://a.test/private/x", net.calls)

    def test_ai_block_for_our_agent_only(self):
        robots = b"User-agent: ArtsFinder-personal\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
        _, f = make({"https://a.test/robots.txt": robots, "https://a.test/p": b"x"})
        with self.assertRaises(RobotsDisallowed):
            f.get("https://a.test/p")

    def test_missing_robots_means_allowed(self):
        _, f = make({"https://a.test/p": b"x"})  # robots.txt -> 404
        self.assertEqual(f.get("https://a.test/p"), "x")

    def test_refused_robots_means_disallowed(self):
        net, f = make({"https://a.test/robots.txt": 403, "https://a.test/p": b"x"})
        with self.assertRaises(RobotsDisallowed):
            f.get("https://a.test/p")
        self.assertNotIn("https://a.test/p", net.calls)

    def test_min_gap_is_3_seconds(self):
        net, f = make({"https://a.test/p1": b"1", "https://a.test/p2": b"2"}, min_delay=0)
        f.get("https://a.test/p1")
        f.get("https://a.test/p2")
        gaps = [b - a for a, b in zip(net.times, net.times[1:])]
        self.assertTrue(all(g >= 3 for g in gaps), gaps)

    def test_robots_crawl_delay_is_obeyed(self):
        net, f = make({"https://a.test/robots.txt": b"User-agent: *\nCrawl-delay: 10\n",
                       "https://a.test/p1": b"1", "https://a.test/p2": b"2"})
        f.get("https://a.test/p1")
        f.get("https://a.test/p2")
        gaps = [b - a for a, b in zip(net.times, net.times[1:])]
        self.assertTrue(all(g >= 10 for g in gaps), gaps)

    def test_house_crawl_delay_is_obeyed(self):
        net, f = make({"https://a.test/p1": b"1", "https://a.test/p2": b"2"})
        f.get("https://a.test/p1", crawl_delay=10)
        f.get("https://a.test/p2", crawl_delay=10)
        self.assertGreaterEqual(net.times[-1] - net.times[-2], 10)

    def test_retries_twice_then_succeeds(self):
        net, f = make({"https://a.test/p": [503, 503, b"ok"]})
        self.assertEqual(f.get("https://a.test/p"), "ok")
        self.assertEqual(net.calls.count("https://a.test/p"), 3)

    def test_gives_up_after_two_retries(self):
        net, f = make({"https://a.test/p": [500, 500, 500, b"never"]})
        with self.assertRaises(FetchError):
            f.get("https://a.test/p")
        self.assertEqual(net.calls.count("https://a.test/p"), 3)

    def test_no_retry_on_404(self):
        net, f = make({"https://a.test/p": 404})
        with self.assertRaises(FetchError):
            f.get("https://a.test/p")
        self.assertEqual(net.calls.count("https://a.test/p"), 1)

    def test_cache_avoids_second_request(self):
        net, f = make({"https://a.test/p": b"x"})
        f.get("https://a.test/p")
        f.get("https://a.test/p")
        self.assertEqual(net.calls.count("https://a.test/p"), 1)

    def test_rejects_non_http(self):
        _, f = make({})
        with self.assertRaises(FetchError):
            f.get("file:///etc/passwd")


if __name__ == "__main__":
    unittest.main()
