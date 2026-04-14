"""Product name normalizer for Bulgarian supermarket data.

Pure functions only — no DB calls, no side effects.
"""

import re

# Noise words to remove from end of product names
NOISE_WORDS = {"кофа", "бутилка", "опаковка", "пакет", "пластмаса"}

# Unit patterns in priority order (longer patterns first to avoid partial matches)
UNIT_PATTERNS = [
    (r"(\d+(?:[.,]\d+)?)\s*кг\b", "кг"),
    (r"(\d+(?:[.,]\d+)?)\s*гр?\b", "г"),
    (r"(\d+(?:[.,]\d+)?)\s*л\b", "л"),
    (r"(\d+(?:[.,]\d+)?)\s*мл\b", "мл"),
    (r"(\d+(?:[.,]\d+)?)\s*бр\b", "бр"),
    (r"(\d+(?:[.,]\d+)?)\s*оп\b", "оп"),
]


def normalize(name: str) -> str:
    """Normalize a product name.

    - Lowercase
    - Strip whitespace, collapse multiple spaces
    - Remove quantity+unit patterns from end
    - Remove trailing noise words
    - Keep only Cyrillic, Latin, digits, %, .
    """
    # Lowercase
    text = name.lower()

    # Remove quantity+unit patterns
    for pattern, _ in UNIT_PATTERNS:
        text = re.sub(pattern, "", text)

    # Keep only allowed characters (Cyrillic, Latin, digits, %, ., space)
    text = re.sub(r"[^\u0400-\u04ff\w\d%.\s]", "", text)

    # Collapse multiple spaces and strip
    text = re.sub(r"\s+", " ", text).strip()

    # Remove trailing noise words
    words = text.split()
    while words and words[-1] in NOISE_WORDS:
        words.pop()

    return " ".join(words)


def extract_unit(name: str) -> tuple[str, str | None]:
    """Extract unit from product name.

    Detects units in this priority order:
        кг → "кг"
        г, гр → "г"
        л → "л"
        мл → "мл"
        бр → "бр"
        оп → "оп"

    Returns:
        (normalized_name, unit_found_or_None)
    """
    text = name.lower()
    unit_found = None

    # Check each pattern in priority order
    for pattern, unit in UNIT_PATTERNS:
        if re.search(pattern, text):
            unit_found = unit
            break

    return (normalize(name), unit_found)
