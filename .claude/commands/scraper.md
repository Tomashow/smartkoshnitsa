Inspect the live page at $ARGUMENTS and find CSS selectors.

Run this PowerShell-compatible Python snippet:
python3 -c "
import asyncio
from playwright.async_api import async_playwright
async def inspect():
async with async_playwright() as p:
b = await p.chromium.launch(headless=False)
page = await b.new_page()
await page.goto('$ARGUMENTS')
await asyncio.sleep(6)
content = await page.content()
print(content[:5000])
await b.close()
asyncio.run(inspect())
"

From the HTML output, identify:

1. Product name selector
2. Promo price selector
3. Original price selector
4. Valid dates selector

Write findings as comments at top of the scraper file before writing any code.
Do not write any scraper code yet — just report what you found.
