# Review: branch `v0.4-adapters` (checker, 25 Nov 2026)

Scope: `git diff origin/main...v0.4-adapters` (2 commits, 52 files), SPEC.md, docs/RULES.md (incl. "Probe round (25 Nov 2026)" + Decision), real pages in `/home/claude/deep1/probe-deep/`. Offline only, nothing committed.

## What was run
- `python3 -m unittest discover collector/tests`: **196 tests, OK**.
- `python3 app/test/run_tests.py`: **all PASS**.
- Offline end-to-end (scripts in `/home/claude/review-scripts/`): the real `Fetcher` with its opener swapped for one that serves the deep-probe pages by URL (404 for the rest), fake clock. `run.collect_house` for hansons, peterfrancis, fieldings, gorringes, lawrences, rogersjones, duggleby, then a full `run.main` against a copy of `data/lots.json`.
- Saved lot pages pushed through `parse_lot` + `tag` (fieldings x3, peter francis x3, lawrences x2).

### Results in short
- **0 lots from every house offline.** That is expected: the probe never saved a current sale listing that holds lot links. Hansons sale pages were not saved. The Peter Francis sale page has no lots online yet. The Gorringe's `searchresults.asp`, Lawrences `fs<code>/`, Rogers Jones catalogue and Duggleby JSON were never saved. Fieldings' houses.json calendar (`auctions.fieldingsauctioneers.co.uk/`) was never saved. The main-site calendar has dates without a year, so the reader skips every card.
- Calendars parse well. Hansons: 15 cards, 4 wanted. Gorringe's: 2 wanted (011226 "Art & Design Post 1880" with a catalogue, 020327 without). Lawrences: 3 wanted, dates resolved (Winter 20th C 11 Dec, Winter Fine Art 9–10 Feb, Summer 15–16 Jun). Rogers Jones: 6 wanted, only "Chester Monthly" (1 Dec) has a catalogue.
- **No wipe:** the full run wrote 75 lots (lays 49, gildings 15, gorringes 11), the same as before. Empty houses keep their previous lots. Bot-challenge houses keep theirs via `keep_existing_lots`.
- Politeness: every request went through `Fetcher`, robots.txt was asked first for each host, and gaps were ≥3 s (10 s for Gorringe's). The Duggleby call was a `POST`.
- **Lot tagging on real pages (the big finding):**

| Page | Came out as | Should be |
|---|---|---|
| Fieldings 179 "Queen – signed tour programme" | kept, Other/Other | dropped (memorabilia) |
| Fieldings 74 "The Beatles – Sgt. Peppers…" | kept, artist "The Beatles", **title "Sgt"** | dropped |
| Fieldings 684 biscuit tin | kept, Other/Other | dropped |
| Peter Francis 609 walnut cabinet | kept, Other/Other | dropped |
| Peter Francis 294 bag of coins | kept, Other/Other, year_made 1892 | dropped |
| Peter Francis 421 gold pocket watch | dropped (NotArt) | ok |
| Lawrences 1194 diamond necklace | dropped (NotArt) | ok |
| Lawrences 27 Odundo "Terracotta Vessel, 1985" | Magdalene Odundo, b.1950, Other/Ceramic, £5,000–7,000 | ok, but year_made is null (should be 1985) |
| Gardiner fixture: Paul Storr silver, coffee pot, salver | would be fetched and kept as Other | dropped |

The listed houses all collect *mixed* sales on purpose ("antiques", "collectors", "interiors", "monthly"). The whitelabel docstring says "the tagger drops the non-art lots", but it does not: anything not on the short `non_art_words` list is published as type Other. On the public site this means furniture, silver, records and memorabilia. Today's `data/lots.json` has 0 "Other" lots, so this is new with v0.4.

## Rules check
- Bot-challenge houses (Lay's, Gildings, A&G, Mallams, McTear's, Halls) are off with `keep_existing_lots`. OK.
- Terms-forbid houses (Mellors & Kirk, Trevanion, Serrell, Morgan Evans, Gardiner Houlgate) are off and their reasons quote the clauses. Ross's is off (terms unreadable). OK.
- On: Hansons, Fieldings, Peter Francis, Gorringe's, Lawrences, Duggleby, Rogers Jones, all `full`. Morphets is on, but its adapter `easylive` is not written, so it is skipped. This matches the Decision list.
- No house is `text_only` and enabled. No reviewed house has an image-only ban, so that is consistent.
- the-saleroom block: intact. `check_not_blocked` runs in `_fetch` and in `_request`, and there is a test for `post_json` too.
- Every network call goes through `Fetcher` (grep: no urllib/socket use outside fetcher.py). `post_json` gets robots.txt, throttle, retries, cache and the honest UA, with no cookies or tokens. Technically sound.
- **Conflicts found:** see must-fix 1 and 2.

## MUST-FIX (before merging or running on the public site)
1. **Junk "Other" lots get published.** `collector/tagger.py` `tag()`: after `is_non_art`, raise `NotArt` when `typ == "Other"` and there is no `artist_dates` and no sculpture word. That keeps the Odundo pot and drops the cabinet, coins, silver and memorabilia. Update the SPEC.md "Lots that are skipped" line first (and `_worth_fetching` follows automatically).
2. **Fieldings and Peter Francis: nobody has read their terms.** In `collector/houses.json` + `docs/RULES.md`, the RULES table still says "Not checked (low value) / Unclear", and the Decision says "terms not read → off". Either read `/terms-and-conditions-of-business` and `/terms-and-conditions` and update the rows, or set `enabled:false` until someone does. The user has to confirm, because the Decision list and the Decision rule disagree.
3. **Duggleby `/api` use is not cleared in RULES.md.** `docs/RULES.md` Recommendation 4 says "never use search, `/api`, `/rss`". `FilterBidItems` is the site's search endpoint (SearchText/Filters), and its robots.txt blocks search query strings. A POST only side-steps the query-string rule. Add an explicit RULES.md line: user-approved, robots allows `/api/Auctions/*`, same data as the public page, one request per 800 lots. Until then set `duggleby` `enabled:false`.
4. **Diagnose cannot fill the UNVERIFIED gaps in several cases.** Exactly what is missing:
   - a. `gorringes.py` / `rogersjones.py` / `lawrences.py` / `whitelabel.py` `list_sales`: in diagnose they keep `sales[:1]`. The slice is taken *before* sorting, and it can pick a sale with no catalogue (`url None`), or no lots yet (Peter Francis today). Then no sale or lot page is saved. Fix: in diagnose, keep the first wanted sale that has a `url`, and let `fetch_lots` try the next sale until one `lot` snapshot exists.
   - b. `gorringes.py` `list_lots` never fetches `sale["url"]` (the real, verified "View Lots" page `auction-catalog/<code>`). It only fetches the guessed `searchresults.asp`. If that 404s, diagnose saves nothing. Fix: in diagnose, also `fetch` + `snapshot(house, "catalog", sale["url"])`.
   - c. `lawrences.py` `list_lots` never fetches the Auctionet event page (`sale["url"]`). It only fetches the guessed `fs<code>/` (404 → nothing saved). Fix: in diagnose, snapshot `sale["url"]` when present, and also try `general-sales` as well as `fine-art-sales`.
   - d. `base.py` `fetch_json`: nothing is saved when the answer is not JSON (an HTML error page, a token/CSRF wall, 403), which is the most likely failure. Duggleby saves `repr()` of 2 parsed rows as `calendar.html`. Fix: snapshot the raw response text inside `fetch_json` (kind `calendar.json` / `sale.json`) before `json.loads`, and in diagnose fetch one `ItemLink` lot page and the HTML sale page `/auctions/<n>/`.
   - e. Fieldings: `whitelabel` only saves the first calendar that loads. That is fine, but note the probe never saw `auctions.fieldingsauctioneers.co.uk/`. If it 404s, `/auctions/` is saved instead.
5. **Title cut at abbreviations.** `whitelabel.py` `_headline` (also used by `duggleby.py`) splits on `". "`. Real page: "The Beatles - Sgt. Peppers…" gives title "Sgt", and "John Piper - St. Ives…" would give "St". Fix: do not split after a 1–3-letter word or capital initial (`(?<!\b[A-Z][a-z]{0,2})\.\s`).

## SHOULD-FIX
1. `collector/tagger.py` KEYWORDS: "Sepia wash on paper" → Other/Other (also "pen and wash", "brown wash", "wash drawing"). Add `\bwash\b|\bsepia\b|\bpen\b|drawing` to the `("Work on paper","Pencil/Charcoal/Ink")` row, and in `classify` fall back to `("Work on paper","Other")` when the text says `on paper`. Add tests.
2. `collector/tagger.py` `_YEAR_PATTERNS`: a trailing year in a title ("Terracotta Vessel, 1985") is missed. Add `,\s*(1[89]\d\d|20\d\d)\s*$` for the title only. The coin bag also got year_made 1892 from "dated 1892": fine once must-fix 1 drops it.
3. Risk of losing data in `collector/run.py` `merge_lots`: any non-empty fresh result replaces *all* old lots of a house. With the UNVERIFIED Gorringe's/Rogers Jones readers, one bad listing (e.g. 2 junk links) would replace the 11 good Gorringe's lots. Fix: if fresh has fewer than half the still-current old lots, keep the union for that night and log a warning.
4. `collector/fetcher.py` `BLOCKED_HOSTS`: RULES.md says never fetch `easyliveauction.com` until its terms are read. The whitelabel pages are full of `whitelabel.easyliveauction.com` links. Add it to `BLOCKED_HOSTS` (image *links* to `content.easyliveauction.com` are not fetched, so they stay fine).
5. `schema/tagger` `apply_content_policy`: a missing `content_policy` is treated as `"full"`, but SPEC says it is required. Fail closed instead (`house["content_policy"]`, or `text_only` + warning), and add a houses.json test: every house has a valid policy, and no enabled house has "bot challenge" in its reason or a the-saleroom website.
6. `docs/RULES.md` Lawrences row: "other use of the document needs permission" reads close to the Serrell/Trevanion clause that led to those two being dropped. Ask the user to confirm Lawrences stays "full".
7. `whitelabel.py` / `rogersjones.py` / `duggleby.py` sale filters: mixed "monthly / antiques / collectors" sales are let in. After must-fix 1 this is fine, but each one costs lot-page requests (150/night budget). Consider `max_new_lot_pages` 60 for the mixed-sale houses.

## NICE-TO-HAVE (DRY / quality)
1. `_has_class(node, name)` is copied into gorringes.py, lawrences.py and rogersjones.py: add `Node.has_class_word()` to `htmlutil.py` and use it.
2. The same "for cal_url in calendar_urls: try fetch / snapshot / parse" loop appears in whitelabel, rogersjones and lawrences (`_safe_fetch`): move a `read_calendars(house, default_urls, parse)` into `base.py`.
3. Artist/title splitting lives in 4 regexes (`whitelabel._ARTIST_TITLE`, `lawrences._ARTIST_TITLE`, `duggleby._ARTIST_LEAD`, `tagger._ARTIST_LEAD`), and `lawrences.tidy_caps` is clean-up. SPEC says clean-up lives in tagger.py, so move them there (`tagger.split_artist_title`). duggleby.py then no longer imports `WhiteLabelAdapter` private statics.
4. `whitelabel.py`: `_stored_key` and `_lot_key` are the same thing. Keep one.
5. `fetcher.py`: the HTTPError, network-error and cache log lines still say "GET" for POSTs. Use `request.get_method()`.
6. `whitelabel.py` docstring says the second hex is a per-sale day id, but probe pages show it is shared across sales (day-1 / day-2 id per house). The grouping still works because the key is `(auction, day)`. Fix the comment.
7. houses.json `notes`: document `sale_include_extra` and the duggleby/lawrences/gorringes/rogersjones options in one line each (the options now live only in the adapter docstrings).
