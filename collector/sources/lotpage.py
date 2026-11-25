"""Generic lot-page reader shared by adapters whose lot pages are not (yet) known in detail.

Moved out of goauction.py so other adapters reuse it (DRY). Order of trust: JSON-LD, labelled fields
('Estimate: ...', 'Medium'), og:/meta tags, visible text. A missing piece gives None, never a crash.
"""
import json
import re
from urllib.parse import urlsplit

from .htmlutil import clean_url, meta_tags, parse, parse_date_range

_SLUG_LOT_NO = re.compile(r"/lot-(\d+[a-z]?)(?:-|/|$)", re.I)
_LOT_NO_TEXT = re.compile(r"\blot\s*(?:no\.?|number|#)?\s*:?\s*(\d+[A-Za-z]?)\b", re.I)
_LIFE_DATES = re.compile(r"\(\s*(?:[A-Za-z.]+\s+)?(?:b\.\s*|born\s+|fl\.?\s*)?\d{4}\s*(?:[-–—]\s*\d{4})?\s*\)\s*$")

# label (case-insensitive, whole label) -> raw_lot field. Order matters (first hit wins per field).
LABELS = {
    "estimate_text": r"estimate(?:\s*\(gbp\))?|guide price|est\.?",
    "medium_detail": r"medium|materials?|media|technique",
    "dimensions": r"dimensions?|size|image size|overall size|measurements?|sight size",
    "framed": r"framed(?: size| dimensions?)?|frame size",
    "artist_text": r"artist|maker|creator|painter|sculptor",
    "description": r"description|details|catalogue note|lot details",
    "date_made_text": r"date made|date of work|year made|year|circa|dated",
    "auction_date": r"auction date|sale date|date of sale",
}
_LABEL_RX = {f: re.compile(r"^(?:" + rx + r")\b", re.I) for f, rx in LABELS.items()}
_ANY_LABEL = re.compile(r"^(?:" + "|".join(LABELS.values()) + r")\s*(?::|$)", re.I)


def _as_int(v):
    try:
        f = float(str(v).replace(",", "").replace("£", ""))
        return int(round(f))
    except (TypeError, ValueError):
        return None


