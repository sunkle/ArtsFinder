"""Playwright checks for the app. Run from anywhere:  python3 app/test/run_tests.py

Self-contained: it builds the app from test/fixture-lots.json into a temp folder (never touching app/dist/),
and shifts every fixture date so the fixture is always "relative to today" (it can never go out of date).
Needs: pip install playwright, and Google Chrome at /usr/bin/google-chrome."""
import json, re, sys, tempfile
from datetime import date, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import build  # app/build.py

SHOTS = ROOT / "test/screens"; SHOTS.mkdir(exist_ok=True)
TMP = tempfile.TemporaryDirectory(prefix="arts-finder-test-")
TODAY = date.today()
iso = lambda d: d.isoformat()


def make_fixture(name="fixture"):
    """Fixture lots with their dates moved so that 'today' sits where 2026-11-23 sat when it was written."""
    data = json.loads((ROOT / "test/fixture-lots.json").read_text(encoding="utf-8"))
    base = date(2026, 11, 23)
    for lot in data["lots"]:
        lot["sale_date"] = iso(TODAY + (date.fromisoformat(lot["sale_date"]) - base))
        lot["sale_end_date"] = None
    harbour = next(l for l in data["lots"] if l["title"] == "Harbour Test")
    harbour["sale_end_date"] = iso(date.fromisoformat(harbour["sale_date"]) + timedelta(days=1))  # a two-day sale
    path = Path(TMP.name) / f"{name}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path, data


def build_to(src, name):
    out = Path(TMP.name) / name
    build.build(src, out)
    return out


def tiny_lot(n, start, end):
    return {"id": f"h-1-{n}", "house_id": "h", "sale_title": "S", "sale_date": iso(start), "sale_end_date": end and iso(end),
            "lot_number": str(n), "title": f"Lot {n}", "artist": None, "artist_dates": None, "attribution_note": None,
            "type": "Painting", "medium": "Oil", "medium_detail": None, "year_made": None, "date_made_text": None,
            "estimate_low": None, "estimate_high": None, "dimensions": None, "description": "", "image_url": None,
            "lot_url": "https://example.com/" + str(n), "collected_at": "2026-11-23T02:00:00Z"}


fixture_path, FIX = make_fixture()
DIST = build_to(fixture_path, "dist")
URL = (DIST / "index.html").as_uri()
fails = []
def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond: fails.append(name)
count = lambda pg: pg.locator("#grid .card").count()
titles = lambda pg: pg.locator("#grid .card h2").all_inner_texts()

