"""Checks a lots.json against SPEC.md. Used by run.py and the tests.
CLI: python3 -m collector.validate data/lots.json"""
import json
import re
import sys
from datetime import date, datetime

from .schema import ATTRIBUTION_NOTES, HOUSE_FIELDS, LOT_FIELDS, MAX_DESC, MEDIUMS, OPTIONAL_LOT_FIELDS, SCHEMA_VERSION, TYPES

REQUIRED_STR = ["id", "house_id", "sale_title", "sale_date", "lot_number", "title", "type", "medium",
                "description", "lot_url", "collected_at"]
NULLABLE_STR = ["artist", "artist_dates", "attribution_note", "medium_detail", "date_made_text",
                "dimensions", "image_url", "sale_end_date"]


def _is_date(s):
    try:
        return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", s)) and bool(date.fromisoformat(s))
    except (TypeError, ValueError):
        return False


def _is_datetime(s):
    try:
        return isinstance(s, str) and bool(datetime.fromisoformat(s))
    except ValueError:
        return False


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def validate_lot(lot):
    """Return a list of problems (empty list = valid)."""
    if not isinstance(lot, dict):
        return ["lot is not an object"]
    errs = []
    missing = [f for f in LOT_FIELDS if f not in lot and f not in OPTIONAL_LOT_FIELDS]
    extra = [f for f in lot if f not in LOT_FIELDS]
    if missing:
        errs.append(f"missing fields: {missing}")
    if extra:
        errs.append(f"unknown fields: {extra}")
    for f in REQUIRED_STR:
        if f in lot and not (isinstance(lot[f], str) and lot[f].strip()) and f != "description":
            errs.append(f"{f} must be a non-empty string")
    for f in NULLABLE_STR:
        if lot.get(f) is not None and not isinstance(lot[f], str):
            errs.append(f"{f} must be a string or null")
    if not isinstance(lot.get("description"), str):
        errs.append("description must be a string")
    elif len(lot["description"]) > MAX_DESC:
        errs.append(f"description longer than {MAX_DESC}")
    if lot.get("type") not in TYPES:
        errs.append(f"type not allowed: {lot.get('type')!r}")
    if lot.get("medium") not in MEDIUMS:
        errs.append(f"medium not allowed: {lot.get('medium')!r}")
    if "sale_date" in lot and not _is_date(lot["sale_date"]):
        errs.append("sale_date must be a real YYYY-MM-DD date")
    end = lot.get("sale_end_date")
    if end is not None and not (isinstance(end, str) and _is_date(end)):
        errs.append("sale_end_date must be a real YYYY-MM-DD date or null")
    elif end is not None and _is_date(lot.get("sale_date")) and end <= lot["sale_date"]:
        errs.append("sale_end_date must be after sale_date (use null for a one-day sale)")
    if lot.get("attribution_note") is not None and lot["attribution_note"] not in ATTRIBUTION_NOTES:
        errs.append(f"attribution_note not allowed: {lot['attribution_note']!r}")
    if "collected_at" in lot and not _is_datetime(lot["collected_at"]):
        errs.append("collected_at must be an ISO datetime")
    for f in ("year_made", "estimate_low", "estimate_high"):
        if lot.get(f) is not None and not _is_int(lot[f]):
            errs.append(f"{f} must be an integer or null")
    y = lot.get("year_made")
    if _is_int(y) and not 1000 <= y <= 2100:
        errs.append("year_made out of range")
    lo, hi = lot.get("estimate_low"), lot.get("estimate_high")
    if _is_int(lo) and _is_int(hi) and lo > hi:
        errs.append("estimate_low is above estimate_high")
    if _is_int(lo) and lo < 0:
        errs.append("estimate_low is negative")
    if isinstance(lot.get("lot_url"), str) and not lot["lot_url"].startswith(("http://", "https://")):
        errs.append("lot_url must be an http(s) link")
    if isinstance(lot.get("image_url"), str) and not lot["image_url"].startswith(("http://", "https://")):
        errs.append("image_url must be an http(s) link or null")
    if isinstance(lot.get("id"), str) and isinstance(lot.get("house_id"), str) \
            and not lot["id"].startswith(lot["house_id"] + "-"):
        errs.append("id must start with '<house_id>-'")
    return errs


def validate_data(data):
    """Check a whole lots.json (already loaded). Returns a list of problems."""
    if not isinstance(data, dict):
        return ["file is not an object"]
    errs = []
    if data.get("schema_version") != SCHEMA_VERSION:
        errs.append(f"schema_version must be {SCHEMA_VERSION}")
    if not _is_datetime(data.get("generated_at")):
        errs.append("generated_at must be an ISO datetime")
    houses, lots = data.get("houses"), data.get("lots")
    if not isinstance(houses, list) or not isinstance(lots, list):
        return errs + ["houses and lots must be lists"]
    house_ids = set()
    for i, h in enumerate(houses):
        if not isinstance(h, dict) or any(not isinstance(h.get(f), str) or not h[f] for f in HOUSE_FIELDS):
            errs.append(f"houses[{i}] needs non-empty string fields {HOUSE_FIELDS}")
        else:
            house_ids.add(h["id"])
    seen = set()
    for i, lot in enumerate(lots):
        errs += [f"lots[{i}] {e}" for e in validate_lot(lot)]
        if isinstance(lot, dict):
            if lot.get("id") in seen:
                errs.append(f"lots[{i}] duplicate id {lot.get('id')}")
            seen.add(lot.get("id"))
            if lot.get("house_id") not in house_ids:
                errs.append(f"lots[{i}] house_id {lot.get('house_id')!r} not in houses")
    return errs


def main(argv=None):
    path = (argv or sys.argv[1:] or ["data/lots.json"])[0]
    with open(path, encoding="utf-8") as f:
        errs = validate_data(json.load(f))
    for e in errs[:50]:
        print(e)
    print("OK" if not errs else f"{len(errs)} problem(s)")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