class LotPageMixin:
    """Adds parse_lot(html, url, house) and its helpers to an Adapter."""

    # ---------- one lot page ----------
    def parse_lot(self, html, url, house=None):
        """Lot page -> raw_lot. Order of trust: JSON-LD, labelled fields, og:/meta tags, visible text."""
        root = parse(html)
        meta = meta_tags(root)
        ld = self._json_ld(root)
        lines = self._main_lines(root)
        labelled = self._labelled(lines)
        raw = {"lot_url": url}

        raw["title"] = self._clean_title(
            ld.get("name") or self._first_text(root, "h1") or meta.get("og:title") or self._first_text(root, "title"),
            house)
        raw["lot_number"] = (self._lot_number(lines, raw["title"], url)) or ""
        raw["title"] = re.sub(r"^\s*lot\s*\d+[A-Za-z]?\s*[-–—:.]*\s*", "", raw["title"] or "", flags=re.I).strip()

        creator = ld.get("creator") or ld.get("artist")
        creator = creator.get("name") if isinstance(creator, dict) else creator
        raw["artist_text"] = labelled.get("artist_text") or creator or self._artist_class(root) \
            or self._artist_heading(lines, raw["title"])
        raw["medium_detail"] = labelled.get("medium_detail")
        raw["estimate_text"] = labelled.get("estimate_text")
        offers = ld.get("offers")
        offers = offers[0] if isinstance(offers, list) and offers else offers
        offers = offers if isinstance(offers, dict) else {}
        if not raw["estimate_text"]:
            low = _as_int(offers.get("lowPrice") or offers.get("price"))
            high = _as_int(offers.get("highPrice") or offers.get("price"))
            if low is not None:
                raw["estimate_low"], raw["estimate_high"] = low, high if high is not None else low
        raw["dimensions"] = labelled.get("dimensions") or labelled.get("framed")
        raw["date_made_text"] = labelled.get("date_made_text")
        # The lot's own sale day(s), when shown. The tagger only uses it to widen a sale's end date.
        raw["sale_date"], raw["sale_end_date"] = parse_date_range(labelled.get("auction_date"))
        raw["description"] = (labelled.get("description") or ld.get("description") or meta.get("og:description")
                              or meta.get("description") or self._visible_summary(lines, raw["title"]))
        image = ld.get("image")
        image = image[0] if isinstance(image, list) and image else image
        image = image.get("url") if isinstance(image, dict) else image
        raw["image_url"] = image or meta.get("og:image") or self._stock_image(root)
        if raw["image_url"]:
            raw["image_url"] = clean_url(url, raw["image_url"])
        return {k: v for k, v in raw.items() if v not in (None, "")}

    # -- extraction pieces --
    @staticmethod
    def _json_ld(root):
        """First schema.org Product/artwork object found in any ld+json block ({} if none)."""
        def walk(obj):
            if isinstance(obj, list):
                for o in obj:
                    yield from walk(o)
            elif isinstance(obj, dict):
                yield obj
                yield from walk(obj.get("@graph", []))
        for s in root.find_all("script", lambda n: "ld+json" in n.get("type").lower()):
            try:
                data = json.loads(s.raw_text())
            except ValueError:
                continue
            for obj in walk(data):
                kind = obj.get("@type")
                kinds = kind if isinstance(kind, list) else [kind]
                if any(str(k) in ("Product", "VisualArtwork", "CreativeWork", "Offer") for k in kinds):
                    return obj
        return {}

    @staticmethod
    def _first_text(root, tag):
        for n in root.find_all(tag):
            if n.text():
                return n.text()
        return None

    @staticmethod
    def _clean_title(title, house):
        title = re.sub(r"\s+", " ", title or "").strip()
        if house and house.get("name"):
            title = re.sub(r"\s*[|–—-]\s*" + re.escape(house["name"]) + r"\s*$", "", title, flags=re.I)
        return title

    @staticmethod
    def _main_lines(root):
        """Visible text lines, without navigation/header/footer chrome where the page marks it."""
        return root.lines(skip={"nav", "footer"})

    @staticmethod
    def _labelled(lines):
        """'Label: value' on one line, or 'Label' alone with the value on the next line(s).
        Without a colon only an estimate may carry its value ('Estimate £800 - £1,200')."""
        out = {}
        for i, line in enumerate(lines):
            for field, rx in _LABEL_RX.items():
                m = rx.match(line)
                if not m or field in out:
                    continue
                rest = line[m.end():].strip()
                if not rest:  # label alone: the value is on the next line(s)
                    parts = []
                    for follow in lines[i + 1:i + 6]:
                        if _ANY_LABEL.match(follow):
                            break
                        parts.append(follow)
                        if field != "description":
                            break
                    value = " ".join(parts)
                elif rest[0] == ":" or (rest[0] in "–-" and rest[1:2].isspace()):
                    value = rest.lstrip(":–- ")
                elif field == "estimate_text" and re.match(r"[\d£]", rest):
                    value = rest
                else:
                    continue  # prose that merely starts with the word
                if value:
                    out[field] = value[:600]
        return out

    @staticmethod
    def _lot_number(lines, title, url):
        m = _SLUG_LOT_NO.search(urlsplit(url).path)
        if m:
            return m.group(1)
        for text in [title] + lines[:30]:
            hit = _LOT_NO_TEXT.search(text or "")
            if hit:
                return hit.group(1)
        return ""

    @staticmethod
    def _artist_class(root):
        for n in root.iter():
            if n.tag not in ("html", "body") and "artist" in (n.get("class") + " " + n.get("itemprop")).lower():
                t = n.text()
                if t and len(t) < 120 and len(n.lines()) <= 2:
                    return t
        return None

    @staticmethod
    def _artist_heading(lines, title):
        """A short line near the top ending in life dates, e.g. 'JOHN PIPER (1903-1992)'."""
        for line in lines[:60]:
            if line != title and len(line) < 90 and _LIFE_DATES.search(line) and not _ANY_LABEL.match(line) \
                    and not re.search(r"[£$]|\blot\b|\bestimate\b", line, re.I) and re.search(r"[A-Za-z]{3}", line):
                return line
        return None

    @staticmethod
    def _visible_summary(lines, title):
        keep = [l for l in lines if l != title and not _ANY_LABEL.match(l) and len(l) > 25]
        return " ".join(keep[:3])[:600] or None

    @staticmethod
    def _stock_image(root):
        for img in root.find_all("img"):
            src = img.get("src") or img.get("data-src")
            if src and "/stock/" in src:
                return src
        return None
