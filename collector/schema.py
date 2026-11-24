"""The one place that holds the SPEC.md constants. Everything else imports from here (DRY).
TYPES, MEDIUMS and attribution notes live in shared/schema.json (the app reads the same file)."""
import json
import os

SCHEMA_VERSION = 1
MAX_DESC = 300

SHARED_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shared")


def load_shared(name):
    """Read one of the shared/*.json files (also embedded into the app by app/build.py)."""
    with open(os.path.join(SHARED_DIR, name), encoding="utf-8") as f:
        return json.load(f)


_SCHEMA = load_shared("schema.json")
TYPES = _SCHEMA["types"]
MEDIUMS = _SCHEMA["mediums"]
ATTRIBUTION_NOTES = _SCHEMA["attribution_notes"]

HOUSE_FIELDS = ["id", "name", "town", "region", "website"]

LOT_FIELDS = [
    "id", "house_id", "sale_title", "sale_date", "sale_end_date", "lot_number", "title", "artist",
    "artist_dates", "attribution_note", "type", "medium", "medium_detail", "year_made",
    "date_made_text", "estimate_low", "estimate_high", "dimensions", "description",
    "image_url", "lot_url", "collected_at",
]
# Fields that may be missing entirely (older data files).
OPTIONAL_LOT_FIELDS = {"attribution_note", "sale_end_date"}


def last_day(lot):
    """The last day a lot's sale runs: sale_end_date, or sale_date for a one-day sale (YYYY-MM-DD strings)."""
    return lot.get("sale_end_date") or lot.get("sale_date") or ""
