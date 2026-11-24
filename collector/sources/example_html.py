"""Stub adapter showing the pattern: fetch a page, parse it with html.parser, return raw dicts.

It expects made-up markup (see tests). Copy this file as the starting point for a real adapter.
"""
from html.parser import HTMLParser
from urllib.parse import urljoin

from .base import Adapter


class _LotParser(HTMLParser):
    """Collects <div class="lot" data-lot="N"> blocks: <a href>title</a>, <span class="est">."""

    def __init__(self):
        super().__init__()
        self.lots, self._lot, self._field = [], None, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "div" and "lot" in (a.get("class") or "").split():
            self._lot = {"lot_number": a.get("data-lot", ""), "title": "", "estimate_text": ""}
            self.lots.append(self._lot)
        elif self._lot is not None and tag == "a":
            self._lot["lot_url"], self._field = a.get("href", ""), "title"
        elif self._lot is not None and tag == "span" and a.get("class") == "est":
            self._field = "estimate_text"
        elif self._lot is not None and tag == "img":
            self._lot["image_url"] = a.get("src")

    def handle_endtag(self, tag):
        if tag in ("a", "span"):
            self._field = None

    def handle_data(self, data):
        if self._lot is not None and self._field:
            self._lot[self._field] += data


class ExampleHtmlAdapter(Adapter):
    def list_sales(self, house):
        # A real adapter would parse a sales index page. The stub reads one URL from houses.json.
        return [{"id": house["sale_id"], "title": house.get("sale_title", ""),
                 "date": house["sale_date"], "end_date": house.get("sale_end_date"), "url": house["sales_url"]}]

    def list_lots(self, house, sale):
        parser = _LotParser()
        parser.feed(self.fetch(house, sale["url"]))
        for lot in parser.lots:
            lot["lot_url"] = urljoin(sale["url"], lot.get("lot_url", ""))
        return parser.lots
