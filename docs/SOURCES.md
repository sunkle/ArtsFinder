# Sources notes (sample run 2026-11-23)

Rules from the coordinator: no the-saleroom.com (terms forbid systematic download); Roseberys skipped (robots.txt blocks AI agents); Lay's, Anderson & Garland, Mallams, McTear's want 10 s between requests. WebFetch also rate-limits parallel fetches of one site, so fetch one page at a time.

## Key finding: "GoAuction" platform (shared adapter)
Lay's, McTear's, Anderson & Garland, Mallams and Halls Fine Art all use the same platform (URLs contain `/auction/details/...?au=<id>`, `/auction/lot/...?lot=<id>`, images on `<house>.goauction.co.uk`). One adapter should serve all five; only the base URL differs. This is the best candidate for the first adapter.

## Lay's (davidlay.co.uk) - WORKED, 15 lots
- Sale list: home page https://www.davidlay.co.uk lists upcoming sales with `au` ids.
- Catalogue: `/auction/details/<slug>/?au=566&pn=<page>&g=1` (48 lots per page, `pp=48`). The listing gives lot number, title, artist with dates, estimate, lot id, image stock id. No medium on the listing.
- Lot page: `/auction/lot/<anything>/?lot=<lotid>&au=566` works (slug ignored). Canonical form: `/auction/lot/lot-<n>---<artist-slug-with-dates>/?lot=<lotid>`.
- Lot page is structured and shows: title, artist (name + dates), medium, dimensions (image and framed), description, estimate, auction date, image URL (`https://davidlay.goauction.co.uk/stock/<stockid>-medium.jpg?v=<v>`, `-small` on listings). So medium needs one lot-page request per lot (3+ s gap, 10 s requested).
- Sale 566 "Cornish Art, Fine Art & Studio Pottery", 26 Nov 2026, about 746 lots. Other upcoming sales are ceramics, jewellery, watches, stamps (not art).

## McTear's (mctears.co.uk) - FAILED, 0 lots
- Same GoAuction URL pattern (`/auction/details/-the-scottish-pictures-auction?au=<id>`, lots at `/auction/lot/lot-<n>---<artist>/?lot=<id>`).
- Calendar https://www.mctears.co.uk/auctions-events-calendar?m=2026-12 lists Scottish Contemporary Art 3 Dec and Scottish Pictures 9 Dec 2026, but the page text gives no links, so I could not find the `au` ids. Cached pages I got were old sales (au=1887 Jan 2026, au=1892 Feb 2026, au=1948 Oct 2026) and some fetches returned client_error. The collector must read the link hrefs from the calendar HTML (WebFetch strips them).

## Anderson & Garland (andersonandgarland.com) - 0 lots
- GoAuction platform. Sale list on home page with au ids: The Art Auction 17 Dec 2026 `au=1005` (catalogue not online yet, "Remind me" only), Urban Art 9 Dec `au=999` (coming soon), Modern Art & Design 20 Jan 2027 `au=983`.
- The Collectors' Auction 1 Dec `au=959` is online (306 lots) but is music, memorabilia, coins; listing has no artist field (title only), lot id and stock id given. Not art, so no lots recorded. Re-run once the Art Auction goes online (expected around early December).

## Mallams (mallams.co.uk) - FAILED, 0 lots
- Own site fetches mostly returned client_error; /forthcoming-auctions/ returned a stale 2024 cache. GoAuction pattern confirmed from search results (`/auction/details/-modern-art--design/?au=<id>`). The December 2026 "Modern Art & Design" (9-10 Dec) `au` id was not found. Only the-saleroom lists it, which is not allowed.

## Roseberys - SKIPPED (robots.txt). No lots collected.

## Halls (hallsgb.com, fineart.hallsgb.com) - FAILED, 0 lots
- Sites fetched but contain no auction list; /auctions, /auction-calendar, /upcoming-auctions returned client_error. Platform is GoAuction for live sales (`fineart.hallsgb.com/auction/search/?au=283&pn=2&g=1`) and a separate timed-sale site `finearttimed.hallsgb.com/past-auctions/halls-<id>`. Need the real calendar URL from the HTML.

