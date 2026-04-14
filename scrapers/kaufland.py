"""Kaufland Bulgaria scraper.

Data source: Schwarz leaflets API + object storage PDF.
Flow: fetch flyer metadata → download PDF → parse with spatial strategy → upsert.

# SELECTOR FOUND: data-download-url on [data-t-name="FlyerTile"] (stale; use API instead)
# SOURCE: https://www.kaufland.bg/broshuri.html
# API:    https://endpoints.leaflets.schwarz/v4/flyer?flyer_identifier=BG_bg_KDZ_{region}&region_id={region}
# DATE INSPECTED: 2026-04-14
"""

import sys
from datetime import date, datetime
from pathlib import Path

import httpx

from db.models import get_or_create_catalog

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept-Language": "bg-BG,bg;q=0.9,en;q=0.5",
    "Referer": "https://leaflets.kaufland.com/",
    "Origin": "https://leaflets.kaufland.com",
}

# Sofia region — lists the main weekly brochure
_FLYER_API = (
    "https://endpoints.leaflets.schwarz/v4/flyer"
    "?flyer_identifier=BG_bg_KDZ_7800_BG16-LFT&region_id=7800"
)
_PDF_DIR = Path("data/pdfs")
_STORE_SLUG = "kaufland"
_SOURCE_URL = "https://www.kaufland.bg/broshuri.html"


class KauflandScraper:
    def scrape(self) -> list[dict]:
        # 1. Fetch flyer metadata
        meta = self._fetch_meta()
        if not meta:
            return []

        pdf_url = meta["pdf_url"]
        valid_from = meta["valid_from"]
        valid_to = meta["valid_to"]
        flyer_id = meta["flyer_id"]

        # 2. Download PDF (skip if already on disk for this flyer id)
        pdf_path = _PDF_DIR / f"kaufland_{flyer_id}.pdf"
        if not pdf_path.exists():
            ok = self._download_pdf(pdf_url, pdf_path)
            if not ok:
                return []
        else:
            print(f"[kaufland] PDF already cached: {pdf_path}")

        # 3. Parse PDF → products
        from parser.pdf_parser import parse_pdf
        products = parse_pdf(str(pdf_path), "Кауфланд", valid_from, valid_to)
        print(f"[kaufland] parsed {len(products)} products from PDF")

        if not products:
            return []

        # 4. Attach catalog_id to every product
        catalog_id = get_or_create_catalog(
            store_slug=_STORE_SLUG,
            start_date=valid_from,
            end_date=valid_to,
            source_url=_SOURCE_URL,
        )
        for p in products:
            p["catalog_id"] = catalog_id

        return products

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_meta(self) -> dict | None:
        """Call the Schwarz leaflets API and return flyer metadata."""
        try:
            r = httpx.get(_FLYER_API, headers=_HEADERS, timeout=20, follow_redirects=True)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"[kaufland] API error: {e}", file=sys.stderr)
            return None

        if not data.get("success"):
            print(f"[kaufland] API returned success=false: {data.get('message')}", file=sys.stderr)
            return None

        flyer = data.get("flyer", {})
        pdf_url = flyer.get("pdfUrl") or flyer.get("hiResPdfUrl")
        if not pdf_url:
            print("[kaufland] No pdfUrl in API response", file=sys.stderr)
            return None

        # Parse validity dates from title "13.04.2026 - 19.04.2026"
        valid_from, valid_to = self._parse_dates(flyer.get("title", ""))
        print(
            f"[kaufland] flyer id={flyer['id']} "
            f"valid {valid_from} – {valid_to} "
            f"({flyer.get('fileSize', 0) // 1024 // 1024} MB)"
        )

        return {
            "flyer_id": flyer["id"],
            "pdf_url": pdf_url,
            "valid_from": valid_from,
            "valid_to": valid_to,
        }

    @staticmethod
    def _parse_dates(title: str) -> tuple[date, date]:
        """Parse '13.04.2026 - 19.04.2026' from flyer title."""
        import re
        m = re.findall(r"(\d{2})\.(\d{2})\.(\d{4})", title)
        today = date.today()
        if len(m) >= 2:
            try:
                d1 = date(int(m[0][2]), int(m[0][1]), int(m[0][0]))
                d2 = date(int(m[1][2]), int(m[1][1]), int(m[1][0]))
                return d1, d2
            except ValueError:
                pass
        # fallback: this week Mon–Sun
        from datetime import timedelta
        monday = today - timedelta(days=today.weekday())
        return monday, monday + timedelta(days=6)

    def _download_pdf(self, url: str, dest: Path) -> bool:
        """Download PDF to dest. Returns True on success."""
        _PDF_DIR.mkdir(parents=True, exist_ok=True)
        print(f"[kaufland] downloading PDF → {dest}")
        try:
            with httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=120) as client:
                r = client.get(url)
                r.raise_for_status()
                dest.write_bytes(r.content)
            size_mb = dest.stat().st_size / 1024 / 1024
            print(f"[kaufland] downloaded {size_mb:.1f} MB")
            return True
        except Exception as e:
            print(f"[kaufland] download error: {e}", file=sys.stderr)
            return False
