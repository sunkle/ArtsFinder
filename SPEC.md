# Arts Finder: shared spec (v0.x)

Everyone (coder, checker, collector, app) follows this file. Change it here first, never in only one place (DRY).

## Purpose
A personal tool that lists upcoming original art lots from small and medium UK auction houses, filterable on iPhone and iPad.

## Architecture (free to run)
```
collector/  (Python 3.11+, standard library only)
  sources/<platform>.py   one adapter per catalogue platform (the-saleroom, easyLive, bidpath, ...)
  houses.json             which houses to collect, each naming its adapter and URLs (config, not code)
  tagger.py               turns raw lot text into the fixed fields below (rules first; AI optional later)
  run.py                  loops houses -> adapter -> tagger -> validate -> writes data/lots.json
app/
  index.html              single-file web app (PWA): reads lots.json, filters, sorts. No build step.
  manifest.webmanifest, sw.js, icon
.github/workflows/collect.yml   nightly job: run collector, commit data/lots.json, publish to GitHub Pages
```
Rules: adapters only fetch and parse; all clean-up lives in tagger.py; field names come only from this file.

## Polite collecting (non-negotiable)
- Obey robots.txt. One request at a time, at least 3 seconds apart. Run once a night. Honest User-Agent naming the project.
- The site is **public but unlisted** (user decision 25 Nov 2026): anyone with the link can open it, but it is never advertised, indexed or linked from elsewhere. Store a short description (max 300 chars) and link back to the lot page; images are linked, never copied.
- If a site's terms forbid automated access, or forbid copying or using its catalogue text, or cannot be read, the house is not collected at all: `"enabled": false` in houses.json with `disabled_reason` quoting the docs/RULES.md verdict.
- Each house has a `content_policy` (see "houses.json flags"). The tagger and run.py enforce it; adapters just fetch and parse.

## Lot record (data/lots.json)
File shape: `{"generated_at": ISO datetime, "schema_version": 1, "houses": [House], "lots": [Lot]}`

House: `{"id": "roseberys", "name": "Roseberys", "town": "London", "region": "London", "website": "https://..."}`

Lot (null where unknown, never invent):
| field | type | example |
|---|---|---|
| id | string, `<house_id>-<sale_id>-<lot_number>` | `roseberys-1234-56` |
| house_id | string | `roseberys` |
| sale_title | string | `Modern British Art` |
| sale_date | `YYYY-MM-DD` (first day) | `2026-12-03` |
| sale_end_date | `YYYY-MM-DD` last day of a multi-day sale, or null (= same as sale_date). Must be after sale_date. "Past" checks and "Hide past auctions" use it (fallback sale_date) | `2026-12-04` |
| lot_number | string | `56` |
| title | string | `Harbour at St Ives` |
| artist | string or null, as "First Last" | `John Piper` |
| artist_dates | string or null | `1903-1992` |
| attribution_note | string or null: `Attributed to`, `Ascribed to`, `Circle of`, `After`, `Manner of`, `Follower of`, `Studio of`, `School of`, `Style of`, `Workshop of`, `Imitator of`. "Original works only" hides any lot where it is `After` | `After` |
| type | one of TYPES | `Painting` |
| medium | one of MEDIUMS | `Oil` |
| medium_detail | string or null, as catalogued | `oil on canvas board` |
| year_made | integer or null (best single year; circa -> that year) | `1952` |
| date_made_text | string or null, as catalogued | `c.1950s` |
| estimate_low / estimate_high | integer GBP or null | `800` / `1200` |
| dimensions | string or null | `40 x 50cm` |
| description | string, max 300 chars | |
| image_url | string or null (link only) | |
| lot_url | string (required) | |
| collected_at | ISO datetime | |

Lists below live in `shared/schema.json` (read by `collector/schema.py`, embedded in the app by `app/build.py`). Never copy them elsewhere.

TYPES: `Painting`, `Work on paper` (watercolour, drawing, pastel, gouache), `Print`, `Sculpture`, `Photograph`, `Other`
MEDIUMS: `Oil`, `Acrylic`, `Watercolour`, `Gouache`, `Pastel`, `Pencil/Charcoal/Ink`, `Mixed media`, `Tempera`, `Etching/Engraving`, `Lithograph`, `Screenprint`, `Woodcut/Linocut`, `Bronze`, `Stone/Marble`, `Wood`, `Ceramic`, `Other metal`, `Other`

## Lots that are skipped
Not artwork: if the title or medium contains a word from `non_art_words` in `shared/rules.json` (ring, jewellery, watch, pottery, vase, bowl, ...), the tagger skips the lot. It never skips a Painting, Work on paper, Print or Photograph, nor a Sculpture whose text says sculpture or maquette (so a ceramic sculpture by an artist stays). Also skipped: a lot of type `Other` with no artist life dates and no sculpture word (furniture, silver, records, programmes, tins, memorabilia, clocks ...), so an undated mixed-sale lot never shows up as "Other". A dated artist's pot (e.g. Magdalene Odundo, b.1950) stays. A lot whose lot page could not be read is left out and retried the next run.

## houses.json flags
`enabled`, `crawl_delay`, `disabled_reason`, `content_policy` (required on every house: `"full"` = description + link to the image; `"text_only"` = description only, `image_url` is always null; a missing value fails closed to `"text_only"` with a warning; any other value is an error and the house's lots are rejected), plus `keep_existing_lots` (true = keep the stored lots of a house switched off only because its adapter is not written yet, until their sales end). `api_allowed` (default false: `Fetcher.post_json` refuses any URL under `/api` or containing `search` unless it is `true`, and always applies robots.txt to the full URL including its query). `the-saleroom.com` and `easyliveauction.com` (and their subdomains) are refused by `collector/fetcher.py` whatever houses.json says.

## App behaviour
- Filters: type, medium, search box (artist or title), house, region, auction date range, year made range, estimate range, "original works only" (hides Print and anything marked reproduction/after/print/poster), "hide past auctions" (on by default).
- Sort: auction date (default, soonest first), year made, estimate, artist A-Z.
- Filter chips show how many lots each has and are hidden when it is 0. Card: image (lazy, if any, shown whole, never cropped), title, artist + dates, type/medium, year, estimate, house, auction date (a range such as "26–27 Nov 2026" for multi-day sales), link "View lot" (opens house page).
- Mobile first (iPhone width 375px), works offline after first load, dark mode follows the phone, "Add to Home Screen" works.
- Favourites (star) kept on the device (localStorage, wrapped in try/catch).
- The built site is public but unlisted on free hosting: it has `<meta name="robots" content="noindex,nofollow">` and a `robots.txt` with `Disallow: /`. All inputs are at least 16px so iOS Safari does not zoom. The service worker cache name carries a build hash (network-first for the page and data).
