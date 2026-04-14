"""Billa Bulgaria scraper v2.

Data source: ssbbilla.site — the official accessibility version of Billa's
weekly brochure, linked from billa.bg/promocii ("Брошура за незрящи").
Plain server-rendered HTML; no Playwright, no OCR, no extra dependencies.
"""

# SELECTOR FOUND: div.product > div.actualProduct (product name)
# SELECTOR FOUND: div[style*="width:22%"] span.price + span.currency:лв. (original BGN price)
# SELECTOR FOUND: div[style*="width:21%"] span.price + span.currency:лв. (current BGN price)
# SOURCE: https://ssbbilla.site/catalog/sedmichna-broshura
# DATE INSPECTED: 2026-04-14

import re
import sys
from datetime import date, timedelta

import httpx

from db.models import get_or_create_catalog
from parser.normalizer import extract_unit

SOURCE_URL = "https://ssbbilla.site/catalog/sedmichna-broshura"

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

# Promotional prefixes that appear before the actual product name
_NOISE_PREFIX = re.compile(
    r"^(супер цена\s*[-–]\s*"
    r"|само с billa card\s*[-–]\s*"
    r"|сега в billa\s*[-–]\s*"
    r"|мултипак оферта 1\+1\s*"
    r"|празнични оферти\s*)",
    re.IGNORECASE,
)


class BillaScraper:
    def scrape(self) -> list[dict]:
        html = self._fetch()
        if not html:
            return []

        valid_from, valid_to = self._extract_dates(html)
        catalog_id = get_or_create_catalog("billa", valid_from, valid_to, SOURCE_URL)

        products = []
        for block in html.split('<div class="product">')[1:]:
            try:
                product = self._parse_block(block, catalog_id)
                if product:
                    products.append(product)
            except Exception as e:
                print(f"[billa] skip: {e}", file=sys.stderr)

        print(f"Billa: found {len(products)} products")
        return products

    async def scrape_async(self) -> list[dict]:
        """Async shim for callers that expect an awaitable."""
        return self.scrape()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch(self) -> str | None:
        try:
            r = httpx.get(
                SOURCE_URL,
                headers={
                    "User-Agent": _USER_AGENT,
                    "Accept-Language": "bg-BG,bg;q=0.9,en;q=0.5",
                },
                timeout=20,
                follow_redirects=True,
            )
            r.raise_for_status()
            return r.text
        except Exception as e:
            print(f"[billa] fetch error: {e}", file=sys.stderr)
            return None

    def _extract_dates(self, html: str) -> tuple[date, date]:
        """Parse 'Валидност: от четвъртък 09.04. до 15.04.2026 г.' from page header."""
        m = re.search(
            r"Валидност: от \S+ (\d{2})\.(\d{2})\. до (\d{2})\.(\d{2})\.(\d{4}) г",
            html,
        )
        if m:
            year = int(m.group(5))
            try:
                return (
                    date(year, int(m.group(2)), int(m.group(1))),
                    date(year, int(m.group(4)), int(m.group(3))),
                )
            except ValueError:
                pass
        fallback = date.today()
        return fallback, fallback + timedelta(days=7)

    def _parse_block(self, block: str, catalog_id: int) -> dict | None:
        # --- Name ---
        nm = re.search(
            r'class="actualProduct"[^>]*>\s*(.*?)\s*</div>', block, re.DOTALL
        )
        if not nm:
            return None
        raw_name = re.sub(r"<[^>]+>", " ", nm.group(1))
        raw_name = re.sub(r"\s+", " ", raw_name).strip()
        raw_name = _NOISE_PREFIX.sub("", raw_name).strip()
        if len(raw_name) < 3:
            return None

        # --- Current price (BGN) from 21%-width div ---
        price = self._extract_bgn(block, "width:21%")
        if price is None or price > 500:
            return None

        # --- Original price (BGN) from 22%-width div (None if no discount) ---
        original_price = self._extract_bgn(block, "width:22%")

        normalized_name, unit = extract_unit(raw_name)

        return {
            "catalog_id": catalog_id,
            "name": normalized_name,
            "price": price,
            "original_price": original_price,
            "unit": unit,
            "quantity": None,
            "image_url": None,
        }

    @staticmethod
    def _extract_bgn(block: str, width_marker: str) -> float | None:
        """Extract the first BGN price from a div identified by its width style."""
        dm = re.search(
            rf"{re.escape(width_marker)}[^>]*>(.*?)</div>", block, re.DOTALL
        )
        if not dm:
            return None
        prices = re.findall(
            r'class="price">(\d+\.\d+)</span>\s*<span class="currency">лв',
            dm.group(1),
        )
        if not prices:
            return None
        try:
            return float(prices[0])
        except ValueError:
            return None
