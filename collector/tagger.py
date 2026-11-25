"""Turns free catalogue text into the SPEC fields. Pure: no network, no files.
Unknown means None. Never invent."""
import html
import re
from datetime import datetime, timezone

from .schema import CONTENT_POLICIES, MAX_DESC, load_shared

# ---- the "not an original work" and "not art" rules live in shared/rules.json (the app embeds the same file) ----
RULES = load_shared("rules.json")
AFTER_NOTE = RULES["after_note"]


def _words_rx(words):
    return re.compile(r"\b(" + "|".join(map(re.escape, words)) + r")\b", re.I)


_REPRO_TITLE = _words_rx(RULES["title_words"])
_REPRO_DESC = _words_rx(RULES["description_words"])


class NotArt(ValueError):
    """A lot that is not artwork (jewellery, pottery, ...): skipped, not an error."""


_NON_ART = re.compile(r"\b(?:" + "|".join(map(re.escape, RULES["non_art_words"])) + r")(?:e?s)?\b", re.I)
_SCULPTURE_WORDS = re.compile(r"\b(?:" + "|".join(map(re.escape, RULES["sculpture_words"])) + r")\b", re.I)
_ART_TYPES = ("Painting", "Work on paper", "Print", "Photograph")


def is_non_art(typ, title, medium_detail, description):
    """Jewellery, pottery and the like. Never applies to paintings/works on paper/prints/photographs (a picture
    called 'Bowl of Fruit' stays), nor to a Sculpture whose text says sculpture/maquette."""
    if typ in _ART_TYPES or not _NON_ART.search(f"{title} {medium_detail or ''}"):
        return False
    return not (typ == "Sculpture" and _SCULPTURE_WORDS.search(f"{title} {medium_detail or ''} {description}"))


def is_reproduction(lot):
    """True if a finished Lot dict is a print, reproduction or 'after' work (same rule as the app)."""
    return (lot.get("type") in RULES["hidden_types"]
            or lot.get("attribution_note") == AFTER_NOTE
            or bool(_REPRO_TITLE.search(f"{lot.get('title') or ''} {lot.get('medium_detail') or ''}"))
            or bool(_REPRO_DESC.search(lot.get("description") or "")))


# ---- the ONE keyword table: (type, medium) -> regex. First match wins, so order matters. ----
# type None = decide from the text (see _mixed_type).
KEYWORDS = {
    ("Print", "Etching/Engraving"): r"etching|engraving|aquatint|drypoint|mezzotint",
    ("Print", "Lithograph"): r"lithograph",
    ("Print", "Screenprint"): r"screen-?print|silk-?screen|serigraph",
    ("Print", "Woodcut/Linocut"): r"woodcut|lino-?cut|woodblock",
    ("Photograph", "Other"): r"photograph|gelatin silver|c-type|chromogenic",
    (None, "Mixed media"): r"mixed media|collage|assemblage",
    ("Painting", "Oil"): r"\boils?\b",
    ("Painting", "Acrylic"): r"acrylic|\bvinyl\b",
    ("Painting", "Tempera"): r"tempera",
    ("Work on paper", "Watercolour"): r"water-?colou?r",
    ("Work on paper", "Gouache"): r"gouache|body-?colou?r",
    ("Work on paper", "Pastel"): r"pastel",
    ("Work on paper", "Pencil/Charcoal/Ink"): r"pencil|charcoal|\bink\b|crayon|chalk|graphite|conte\b|felt[- ]?tip",
    ("Sculpture", "Bronze"): r"bronze",
    ("Sculpture", "Stone/Marble"): r"marble|alabaster|granite|limestone|soapstone|portland stone|carved stone",
    ("Sculpture", "Wood"): r"limewood|carved wood|wood carving|carved oak",
    ("Sculpture", "Other metal"): r"\b(?:steel|brass|aluminium|aluminum|cast iron|welded)\b",
    ("Sculpture", "Ceramic"): r"(?:ceramic|earthenware|stoneware|porcelain|terracotta)\b[^.;]{0,40}\b(?:sculpture|maquette)"
                              r"|\b(?:sculpture|maquette)\b[^.;]{0,40}\b(?:ceramic|earthenware|stoneware|porcelain|terracotta)",
    ("Other", "Ceramic"): r"ceramic|earthenware|stoneware|porcelain|terracotta",
    ("Sculpture", "Other"): r"sculpture|maquette|carving",
    ("Print", "Other"): r"\b(?:print|giclee|giclée|poster|offset|reproduction)\b",
}
_COMPILED = [(t, m, re.compile(rx, re.I)) for (t, m), rx in KEYWORDS.items()]

