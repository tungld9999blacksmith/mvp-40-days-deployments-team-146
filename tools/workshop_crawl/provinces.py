"""Vietnam's 34 provincial units (since 2025-07-01) and the old → new name mapping.

Google addresses still often use the 63 pre-merger province names, so every region
read from a place is folded back to one of the 34 current names.
"""

from __future__ import annotations

import re
import unicodedata

# Current provincial units — region names stored on service_center / workshop.
PROVINCES: list[str] = [
    # 6 centrally governed cities
    "Hà Nội",
    "TP. Hồ Chí Minh",
    "Hải Phòng",
    "Đà Nẵng",
    "Cần Thơ",
    "Huế",
    # 28 provinces
    "Lai Châu",
    "Điện Biên",
    "Sơn La",
    "Lạng Sơn",
    "Cao Bằng",
    "Quảng Ninh",
    "Tuyên Quang",
    "Lào Cai",
    "Thái Nguyên",
    "Phú Thọ",
    "Bắc Ninh",
    "Hưng Yên",
    "Ninh Bình",
    "Thanh Hóa",
    "Nghệ An",
    "Hà Tĩnh",
    "Quảng Trị",
    "Quảng Ngãi",
    "Gia Lai",
    "Khánh Hòa",
    "Đắk Lắk",
    "Lâm Đồng",
    "Đồng Nai",
    "Tây Ninh",
    "Vĩnh Long",
    "Đồng Tháp",
    "An Giang",
    "Cà Mau",
]

# Pre-merger province → current provincial unit.
OLD_TO_NEW: dict[str, str] = {
    "Hà Giang": "Tuyên Quang",
    "Yên Bái": "Lào Cai",
    "Bắc Kạn": "Thái Nguyên",
    "Vĩnh Phúc": "Phú Thọ",
    "Hòa Bình": "Phú Thọ",
    "Bắc Giang": "Bắc Ninh",
    "Thái Bình": "Hưng Yên",
    "Hải Dương": "Hải Phòng",
    "Hà Nam": "Ninh Bình",
    "Nam Định": "Ninh Bình",
    "Quảng Bình": "Quảng Trị",
    "Quảng Nam": "Đà Nẵng",
    "Kon Tum": "Quảng Ngãi",
    "Bình Định": "Gia Lai",
    "Ninh Thuận": "Khánh Hòa",
    "Đắk Nông": "Lâm Đồng",
    "Bình Thuận": "Lâm Đồng",
    "Phú Yên": "Đắk Lắk",
    "Bình Dương": "TP. Hồ Chí Minh",
    "Bà Rịa - Vũng Tàu": "TP. Hồ Chí Minh",
    "Bà Rịa Vũng Tàu": "TP. Hồ Chí Minh",
    "Vũng Tàu": "TP. Hồ Chí Minh",
    "Bình Phước": "Đồng Nai",
    "Long An": "Tây Ninh",
    "Sóc Trăng": "Cần Thơ",
    "Hậu Giang": "Cần Thơ",
    "Bến Tre": "Vĩnh Long",
    "Trà Vinh": "Vĩnh Long",
    "Tiền Giang": "Đồng Tháp",
    "Bạc Liêu": "Cà Mau",
    "Kiên Giang": "An Giang",
    # Aliases of current names
    "Thừa Thiên Huế": "Huế",
    "Thừa Thiên - Huế": "Huế",
    "Hồ Chí Minh": "TP. Hồ Chí Minh",
    "Thành phố Hồ Chí Minh": "TP. Hồ Chí Minh",
    "Ho Chi Minh City": "TP. Hồ Chí Minh",
    "Sài Gòn": "TP. Hồ Chí Minh",
    "Hanoi": "Hà Nội",
    "Da Nang": "Đà Nẵng",
    "Hai Phong": "Hải Phòng",
    "Can Tho": "Cần Thơ",
    "Hue": "Huế",
    "Đắc Lắk": "Đắk Lắk",
    "Thanh Hoá": "Thanh Hóa",
    "Khánh Hoà": "Khánh Hòa",
}

_PREFIXES = ("thanh pho ", "tinh ", "tp ", "province ", "city ")


def fold(value: str | None) -> str:
    """Accent-, case- and punctuation-insensitive form: "TP. Hồ Chí Minh" → "tp ho chi minh"."""
    if not value:
        return ""
    text = unicodedata.normalize("NFD", value.replace("đ", "d").replace("Đ", "D"))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    return " ".join(re.sub(r"[^0-9a-z]+", " ", text).split())


def _strip_prefix(folded: str) -> str:
    for prefix in _PREFIXES:
        if folded.startswith(prefix):
            return folded[len(prefix) :]
    return folded


# folded name (without "tinh"/"thanh pho") → current province
_LOOKUP: dict[str, str] = {}
for _name in PROVINCES:
    _LOOKUP[_strip_prefix(fold(_name))] = _name
for _old, _new in OLD_TO_NEW.items():
    _LOOKUP[_strip_prefix(fold(_old))] = _new
# Longest names first so "ba ria vung tau" wins over "vung tau" when scanning addresses.
_SCAN_ORDER = sorted(_LOOKUP, key=len, reverse=True)


def normalize_province(value: str | None) -> str | None:
    """Map a province name (old or new, any accents / prefix) to a current province."""
    key = _strip_prefix(fold(value))
    return _LOOKUP.get(key) if key else None


def province_in_address(address: str | None) -> str | None:
    """Find the province named in a free-text address, scanning from the end (most specific last)."""
    folded = fold(address)
    if not folded:
        return None
    best: tuple[int, str] | None = None
    for key in _SCAN_ORDER:
        idx = folded.rfind(key)
        # Whole-word match only.
        if idx < 0:
            continue
        end = idx + len(key)
        if (idx > 0 and folded[idx - 1] != " ") or (end < len(folded) and folded[end] != " "):
            continue
        if best is None or idx > best[0]:
            best = (idx, _LOOKUP[key])
    return best[1] if best else None


# Search box per province ([west, south, east, north]). A province-wide query searched over the
# whole of Vietnam returns only a handful of places; restricting it to the province returns many more.
PROVINCE_BBOX: dict[str, list[float]] = {
    "Hà Nội": [105.28, 20.56, 106.02, 21.39],
}

# Pre-2025 districts, as place providers still label addresses. With ``crawl --by-area`` each one
# gets its own generic queries, to reach more workshops in a big city.
PROVINCE_AREAS: dict[str, list[str]] = {
    "Hà Nội": [
        "Ba Đình", "Hoàn Kiếm", "Tây Hồ", "Long Biên", "Cầu Giấy", "Đống Đa", "Hai Bà Trưng",
        "Hoàng Mai", "Thanh Xuân", "Nam Từ Liêm", "Bắc Từ Liêm", "Hà Đông", "Sơn Tây",
        "Ba Vì", "Phúc Thọ", "Đan Phượng", "Hoài Đức", "Quốc Oai", "Thạch Thất", "Chương Mỹ",
        "Thanh Oai", "Thường Tín", "Phú Xuyên", "Ứng Hòa", "Mỹ Đức", "Thanh Trì", "Gia Lâm",
        "Đông Anh", "Sóc Sơn", "Mê Linh",
    ],
}  # fmt: skip
