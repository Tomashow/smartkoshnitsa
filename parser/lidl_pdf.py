"""Lidl Bulgaria PDF brochure parser.

Lidl-specific layout: 2–3 columns per page, EUR-primary prices, embedded JPEG images.

Price block per product (anchored by compact sale-EUR token "X.XX€"):
  ORIGINAL EUR : "X.XX" + "€" (two separate tokens) ~15pt ABOVE compact token
  ORIGINAL BGN : "X.XX" + "ЛВ." (two tokens)   ~8pt  ABOVE compact token
  SALE EUR     : "X.XX€"  (compact, combined)    ← anchor
  SALE BGN     : stored as price = sale_eur × 1.95583

Images are embedded DCT JPEGs (one per product); matched by spatial proximity.
"""

import re
import sys
from pathlib import Path

BGN_PER_EUR = 1.95583

# Y thresholds for stripping header/footer text
_HEADER_Y = 28
_FOOTER_Y = 748

_RE_COMPACT_EUR = re.compile(r"^(\d+)\.(\d{2})€$")   # "0.89€"
_RE_NUM = re.compile(r"^(\d+)\.(\d{2})$")              # "1.09" (separate token)
_RE_DATE = re.compile(r"^\d{2}\.\d{2}\.?\d*$")         # "30.03." "26.04.2026"
_RE_PERCENT = re.compile(r"^-?\d+%$")                  # "-26%" or "26%"
_RE_LATIN_UNIT = re.compile(                           # "500g/опаковка", "1l/опаковка"
    r"(\d+(?:[.,]\d+)?)\s*([gGlLkK]{1,2})\s*/\S*",
    re.IGNORECASE,
)
_RE_ORPHAN_UNIT = re.compile(                          # standalone "g/бр.", "l/опаковка"
    r"(?<!\d)([gGlL]{1,2}|ml|ML)\s*/\S+",
    re.IGNORECASE,
)

# Tokens that are never part of a product name
_SKIP = frozenset({
    "€", "лв.", "акция", "виж", "повече", "на", "www.lidl.bg",
    "www.lidl.bg/kontakt", "цените", "са", "обозначени", "в",
    "евро", "и", "лева", "по", "валутен", "курс", "1.95583",
    "=", "от", "понеделник", "до", "брошурата", "е", "за",
    "периода", "всички", "цени", "нея", "посочени", "с", "включен",
    "ддс", "важат", "отбелязания", "съответната", "страница",
    "период", "арти-", "кулите", "могат", "да", "бъдат", "изчерпани",
    "преди", "последния", "ден", "промоция", "или", "не", "налични",
    "разновидности", "размери", "артикули", "без", "ценово",
    "намаление", "се", "продават", "количества", "обичайни", "едно",
    "домакинство", "артикула", "kg", "клиент", "при", "намалени",
    "важи", "информация", "характеристиките", "състава", "опаковките",
    "лидл", "българия", "носи", "отговорност", "допуснати", "печатни",
    "грешки", "запазва", "правото", "промяна", "декорацията",
    "включена", "тяхната", "цена", "намериш", "можеш", "свържеш",
    "нас", "*", "този", "артикул", "изчерпан", "още", "1-вия",
    "търговската", "трайно", "ниски", "заслужава", "си", "теб",
    "стъпка", "към", "еврото", "гаранция", "качество", "световен",
    "лидер", "контрола", "14/2026", "г.",
    # Page 1 decorative / header words
    "всяka", "всяка", "въ", "l", "g", "ml",
    # Disclaimer / fine-print words that leak into product zones
    "налична", "могат", "бъдат", "продават", "клиент)",
    "важи", "артикул", "намалени", "намаление",
})


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def parse_lidl_pdf(pdf_path: str) -> list[dict]:
    """Parse a Lidl Bulgaria brochure PDF.

    Returns list of product dicts with keys:
        name, price, original_price, unit, image_url, page_number
    """
    import pdfplumber
    import fitz

    img_dir = Path("data/pdfs/images")
    img_dir.mkdir(parents=True, exist_ok=True)
    pdf_stem = Path(pdf_path).stem

    doc = fitz.open(pdf_path)
    products: list[dict] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            page_num = page_idx + 1
            try:
                fitz_page = doc[page_idx]
                products.extend(
                    _parse_page(page, fitz_page, page_num, img_dir, pdf_stem)
                )
            except Exception as exc:
                print(f"[lidl] page {page_num} error: {exc}", file=sys.stderr)

    doc.close()

    # Normalise names + extract units
    from parser.normalizer import extract_unit

    final: list[dict] = []
    seen: set[tuple] = set()
    for p in products:
        # Detect unit from Latin patterns BEFORE stripping them
        # "500 g/опаковка" → unit "г" | "1 l/опаковка" → unit "л"
        raw = p["name"]
        if not p.get("unit"):
            mu = re.search(
                r"\b(\d+(?:[.,]\d+)?)\s*(kg|ml|[gGlL])\s*/",
                raw, flags=re.IGNORECASE
            )
            if mu:
                _u = mu.group(2).lower()
                p["unit"] = {"kg": "кг", "g": "г", "l": "л", "ml": "мл"}.get(_u)

        # Convert Latin unit tokens to Cyrillic so extract_unit can recognise them:
        # "500 g/опаковка" → "500 г"  |  "1 l/опаковка" → "1 л"
        raw = re.sub(r"(\d+(?:[.,]\d+)?)\s*kg\s*/\S*", r"\1 кг", raw, flags=re.IGNORECASE)
        raw = re.sub(r"(\d+(?:[.,]\d+)?)\s*ml\s*/\S*", r"\1 мл", raw, flags=re.IGNORECASE)
        raw = re.sub(r"(\d+(?:[.,]\d+)?)\s*g\s*/\S*",  r"\1 г",  raw, flags=re.IGNORECASE)
        raw = re.sub(r"(\d+(?:[.,]\d+)?)\s*l\s*/\S*",  r"\1 л",  raw, flags=re.IGNORECASE)
        # Remove orphaned unit tokens without leading number
        raw = re.sub(r"\b(kg|ml|[gGlL])\s*/\S*", " ", raw, flags=re.IGNORECASE)
        p["name"] = raw

        clean, unit = extract_unit(raw)
        if not clean or len(clean) < 3:
            continue
        p["name"] = clean
        if not p.get("unit"):
            p["unit"] = unit
        key = (clean.lower(), round(p["price"], 2))
        if key not in seen:
            seen.add(key)
            final.append(p)

    return final


