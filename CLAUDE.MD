# SmartKoshnitsa — Claude Code project

## Environment

- OS: Windows 11
- Shell: PowerShell
- Python: python3 (not python or py)
- Venv: venv\Scripts\activates
- Use dir instead of ls
- Use copy instead of cp
- Use del instead of rm
- Use mkdir instead of mkdir -p
- Never use bash syntax — always PowerShell

## What this is

Bulgarian supermarket price comparison. Scrapes weekly PDF/HTML catalogs from
Kaufland, Lidl, Billa Bulgaria. FastAPI backend + vanilla JS frontend. SQLite.

## Run commands

- python run.py init # create DB, seed stores, install playwright
- python run.py scrape # run all scrapers
- python run.py serve # start API on :8000
- python run.py search "мляко" # test search from CLI
- python -m pytest tests/ -v

## Architecture rules — never break these

- All DB logic lives in db/models.py only. api/main.py imports from there.
- Scrapers are independent. One failing must not affect others.
- normalizer.py is pure functions — no DB calls, no side effects.
- Frontend calls only /api/\* — no direct DB access ever.
- Every file operation: open(path, encoding="utf-8")

## Bulgarian text rules

- Never romanize Cyrillic — preserve Bulgarian text as-is
- Price format: "1,29" or "1.29" → always normalize to float 1.29
- Date format from sites: DD.MM.YYYY → datetime.strptime(s, "%d.%m.%Y").date()
- Fuzzy match threshold: 65, scorer: rapidfuzz.fuzz.WRatio
- Units to recognize: кг, г, л, мл, бр, оп, пакет

## Scraper rules

- Always inspect real HTML with page.content() before writing selectors
- Add comment in each scraper: "# SELECTOR FOUND: <actual selector used>"
- Anti-bot: rotate User-Agent, add Bulgarian Accept-Language header
- Per-item exception handling — log to stderr, never crash whole scrape
- Human delay: asyncio.sleep(random.uniform(1.5, 3.5)) between requests

## Price parsing

- Regex: r'(\d+)[,\.](\d{2})' → float(f"{m[1]}.{m[2]}")
- Skip if price > 500 (parsing error)
- Skip if product name < 3 chars
- Original price = crossed-out / was-price if found

## When stuck on a scraper selector

Run this snippet to inspect the live page:
from playwright.async_api import async_playwright
import asyncio
async def inspect(url):
async with async_playwright() as p:
b = await p.chromium.launch(headless=False)
page = await b.new_page()
await page.goto(url)
await asyncio.sleep(5)
print(await page.content())
input("inspect in browser, then press Enter")
await b.close()
asyncio.run(inspect("https://www.billa.bg/promotions"))

## Windows-specific — ALWAYS follow these

- Use python3 not python or py
- Use python3 -m pytest not pytest directly
- Path separator is \ in PowerShell but / works in Python strings
- Activate venv first: venv\Scripts\activate
- Never use bash syntax (&&, |, grep, ls, cat) — use PowerShell equivalents
- PowerShell equivalents:
  ls -la → dir
  cat file → type file
  grep → Select-String
  rm -rf → Remove-Item -Recurse -Force
  cp → Copy-Item
  mv → Move-Item

## How to run things in this project

- Always check venv is active before running anything
- Test a single file: python3 -m pytest tests/test_X.py -v
- Test all: python3 -m pytest tests/ -v
- Quick scraper test: python3 -c "import asyncio; from scrapers.billa import BillaScraper; asyncio.run(BillaScraper().scrape())"

## Current project state

- [x] DB models created and init works
- [x] Stores seeded: Кауфланд, Лидл, Билла
- [x] normalizer.py ✓
- [ ] scrapers/billa.py ← NEXT
- [ ] scrapers/lidl.py
- [ ] scrapers/kaufland.py
- [ ] parser/pdf_parser.py
- [ ] api/main.py
- [ ] frontend/index.html

## Definition of done for each scraper

A scraper is done when:

1. It returns > 10 products with name + price + unit
2. upsert_products() inserts them into DB without error
3. python3 run.py search "мляко" returns results from that store
   Update this checklist when each item is completed.
