"""Small, forgiving HTML helpers shared by adapters (standard library only).

parse(html) -> Node tree. Real pages are messy, so the parser never raises: unclosed or stray tags
are tolerated. Also parse_date(): finds the first UK-style date in free text.
"""
import re
from datetime import date
from html.parser import HTMLParser

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
SKIP = {"script", "style", "noscript", "template", "svg"}
BLOCK = {"address", "article", "aside", "blockquote", "br", "dd", "div", "dl", "dt", "fieldset", "figcaption",
         "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main", "nav",
         "ol", "p", "pre", "section", "table", "tbody", "td", "th", "thead", "tr", "ul"}


class Node:
    def __init__(self, tag, attrs=None, parent=None):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs or {}), parent, []

    def get(self, name, default=""):
        return self.attrs.get(name) or default

    def iter(self):
        """This node and every descendant, document order."""
        yield self
        for c in self.children:
            if isinstance(c, Node):
                yield from c.iter()

    def find_all(self, tag=None, test=None):
        return [n for n in self.iter() if (tag is None or n.tag == tag) and (test is None or test(n))]

    def has_class(self, word):
        return word in (self.get("class") + " " + self.get("id")).lower()

    def _pieces(self, out, skip=()):
        if self.tag in SKIP or self.tag in skip:
            return
        if self.tag in BLOCK:
            out.append("\n")
        for c in self.children:
            if isinstance(c, Node):
                c._pieces(out, skip)
            else:
                out.append(c)
        if self.tag in BLOCK:
            out.append("\n")

    def lines(self, skip=()):
        """Visible text as non-empty lines (block tags and table cells start new lines).
        `skip`: extra tag names to leave out, e.g. {"nav", "footer"}."""
        out = []
        self._pieces(out, skip)
        text = "".join(out).replace("\xa0", " ")
        return [l for l in (re.sub(r"[ \t\r\f\v]+", " ", x).strip() for x in text.split("\n")) if l]

    def text(self):
        """Visible text on one line."""
        return " ".join(self.lines())

    def raw_text(self):
        """All text including script/style content (for JSON-LD)."""
        return "".join(c if isinstance(c, str) else c.raw_text() for c in self.children)


class _Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("[root]")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, {k: (v or "") for k, v in attrs}, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        node = Node(tag, {k: (v or "") for k, v in attrs}, self.stack[-1])
        self.stack[-1].children.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return  # a stray end tag with no matching open tag is ignored

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse(html):
    builder = _Builder()
    try:
        builder.feed(html or "")
        builder.close()
    except Exception:  # never let odd markup crash a run; keep what was parsed so far
        pass
    return builder.root


# ---- dates -----------------------------------------------------------------
MONTHS = {m: i for i, names in enumerate(
    ["jan january", "feb february", "mar march", "apr april", "may", "jun june", "jul july", "aug august",
     "sep sept september", "oct october", "nov november", "dec december"], 1) for m in names.split()}
_MON = r"(?P<{}>[A-Za-z]{{3,9}})\.?"
_ORD = r"(?:st|nd|rd|th)?"
_DATE_PATTERNS = [
    ("iso", re.compile(r"\b(?P<y>20\d\d)-(?P<m>\d\d)-(?P<d>\d\d)\b")),
    ("span", re.compile(r"\b(?P<d>\d{1,2})" + _ORD + r"\s+" + _MON.format("m") + r"\s*[-–—]\s*(?P<d2>\d{1,2})" + _ORD
                        + r"\s+" + _MON.format("m2") + r",?\s+(?P<y>20\d\d)\b")),
    ("dmy", re.compile(r"\b(?P<d>\d{1,2})" + _ORD + r"(?:\s*[-–—&]\s*(?P<d2>\d{1,2})" + _ORD + r")?\s+"
                       + _MON.format("m") + r",?\s+(?P<y>20\d\d)\b")),
    ("mdy", re.compile(r"\b" + _MON.format("m") + r"\s+(?P<d>\d{1,2})" + _ORD + r",?\s+(?P<y>20\d\d)\b")),
    ("slash", re.compile(r"\b(?P<d>\d{1,2})/(?P<m>\d{1,2})/(?P<y>20\d\d)\b")),
]


def _month(value):
    return int(value) if str(value).isdigit() else MONTHS.get(str(value).lower().rstrip("."))


def parse_date_range(text):
    """First date or date range in the text -> (start, end) as 'YYYY-MM-DD'; end is None for a single day.
    Understands '26 Nov 2026', '26-27 Nov 2026', '9-10 Dec 2026', '28 Dec - 3 Jan 2027', 'December 3, 2026',
    '2026-12-03', '03/12/2026'. (None, None) if there is no date."""
    best = None
    for kind, rx in _DATE_PATTERNS:
        for m in rx.finditer(text or ""):
            groups = m.groupdict()
            month, year = _month(groups["m"]) if "m" in rx.groupindex else None, int(groups["y"])
            month2 = _month(groups["m2"]) if groups.get("m2") else month
            try:
                start = date(year - (1 if month and month2 and month > month2 else 0), month, int(groups["d"]))
                end = date(year, month2, int(groups["d2"])) if groups.get("d2") else None
            except (TypeError, ValueError):
                continue
            if end is not None and end <= start:
                end = None
            if best is None or m.start() < best[0]:
                best = (m.start(), start.isoformat(), end.isoformat() if end else None)
            break
    return (best[1], best[2]) if best else (None, None)


def parse_date(text):
    """First date in the text as 'YYYY-MM-DD' (first day of a range), or None."""
    return parse_date_range(text)[0]