# ---------------------------------------------------------------------------
# Validity date helper (used by the scraper)
# ---------------------------------------------------------------------------


def parse_validity_from_pdf(pdf_path: str):
    """Extract validity dates from the Lidl PDF footer.

    Returns (valid_from: date, valid_to: date).
    Falls back to current Mon–Sun if parsing fails.
    """
    import pdfplumber
    from datetime import date, timedelta

    today = date.today()
    monday = today - timedelta(days=today.weekday())
    fallback = (monday, monday + timedelta(days=6))

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:2]:
                words = page.extract_words()
                for w in words:
                    # "26.04.2026" full-year date
                    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", w["text"])
                    if m:
                        # Scan surrounding words for two such dates
                        text_blob = " ".join(x["text"] for x in words)
                        dates = re.findall(r"(\d{2})\.(\d{2})\.(\d{4})", text_blob)
                        if len(dates) >= 2:
                            d1 = date(int(dates[0][2]), int(dates[0][1]), int(dates[0][0]))
                            d2 = date(int(dates[1][2]), int(dates[1][1]), int(dates[1][0]))
                            return (min(d1, d2), max(d1, d2))
    except Exception:
        pass

    # Try short dates "30.03." "26.04." with current year
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:1]:
                text = " ".join(w["text"] for w in page.extract_words())
                short = re.findall(r"(\d{2})\.(\d{2})\.", text)
                if len(short) >= 2:
                    year = today.year
                    d1 = date(year, int(short[0][1]), int(short[0][0]))
                    d2 = date(year, int(short[1][1]), int(short[1][0]))
                    if d2 < d1:
                        d2 = date(year + 1, int(short[1][1]), int(short[1][0]))
                    return (d1, d2)
    except Exception:
        pass

    return fallback


# ---------------------------------------------------------------------------
# Page-level parsing
# ---------------------------------------------------------------------------


def _footer_y(words: list, page_height: float) -> float:
    """Detect y where the footer/disclaimer section starts on this page."""
    _markers = {"брошурата", "виж", "цените", "*"}
    for w in sorted(words, key=lambda x: x["top"]):
        wy = float(w["top"])
        if wy < page_height * 0.55:
            continue                    # must be in bottom ~45%
        if w["text"].lower() in _markers:
            return wy - 2               # just above the footer marker
    return _FOOTER_Y


