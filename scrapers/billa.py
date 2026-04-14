"""Billa Bulgaria scraper.

Data source: Nuxt 3 SSR JSON payload embedded in the homepage.
Products are weekly promotional teaser items stored server-side.
"""

import asyncio
import json
import random
import re
import sys
from datetime import date, datetime, timedelta

from playwright.async_api import async_playwright

from db.models import get_or_create_catalog
from parser.normalizer import extract_unit

# SELECTOR FOUND — PRODUCT NAME: Nuxt SSR JSON data[i+4] relative to price element at index i;
#   parsed from HTML  <p>Name<br>…</p>\n<p>quantity unit</p>
# SELECTOR FOUND — PROMO PRICE: Nuxt SSR JSON string containing "НОВА ЦЕНА: X,XX € / X,XX лв.",
#   regex: r'НОВА ЦЕНА:\s*[\d,]+\s*€\s*/\s*(\d+)[,\.](\d{2})\s*лв'
# SELECTOR FOUND — ORIGINAL PRICE: same string, "СТАРА ЦЕНА: X,XX € / X,XX лв.",
#   regex: r'СТАРА ЦЕНА:\s*[\d,]+\s*€\s*/\s*(\d+)[,\.](\d{2})\s*лв'
# SELECTOR FOUND — VALID DATES: Nuxt SSR JSON string "Валидно от DD.MM.YYYY г. до DD.MM.YYYY г.",
#   regex: r'Валидно от (\d{2}\.\d{2}\.\d{4}) г\. до (\d{2}\.\d{2}\.\d{4})'
# DATA SOURCE: <script type="application/json" data-nuxt-data="nuxt-app"> on https://www.billa.bg

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
]


class BillaScraper:
    URL = "https://www.billa.bg"

    async def scrape(self) -> list[dict]:
        content = await self._fetch_page()
        if not content:
            return []

        data = self._extract_nuxt_data(content)
        if not data:
            return []

        valid_from, valid_to = self._extract_dates(data)
        catalog_id = get_or_create_catalog("billa", valid_from, valid_to, self.URL)

        products = []
        for price_text, image_url, product_html in self._iter_teasers(data):
            try:
                product = self._parse_teaser(price_text, image_url, product_html, catalog_id)
                if product:
                    products.append(product)
            except Exception as e:
                print(f"[billa] skip product: {e}", file=sys.stderr)

        print(f"Billa: found {len(products)} products")
        return products

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_page(self) -> str | None:
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                ctx = await browser.new_context(
                    user_agent=random.choice(_USER_AGENTS),
                    locale="bg-BG",
                    extra_http_headers={"Accept-Language": "bg-BG,bg;q=0.9,en;q=0.5"},
                )
                page = await ctx.new_page()
                await page.goto(self.URL)
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(3)

                # Scroll to trigger lazy-loaded promo sections
                for _ in range(10):
                    await page.evaluate("window.scrollBy(0, 800)")
                    await asyncio.sleep(0.4)

                # Human delay
                await asyncio.sleep(random.uniform(1.5, 3.5))

                content = await page.content()
                await browser.close()
                return content
        except Exception as e:
            print(f"[billa] fetch error: {e}", file=sys.stderr)
            return None

    def _extract_nuxt_data(self, html: str) -> list | None:
        m = re.search(
            r'<script[^>]+type="application/json"[^>]+data-nuxt-data="nuxt-app"[^>]*>(.*?)</script>',
            html,
            re.DOTALL,
        )
        if not m:
            print("[billa] ERROR: Nuxt SSR data not found", file=sys.stderr)
            return None
        try:
            return json.loads(m.group(1))
        except Exception as e:
            print(f"[billa] JSON parse error: {e}", file=sys.stderr)
            return None

    def _extract_dates(self, data: list) -> tuple[date, date]:
        """Find 'Валидно от DD.MM.YYYY г. до DD.MM.YYYY г.' in SSR data."""
        fallback_from = date.today()
        fallback_to = date.today() + timedelta(days=7)
        for el in data:
            if not isinstance(el, str):
                continue
            m = re.search(
                r"Валидно от (\d{2}\.\d{2}\.\d{4}) г\. до (\d{2}\.\d{2}\.\d{4})",
                el,
            )
            if m:
                try:
                    return (
                        datetime.strptime(m.group(1), "%d.%m.%Y").date(),
                        datetime.strptime(m.group(2), "%d.%m.%Y").date(),
                    )
                except ValueError:
                    pass
        return fallback_from, fallback_to

    def _iter_teasers(self, data: list):
        """Yield (price_text, image_url, product_html) for each promo teaser."""
        for i, el in enumerate(data):
            if not isinstance(el, str):
                continue
            if "НОВА ЦЕНА" not in el:
                continue
            if i + 4 >= len(data):
                continue

            image_url = None
            if isinstance(data[i + 1], str) and data[i + 1].startswith("https://"):
                image_url = data[i + 1]

            product_html = data[i + 4]
            if not isinstance(product_html, str) or "<p>" not in product_html:
                continue

            yield el, image_url, product_html

    def _parse_teaser(
        self,
        price_text: str,
        image_url: str | None,
        product_html: str,
        catalog_id: int,
    ) -> dict | None:
        # Extract <p> tag contents
        p_contents = re.findall(r"<p>(.*?)</p>", product_html, re.DOTALL)
        if not p_contents:
            return None

        # First <p>: product name (may contain <br> tags)
        raw_name = re.sub(r"<[^>]+>", " ", p_contents[0]).strip()
        raw_name = re.sub(r"\s+", " ", raw_name).strip()
        if len(raw_name) < 3:
            return None

        # Second <p>: quantity + unit (e.g. "650 г", "1 бр", "2 x 1,5 л")
        raw_quantity = ""
        if len(p_contents) > 1:
            raw_quantity = re.sub(r"<[^>]+>", "", p_contents[1]).strip()

        full_text = raw_name + (" " + raw_quantity if raw_quantity else "")
        normalized_name, unit = extract_unit(full_text)

        # Parse promo price — take лв amount
        pm = re.search(
            r"НОВА ЦЕНА:\s*[\d,]+\s*€\s*/\s*(\d+)[,\.](\d{2})\s*лв",
            price_text,
        )
        if not pm:
            return None
        price = float(f"{pm.group(1)}.{pm.group(2)}")
        if price > 500:
            return None

        # Parse original price
        original_price = None
        om = re.search(
            r"СТАРА ЦЕНА:\s*[\d,]+\s*€\s*/\s*(\d+)[,\.](\d{2})\s*лв",
            price_text,
        )
        if om:
            original_price = float(f"{om.group(1)}.{om.group(2)}")

        return {
            "catalog_id": catalog_id,
            "name": normalized_name,
            "price": price,
            "original_price": original_price,
            "unit": unit,
            "quantity": None,
            "image_url": image_url,
        }
