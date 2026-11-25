# Arts Finder: collection rules per source

Checked 2026-11-23 by the checker, using WebFetch/WebSearch only. "Not found" means the page could not be fetched or no relevant clause was visible. It does not mean "allowed". Re-check before enabling any adapter, and again every 6 months.

Rules from SPEC.md always apply on top of this table: obey robots.txt, one request at a time, at least 3 s apart (10 s where robots.txt says `crawl-delay: 10`), nightly only, honest User-Agent, link back, never copy images.

Note: several house robots.txt files block named AI crawlers (e.g. ClaudeBot, GPTBot) site-wide. Our collector must use its own honest User-Agent (e.g. `ArtsFinder-personal/0.1 (+repo URL)`). It must never pretend to be a browser or a search engine.

| Source | robots.txt on catalogue/lot paths | Terms on automated access | Feeds / API / alerts | Verdict |
|---|---|---|---|---|
| the-saleroom.com | Lot/auction pages not blocked generally; blocks `/archivelot`, `/url-for-lot-number`, `/timed-bid-details`, search-filter and `?pgSearchTerm` URLs. Publishes lots and auctions sitemaps. | Website T&Cs cl. 3.2 forbid building a database by systematically or regularly downloading or "spidering". Cl. 6.1 forbids extracting content without written consent. Licence is personal, non-commercial viewing only. | Free email "Auction Alerts" (keyword + price range). No RSS/API/iCal found. | **Not allowed** (without written consent) |
| easyliveauction.com | Not found (site refused fetch) | Not found (has "Site Usage Terms" page, but it could not be fetched) | "My Auction Alerts" email service. No RSS/API found. | **Unclear** |
| roseberys.co.uk | Only CMS/system folders blocked; no lot/catalogue rules; no crawl-delay. Named AI/SEO bots blocked site-wide. | No robots/scraping clause. Claims copyright in catalogue text and illustrations; reproduction needs prior written approval. | Email keyword alerts for new catalogues, sale reminders, mailing list. No RSS/API/iCal. | **OK with care** (store only a short summary + link, as SPEC says) |
| mallams.co.uk | Only account/admin/system paths and `/cms/lotdetailspdf/` blocked; `crawl-delay: 10`. | Not found (site refused fetch of home and terms) | Not found | **Unclear** |
| davidlay.co.uk (Bidpath) | Same as Mallams: only `/cms/lotdetailspdf/` lot-related; `crawl-delay: 10`. | Conditions of Business: no robots/scraping/reuse clause. No separate website terms page. | "Remind me" / sale-online email notifications, newsletter. No RSS. | **OK with care** (10 s delay) |
| hallsgb.com | `Allow: /`; blocks `/get`, `/api`, `/rss`, `/captcha/check`. No lot rules; no crawl-delay. | Terms of Use: no robot clause. Forbids reproducing or commercial use of site information without consent. Allows "download or print individual sections of the website for personal use". | None found (`/rss` exists but is disallowed). | **OK with care** (personal use only; do not use `/api` or `/rss`) |
| davidduggleby.com | Blocks `/live/`, search and tracking query strings, login pages. No lot rules; no crawl-delay. SEO bots blocked. | Only terms of sale PDF found: no robots clause. Auctioneer owns copyright in photos and catalogue text. | Newsletter sign-up page. No RSS/alerts. | **OK with care** (link images, never copy) |
| andersonandgarland.com (Bidpath) | Only `/cms/lotdetailspdf/` lot-related; `crawl-delay: 10`. | Terms of Business: no robots/scraping clause. No separate website terms. | Lot Alerts page, "Remind me" emails, newsletter. No RSS. | **OK with care** (10 s delay) |
| mctears.co.uk | Only `/cms/lotdetailspdf/` lot-related; `crawl-delay: 10`. | Not found (terms page could not be fetched) | Not found | **Unclear** |
| rogersjones.co.uk | Main site robots.txt: not found (fetch refused). Bidding subdomain `auctions.rogersjones.co.uk` blocks only `/myaccount/`. | Not found (no terms page linked from home or forthcoming sales pages) | Catalogue alerts / newsletter sign-up (appears to be Mailchimp). No RSS. | **Unclear** |
| morphets.co.uk (Easy Live) | Blocks `/manage/`, `/auctioneer/`, `/live_v2/`, `/components/`. No lot rules; no crawl-delay. | Terms and Conditions: no robots/scraping/reuse clause found. | Mailing-list subscribe form with categories (incl. Fine Art). No RSS. | **OK with care** |

