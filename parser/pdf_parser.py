"""
PDF parser for supermarket brochures.
Tries three strategies in order, uses first that returns > 5 products.
"""

import re
from datetime import date

# Quality check: reject a strategy if >40% of names start with digits
def _quality_ok(products: list) -> bool:
    if not products:
        return False
    bad = sum(1 for p in products if re.match(r'^\d', p['name']))
    return bad / len(products) < 0.4


def parse_pdf(pdf_path: str, store_name: str,
              valid_from: date, valid_to: date) -> list[dict]:

    products = []

    # STRATEGY 1 — pdfplumber tables
    try:
        import pdfplumber
        _products = []
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if not row:
                            continue
                        cells = [c for c in row if c]
                        text = ' '.join(cells)
                        prices = re.findall(r'(\d+)[,.](\d{2})', text)
                        if not prices:
                            continue
                        price = float(f'{prices[0][0]}.{prices[0][1]}')
                        if price > 500 or price < 0.01:
                            continue
                        name = cells[0] if cells else ''
                        name = name.strip()
                        if len(name) < 3:
                            continue
                        original = None
                        if len(prices) > 1:
                            p2 = float(f'{prices[1][0]}.{prices[1][1]}')
                            if p2 > price:
                                original = p2
                        _products.append({
                            'name': name,
                            'price': price,
                            'original_price': original,
                            'page_number': page_num,
                        })
        if len(_products) > 5 and _quality_ok(_products):
            print(f'Strategy 1 (tables): {len(_products)} products', flush=True)
            products = _products
        elif _products:
            print(f'Strategy 1 (tables): {len(_products)} products but quality check failed, trying next', flush=True)
    except Exception as e:
        print(f'Strategy 1 failed: {e}', flush=True)

    # STRATEGY 2 — pymupdf spatial pairing (name blocks ↔ price blocks by proximity)
    # Works well for visual product catalog PDFs where name and price are separate text layers.
    if len(products) <= 5:
        try:
            import fitz
            _products = []
            doc = fitz.open(pdf_path)

            for page_num, page in enumerate(doc, 1):
                blocks = page.get_text('blocks')
                page_w = page.rect.width
                page_h = page.rect.height

                name_blocks = []   # list of dicts
                price_blocks = []  # list of dicts

                for block in blocks:
                    text = block[4].strip()
                    if not text:
                        continue
                    x, y = block[0], block[1]

                    # --- Price block: contains BGN price (ЛВ.) ---
                    bgn_matches = re.findall(r'(\d+)[,.](\d{2})ЛВ\.', text)
                    if bgn_matches:
                        bgn_prices = [
                            float(f'{m[0]}.{m[1]}') for m in bgn_matches
                        ]
                        bgn_prices = [p for p in bgn_prices if 0.01 < p < 500]
                        if bgn_prices:
                            price = min(bgn_prices)
                            original = (
                                max(bgn_prices)
                                if len(bgn_prices) > 1 and max(bgn_prices) > price
                                else None
                            )
                            price_blocks.append({
                                'x': x, 'y': y,
                                'price': price, 'original': original,
                            })
                        continue

                    # --- Name block: Cyrillic text, not a banner/footer ---
                    cyrillic_count = len(re.findall(r'[а-яА-ЯёЁ]', text))
                    if cyrillic_count < 3:
                        continue
                    if '%' in text:
                        continue
                    # Split into lines; product names are 1-3 lines
                    lines = [l.strip() for l in text.split('\n') if l.strip()]
                    if not lines or len(lines) > 5:
                        continue
                    first = lines[0]
                    # Skip ALL-CAPS single words (section banners)
                    if first.isupper() and len(first.split()) <= 2:
                        continue
                    # Skip short noise
                    if len(first) < 3:
                        continue
                    # Skip leading digit (price/code fragments)
                    if re.match(r'^\d', first):
                        continue
                    # Skip footer-style long sentences (> 60 chars with spaces)
                    if len(first) > 60 and first.count(' ') > 8:
                        continue
                    name_blocks.append({
                        'x': x, 'y': y, 'name': first,
                    })

                # Pair each price block with the nearest name block
                used_name_indices = set()
                for pb in price_blocks:
                    best_idx = None
                    best_score = float('inf')
                    for i, nb in enumerate(name_blocks):
                        if i in used_name_indices:
                            continue
                        dx = abs(nb['x'] - pb['x'])
                        dy = abs(nb['y'] - pb['y'])
                        if dx > 350 or dy > 250:
                            continue
                        score = dx * 0.4 + dy
                        if score < best_score:
                            best_score = score
                            best_idx = i
                    if best_idx is not None:
                        nb = name_blocks[best_idx]
                        used_name_indices.add(best_idx)
                        _products.append({
                            'name': nb['name'],
                            'price': pb['price'],
                            'original_price': pb.get('original'),
                            'page_number': page_num,
                        })

            print(f'Strategy 2 (spatial): {len(_products)} products', flush=True)
            products = _products
        except Exception as e:
            print(f'Strategy 2 failed: {e}', flush=True)

    # STRATEGY 3 — pdfplumber text by coordinates (last resort)
    if len(products) <= 5:
        try:
            import pdfplumber
            _products = []
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    words = page.extract_words()
                    lines: dict = {}
                    for word in words:
                        y = round(word['top'] / 3) * 3
                        if y not in lines:
                            lines[y] = []
                        lines[y].append(word['text'])
                    for y in sorted(lines.keys()):
                        text = ' '.join(lines[y])
                        prices = re.findall(r'(\d+)[,.](\d{2})', text)
                        if not prices:
                            continue
                        price = float(f'{prices[0][0]}.{prices[0][1]}')
                        if price > 500 or price < 0.01:
                            continue
                        name_part = re.split(r'\d+[,.]\d{2}', text)[0].strip()
                        if len(name_part) < 3:
                            continue
                        _products.append({
                            'name': name_part,
                            'price': price,
                            'page_number': page_num,
                        })
            print(f'Strategy 3 (words): {len(_products)} products', flush=True)
            products = _products
        except Exception as e:
            print(f'Strategy 3 failed: {e}', flush=True)

    # Post-process: normalize units, deduplicate, attach metadata
    from parser.normalizer import extract_unit
    final = []
    seen = set()
    for p in products:
        name, unit = extract_unit(p['name'])
        key = (name.lower(), p['price'])
        if key in seen:
            continue
        seen.add(key)
        final.append({
            'name': name,
            'price': p['price'],
            'original_price': p.get('original_price'),
            'unit': unit,
            'page_number': p.get('page_number'),
            'store_name': store_name,
            'valid_from': valid_from,
            'valid_to': valid_to,
        })
    return final
