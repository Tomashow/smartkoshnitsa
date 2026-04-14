# SmartKoshnitsa — Project Summary

## What we are building

Bulgarian supermarket price comparison app. Users add items to a basket,
app finds cheapest price across Kaufland, Lidl, Billa and suggests optimal
split (buy X at Lidl, Y at Kaufland) to minimize total spend.

## Tech stack

- Python 3.14 on Windows 11 / PowerShell
- FastAPI backend
- SQLite + SQLModel ORM
- Playwright (async) for scraping
- rapidfuzz for fuzzy product name matching
- Vanilla JS frontend (no framework)
- GitHub Actions for weekly auto-scrape
- Railway for free hosting

## Project location

C:\Users\Uladzislau_Tamashou\Desktop\cheapToday\smartkoshnitsa\

## Run commands

venv\Scripts\activate # always first
python3 run.py init # create DB + seed stores
python3 run.py scrape # run all scrapers
python3 run.py serve # start API on :8000
python3 run.py search "мляко" # test search
python3 -m pytest tests/ -v # run tests

## What is built and working

### DB (db/models.py) ✓

Tables: Store, Catalog, Product
Functions:

- init_db() creates tables, seeds 3 stores
- get_engine() reads DB_PATH from env
- get_or_create_catalog() finds or creates catalog entry
- upsert_products(products) inserts product list into DB
- search_products(query, limit) fuzzy search active products
- get_basket_comparison(queries) core smart basket algorithm
- count_active_products() count valid products today

Stores seeded:

- Кауфланд slug=kaufland https://www.kaufland.bg
- Лидл slug=lidl https://www.lidl.bg
- Билла slug=billa https://www.billa.bg

### Normalizer (parser/normalizer.py) ✓

Functions:

- normalize(name) -> str
  lowercase, strip, remove quantity+unit patterns,
  remove noise words (кофа, бутилка, опаковка)
- extract_unit(name) -> tuple[str, str|None]
  detects: кг, г, л, мл, бр, оп

Tests: tests/test_normalizer.py — 10 cases, all passing

### Billa scraper (scrapers/billa.py) ✓ partial

Current state: scrapes Nuxt3 SSR JSON from homepage
Returns: 17 products (teasers only)
Status: NEEDS FIX — must target /promotions page for 100-200+ products
Next step: inspect https://www.billa.bg/promotions, find API calls,
rewrite to get full catalog

### Not built yet

- scrapers/lidl.py
- scrapers/kaufland.py
- parser/pdf_parser.py (for Kaufland PDFs)
- api/main.py (FastAPI endpoints)
- frontend/index.html (basket UI)
- .github/workflows/scrape.yml

## Current task

Fix Billa scraper to return 100+ products from /promotions page.
Inspect page for API calls first, then rewrite scraper.

## DB schema

Store
id int PK
name str "Кауфланд"
slug str unique "kaufland"
website_url str

Catalog
id int PK
store_id int FK → store.id
start_date date
end_date date
source_url str
scraped_at datetime

Product
id int PK
catalog_id int FK → catalog.id
name str
price float
original_price float|None
unit str|None "кг","г","л","мл","бр","оп"
quantity float|None
image_url str|None
scraped_at datetime

NOTE: Product is missing store_id direct column.
Currently store = Product → Catalog → Store (extra join).
Add store_id to Product later as optimization.

## Bulgarian text rules

- Never romanize Cyrillic
- Price format: "1,29" or "1.29" → float 1.29
- Date format: DD.MM.YYYY → datetime.strptime(s, "%d.%m.%Y").date()
- Fuzzy threshold: 65, scorer: rapidfuzz.fuzz.WRatio
- Units: кг, г, гр, л, мл, бр, оп, пакет

## Scraper rules

- Inspect real HTML before writing selectors
- Add comment: # SELECTOR FOUND: <actual selector>
- Anti-bot: rotate User-Agent, Bulgarian Accept-Language header
- Per-item try/except — never crash whole scrape
- Human delay: asyncio.sleep(random.uniform(1.5, 3.5))

## Price parsing

- Regex: r'(\d+)[,\.](\d{2})' → float(f"{m[1]}.{m[2]}")
- Skip price > 500 (parsing error)
- Skip name < 3 chars

## Tools configured

- Claude Code CLI with Plan Mode
- GitHub MCP — connected (cmd /c npx @modelcontextprotocol/server-github)
- SQLite MCP — configured in .claude/settings.json
- venv at venv\Scripts\activate

## Slash commands (.claude/commands/)

- /scraper <url> inspect live page, find selectors
- /test <file> run tests and fix failures
- /scrape-test <name> test scraper end to end
- /checkpoint run tests + suggest commit message

## Deployment plan (not started)

- GitHub Actions: weekly cron Monday 4am UTC
  scrapes all stores → commits updated DB → triggers Railway redeploy
- Railway free tier: serves FastAPI + frontend
- Total cost: €0

## What is built and working (updated)

- scrapers/billa.py ✓ — 311 products via ssbbilla.site HTML
- scrapers/kaufland.py ✓ — Schwarz API → PDF download → spatial parser → 187 products
- parser/pdf_parser.py ✓ — 3 strategies (tables / spatial pymupdf / word grouping)
- api/main.py ✓ — FastAPI /api/search endpoint
- frontend/index.html ✓ — vanilla JS search UI
- render.yaml ✓ — Render.com deploy config
- DB: 515 active products (311 Billa + 187 Kaufland + seeds)

## TODO

- [ ] Duplicate products in DB — `upsert_products` inserts new rows each scrape run instead
      of updating existing ones. Fix: add unique constraint on (catalog_id, name, price) or
      wipe catalog products before re-inserting. Clean up now: `python3 run.py init && python3 run.py scrape`
- [ ] Kaufland PDF name quality — ~5-10% of parsed names are partial descriptors
      (e.g. "български" instead of "български домати"). Spatial pairing picks up
      adjective blocks instead of the full name block. Fix: prefer blocks with 2+ words
      or blocks that contain a unit keyword (кг, г, бр).
- [ ] Lidl scraper — not started
- [ ] GitHub Actions weekly cron — auto-scrape + commit DB + trigger redeploy
- [ ] Basket comparison UI — frontend calls /api/basket, shows cheapest split across stores

## Next steps in order

1. Fix duplicate upsert issue
2. Build Lidl scraper → 100+ products
3. Improve Kaufland name quality (adjective-only names)
4. GitHub Actions weekly cron
5. Basket comparison endpoint + UI
