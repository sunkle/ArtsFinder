# Arts Finder

A personal web page that lists upcoming original art at small UK auction houses. Every night a free
robot on GitHub visits the houses' public catalogue pages (politely: it obeys robots.txt, goes slowly
and says who it is), tidies the lots into one list, and publishes the page. You open it on your iPhone.

The site is public but unlisted: anyone with the link can open it, but it is not advertised or indexed.
It stores a short description and a link back to each lot, and links to images instead of copying them.
Houses whose terms forbid copying or using their catalogue text are not collected at all.

## What to expect at first

Coverage is thin until more adapters land. Hansons, Fieldings and Peter Francis are collected through the
white-label catalogue reader (written from real pages, see "Which house needs which adapter"). Lay's, Gildings,
Anderson & Garland and the other GoAuction houses are switched off (their sites challenge automated clients);
their stored lots stay until the sales end. Gorringe's, Lawrences, David Duggleby, Rogers Jones and Morphets
need their own readers, which are not all written yet. Some houses have no art sale online for weeks (Lay's
current sale ends 27 Nov; Anderson & Garland's art auction is about 17 Dec). So the page will often show
only a few dozen lots, and some days almost none. That is the tool working, not broken. Each new reader
adds a house.

Lots already stored for a house whose reader is missing (Gorringe's) are kept until their sale ends.

## Set it up (free, about 15 minutes)

1. **Make a GitHub account.** In Safari go to github.com and choose Sign up. Verify your email.
2. **Understand that the site will be public.** Free GitHub Pages hosting needs a **public** repository.
   That means the web page, the list of lots (`lots.json`) and the code can be seen by anyone who has
   the link. They are not secret, only hard to find: the page asks search engines not to list it
   (`noindex` and a `robots.txt` that says `Disallow: /`), but that is a request, not a lock. There is
   nothing personal in it (your favourites stay on your phone). If you want it private, read
   "Keeping it private" below before you carry on.
3. **Put the files into a GitHub repository.** Safari on iPhone cannot upload folders, so do not try to
   upload the files by hand there. Pick one:
   - **Recommended: Claude does it for you.** Connect your GitHub account to Claude when asked. Claude
     then creates the `arts-finder` repository and pushes all the files, including the hidden `.github`
     folder that holds the nightly job. You do nothing else for this step.
   - **Fallback, on a computer:** make a new empty public repository called `arts-finder` on github.com,
     unzip the Arts Finder zip, and drag the contents (including the hidden `.github` folder) into the
     "uploading an existing file" page. Or use `git` if you know it.
   - **Fallback, on the iPhone:** install the free **Working Copy** app. Clone your empty repository
     into it, use Import to bring in the unzipped files (make sure `.github` comes too), then Commit and
     Push. Check on github.com that `.github/workflows/collect.yml` is in the repository.
4. **Turn on Pages.** Settings, then Pages. Under Build and deployment, set **Source: GitHub Actions**.
5. **Run it the first time.** Tap Actions, then "Collect lots and publish" in the list, then Run workflow,
   then the green Run workflow button. Wait a few minutes until it shows a green tick. (A red cross means
   tap it and read the message, or send it to Claude.)
6. **Open your site.** Settings, then Pages shows the address, like `https://YOURNAME.github.io/arts-finder/`.
   Open it in Safari, tap the Share button, then **Add to Home Screen**.

After that it updates itself every night at about 02:17 UK time. You can also run it by hand any time
(step 5). If GitHub is slow and starts the nightly run after 03:00 UK time, that night is skipped; the
next night catches up.

**It can switch itself off.** GitHub turns off scheduled jobs in a repository that has had no activity for
60 days. The job saves `data/lots.json` whenever the lots change, which counts as activity, but a quiet
stretch could still trip it. If the page stops updating: open the repo, tap Actions, tap "Collect lots and
publish", and tap **Enable workflow** if you see it. Then Run workflow once.

## Keeping it private

Free GitHub Pages is public. If that is not acceptable, these keep the page private. They are listed
for you to choose from; this project does not pick one.

- **GitHub Pro** (paid, a few pounds a month): lets Pages be served from a **private** repository, and
  the site can then be limited to people you invite.
- **Cloudflare Pages + Cloudflare Access** (free for one user): the site is hosted at Cloudflare and Access
  asks for a login (for example a one-time code sent to your email) before showing anything. The repository
  can stay private. Needs a one-off setup and the workflow changed to upload the built `app/dist` folder
  to Cloudflare. Ask Claude to do the change.

## Add a house

Open `collector/houses.json` on github.com, tap the pencil to edit, copy an existing entry, and change it:

| field | meaning |
|---|---|
| `id` | short lowercase name, no spaces (used in lot ids) |
| `name`, `town`, `region`, `website` | shown in the app |
| `adapter` | which reader to use (see below) |
| `enabled` | `true` to collect, `false` to skip |
| `crawl_delay` | seconds between page requests: 3 normally, 10 if the house's robots.txt says `Crawl-delay: 10` |
| `disabled_reason` | why it is off (quote the `docs/RULES.md` verdict), or `null` when it is on |
| `content_policy` | `full` = description and a link to the image; `text_only` = description only, no image link. Required |
| `keep_existing_lots` | optional. `true` keeps the house's already-stored lots (until their sale ends) while it is off only because its adapter is not written yet. Without it, switching a house off removes its lots |

Before switching a house on, read its website terms and robots.txt (see `docs/RULES.md`). Never add
the-saleroom.com: its terms forbid it, and the fetcher refuses it (and its subdomains) in code.

Tap Commit changes. The next run (or a manual run) picks it up.

## Switch a house off

In `collector/houses.json` find the house, change `"enabled": true` to `"enabled": false`, and put a
reason in `disabled_reason`, in quotes. Commit. At the next run its lots disappear from the page.

## Which house needs which adapter

| House | adapter | now |
|---|---|---|
| Hansons, Fieldings, Peter Francis | `whitelabel` | on |
| Gorringe's, Lawrences, David Duggleby, Rogers Jones | `gorringes`, `lawrences`, `duggleby`, `rogersjones` | on, adapter not written yet (skipped until it is) |
| Morphets | `easylive` | on, adapter not written yet |
| Gardiner Houlgate, Mellors & Kirk, Trevanion, Philip Serrell, Morgan Evans | `whitelabel` / none / `easylive` | off: terms forbid copying or using the text (reason in `houses.json`) |
| Ross's | none | off: terms unreadable, read them by hand |
| Lay's, Gildings, Anderson & Garland, Mallams, McTear's, Halls | `goauction` | off: bot challenge, we do not bypass it; stored lots kept until their sales end |
| Roseberys | `roseberys` | off: robots.txt blocks AI agents |

The `whitelabel` adapter reads the catalogue platform shared by Hansons, Fieldings, Peter Francis, Gardiner Houlgate,
Mellors & Kirk and Trevanion (`/catalogue/<id>/<id>/<slug>/` sale pages, 60 lots a page, and
`/catalogue/lot/...-lot-<n>/` lot pages). A house using it needs `calendar_urls`; optional per-house settings
(`sale_include`, `sale_exclude`, ...) are listed at the top of `collector/sources/whitelabel.py`.

The `goauction` adapter reads the GoAuction platform (`/auction/details/...?au=` sale pages and
`/auction/lot/...?lot=` lot pages) shared by five houses. A house using it also needs `calendar_urls`
in `houses.json` (the page(s) that list its sales; `{month}` becomes YYYY-MM). Optional per-house
settings are listed at the top of `collector/sources/goauction.py`.

**Run time.** Collection is incremental. Each night the robot reads the sale listing pages but opens a lot
page only for lots it has not stored before; known lots are reused (their estimate and sale dates are refreshed
from the listing; the stored title is never overwritten). A lot whose page failed to load is left out and tried again the next night. At most `max_new_lot_pages` new lot pages are read per house per run (default 150, set it
in `houses.json`), so a big sale such as Lay's 746 lots fills in over about five nights; the log says how
many lots were new, reused and deferred. At 10 s per page that is about 25 minutes per house, and the
workflow stops itself after 90 minutes (`timeout-minutes`), which keeps GitHub's free minutes safe.

## First real run (diagnose)

The goauction adapter was written without seeing real pages. When you tap Run workflow, the box
"Diagnose run" is ticked by default: it saves each house's first calendar, sale and lot page and
collects no data. Open the finished run, scroll to Artifacts and download `diagnose` (a zip of
`<house>/calendar.html`, `sale.html`, `lot.html`) and send it to Claude so the adapter can be fixed.
Untick the box for a real collection. (The nightly schedule always does a real collection.)

An enabled house whose adapter is missing is skipped and the run still succeeds.

## For developers

```
python3 -m unittest discover collector/tests   # all tests (Python 3.11+, standard library only)
python3 -m collector.run                       # collect (run from the repo root); --only <id> for one house
python3 -m collector.validate data/lots.json   # check a data file against SPEC.md
python3 -m collector.run --diagnose           # save sample pages to diagnose/<house>/, write no data
python3 app/build.py                           # build app/dist from data/lots.json (embeds shared/*.json, writes robots.txt, versions sw.js)
python3 app/build.py some.json --out /tmp/x    # build from another data file into another folder
python3 app/test/run_tests.py                  # app tests (Playwright + Chrome): builds the fixture itself into a temp folder, dates are relative to today
```

- `collector/fetcher.py` is the only code that uses the network.
- `collector/sources/<name>.py` adapters fetch and parse only; register them in `collector/sources/__init__.py`.
  `example_html.py` is the template.
- `collector/tagger.py` does all clean-up. `collector/schema.py` loads the SPEC lists from `shared/schema.json`
  (types, mediums, attribution notes); `app/build.py` embeds the same file in the app, so change them there only.
- `shared/rules.json` is the one definition of "not an original" (prints, reproductions, "After" works) and of
  "not art" (`non_art_words`: rings, jewellery, pottery, ... skipped unless clearly sculpture).
  `tagger.py` reads it and `app/build.py` embeds it in the app, so change it there only.
- Multi-day sales: `sale_date` is the first day, `sale_end_date` the last (null for one day). Past checks use the last day.
- If a house fails one night, its previous lots are kept (they keep their older `collected_at`).