## David Duggleby (davidduggleby.com) - FAILED, 0 lots
- Custom ASP.NET site. The auction list is loaded by JavaScript ("Loading Auction..."). Catalogue URLs found: `/auctions/<id>/<Name>/` (Modern Art 2787, Fine Paintings 2789) and category pages `/auctions/0/Art/?category=2`, but fetching them returned client_error or no lots. Needs a JS-aware approach or finding the JSON endpoint the page calls (check browser network tab).

## Rogers Jones (rogersjones.co.uk) - 0 lots
- Home page lists sales (works as plain HTML): sale pages `/en/sales/YYYY/M/D/<slug>`; bidding on `auctions.rogersjones.co.uk/auctions/<id>/<code>`. The Welsh Sale (22-23 Nov) is before the cut-off date. Chester Monthly (1 Dec 2026) is "Online Soon" and has no lots yet. Retry later.

## Morphets (morphets.co.uk) - 0 lots recorded
- Platform: Easy Live Auction white label. Catalogue `/catalogue/<hash>/<hash>/<slug>/` for Fine Art & Antique sale 26 Nov 2026 (488 lots, 60 per page). Page 1 is readable but pagination links are JS (`#`) so pages 2-9 were unreachable. Page 1 is mostly metalware, books, clocks and maps; only a few possible prints/sculpture, with truncated titles and no medium/artist fields, so none recorded. Lot URLs contain a hash per lot (`/catalogue/lot/<hash>/<hash>/<slug>-lot-<n>/`) so they can only be taken from the listing HTML. Images: `content.easyliveauction.com/auctions/images_lots/<id>_mor02/<imageid>_PREVIEW.JPG`. Modern British & 20th/21st Century Art sale is 9 Jan 2027, not online yet.

## Tool limits to know about
The WebFetch tool returns a summary, drops link hrefs, caches old pages and rate-limits. A real collector using urllib will see raw HTML and should do better, but robots.txt for each house still needs checking first.

---
# Second pass (2026-11-23): 75 lots total (Lay's 49, Gildings 15, Gorringe's 11)

Rules followed: no the-saleroom, Roseberys skipped, 10 s gaps on Lay's and Gildings (Lay's and Gildings fetches were alternated, so each saw 20 s or more between its own requests). The WebFetch tool itself refuses sites whose robots.txt it cannot read (error ROBOTS_UNREACHABLE), so a house is only "readable" if the fetch tool accepted it.

## Lay's - 49 lots now
- Sale 566 spans 26 and 27 Nov 2026 (lots from about 480 on are shown as 27 Nov on the lot page). sale_date uses the first day, 2026-11-26.
- Listing pages `?au=566&pn=N&g=1` (48 per page) give lot id and stock id but the stock id suffix is cut off (listing says 201306, image is 201306-1). Always take the image URL from the lot page, not the listing.
- Lot page gives medium, dimensions, estimate, image URL. Pottery and jewellery lots (lots 483+, 627-674) are in the same sale and must be filtered out (e.g. lot 501 is a gold ring).

