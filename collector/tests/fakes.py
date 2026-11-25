"""Test doubles shared by the adapter tests (DRY)."""
import json

from collector.fetcher import FetchError


class FakeFetcher:
    """pages: url -> html. A missing url raises FetchError, like a 404. post_json answers from `json_pages`
    (url -> list of answers, or a function (payload) -> answer)."""

    def __init__(self, pages=None, json_pages=None):
        self.pages, self.json_pages, self.calls, self.posts = pages or {}, json_pages or {}, [], []

    def get(self, url, crawl_delay=0):
        self.calls.append(url)
        if url not in self.pages:
            raise FetchError("HTTP 404 for " + url)
        return self.pages[url]

    def post_json(self, url, payload, crawl_delay=0, api_allowed=False):
        self.posts.append((url, payload))
        answer = self.json_pages.get(url)
        if answer is None:
            raise FetchError("HTTP 404 for " + url)
        return json.dumps(answer(payload) if callable(answer) else answer)