def _parse_page(page, fitz_page, page_num: int,
                img_dir: Path, pdf_stem: str) -> list[dict]:
    words = page.extract_words()
    page_width = float(page.width)
    page_height = float(page.height)

    # Strip header/footer — detect actual footer start per page
    footer_y = _footer_y(words, page_height)
    words = [w for w in words if _HEADER_Y < float(w["top"]) < footer_y]

    # Find all compact sale-EUR tokens  e.g. "0.89€"
    sale_tokens = []
    for w in words:
        val = _compact_eur(w["text"])
        if val is not None and 0.05 <= val <= 300:
            sale_tokens.append({"x": float(w["x0"]), "y": float(w["top"]), "val": val})

    if not sale_tokens:
        return []

    # Group into price rows (tokens within 8pt y of each other)
    sale_tokens.sort(key=lambda t: (t["y"], t["x"]))
    rows: list[list[dict]] = []
    cur: list[dict] = [sale_tokens[0]]
    for tok in sale_tokens[1:]:
        if abs(tok["y"] - cur[0]["y"]) <= 8:
            cur.append(tok)
        else:
            rows.append(cur)
            cur = [tok]
    rows.append(cur)

    # Y centre of each row
    row_ys = [sum(t["y"] for t in r) / len(r) for r in rows]

    # Zone y boundaries (midpoints between consecutive rows)
    zone_y0s = [_HEADER_Y] + [
        (row_ys[i] + row_ys[i + 1]) / 2 for i in range(len(row_ys) - 1)
    ]
    zone_y1s = [
        (row_ys[i] + row_ys[i + 1]) / 2 for i in range(len(row_ys) - 1)
    ] + [_FOOTER_Y]

    # Collect images for this page (skip large background images)
    page_images = _page_images(fitz_page, page_width, float(page.height))

    products: list[dict] = []
    for row, zy0, zy1, ry in zip(rows, zone_y0s, zone_y1s, row_ys):
        row.sort(key=lambda t: t["x"])

        # X-column boundaries for this row
        col_x0s = [0.0] + [
            (row[i]["x"] + row[i + 1]["x"]) / 2 for i in range(len(row) - 1)
        ]
        col_x1s = [
            (row[i]["x"] + row[i + 1]["x"]) / 2 for i in range(len(row) - 1)
        ] + [page_width]

        for col_idx, tok in enumerate(row):
            cx0 = col_x0s[col_idx]
            cx1 = col_x1s[col_idx]

            # Words in this column × zone
            zone_words = [
                w for w in words
                if cx0 <= float(w["x0"]) < cx1 and zy0 <= float(w["top"]) < zy1
            ]

            orig_eur = _find_original_eur(zone_words, tok["y"])
            sale_bgn = round(tok["val"] * BGN_PER_EUR, 2)
            orig_bgn = round(orig_eur * BGN_PER_EUR, 2) if orig_eur else None

            name = _collect_name(zone_words, tok["y"])
            if not name:
                continue

            img_url = _match_image(
                page_images, cx0, cx1, zy0, tok["y"],
                fitz_page, img_dir, pdf_stem, page_num, len(rows) - 1 - rows.index(row), col_idx,
            )

            products.append({
                "name": name,
                "price": sale_bgn,
                "original_price": orig_bgn,
                "unit": None,
                "image_url": img_url,
                "page_number": page_num,
            })

    return products


# ---------------------------------------------------------------------------
# Price helpers
# ---------------------------------------------------------------------------


def _compact_eur(text: str) -> float | None:
    """Parse compact sale-EUR token like '0.89€'. Returns float or None."""
    m = _RE_COMPACT_EUR.match(text)
    if m:
        return float(f"{m.group(1)}.{m.group(2)}")
    return None


def _find_original_eur(zone_words: list, sale_y: float,
                       max_above: float = 28) -> float | None:
    """Find the original (crossed-out) EUR price above the sale token.

    Looks for a separate "€" token and its adjacent numeric token.
    """
    for w in zone_words:
        if w["text"] != "€":
            continue
        wy = float(w["top"])
        if not (sale_y - max_above <= wy < sale_y - 2):
            continue
        # Number token immediately left of "€" at same row
        for nw in zone_words:
            if (
                abs(float(nw["top"]) - wy) < 3
                and float(nw["x1"]) <= float(w["x0"]) + 6
                and float(nw["x0"]) < float(w["x0"])
            ):
                val = _parse_num(nw["text"])
                if val is not None and 0.05 <= val <= 300:
                    return val
    return None


def _parse_num(text: str) -> float | None:
    m = _RE_NUM.match(text)
    if m:
        return float(f"{m.group(1)}.{m.group(2)}")
    return None


# ---------------------------------------------------------------------------
# Name extraction
# ---------------------------------------------------------------------------


