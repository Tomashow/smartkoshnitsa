# SmartKoshnitsa — Claude Code project

## Environment

- OS: Windows 11
- Shell: PowerShell
- Python: python3 (not python or py)
- Venv: venv\Scripts\activate
- Never use bash syntax — always PowerShell

## PowerShell equivalents

| bash       | PowerShell                  |
| ---------- | --------------------------- |
| ls -la     | dir                         |
| cat file   | type file                   |
| grep       | Select-String               |
| rm -rf     | Remove-Item -Recurse -Force |
| cp         | Copy-Item                   |
| mv         | Move-Item                   |
| touch file | New-Item file               |

## What this is

Bulgarian supermarket price comparison. Scrapes weekly catalogs from
Kaufland, Lidl, Billa Bulgaria. FastAPI backend + vanilla JS frontend. SQLite.

## Run commands

- python3 run.py init # create DB, seed stores
- python3 run.py scrape # run all scrapers
- python3 run.py serve # start API on :8000
- python3 run.py search "мляко" # test search from CLI
- python3 -m pytest tests/ -v # run all tests

## Current focus

<!-- UPDATE THIS EVERY SESSION — one line only -->

Fixing Billa scraper: currently returns 17 products (homepage teasers).
Must target /promotions page and return 100+ products.

## Project state

- [x] DB models + init_db() working
- [x] Stores seeded: Кауфланд / Лидл / Билла
- [x] normalizer.py + 10 tests passing
- [x] scrapers/billa.py v1 — 17 products (NEEDS FIX → 100+)
- [ ] scrapers/billa.py v2 — /promotions page ← CURRENT
- [ ] scrapers/lidl.py
- [ ] scrapers/kaufland.py
- [ ] parser/pdf_parser.py
- [ ] api/main.py
- [ ] frontend/index.html
- [ ] GitHub Actions + Railway deploy

## Definition of done — each scraper

1. Returns 100+ products with name, price, unit, valid_from, valid_to
2. upsert_products() inserts without errors
3. python3 run.py search "мляко" returns results from that store
4. All tests pass

## Architecture rules — never break

- All DB logic in db/models.py only
- Scrapers are independent — one failing never affects others
- normalizer.py is pure functions — no DB calls
- Frontend calls only /api/\* — never direct DB
- Every file operation: open(path, encoding="utf-8")

## Bulgarian text rules

- Never romanize Cyrillic — preserve as-is
- Price: "1,29" or "1.29" → float 1.29
- Dates: DD.MM.YYYY → datetime.strptime(s, "%d.%m.%Y").date()
- Fuzzy threshold: 65, scorer: rapidfuzz.fuzz.WRatio
- Units: кг, г, гр, л, мл, бр, оп, пакет

## Scraper rules

- ALWAYS inspect real HTML before writing any selectors
- Add at top of each scraper file:
  # SELECTOR FOUND: <actual selector>
  # SOURCE: <url inspected>
  # DATE INSPECTED: <date>
- Anti-bot: rotate User-Agent, Bulgarian Accept-Language
- Per-item try/except — log to stderr, never crash whole scrape
- Human delay: asyncio.sleep(random.uniform(1.5, 3.5))
- Intercept network calls to find hidden APIs:
  page.on('request', lambda r: print(r.url) if '/api/' in r.url else None)

## Price parsing

- Regex: r'(\d+)[,\.](\d{2})' → float(f"{m[1]}.{m[2]}")
- Skip price > 500 (parsing error)
- Skip name < 3 chars
- original_price = crossed-out price if found

## DB schema (current)

Store: id, name, slug, website_url
Catalog: id, store_id, start_date, end_date, source_url, scraped_at
Product: id, catalog_id, name, price, original_price, unit, quantity,
image_url, scraped_at
NOTE: Product missing store_id — currently Store reached via Catalog join.
Add store_id to Product as optimization after all scrapers done.

## Inspector snippet (Windows compatible)

python3 -c "
import asyncio
from playwright.async_api import async_playwright
async def inspect():
async with async_playwright() as p:
b = await p.chromium.launch(headless=False)
ctx = await b.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36', locale='bg-BG')
page = await ctx.new_page()
api_calls = []
page.on('request', lambda r: api_calls.append(r.url) if '/api/' in r.url or 'json' in r.url else None)
await page.goto('URL_HERE')
await page.wait_for_load_state('networkidle')
await asyncio.sleep(5)
for i in range(5):
await page.evaluate('window.scrollBy(0, 800)')
await asyncio.sleep(1)
print('API CALLS:')
for u in api_calls: print(u)
print('HTML:')
print((await page.content())[:8000])
await b.close()
asyncio.run(inspect())
"

## Tools configured

- Claude Code CLI + Plan Mode
- GitHub MCP: cmd /c npx @modelcontextprotocol/server-github ✓
- SQLite MCP: uvx mcp-server-sqlite (in .claude/settings.json)
- venv: venv\Scripts\activate

## Slash commands available

- /status → test + DB counts + current focus
- /done → tests + git diff + suggest commit
- /fix-scraper → diagnose + fix named scraper
- /scraper <url> → inspect page, find selectors
- /test <file> → run tests, fix failures

## Next 4 milestones in order

1. Billa scraper → 100+ products
2. Lidl scraper → 100+ products
3. Kaufland scraper + PDF parser
4. API + frontend
