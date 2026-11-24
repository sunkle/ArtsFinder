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
