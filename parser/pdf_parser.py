"""
PDF parser for supermarket brochures.
Tries three strategies in order, uses first that returns > 5 products.
Strategy 2 (spatial) adds a pymupdf4llm fallback for image-only pages.
"""

import re
from datetime import date

# Quality check: reject a strategy if >40% of names start with digits
def _quality_ok(products: list) -> bool:
    if not products:
        return False
    bad = sum(1 for p in products if re.match(r'^\d', p['name']))
    return bad / len(products) < 0.4


def _ocr_page_fallback(pdf_path: str, page_idx: int, page_num: int) -> list[dict]:
    """
    Fallback for pages where spatial parser found 0 products.
    Uses pymupdf4llm OCR to extract text, then parses BGN prices
    and pairs them with nearby Cyrillic product names.
    """
    try:
        import pymupdf4llm

        md = pymupdf4llm.to_markdown(pdf_path, pages=[page_idx])

        # Extract OCR picture-text block if present; otherwise use full text
        m = re.search(r'Start of picture text(.*?)End of picture text', md, re.DOTALL)
        text = m.group(1) if m else md

        # Split into lines
        lines = [l.strip() for l in re.split(r'<br>|\n', text) if l.strip()]

        # Match: optional EUR price then BGN price  e.g.  "1,53€ 2,99ЛВ." or "2,99 ЛВ."
        bgn_pat = re.compile(r'(\d+)[,.](\d{2})\s*[ЛлLl]\s*[ВвBb]', re.IGNORECASE)

        products = []
        for i, line in enumerate(lines):
            bgn_hits = bgn_pat.findall(line)
            if not bgn_hits:
                continue

            # Collect Cyrillic context from a window of ±3 lines around the price line
            window = lines[max(0, i - 3):i] + lines[i + 1:min(len(lines), i + 4)]
            cyrillic_tokens = []
            for ctx in window:
                if bgn_pat.search(ctx):          # skip other price lines
                    continue
                if '%' in ctx:                   # skip discount badges
                    continue
                tokens = [t for t in ctx.split()
                          if len(re.findall(r'[а-яА-ЯёЁ]', t)) >= 2]
                cyrillic_tokens.extend(tokens)

            if not cyrillic_tokens:
                continue

            name = ' '.join(cyrillic_tokens[:3])  # first 3 Cyrillic words as name

            # Filter promo/navigation noise
            name_lower = name.lower()
            _promo_noise = ('хипермаркет', 'промоци', 'етикет', 'офер',
                            'брошур', 'покупка', 'страниц', 'информац')
            if any(kw in name_lower for kw in _promo_noise):
                continue
            _prepositions = ('от', 'до', 'в', 'на', 'към', 'за', 'при', 'с',
                             'по', 'под', 'над', 'без', 'пред', 'след')
            if name_lower.split()[0] in _prepositions:
                continue

            for hit in bgn_hits:
                price = float(f'{hit[0]}.{hit[1]}')
                if 0.01 < price < 500:
                    products.append({
                        'name': name,
                        'price': price,
                        'original_price': None,
                        'page_number': page_num,
                    })

        return products
    except Exception as e:
        print(f'OCR fallback page {page_num} failed: {e}', flush=True)
        return []


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

    # STRATEGY 2 — pymupdf spatial pairing + pymupdf4llm fallback for image-only pages
    if len(products) <= 5:
        try:
            import fitz
            _products = []
            doc = fitz.open(pdf_path)
            empty_page_indices = []  # (page_num, page_idx) for pages with 0 spatial hits

            for page_num, page in enumerate(doc, 1):
                page_start = len(_products)
                blocks = page.get_text('blocks')

                name_blocks = []
                raw_price_blocks = []

                for block in blocks:
                    text = block[4].strip()
                    if not text:
                        continue
                    x, y = block[0], block[1]

                    # --- Raw price block: contains any BGN price (ЛВ.) ---
                    bgn_matches = re.findall(r'(\d+)[,.](\d{2})ЛВ\.', text)
                    if bgn_matches:
                        bgn_prices = [
                            float(f'{m[0]}.{m[1]}') for m in bgn_matches
                        ]
                        bgn_prices = [p for p in bgn_prices if 0.01 < p < 500]
                        if bgn_prices:
                            raw_price_blocks.append({
                                'x': x, 'y': y,
                                'price': min(bgn_prices),
                            })
                        continue

                    # --- Name block: Cyrillic text, not a banner/footer ---
                    cyrillic_count = len(re.findall(r'[а-яА-ЯёЁ]', text))
                    if cyrillic_count < 3:
                        continue
                    if '%' in text:
                        continue
                    lines = [l.strip() for l in text.split('\n') if l.strip()]
                    if not lines or len(lines) > 5:
                        continue
                    first = lines[0]
                    if first.isupper() and len(first.split()) <= 2:
                        continue
                    if len(first) < 3:
                        continue
                    if re.match(r'^\d', first):
                        continue
                    if len(first) > 60 and first.count(' ') > 8:
                        continue
                    # Skip promo/navigation text
                    first_lower = first.lower()
                    _noise_kw = ('хипермаркет', 'промоци', 'етикет', 'брошур',
                                 'покупка', 'страниц', 'информац', 'офер')
                    if any(kw in first_lower for kw in _noise_kw):
                        continue
                    _preps = ('от', 'до', 'в', 'на', 'към', 'за', 'при',
                              'по', 'под', 'над', 'без', 'пред', 'след',
                              'допълнително', 'търси')
                    if first_lower.split()[0] in _preps:
                        continue
                    name_blocks.append({'x': x, 'y': y, 'name': first})

                # --- Phase 1: pair raw price blocks into (current, original) pairs ---
                used_raw = set()
                price_pairs = []
                for i, pb in enumerate(raw_price_blocks):
                    if i in used_raw:
                        continue
                    best_j = None
                    best_dy = float('inf')
                    for j, ob in enumerate(raw_price_blocks):
                        if j == i or j in used_raw:
                            continue
                        dx = abs(ob['x'] - pb['x'])
                        dy = ob['y'] - pb['y']
                        if dx <= 20 and -15 <= dy <= -4:
                            if abs(dy) < best_dy:
                                best_dy = abs(dy)
                                best_j = j
                    if best_j is not None:
                        ob = raw_price_blocks[best_j]
                        used_raw.update([i, best_j])
                        price_pairs.append({
                            'x': pb['x'], 'y': pb['y'],
                            'price': pb['price'],
                            'original_price': ob['price'],
                        })
                    else:
                        used_raw.add(i)
                        price_pairs.append({
                            'x': pb['x'], 'y': pb['y'],
                            'price': pb['price'],
                            'original_price': None,
                        })

                # --- Phase 2: match each name block to its nearest price pair ---
                used_pair_indices = set()
                for nb in name_blocks:
                    best_idx = None
                    best_score = float('inf')
                    for i, pp in enumerate(price_pairs):
                        if i in used_pair_indices:
                            continue
                        dx = abs(pp['x'] - nb['x'])
                        dy = abs(pp['y'] - nb['y'])
                        if dx > 350 or dy > 250:
                            continue
                        score = dx * 0.4 + dy
                        if score < best_score:
                            best_score = score
                            best_idx = i
                    if best_idx is None:
                        continue
                    pp = price_pairs[best_idx]
                    used_pair_indices.add(best_idx)
                    _products.append({
                        'name': nb['name'],
                        'price': pp['price'],
                        'original_price': pp['original_price'],
                        'page_number': page_num,
                    })

                if len(_products) == page_start:
                    empty_page_indices.append((page_num, page_num - 1))

            # --- Fallback: pymupdf4llm OCR for image-only pages ---
            if empty_page_indices:
                print(
                    f'Strategy 2: {len(empty_page_indices)} image-only pages, '
                    f'running OCR fallback...', flush=True
                )
                for page_num, page_idx in empty_page_indices:
                    ocr_hits = _ocr_page_fallback(pdf_path, page_idx, page_num)
                    _products.extend(ocr_hits)

            print(f'Strategy 2 (spatial+OCR): {len(_products)} products', flush=True)
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