# ---- artist ----
PREFIXES = {
    "attributed to": "Attributed to", "ascribed to": "Ascribed to", "circle of": "Circle of", "after": AFTER_NOTE,
    "copy after": AFTER_NOTE, "manner of": "Manner of", "in the manner of": "Manner of", "follower of": "Follower of",
    "studio of": "Studio of", "from the studio of": "Studio of", "school of": "School of", "style of": "Style of",
    "in the style of": "Style of", "workshop of": "Workshop of", "imitator of": "Imitator of",
}
_PREFIX_WORDS = "|".join(sorted(PREFIXES, key=len, reverse=True))
_PREFIX = re.compile(r"^(" + _PREFIX_WORDS + r")\b[:.]?\s+", re.I)
# Letters after a name: honours and societies (never part of the name). Compared without dots, in capitals.
POSTNOMINALS = set("""RA PRA ARA PPRA RSA PRSA RSW PRSW RWS PRWS ARWS RBA PRBA RP PRP RI PRI ROI PROI RSMA RBSA RCA ARCA
NEAC OBE CBE MBE KBE CH RE ARE PRE RWA RUA RHA RGI RSPP PS RMS RBS SWA SWLA SGFA PPS FRSA FRBS FRS ARBS HRSA HRWS
VPRA ARSA ARBA""".split())
_HONORIFIC = re.compile(r"^(?:sir|dame|lord|lady|dr|rev|the rev|prof|professor)\.?\s+(?=\S+\s+\S)", re.I)
_MARKS = re.compile(r"[§*†‡¶#]")  # artist's resale right marks and footnote symbols
_PARTICLES = {"van", "von", "de", "der", "den", "du", "da", "di", "le", "la", "del", "della", "ter", "ten"}
_ANON = re.compile(r"unknown|anonymous|\bschool\b|\bartist$", re.I)
# "JOHN PIPER (1903-1992)" at the start of a description, when no artist field was given.
_ARTIST_LEAD = re.compile(r"^\s*((?i:" + _PREFIX_WORDS + r")\s+)?([A-Z][A-Z'’.\- ]{2,}[A-Z.])\s*(\([^)]*\d{4}[^)]*\))")
_YEAR = r"(1[2-9]\d\d|20\d\d)"


def clean_text(s):
    """Strip tags/entities and squash whitespace."""
    if s is None:
        return ""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", str(s)))).strip()


def _case_word(w, first):
    if re.fullmatch(r"(?:[A-Za-z]\.)+", w):
        return w.upper()
    if not first and w.lower() in _PARTICLES:
        return w.lower()
    out = []
    for piece in re.split(r"(['’\-])", w):
        piece = piece.capitalize()
        if piece.startswith("Mc") and len(piece) > 2:
            piece = "Mc" + piece[2:].capitalize()
        out.append(piece)
    return "".join(out)


def _shouty(w):
    letters = [c for c in w if c.isalpha()]
    return len(letters) > 1 and sum(c.isupper() for c in letters) >= 0.7 * len(letters)


def _is_postnominal(w):
    return w.replace(".", "").upper() in POSTNOMINALS


def _name_case(name):
    """Fix SHOUTY words only; words already in mixed case are trusted. Honours (RA, RWS...) and a lone
    pen-name or initials ('BB') stay in capitals."""
    words = name.split()
    if len(words) == 1 and _shouty(words[0]) and len(words[0]) <= 3:
        return words[0].upper()
    return " ".join(w.upper() if _is_postnominal(w) and w.isupper() else
                    _case_word(w, i == 0) if _shouty(w) or re.fullmatch(r"(?:[A-Za-z]\.)+", w) else w
                    for i, w in enumerate(words))


def _strip_postnominals(name):
    words = name.split()
    while len(words) > 1 and _is_postnominal(words[-1].strip(",;")):
        words.pop()
        if words:
            words[-1] = words[-1].rstrip(",;")
    return " ".join(words)