## Recommendation (which adapters may be enabled)
1. Enable now, with care: Roseberys, David Lay, Halls, David Duggleby, Anderson & Garland, Morphets. Use a 10 s gap for any site with `crawl-delay: 10`.
2. Disable the-saleroom.com adapter (`"enabled": false, "reason": "T&Cs 3.2 forbid systematic downloading/spidering"`). Do not collect any house through the-saleroom. Ask them for written consent only if it is ever needed.
3. Keep easyliveauction.com, Mallams, McTears and Rogers Jones disabled ("terms unclear"). Read their terms by hand in a browser, then update this file.
4. For every enabled house: fetch only public sale/lot pages and sitemaps; never use search, `/api`, `/rss`, live-bidding or PDF paths blocked above; store ≤300-char text + link, never copy images.
5. A cheap, rule-safe extra: the user can sign up to each house's email/keyword alerts (Roseberys, A&G, the-saleroom) by hand. These are personal alerts, not data feeds; none of the sources offers a public API, RSS or iCal.

## Probe round (25 Nov 2026)

**Status: terms read 25 Nov 2026** by the checker, using approved WebFetch calls (1–2 per source). Platform and art-sales columns come from the polite probe's saved home pages (`/home/claude/probe1/probe/*/page1.html`, `report.md`). "Not found" means no such clause was seen in what was fetched. It does not mean "allowed". No house has an explicit robots/scraping/data-mining ban; most limits are copyright on catalogue text and photos.

The probe found all 20 sites below open to an honest User-Agent with robots.txt obeyed (no bot challenge, no robots block on the pages fetched).

**easyLive note:** the "easyLive" houses below run on their own domains. Their own terms govern those pages. easyLive's "Site Usage Terms" only matter if the collector fetches `easyliveauction.com`. It must not, until those terms are read.