with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome")
    for name, size, mobile in (("phone", (375, 812), True), ("ipad", (1024, 1366), False)):
        ctx = b.new_context(viewport={"width": size[0], "height": size[1]}, is_mobile=mobile, has_touch=mobile)
        pg = ctx.new_page(); errs = []
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(URL); pg.wait_for_selector("#grid .card")
        # default: 12 fixture lots, 1 past hidden -> 11
        check(f"{name}: past hidden by default (11)", count(pg) == 11 and "Past Auction Test" not in titles(pg))
        check(f"{name}: count text", pg.inner_text("#count").startswith("11 lots of 12"))
        pg.screenshot(path=str(SHOTS / f"{name}-list.png"))
        if mobile:
            pg.click("#openFilters"); pg.wait_for_timeout(400)
            pg.screenshot(path=str(SHOTS / f"{name}-filters.png"))
        # type filter
        check(f"{name}: chips show counts", pg.inner_text(".chip[data-v='Sculpture']").replace("\n", " ").strip() == "Sculpture 2")
        check(f"{name}: chips with 0 lots are hidden", pg.locator(".chip[data-v='Tempera']").count() == 0 and pg.locator(".chip[data-v='Gouache']").count() == 0)
        pg.click(".chip[data-v='Sculpture']"); check(f"{name}: type=Sculpture (2)", count(pg) == 2)
        pg.click(".chip[data-v='Photograph']"); check(f"{name}: multi type (3)", count(pg) == 3)
        pg.click("#clear"); check(f"{name}: clear restores 11", count(pg) == 11)
        pg.click(".chip[data-v='Oil']"); check(f"{name}: medium Oil (1, past hidden... + poster)", count(pg) == 2)
        pg.click("#clear")
        # house + region
        pg.select_option("select[aria-label='Auction house']", "testhouse-c"); check(f"{name}: house C (4)", count(pg) == 4)
        pg.click("#clear"); pg.select_option("select[aria-label='Region']", "London"); check(f"{name}: region London (4)", count(pg) == 4)
        pg.click("#clear")
        # artist search
        pg.fill("#q", "artist f"); check(f"{name}: artist search", titles(pg) == ["Bronze Test"])
        pg.fill("#q", "harbour"); check(f"{name}: search finds titles", titles(pg) == ["Harbour Test"])
        pg.fill("#q", "bronze"); check(f"{name}: search finds medium detail or title", "Bronze Test" in titles(pg))
        check(f"{name}: search placeholder", pg.get_attribute("#q", "placeholder") == "Artist or title")
        pg.click("#clear"); check(f"{name}: clear empties search", pg.input_value("#q") == "")
        # ranges
        pg.fill("input[aria-label='Year made From']", "1950"); pg.fill("input[aria-label='Year made To']", "1970")
        check(f"{name}: year range", sorted(titles(pg)) == ["Bronze Test", "Harbour Test", "Watercolour Test"])
        pg.click("#clear")
        pg.fill("input[aria-label='Estimate (£) Min']", "1000"); check(f"{name}: estimate min 1000 (2)", sorted(titles(pg)) == ["Bronze Test", "Harbour Test"])
        pg.click("#clear")
        pg.fill("input[aria-label='Auction date From']", iso(TODAY + timedelta(days=17))); pg.fill("input[aria-label='Auction date To']", iso(TODAY + timedelta(days=24)))
        check(f"{name}: date range (4)", count(pg) == 4)
        pg.click("#clear")
        # multi-day sale, iOS zoom, artwork not cropped
        pg.fill("#q", "harbour")
        house_line = pg.locator("#grid .card .house").first.inner_text()
        check(f"{name}: two-day sale shows a range ({house_line!r})", bool(re.search(r"\d+–\d+ \w+ \d{4}|\d+ \w+ – \d+ \w+ \d{4}", house_line)))
        pg.click("#clear")
        small = pg.evaluate("[...document.querySelectorAll('input:not([type=checkbox]),select')].filter(e=>parseFloat(getComputedStyle(e).fontSize)<16).length")
        check(f"{name}: every input/select is at least 16px", small == 0)
        check(f"{name}: images are contained, not cropped", pg.evaluate("getComputedStyle(document.querySelector('.img img')).objectFit") == "contain")
        # original only
        pg.check("text=Original works only"); t = titles(pg)
        check(f"{name}: original-only hides prints/repro", count(pg) == 7 and "Lithograph Test" not in t and "Poster Reproduction After Test" not in t and "Acrylic Test" not in t)
        cards = pg.locator("#grid .card .artist").all_inner_texts()
        check(f"{name}: note shown before artist", any(c.startswith("Circle of Test Artist C") for c in cards))
        pg.click("#clear")
        # show past
        pg.uncheck("text=Hide past auctions"); check(f"{name}: show past (12)", count(pg) == 12)
        pg.click("#clear")
        # sort
        pg.select_option("#sort", "artist"); check(f"{name}: sort artist, nulls last", titles(pg)[0] == "Harbour Test" and titles(pg)[-1] == "Unknown Drawing")
        pg.select_option("#sort", "est"); check(f"{name}: sort estimate", titles(pg)[0] == "Mixed Test")
        pg.select_option("#sort", "year"); check(f"{name}: sort year", titles(pg)[0] == "Lithograph Test")
        pg.select_option("#sort", "date"); check(f"{name}: sort date", titles(pg)[-1] in ("Photo Test", "Mixed Test"))
        if mobile: pg.click("#closeFilters"); pg.wait_for_timeout(350)
        # empty state
        pg.fill("#q", "zzzz"); check(f"{name}: empty state", "No lots match" in pg.inner_text("#grid"))
        pg.screenshot(path=str(SHOTS / f"{name}-empty.png")); pg.click("#grid .empty button"); check(f"{name}: empty-state clear", count(pg) == 11)
        # favourites
        pg.locator(".star").nth(0).click(); pg.locator(".star").nth(2).click()
        pg.click("#favOnly"); check(f"{name}: favourites only (2)", count(pg) == 2)
        pg.reload(); pg.wait_for_selector("#grid .card"); pg.click("#favOnly")
        check(f"{name}: favourites persist after reload (2)", count(pg) == 2)
        pg.screenshot(path=str(SHOTS / f"{name}-favs.png"))
        # no-image band, dimensions, compact view
        pg.click("#favOnly")
        band = pg.locator("#grid .card .img.none").first
        check(f"{name}: no-image card is a slim 48px band", band.bounding_box()["height"] <= 48.5 and "Painting · Acrylic" in pg.locator("#grid .card:has-text('Acrylic Test') .img").inner_text())
        check(f"{name}: dimensions shown on cards", pg.locator("#grid .card:has-text('Acrylic Test') .dims").inner_text() == "40 x 50cm" and pg.locator("#grid .card:has-text('Watercolour Test') .dims").count() == 0)
        pg.click(".seg [data-v=compact]")
        row = pg.locator("#grid .card:not(:has(img))").first
        check(f"{name}: compact rows are short ({row.bounding_box()['height']:.0f}px)", row.bounding_box()["height"] < 85 and count(pg) == 11)
        check(f"{name}: compact row opens lot_url", pg.locator("#grid .card h2 a").first.get_attribute("href").startswith("https://"))
        check(f"{name}: compact tap targets >= 44px", pg.evaluate("[...document.querySelectorAll('.star,.seg .btn,#sort')].every(e=>e.getBoundingClientRect().height>=43.5&&e.getBoundingClientRect().width>=43.5)"))
        check(f"{name}: compact choice remembered", (pg.reload(), pg.wait_for_selector("#grid .card"), pg.evaluate("document.getElementById('grid').classList.contains('compact')"))[2])
        if mobile: pg.screenshot(path=str(SHOTS / "phone-compact.png"))
        pg.click(".seg [data-v=cards]"); check(f"{name}: back to cards", not pg.evaluate("document.getElementById('grid').classList.contains('compact')"))
        # view lot link
        a = pg.locator(".link").first
        check(f"{name}: View lot opens new tab", a.get_attribute("target") == "_blank" and a.get_attribute("href").startswith("https://"))
        check(f"{name}: no console errors", not errs)
        if errs: print(errs)
        ctx.close()
    # dark mode screenshot
    ctx = b.new_context(viewport={"width": 375, "height": 812}, color_scheme="dark", is_mobile=True)
    pg = ctx.new_page(); pg.goto(URL); pg.wait_for_selector("#grid .card"); pg.screenshot(path=str(SHOTS / "phone-dark.png"))
    # localStorage blocked must not break the app
    ctx = b.new_context(); pg = ctx.new_page(); pg.add_init_script("Object.defineProperty(window,'localStorage',{get(){throw new Error('blocked')}})")
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e))); pg.goto(URL); pg.wait_for_selector("#grid .card"); pg.locator(".star").first.click()
    check("localStorage blocked: still works", count(pg) == 11 and not errs)
    # multi-day sales: still shown on their last day, hidden the day after
    tiny = {"generated_at": "2026-11-23T02:00:00Z", "schema_version": 1,
            "houses": [{"id": "h", "name": "H", "town": "T", "region": "R", "website": "https://example.com"}],
            "lots": [tiny_lot(1, TODAY - timedelta(days=1), TODAY + timedelta(days=1)),   # running now
                     tiny_lot(2, TODAY - timedelta(days=2), TODAY - timedelta(days=1)),   # ended yesterday
                     tiny_lot(3, TODAY, None)]}                                          # one day, today
    tiny_path = Path(TMP.name) / "tiny.json"; tiny_path.write_text(json.dumps(tiny))
    pg = b.new_context().new_page(); pg.goto((build_to(tiny_path, "tiny") / "index.html").as_uri()); pg.wait_for_selector("#grid .card")
    check("multi-day sale still running is shown, ended one hidden", sorted(titles(pg)) == ["Lot 1", "Lot 3"])
    pg.uncheck("text=Hide past auctions")
    check("ended sale says it has passed, running one does not", pg.locator("#grid .card:has-text('Lot 2') .past").count() == 1 and pg.locator("#grid .card:has-text('Lot 1') .past").count() == 0)
    # build outputs: noindex, robots.txt, versioned service worker
    html = (DIST / "index.html").read_text(encoding="utf-8")
    sw = (DIST / "sw.js").read_text(encoding="utf-8")
    check("noindex meta in the app", '<meta name="robots" content="noindex,nofollow">' in html)
    check("robots.txt disallows everything", "Disallow: /" in (DIST / "robots.txt").read_text())
    check("service worker cache name is versioned by the build", re.search(r"PREFIX \+ '[0-9a-f]{12}'", sw) is not None and "__BUILD__" not in sw)
    check("types and mediums are embedded from shared/schema.json", '"embedded-schema">{' in html and "const TYPES = [" not in html)
    b.close()
print("\nFAILED:", fails if fails else "none")