def _collect_name(zone_words: list, sale_y: float,
                  proximity: float = 180.0) -> str:
    """Collect product name words from the zone, excluding price rows.

    Only considers words within *proximity* pt of sale_y to avoid picking up
    decorative/header text that happens to share the column and zone.
    """
    # Build set of "price row" y values to exclude
    price_ys: set[int] = set()
    for w in zone_words:
        t = w["text"]
        wy = round(float(w["top"]))
        if t == "€" or t.upper() in ("ЛВ.", "ЛВ"):
            price_ys.add(wy)
        if _compact_eur(t) is not None:
            price_ys.add(wy)
        if _RE_NUM.match(t):
            price_ys.add(wy)
        if re.match(r"^\d+\.-$", t):       # "1.-"
            price_ys.add(wy)

    name_words = []
    for w in zone_words:
        text = w["text"]
        wy_f = float(w["top"])
        wy = round(wy_f)

        # Proximity gate: ignore text far from the price block
        if abs(wy_f - sale_y) > proximity:
            continue
        if wy in price_ys:
            continue

        # Strip leading/trailing punctuation/brackets for skip-set comparison
        core = text.strip(".,!?():;\"'").lower()
        if core in _SKIP or text.lower() in _SKIP:
            continue
        if _RE_DATE.match(text):
            continue
        if _RE_PERCENT.match(text):
            continue
        # Skip unit-only tokens like "g/опаковка", "l/бр.", "2.5" (size labels)
        if re.match(r"^[gGlLkK]{1,2}/\S+$", text):
            continue
        if not re.search(r"[а-яА-ЯёЁa-zA-Z]", text):
            continue

        name_words.append(w)

    if not name_words:
        return ""

    # Sort by y-group then x
    name_words.sort(key=lambda w: (round(float(w["top"]) / 6) * 6, float(w["x0"])))

    # Join into lines
    lines: list[str] = []
    line_buf: list[str] = []
    cur_y = float(name_words[0]["top"])

    for w in name_words:
        wy = float(w["top"])
        if abs(wy - cur_y) > 5:
            if line_buf:
                lines.append(" ".join(line_buf))
            line_buf = [w["text"]]
            cur_y = wy
        else:
            line_buf.append(w["text"])
    if line_buf:
        lines.append(" ".join(line_buf))

    return " ".join(lines[:5]).strip()


# ---------------------------------------------------------------------------
# Image extraction
# ---------------------------------------------------------------------------


def _page_images(fitz_page, page_width: float, page_height: float) -> list[dict]:
    """Return list of {xref, rect} for product-sized images on this page.

    Filters out large decorative/background images (width > 70% of page).
    """
    seen_xrefs: set[int] = set()
    result: list[dict] = []
    for img in fitz_page.get_images():
        xref = img[0]
        if xref in seen_xrefs:
            continue
        seen_xrefs.add(xref)
        try:
            rects = fitz_page.get_image_rects(xref)
        except Exception:
            continue
        for r in rects:
            w = r.x1 - r.x0
            h = r.y1 - r.y0
            # Skip images that fill most of the page (backgrounds)
            if w > page_width * 0.75 or h > page_height * 0.45:
                continue
            result.append({"xref": xref, "rect": r})
    return result


def _match_image(page_images: list, cx0: float, cx1: float,
                 zy0: float, sale_y: float,
                 fitz_page, img_dir: Path, pdf_stem: str,
                 page_num: int, row_idx: int, col_idx: int) -> str | None:
    """Find the best matching image for this product zone and extract it."""
    img_area_mid = (zy0 + sale_y) / 2

    best = None
    best_score = float("inf")

    for item in page_images:
        r = item["rect"]
        # Image must overlap the column x range
        if r.x1 <= cx0 or r.x0 >= cx1:
            continue
        img_cy = (r.y0 + r.y1) / 2
        # Image centre should be above the sale price
        if img_cy >= sale_y:
            continue
        # Image must be within the zone
        if r.y1 < zy0:
            continue
        score = abs(img_cy - img_area_mid)
        if score < best_score:
            best_score = score
            best = item

    if not best:
        return None

    try:
        from PIL import Image as PILImage
        import io

        doc = fitz_page.parent
        pix = doc.extract_image(best["xref"])
        if not pix:
            return None
        img = PILImage.open(io.BytesIO(pix["image"])).convert("RGB")
        img.thumbnail((300, 300))
        fname = f"{pdf_stem}_p{page_num}_r{row_idx}_c{col_idx}.jpg"
        fpath = img_dir / fname
        if not fpath.exists():
            img.save(fpath, "JPEG", quality=85)
        return f"/images/{fname}"
    except Exception as exc:
        print(f"[lidl] image save error: {exc}", file=sys.stderr)
        return None