| House | Platform (probe) | Terms on automated access (read 25 Nov) | Terms page read | Art sales? (home page evidence) | Verdict |
|---|---|---|---|---|---|
| easyLive (platform; easyliveauction.com) | n/a | Not found. Footer lists "Site Usage Terms", but the URL was not shown and two guessed URLs failed. Web search did not find it. | Not read | n/a | **Unclear** (never fetch easyliveauction.com) |
| Lots Road (lotsroad.com) | easyLive | Not found. Page holds sale and consignment terms only; no website-use terms and no copyright notice. | /terms-and-conditions/ | Yes: paintings & Old Masters, contemporary art depts; weekly sales | **OK with care** |
| Gorringe's (gorringes.co.uk) | custom | Not found. Sale terms only. Auctioneer owns copyright in photos and catalogue text. | /terms-conditions | Yes: Paintings & Prints dept; fine art weekly sales | **OK with care** |
| Lockdales (lockdales.com) | easyLive (Wix front) | Not checked (low value) | /website-terms | Weak: coin/stamp/medal specialist | Unclear (low value) |
| Gardiner Houlgate (gardinerhoulgate.co.uk) | easyLive | Website terms: no robot or scraping clause. Says "Reproduction is prohibited other than in accordance with the copyright notice"; that notice was not shown. | /terms+and+conditions | Yes: Paintings dept; "Antiques, Silver, Paintings" sales | **OK with care** |
| Lawrences (lawrences.co.uk) | custom (Webreality) | Not found. Only terms link is a sale-conditions PDF. Catalogue text and photos are its copyright; other use of the document needs permission. | /media/2240/lawrences-tcs-march-2026.pdf | Yes: Fine Art Sales, Pictures dept | **OK with care** |
| Plymouth Auction Rooms (plymouthauctions.co.uk) | WordPress | Not found. Sale conditions only; footer "All rights reserved". | /terms/ | Yes: Modern & Contemporary Art; Lenkiewicz, Fred Yates | **OK with care** |
| Fieldings (fieldingsauctioneers.co.uk) | easyLive | Not checked (low value) | /terms-and-conditions-of-business | Not found on home page | Unclear (low value) |
| Hansons (hansonsauctioneers.co.uk) | goauction/bidpath | Not found. Sale conditions only; footer "All rights reserved". | /terms-conditions/ | Yes: fine art sales at several branches | **OK with care** |
| Mellors & Kirk (mellorsandkirk.com) | easyLive (Webreality front) | Acceptable-use policy: no robot clause, but bans users who "reproduce, duplicate, copy or re-sell any part of our site". The main "terms of website use" it mentions were not linked. | /terms-conditions/ | Yes: Fine Art, Antiques & Collectors sales | **OK with care** (strict: store only facts + link, no description text) |
| Philip Serrell (serrell.com) | WordPress | Not found. Sale terms cl. 2.3: catalogue text and pictures are theirs; no one may use or copy them without written consent. | /conditions-of-business/ | Yes: Fine Art & Antiques sales; Paintings & Prints | **OK with care** (strict: facts + link only) |
| Trevanion (trevanion.com) | WordPress | Not found. Conditions of Sale cl. 2.3 match Serrell's: no use or copy of catalogue text without written consent. | /buying/, /conditions-of-sale/ | Yes: monthly Fine Art & Antiques auction | **OK with care** (strict: facts + link only) |
| 1818 Auctioneers (1818auctioneers.co.uk) | WordPress | Not found. Online-auction terms cl. 7.1: auctioneer owns photos and catalogue text and layout. | /terms-conditions/ | Some: "Paintings, Artwork and Imagery" category | **OK with care** |
| David Duggleby (davidduggleby.com) | ATG-backed | 23 Nov round: terms of sale only, no robots clause; owns photo/text copyright | /files/pdf/DD/TermsOfSale.pdf | Yes: dedicated Fine Paintings sales (next ends 4 Dec) | **OK with care** (from 23 Nov) |
| Mitchells (mitchellsauction.co.uk) | custom | Not found. Home page has no terms, legal or copyright link. | None exists | Some: "Antiques & Fine Art" (also livestock/land) | **Unclear** (no terms published) |
| Anthemion (anthemionauction.com) | WordPress | Not checked (low value) | /terms-conditions/ | Weak: general sales; "fine art" once | Unclear (low value) |
| Morgan Evans (morganevans.com) | easyLive | Website terms of use: no robot clause. Text, photos and code are theirs; no reproducing or storing the site. Downloading is "strictly prohibited" except for private use. | /en/terms-of-use | Yes: Antiques & Fine Art auctions | **OK with care** (private use only; never publish or share the data) |
| Peter Francis (peterfrancis.co.uk) | easyLive | Not checked (low value) | /terms-and-conditions | Not found on home page | Unclear (low value) |
| Rogers Jones (rogersjones.co.uk) | custom | Not found. No terms page on home or /en/buying; footer "All rights reserved"; full terms are shown only on bidder sign-up. | Home page, /en/buying | Yes, strong: British & European Fine Art, Welsh Art, Kyffin Williams | **OK with care** |
| Bloomfield (bloomfieldauctions.co.uk) | WordPress | Not checked (low value) | Not found | Weak: jewellery & watches focus | Unclear (low value) |
| Ross's (rosss.com) | custom | Not found. /terms-buyer/ and /buyer-terms/ redirect in a loop and could not be read. | Not read | Yes, strong: dedicated Irish Paintings sales | **Unclear** |

**Not allowed:** none in this round. (the-saleroom.com stays Not allowed, from 23 Nov.)

### Ranked shortlist: first 8 adapters (re-ranked 25 Nov, after terms read)
Score = art value x verdict x shared platform. All 8 are "OK with care". Every one must follow the SPEC rules: robots.txt, 3 s+ gap, nightly only, honest User-Agent, link back, never copy images.
1. **David Duggleby**: dedicated picture sales; ATG-backed adapter.
2. **Lots Road**: weekly London sales with paintings depts; easyLive front; no restrictive clause found.
3. **Gardiner Houlgate**: paintings dept; same easyLive adapter as 2.
4. **Rogers Jones**: strongest Welsh art; custom adapter; no terms found, so no restriction found.
5. **Lawrences**: Fine Art Sales + Pictures; Webreality front (shares with 6).
6. **Mellors & Kirk**: fine art sales; easyLive/Webreality. Store facts only (title, date, estimate, link). Do not store description text.
7. **Morgan Evans**: fine art auctions; easyLive. Private use only: the app and its data must never be made public.
8. **Hansons**: fine art at several branches; goauction/bidpath, so it may reuse the David Lay / Anderson & Garland Bidpath adapter.

