"""Tests for product name normalizer."""

import pytest

from parser.normalizer import extract_unit


@pytest.mark.parametrize(
    "input_name,expected_name,expected_unit",
    [
        ("Прясно мляко 3.2% 1л", "прясно мляко 3.2%", "л"),
        ("ПРЕЗИДЕНТ Масло 82% 200г", "президент масло 82%", "г"),
        ("Яйца М 10бр", "яйца м", "бр"),
        ("Олио слънчогледово 1л", "олио слънчогледово", "л"),
        ("Хляб Добруджа 500г", "хляб добруджа", "г"),
        ("Сирене 400г кофа", "сирене", "г"),
        ("кашкавал витошка", "кашкавал витошка", None),
        ("Минерална вода 1.5л", "минерална вода", "л"),
        ("Тоалетна хартия 8бр", "тоалетна хартия", "бр"),
        ("захар 1кг", "захар", "кг"),
    ],
)
def test_extract_unit(input_name: str, expected_name: str, expected_unit: str | None):
    """Test that extract_unit correctly normalizes names and extracts units."""
    name, unit = extract_unit(input_name)
    assert name == expected_name
    assert unit == expected_unit
