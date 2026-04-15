"""Lidl Bulgaria scraper — local PDF brochure.

Reads a pre-downloaded Lidl PDF from data/pdfs/lidl_test.pdf.

# SOURCE: data/pdfs/lidl_test.pdf
# DATE INSPECTED: 2026-04-15
"""

import sys
from pathlib import Path

from db.models import get_or_create_catalog

_PDF_PATH = Path("data/pdfs/lidl_test.pdf")
_STORE_SLUG = "lidl"
_SOURCE_URL = "https://www.lidl.bg/broshuri"


class LidlScraper:
    def scrape(self) -> list[dict]:
        if not _PDF_PATH.exists():
            print(f"[lidl] PDF not found: {_PDF_PATH}", file=sys.stderr)
            return []

        from parser.lidl_pdf import parse_lidl_pdf, parse_validity_from_pdf

        valid_from, valid_to = parse_validity_from_pdf(str(_PDF_PATH))
        print(f"[lidl] validity: {valid_from} – {valid_to}")

        products = parse_lidl_pdf(str(_PDF_PATH))
        print(f"[lidl] parsed {len(products)} products")

        if not products:
            return []

        catalog_id = get_or_create_catalog(
            store_slug=_STORE_SLUG,
            start_date=valid_from,
            end_date=valid_to,
            source_url=_SOURCE_URL,
        )

        # Strip parser-only keys; add catalog metadata
        db_products = []
        for p in products:
            db_products.append({
                "catalog_id": catalog_id,
                "name": p["name"],
                "price": p["price"],
                "original_price": p.get("original_price"),
                "unit": p.get("unit"),
                "image_url": p.get("image_url"),
            })

        return db_products