def _dates(s):
    """Text inside brackets -> '1903-1992', 'b.1943' ('(1943)' means born), 'fl.1850', or None."""
    s = s.strip()
    years = re.findall(r"\b" + _YEAR + r"\b", s)
    if len(years) >= 2:
        return f"{years[0]}-{years[1]}"
    if len(years) == 1:
        if re.search(r"\bfl", s, re.I):
            return f"fl.{years[0]}"
        if re.fullmatch(r"(?:b\.?|born)?\s*" + _YEAR + r"\s*[-–]?", s, re.I):
            return f"b.{years[0]}"
    return None


def parse_artist(text):
    """'JOHN PIPER (1903-1992)' -> ('John Piper', '1903-1992', None). 'After X' -> note 'After'.
    Drops marks (§), honorifics (Sir) and postnominals (RA, PRA, RI ROI RSMA)."""
    t = _MARKS.sub(" ", clean_text(text)).strip()
    note = dates = None
    m = _PREFIX.match(t)
    if m:
        note, t = PREFIXES[m.group(1).lower()], t[m.end():]
    pm = re.search(r"\(([^)]*)\)", t)
    if pm:
        dates, t = _dates(pm.group(1)), t[:pm.start()] + " " + t[pm.end():]
    else:
        tm = re.search(r"\s" + _YEAR + r"\s*[-–]\s*" + _YEAR + r"\s*$", t)
        if tm:
            dates, t = f"{tm.group(1)}-{tm.group(2)}", t[:tm.start()]
    name = _strip_postnominals(t.strip(" ,.;:-"))
    name = _strip_postnominals(_HONORIFIC.sub("", name).strip(" ,;:-"))
    if name.count(",") == 1:
        last, first = [p.strip() for p in name.split(",")]
        if last and first and not re.search(r"\d", name):
            name = f"{first} {last}"
    if not name or _ANON.search(name):
        return None, dates, note
    return _name_case(name), dates, note


# ---- type / medium ----
def _mixed_type(text):
    if re.search(r"\bpaper\b", text, re.I):
        return "Work on paper"
    if re.search(r"canvas|panel|board", text, re.I):
        return "Painting"
    return "Other"


def classify(*texts):
    """Try each text in order (most reliable first). Returns (type, medium); ('Other','Other') if unknown."""
    for text in texts:
        for typ, medium, rx in _COMPILED:
            if text and rx.search(text):
                return (typ or _mixed_type(text)), medium
    return "Other", "Other"


# ---- year ----
_YEAR_PATTERNS = [
    re.compile(r"\bdated\b\s*(?:[A-Za-z]+\s+){0,3}?(?:c\.?\s*)?(?:\d{1,2}[/.\-]){0,2}(\d{4})\b", re.I),
    re.compile(r"\b(?:c\.?|circa|ca\.?)\s*(\d{4})s?\b", re.I),
    re.compile(r"\b(\d{3}0)s\b"),
    re.compile(r"\((" + _YEAR + r")\)"),
]


def parse_year(*texts):
    """Return (year, matched_text) from the first text that holds a plausible year."""
    for text in texts:
        for rx in _YEAR_PATTERNS:
            for m in rx.finditer(text or ""):
                year = int(m.group(1))
                if 1200 <= year <= datetime.now().year:
                    return year, m.group(0).strip()
    return None, None


# ---- estimate ----
_NUM = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(k\b)?", re.I)


def parse_estimate(text):
    """'£800-1,200' -> (800, 1200); '£1k-1.5k' -> (1000, 1500); single figure -> (n, n); else (None, None)."""
    t = clean_text(text)
    if not t or re.search(r"no estimate|on request|\bPOA\b|unestimated", t, re.I):
        return None, None
    nums = []
    for m in _NUM.finditer(t):
        value = float(m.group(1).replace(",", ""))
        nums.append([value, bool(m.group(2))])
        if len(nums) == 2:
            break
    if not nums:
        return None, None
    if len(nums) == 2 and nums[1][1] and not nums[0][1] and nums[0][0] <= nums[1][0]:
        nums[0][1] = True  # '1-2k' means 1k-2k
    values = [int(round(v * (1000 if k else 1))) for v, k in nums]
    if len(values) == 1:
        values *= 2
    return min(values), max(values)


# ---- dimensions ----
_DIM = re.compile(r"(\d+(?:\.\d+)?(?:\s*(?:cm|mm|in(?:ches)?)\b\.?)?(?:\s*[x×]\s*\d+(?:\.\d+)?(?:\s*(?:cm|mm|in(?:ches)?)\b\.?)?){1,2})", re.I)


