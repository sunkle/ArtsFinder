"""Nightly collector: houses.json -> adapters -> tagger -> validate -> data/lots.json.
Usage (from the repo root):  python3 -m collector.run [--only house_id] [--out data/lots.json] [--diagnose]

--diagnose is a quick dry run: for each enabled house it saves its first calendar, sale and lot page
to diagnose/<house>/ (so the real markup can be seen), reads only a couple of lots, and writes NO data."""
import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone

from . import validate
from .fetcher import Fetcher
from .schema import HOUSE_FIELDS, SCHEMA_VERSION, last_day
from .sources import AdapterNotAvailable, get_adapter
from .tagger import NotArt, apply_content_policy, parse_estimate, resolve_end, tag

log = logging.getLogger("collector")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def uk_today():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/London")).strftime("%Y-%m-%d")
    except Exception:  # no tz database: fall back to UTC
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def reuse_stored(stored, raw, sale, house=None):
    """A lot we already hold: keep the stored record (title included: it was cleaned from the lot page),
    refresh only what the listing is good for: the estimate and the sale dates."""
    lot = dict(stored, sale_title=sale.get("title") or stored["sale_title"], sale_date=sale["date"])
    lot["sale_end_date"] = resolve_end(sale["date"], sale.get("end_date"), stored.get("sale_end_date"))
    low, high = parse_estimate(raw.get("estimate_text"))
    if low is not None:
        lot["estimate_low"], lot["estimate_high"] = low, high
    return apply_content_policy(lot, house or {})  # a house switched to text_only loses stored image links too


def collect_house(house, fetcher, today, now, diagnose_dir=None, previous=()):
    """Run one house. Returns (lots, rejected_count). Raises on adapter/network failure."""
    adapter = get_adapter(house["adapter"])(fetcher)
    adapter.diagnose_dir = diagnose_dir
    adapter.previous_lots = [l for l in previous if l.get("house_id") == house["id"]]
    lots, rejected = [], 0
    sales = list(adapter.list_sales(house))
    log.info("%s: found %d sale links", house["id"], len(sales))
    lot_links = 0
    for sale in sales:
        if not diagnose_dir and (not sale.get("date") or (sale.get("end_date") or sale["date"]) < today):
            continue  # past (or undated) sale: do not even fetch its lots
        raws = list(adapter.list_lots(house, sale))
        lot_links += len(raws)
        log.info("%s: sale %s (%s): %d lot links", house["id"], sale.get("id"), sale.get("url"), len(raws))
        for raw in raws:
            try:
                if "_stored" in raw:
                    lot = reuse_stored(raw["_stored"], raw, sale, house)
                else:
                    lot = tag(raw, house, sale, collected_at=now)
                problems = validate.validate_lot(lot)
                if problems:
                    raise ValueError(problems[0])
                lots.append(lot)
            except NotArt as err:
                rejected += 1
                log.debug("%s: skipped: %s", house["id"], err)
            except ValueError as err:
                rejected += 1
                log.debug("%s: rejected lot: %s", house["id"], err)
    log.info("%s: %d sale links, %d lot links in total", house["id"], len(sales), lot_links)
    s = adapter.stats
    log.info("%s: lot pages: %d new, %d reused, %d deferred to later runs", house["id"], s["new"], s["reused"], s["deferred"])
    return lots, rejected


def merge_lots(previous, results, active_ids, today):
    """Combine tonight's results with yesterday's file.

    results: {house_id: [lots]} for houses that worked; a house missing from it (or with an empty
    list when it had lots before) keeps its previous lots, which keep their old collected_at.
    Lots of houses no longer active are dropped, as are sales that have ended (sale_end_date, or sale_date
    for a one-day sale) and duplicate ids."""
    prev_by_house = {}
    for lot in previous:
        prev_by_house.setdefault(lot.get("house_id"), []).append(lot)
    merged, seen = [], set()
    for house_id in sorted(active_ids):
        fresh = results.get(house_id)
        old = [l for l in prev_by_house.get(house_id, []) if last_day(l) >= today]
        chosen = fresh if fresh else old
        for lot in chosen:
            if last_day(lot) >= today and lot["id"] not in seen:
                seen.add(lot["id"])
                merged.append(lot)
    return merged


def build_output(houses, lots, now):
    used = {l["house_id"] for l in lots}
    return {
        "generated_at": now,
        "schema_version": SCHEMA_VERSION,
        "houses": [{k: h[k] for k in HOUSE_FIELDS} for h in houses if h["id"] in used],
        "lots": lots,
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--houses", default=os.path.join(ROOT, "collector", "houses.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "lots.json"))
    ap.add_argument("--only", help="run just this house id")
    ap.add_argument("--diagnose", action="store_true",
                    help="save sample pages to diagnose/<house>/ and write no data (see top of file)")
    ap.add_argument("--diagnose-dir", default=os.path.join(ROOT, "diagnose"))
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    houses = load_json(args.houses, {}).get("houses", [])
    active = [h for h in houses if h.get("enabled") and (not args.only or h["id"] == args.only)]
    previous = load_json(args.out, {}).get("lots", [])
    today, now = uk_today(), datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    fetcher = Fetcher()
    try:
        return _run(args, houses, active, previous, today, now, fetcher)
    finally:
        fetcher.close()


def _run(args, houses, active, previous, today, now, fetcher):

    results = {}
    for house in active:
        try:
            lots, rejected = collect_house(house, fetcher, today, now,
                                           diagnose_dir=args.diagnose_dir if args.diagnose else None,
                                           previous=previous)
            if lots:
                results[house["id"]] = lots
            note = "" if lots else " (nothing found: keeping previous lots)"
            log.info("%s: %d lots, %d rejected%s", house["id"], len(lots), rejected, note)
        except AdapterNotAvailable as err:
            log.info("%s: skipped, %s", house["id"], err)
        except Exception as err:  # one house failing must never stop the others
            log.warning("%s: FAILED (%s: %s), keeping previous lots", house["id"], type(err).__name__, err,
                        exc_info=True)

    if args.diagnose:
        log.info("Diagnose run: sample pages saved under %s; no data written", args.diagnose_dir)
        return 0

    # With --only, other houses just carry over from the previous file.
    # A house switched off only because its adapter is missing (keep_existing_lots) keeps its stored lots
    # until their sales end; any other switched-off house loses its lots.
    keep_ids = {h["id"] for h in houses if h.get("enabled") or h.get("keep_existing_lots")}
    merged = merge_lots(previous, results, keep_ids, today)
    output = build_output(houses, merged, now)
    problems = validate.validate_data(output)
    if problems:
        log.error("Refusing to write: %s", problems[:5])
        return 1
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    tmp = args.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=1)
    os.replace(tmp, args.out)
    log.info("Wrote %s: %d lots from %d houses", args.out, len(merged), len(output["houses"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
