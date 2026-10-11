"""Province normalization to Vietnam's 34 current provincial units (location-search spec §5.4)."""

from __future__ import annotations

import pytest

from src.common.geo import PROVINCES, normalize_province, province_in_address


def test_34_unique_provinces():
    assert len(PROVINCES) == 34 == len(set(PROVINCES))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Hà Nội", "Hà Nội"),
        ("ha noi", "Hà Nội"),
        ("Thành phố Hồ Chí Minh", "TP. Hồ Chí Minh"),
        ("Bình Dương", "TP. Hồ Chí Minh"),
        ("Tỉnh Quảng Nam", "Đà Nẵng"),
        ("Thừa Thiên Huế", "Huế"),
        ("Kiên Giang", "An Giang"),
        ("Bà Rịa - Vũng Tàu", "TP. Hồ Chí Minh"),
        ("Bangkok", None),
        (None, None),
        ("", None),
    ],
)
def test_normalize_province(raw, expected):
    assert normalize_province(raw) == expected


def test_province_in_address_takes_the_last_whole_word_match():
    assert province_in_address("12 Phố Huế, Hai Bà Trưng, Hà Nội, Việt Nam") == "Hà Nội"
    assert province_in_address("QL51, Bà Rịa - Vũng Tàu") == "TP. Hồ Chí Minh"
    assert province_in_address("Khuê Trung") is None  # "hue" inside a word is not Huế
    assert province_in_address(None) is None