def parse_dimensions(*texts):
    found = []
    for text in texts:
        for m in _DIM.finditer(text or ""):
            units = re.findall(r"cm|mm|in", m.group(1), re.I)
            if units:
                nums = re.findall(r"\d+(?:\.\d+)?", m.group(1))
                found.append(" x ".join(nums) + units[-1].lower())
    metric = [d for d in found if d.endswith(("cm", "mm"))]
    return (metric or found or [None])[0]


# ---- helpers ----
def _slug(s):
    return re.sub(r"[^a-z0-9._]+", "-", str(s).lower()).strip("-")


def _truncate(text, limit=MAX_DESC):
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def _int_or_none(v):
    return v if isinstance(v, int) and not isinstance(v, bool) else None


_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def resolve_end(sale_date, *candidates):
    """Last day of a sale: the latest valid date among the candidates, or None if no later than sale_date
    (None = a one-day sale)."""
    ends = [c for c in candidates if isinstance(c, str) and _ISO_DATE.fullmatch(c)]
    end = max(ends, default=None)
    return end if end and end > sale_date else None


def apply_content_policy(lot, house):
    """Enforce the house's content_policy on a finished Lot (a copy is returned). A house with no policy is
    treated as "full"; an unknown value is an error (fails closed rather than leaking images)."""
    policy = house.get("content_policy", "full")
    if policy not in CONTENT_POLICIES:
        raise ValueError(f"unknown content_policy {policy!r} for {house.get('id')}")
    return dict(lot, image_url=None) if policy == "text_only" else lot


def tag(raw_lot, house, sale, collected_at=None):
    """Raw catalogue lot -> SPEC Lot dict. Raises ValueError if lot_number/title/lot_url/sale date are unusable."""
    lot_number = clean_text(raw_lot.get("lot_number"))
    title = clean_text(raw_lot.get("title"))
    lot_url = clean_text(raw_lot.get("lot_url"))
    if not (lot_number and title and lot_url):
        raise ValueError("lot needs lot_number, title and lot_url")
    sale_date = str(sale.get("date") or "")
    if not _ISO_DATE.fullmatch(sale_date):
        raise ValueError(f"bad sale date: {sale_date!r}")

    description_full = clean_text(raw_lot.get("description"))
    medium_detail = clean_text(raw_lot.get("medium_detail")) or None
    artist_text = clean_text(raw_lot.get("artist_text"))
    if not artist_text:
        m = _ARTIST_LEAD.match(description_full)
        artist_text = ((m.group(1) or "") + m.group(2) + " " + m.group(3)) if m else ""
    artist, artist_dates, note = parse_artist(artist_text)

    typ, medium = classify(medium_detail, f"{title} {description_full}")
    if is_non_art(typ, title, medium_detail, description_full):
        raise NotArt(f"not artwork: {title}")

    # Search for a year without the artist's own life dates getting in the way.
    body = description_full.replace(artist_text, " ") if artist_text else description_full
    given_date_text = clean_text(raw_lot.get("date_made_text")) or None
    year, matched = parse_year(given_date_text, medium_detail, body, title)

    low = _int_or_none(raw_lot.get("estimate_low"))
    high = _int_or_none(raw_lot.get("estimate_high"))
    if low is None and high is None:
        low, high = parse_estimate(raw_lot.get("estimate_text"))

    lot = {
        "id": "-".join(_slug(p) for p in (house["id"], sale.get("id"), lot_number)),
        "house_id": house["id"],
        "sale_title": clean_text(sale.get("title")),
        "sale_date": sale_date,
        # a lot page that shows a later day than the sale list (a two-day sale) widens the end date
        "sale_end_date": resolve_end(sale_date, sale.get("end_date"), raw_lot.get("sale_date"), raw_lot.get("sale_end_date")),
        "lot_number": lot_number,
        "title": title,
        "artist": artist,
        "artist_dates": artist_dates,
        "attribution_note": note,
        "type": typ,
        "medium": medium,
        "medium_detail": medium_detail,
        "year_made": year,
        "date_made_text": given_date_text or matched,
        "estimate_low": low,
        "estimate_high": high,
        "dimensions": clean_text(raw_lot.get("dimensions")) or parse_dimensions(medium_detail, description_full, title),
        "description": _truncate(description_full),
        "image_url": clean_text(raw_lot.get("image_url")) or None,
        "lot_url": lot_url,
        "collected_at": collected_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return apply_content_policy(lot, house)