## Gildings (gildings.co.uk) - 15 lots, WORKED
- robots.txt: `User-agent: *`, Disallow only /account, /admin, /cms/lotdetailspdf/, /elmah, /error, /imagebrowser, /language, /profile, /seo. Crawl-delay 10. Lots allowed.
- Platform: GoAuction (same as Lay's). Home page lists sales with `au` ids (au=408 Christmas Art & Antiques 1 Dec 2026, 378 lots; au=409 Affordable Art 5 Jan 2027 not online).
- Catalogue `/auction/details/-christmas-art--antiques?au=408&pn=N&g=1` (48 per page; art is on pages 5-6, lots 189-284). Lot page `/auction/lot/x/?lot=<id>&au=408`; canonical `/auction/lot/lot-<n>---<slug>/?lot=<id>`. Lot page structured: title, artist (dates sometimes), medium, dimensions, estimate, image `https://gildings.goauction.co.uk/stock/<stock>-medium.jpg?v=<v>`. Listing has no medium. Many artist fields are in the title ("Ascribed to", "After", "Circle of", "Provincial School") so the tagger must parse attribution words.

## Gorringe's (gorringes.co.uk, auction.gorringes.co.uk) - 11 lots, WORKED
- robots.txt for www.gorringes.co.uk (Drupal): `*`, crawl-delay 10, blocks only /search/ paths and Drupal system dirs. robots.txt for auction.gorringes.co.uk could not be read separately, but the fetch tool accepted the catalogue and lot pages. Treat as unverified: re-check in the real collector.
- Home page lists sales with codes: `https://auction.gorringes.co.uk/auction-catalog/<DDMMYY>` (011226 = Art & Design Post 1880, Lewes, 1 Dec 2026, 580 lots; 241126 wine; 301126 pop culture/house & garden).
- Catalogue pages: 20 lots per page, `https://auction.gorringes.co.uk/asp/searchresults.asp?st=D&sale_no=011226&pg=N`. Listing gives artist with dates, truncated title, estimate, lot URL, image URL. No medium.
- Lot page URL: `/auction-lot-detail/<Artist,-dates,-title-start>&salelot=011226+++++<n>+&refno=<refno>`. Structured: full title, artist and dates, date made (sometimes), medium and dimensions in quotes, description, estimate, images (`/full/<last3>/<refno>_Catalog_<random>.JPG`). Platform: classic ASP, own catalogue.
- Some lots are "After"/"Follower of" (lot 5, 18): avoid for "original works only".

## Lawrences (lawrences.co.uk) - 0 lots
- robots.txt allows all (www) and the auction site disallows only /admin/, /tv, /*/my. Platform: Auctionet-style site at `auctions.lawrences.co.uk` (`/en/search/25-art`, `/en/events/<id>-<slug>`, `/en/themes/<id>-<slug>`, calendar at `/calendar`). Listing pages are JavaScript-rendered (no lots in fetched text). Winter 20th Century Art & Design Sale is 11 Dec 2026 but no URL found, and the Winter Fine Art sale is Feb 2027. Needs JS or the site's JSON endpoint.

## Chorley's (chorleys.com) - 0 lots
- robots.txt: `*`, blocks /account, /admin, /cms/lotdetailspdf/ etc, crawl-delay 10 (Dukes, Gildings and Chorley's share this GoAuction-style robots file). Home page and /auctions returned client_error twice; gave up.

## Duke's (dukes-auctions.com, app.dukes-auctions.com) - 0 lots
- robots.txt same as Chorley's, allows lots. Cached home page showed only 2016 sales; app.dukes-auctions.com showed 2025-26 sales only. No Nov 2026 art catalogue found. Note: WebFetch caches old pages, so a real collector may do better.

## Golding Young & Mawer (goldingyoung.com) - 0 lots
- robots.txt allows all. Home page lists sales with catalogues on `live.goldingyoung.com/auctions/catalog/id/<id>/` (Grantham Asian Art 25 Nov au=1540, Collective Sale 2 Dec 1541, Lincoln Fine Art Sale 3 Feb 2027 1548). robots.txt of live.goldingyoung.com was unreadable, so skipped.

## 1818 Auctioneers (1818auctioneers.co.uk) - 0 lots
- robots.txt allows all. Timed online sales only; art sales "Paintings, Artworks and Imagery" run 19 Nov-6 Dec and 3-20 Dec 2026 (start dates before or at the edge of the cut-off). Catalogue host `auctions.1818auctioneers.co.uk` returned client_error twice; gave up.

## Bearnes Hampton & Littlewood (bhandl.co.uk) - 0 lots
- www.bhandl.co.uk robots.txt allows all. Home page lists catalogues on `auctions.bhandl.co.uk/auctions/<id>/<code>` (same platform style as Rogers Jones's `auctions.rogersjones.co.uk`): timed sale of ceramics and pictures 20-29 Nov (id 9832), Antiquarian Books, Manuscripts & Prints 1 Dec (9834). The auctions host's robots.txt returned client_error, so skipped.

## Dominic Winter (dominicwinter.co.uk) - 0 lots
- robots.txt unreadable on both hosts (ROBOTS_UNREACHABLE); skipped.