Dropped from the 8: **Ross's**, moved to Unclear because its terms page could not be read.
Next in line: Gorringe's, Plymouth, 1818, then Trevanion and Philip Serrell (WordPress group; store facts + link only for those two).
On hold (Unclear): Ross's, Mitchells, and the easyliveauction.com platform site itself.
Low value, skip for now: Lockdales, Fieldings, Peter Francis, Anthemion, Bloomfield.

### Next step
1. Ross's: open its buyer terms in a normal browser by hand, then update this row.
2. easyLive: find the "Site Usage Terms" URL by hovering over the footer link on easyliveauction.com. Read it before any adapter calls easyliveauction.com directly.
3. Re-check all terms every 6 months. If Arts Finder ever becomes public or shared, re-check them all first: Morgan Evans, Mellors & Kirk, Trevanion and Serrell would then likely be Not allowed.

### Decision (25 Nov 2026, user): public but unlisted, and what that means per house
The site stays public (free hosting) but unlisted. A house whose terms forbid copying or using catalogue text is **not collected at all**; a house whose terms could not be read is off until someone reads them. Each collected house has `content_policy` in `collector/houses.json` ("full" = description + image link, "text_only" = description only).
- **On, "full":** Hansons, Gorringe's, Rogers Jones only (see "v0.4 Decision" below; it supersedes the earlier list that also had Fieldings, Peter Francis, Lawrences, Duggleby and Morphets).
- **Off, terms forbid copying/using text:** Mellors & Kirk (acceptable-use policy), Trevanion and Philip Serrell (sale terms cl. 2.3), Morgan Evans (private use only), Gardiner Houlgate (reproduction prohibited). The reason in houses.json quotes the clause.
- **Off, terms unreadable:** Ross's (user to read the buyer terms by hand, then update this file).
- **Off, bot challenge:** Lay's, Gildings, Anderson & Garland, Mallams, McTear's, Halls: the sites serve a bot challenge to automated clients and we do not bypass it. Their stored lots stay until their sales end (`keep_existing_lots`).

### v0.4 Decision (25 Nov 2026, orchestrator, after the checker's review of branch v0.4-adapters)
Enabled houses are exactly **Hansons, Gorringe's, Rogers Jones** (all "full"). A test (`test_houses_json_follows_the_terms_review`) pins this set.
- **Fieldings, Peter Francis: off.** Terms not read and low art value. `disabled_reason`: "terms not checked". Turn on only after someone reads `/terms-and-conditions-of-business` and `/terms-and-conditions` and updates the table.
- **David Duggleby: off.** Its lot data only comes from a search `/api` endpoint (`FilterBidItems`), and its robots.txt blocks search query strings; we do not sidestep that by using POST. The adapter code and tests stay, but it stays off. This also corrects Recommendation 4 above ("never use search, `/api`, `/rss`"): that rule stands. Safeguard in code: `Fetcher.post_json` applies robots.txt to the full URL including any query, and refuses an `/api` or "search" URL unless the house has an explicit `"api_allowed": true` (default false). No house has it.
- **Lawrences: off.** Its terms say other use of the document needs permission, which matches the clause that excluded Serrell and Trevanion. Code kept.
- **Morphets: off.** "bot challenge (probe 25 Nov)"; it also has no adapter yet.
- **easyliveauction.com is hard-blocked** in `collector/fetcher.py` (like the-saleroom.com) until its Site Usage Terms are read.
- **Mixed sales:** lots of type `Other` with no artist life dates and no sculpture word are dropped by the tagger (SPEC "Lots that are skipped"), and `non_art_words` in `shared/rules.json` now covers furniture, silver, coins, records, programmes, tins, memorabilia, cabinets, clocks and the like.
- **Fail closed:** a house with no `content_policy` is treated as `text_only` (with a warning).
- **Data-loss guard:** if a house's new non-empty result has fewer than half the lots it had for sales still to come, run.py keeps the old lots too and logs a warning.
