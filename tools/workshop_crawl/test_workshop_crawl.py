"""Offline tests for workshop_crawl (no Google / AWS calls).

Run: cd backend && uv run --frozen pytest ../tools/workshop_crawl -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import workshop_crawl as wc  # noqa: E402
from aws_places import VIETNAM_BBOX, AwsPlacesClient  # noqa: E402
from google_places import GooglePlacesClient  # noqa: E402
from places import SearchClient, error_message  # noqa: E402
from provinces import PROVINCES, normalize_province, province_in_address  # noqa: E402


def _place(pid: str, name: str, admin: str | None = "Hà Nội", *, dealer=False, automotive=True, **extra):
    """A normalized place (the shape every client returns)."""
    place = {
        "source": "aws",
        "id": pid,
        "name": name,
        "address": f"1 Đường A, {admin or 'Hà Nội'}, Việt Nam",
        "latitude": 21.0,
        "longitude": 105.8,
        "country": "VN",
        "admin_area": admin,
        "categories": ["car_repair"],
        "automotive": automotive,
        "dealer": dealer,
        "closed": False,
        "maps_uri": None,
    }
    place.update(extra)
    return place


def _google_raw(pid: str, name: str, admin: str = "Hà Nội", *, types=("car_repair",), status="OPERATIONAL"):
    return {
        "id": pid,
        "displayName": {"text": name},
        "formattedAddress": f"1 Đường A, {admin}, Việt Nam",
        "addressComponents": [
            {"longText": "Việt Nam", "shortText": "VN", "types": ["country"]},
            {"longText": admin, "shortText": admin, "types": ["administrative_area_level_1"]},
        ],
        "location": {"latitude": 21.0, "longitude": 105.8},
        "types": list(types),
        "businessStatus": status,
        "googleMapsUri": "https://maps.google.com/?cid=1",
        "nationalPhoneNumber": "024 1234 5678",
    }


def _aws_raw(pid: str, title: str, region: str = "Hà Nội", *, categories=("car_repair",), country="VN"):
    return {
        "PlaceId": pid,
        "PlaceType": "PointOfInterest",
        "Title": title,
        "Address": {
            "Label": f"1 Đường A, {region}, Việt Nam",
            "Country": {"Code2": country, "Code3": "VNM", "Name": "Việt Nam"},
            "Region": {"Name": region},
        },
        "Position": [105.8, 21.0],
        "Categories": [{"Id": c, "Name": c.replace("_", " ").title()} for c in categories],
        "Contacts": {"Phones": [{"Value": "+84 24 1234 5678"}]},
    }


# --------------------------------------------------------------------------- provinces
def test_34_provinces():
    assert len(PROVINCES) == 34 == len(set(PROVINCES))


def test_normalize_province_maps_old_names_and_prefixes():
    assert normalize_province("Thành phố Hồ Chí Minh") == "TP. Hồ Chí Minh"
    assert normalize_province("Bình Dương") == "TP. Hồ Chí Minh"
    assert normalize_province("Tỉnh Quảng Nam") == "Đà Nẵng"
    assert normalize_province("ha noi") == "Hà Nội"
    assert normalize_province("Thừa Thiên Huế") == "Huế"
    assert normalize_province("Bangkok") is None


def test_province_in_address_prefers_the_last_match():
    assert province_in_address("12 Phố Huế, Hai Bà Trưng, Hà Nội, Việt Nam") == "Hà Nội"
    assert province_in_address("QL1A, Bà Rịa - Vũng Tàu") == "TP. Hồ Chí Minh"
    assert province_in_address("no province here") is None


# --------------------------------------------------------------------------- normalization
def test_google_normalize():
    client = GooglePlacesClient("k", Path("unused"))
    place = client.normalize(_google_raw("g1", "VinFast A", "Kiên Giang", types=("car_dealer",), status="CLOSED_PERMANENTLY"))
    assert place["source"] == "google" and place["id"] == "g1"
    assert (place["country"], place["admin_area"]) == ("VN", "Kiên Giang")
    assert place["dealer"] and place["automotive"] and place["closed"]
    assert place["phone"] == "024 1234 5678"


def test_aws_normalize_reads_position_as_lon_lat():
    place = AwsPlacesClient("k", Path("unused")).normalize(_aws_raw("a1", "Gara Minh", "Quảng Nam"))
    assert place["source"] == "aws" and place["id"] == "a1"
    assert (place["latitude"], place["longitude"]) == (21.0, 105.8)
    assert (place["country"], place["admin_area"]) == ("VN", "Quảng Nam")
    assert place["automotive"] and not place["dealer"] and not place["closed"]
    assert place["phone"] == "+84 24 1234 5678"


def test_aws_automotive_detection():
    client = AwsPlacesClient("k", Path("unused"))
    assert client.normalize(_aws_raw("a", "Đại lý X", categories=("car_dealer",)))["dealer"]
    assert not client.normalize(_aws_raw("a", "Nha khoa", categories=("dental_clinic",)))["automotive"]
    assert not client.normalize(_aws_raw("a", "Day care", categories=("child_care",)))["automotive"]
    assert not client.normalize(_aws_raw("a", "Sửa xe máy Hùng", categories=("motorcycle_repair",)))["automotive"]
    # no categories → fall back to the name
    assert client.normalize(_aws_raw("a", "Gara Ô tô Tuấn", categories=()))["automotive"]
    assert not client.normalize(_aws_raw("a", "Cửa hàng tạp hoá", categories=()))["automotive"]


def test_aws_request_body(tmp_path):
    sent = {}

    class Fake(AwsPlacesClient):
        def _post(self, url, body, headers, attempts=4):
            sent.update(url=url, body=body)
            return {"ResultItems": [_aws_raw("a1", "Gara A")]}

    client = Fake("my key", tmp_path, region="ap-southeast-1", with_contact=True)
    places = client.search("gara sửa chữa ô tô Hà Nội", repair_only=True, max_pages=3)
    assert sent["url"] == "https://places.geo.ap-southeast-1.amazonaws.com/v2/search-text?key=my%20key"
    assert sent["body"]["MaxResults"] == 60
    assert sent["body"]["IntendedUse"] == "Storage"
    assert sent["body"]["Filter"]["IncludeCountries"] == ["VNM"]
    assert sent["body"]["AdditionalFeatures"] == ["Contact"]
    assert [p["id"] for p in places] == ["a1"]

    # second call is served from the cache
    sent.clear()
    assert client.search("gara sửa chữa ô tô Hà Nội", repair_only=True, max_pages=3)[0]["id"] == "a1"
    assert not sent and client.cache_hits == 1


def test_error_message_handles_both_providers():
    assert error_message('{"error": {"message": "bad key"}}') == "bad key"
    assert error_message('{"message": "Forbidden"}') == "Forbidden"
    assert error_message("plain text") == "plain text"


# --------------------------------------------------------------------------- crawl logic
def test_resolve_region_falls_back_to_address_then_searched_province():
    assert wc.resolve_region(_place("a", "X", "Kiên Giang"), "Hà Nội") == "An Giang"
    no_admin = _place("b", "X", None, address="5 Lê Lợi, Đà Nẵng")
    assert wc.resolve_region(no_admin, "Hà Nội") == "Đà Nẵng"
    no_admin["address"] = "5 Lê Lợi"
    assert wc.resolve_region(no_admin, "Huế") == "Huế"


def test_keep_place_filters():
    assert wc.keep_place(_place("a", "Gara A"), None)
    assert not wc.keep_place(_place("a", "Gara A", closed=True), None)
    assert not wc.keep_place(_place("a", "Gara A", latitude=None), None)
    assert not wc.keep_place(_place("a", "Nha khoa", automotive=False), None)  # generic query needs a car category
    assert wc.keep_place(_place("a", "VinFast Thăng Long", automotive=False), "vinfast")
    # Brand queries also keep car dealers / repair shops listed without the brand (e.g. "SR Long Biên-Hà Nội").
    assert wc.keep_place(_place("a", "SR Long Biên-Hà Nội"), "vinfast")
    assert not wc.keep_place(_place("a", "Nha khoa", automotive=False), "vinfast")
    assert not wc.keep_place(_place("a", "Gara A", country="LA"), None)


def test_to_record_is_deterministic_and_typed():
    rec = wc.to_record(_place("pid-1", "VinFast A", dealer=True), "Hà Nội", "q")
    again = wc.to_record(_place("pid-1", "VinFast A", dealer=True), "Hà Nội", "q")
    assert rec["center_id"] == again["center_id"] and rec["center_id"].startswith("AL-")
    assert rec["manager_email"] == again["manager_email"]
    assert len(rec["manager_national_id"]) == 12
    assert rec["type"] == "dealer"
    assert (rec["latitude"], rec["longitude"]) == (21.0, 105.8)
    google = wc.to_record(_place("pid-1", "VinFast A", source="google"), "Hà Nội", "q")
    assert google["center_id"].startswith("GM-") and google["center_id"][3:] == rec["center_id"][3:]


def test_select_balanced_spreads_over_provinces_and_backfills():
    recs = [{"region": "Hà Nội", "name": f"Gara {i}"} for i in range(50)]
    recs += [{"region": "Huế", "name": f"Gara {i}"} for i in range(3)]
    recs += [{"region": "Đà Nẵng", "name": "VinFast Đà Nẵng"}, {"region": "Đà Nẵng", "name": "Gara Z"}]
    picked = wc.select_balanced(recs, 10, PROVINCES)
    regions = [r["region"] for r in picked]
    assert len(picked) == 10
    assert regions.count("Huế") == 3  # small province fully used
    assert regions.count("Đà Nẵng") == 2
    assert regions.count("Hà Nội") == 5  # the rest backfilled from the big one
    assert next(r for r in picked if r["region"] == "Đà Nẵng")["name"] == "VinFast Đà Nẵng"


def test_select_balanced_spreads_a_province_over_districts():
    def rec(name, district):
        return {"region": "Hà Nội", "name": name, "address": f"{name}, 1 Phố A, {district}, Hà Nội, Việt Nam"}

    # Crawl order clusters by district (one district query after another).
    recs = [rec(f"Gara BĐ{i}", "Quận Ba Đình") for i in range(4)]
    recs += [rec(f"Gara TH{i}", "Quận Tây Hồ") for i in range(4)]
    recs += [rec("Gara CG", "Quận Cầu Giấy"), rec("VinFast Long Biên", "Quận Long Biên")]

    picked = [r["name"] for r in wc.select_balanced(recs, 5, PROVINCES)]

    assert picked == ["VinFast Long Biên", "Gara BĐ0", "Gara TH0", "Gara CG", "Gara BĐ1"]
    assert wc.district_of(recs[0]) == "quan ba dinh"
    assert wc.district_of({"address": "Hà Nội, Việt Nam"}) == ""


def test_crawl_writes_balanced_file(tmp_path, monkeypatch):
    def fake_search(self, query, *, repair_only, max_pages, bbox=None):
        self.requests_made += 1
        province = next(p for p in PROVINCES if query.endswith(p))
        if "VinFast" in query:
            assert not repair_only
            return [_place(f"vf-{province}", f"VinFast {province}", province, dealer=True)]
        assert repair_only
        return [_place(f"g-{province}-{i}", f"Gara {i}", province) for i in range(5)]

    monkeypatch.setattr(SearchClient, "search", fake_search)
    out = tmp_path / "workshops.json"
    argv = ["crawl", "--source", "aws", "--key", "k", "--target", "20", "--provinces", "Hà Nội,Huế", "--out", str(out)]
    assert wc.main(argv) == 0

    data = json.loads(out.read_text(encoding="utf-8"))
    regions = [w["region"] for w in data["workshops"]]
    assert data["source"] == AwsPlacesClient.label
    assert data["count"] == 12  # 6 unique per province (1 VinFast + 5 gara), target not reached
    assert regions.count("Hà Nội") == regions.count("Huế") == 6
    assert sum(w["type"] == "dealer" for w in data["workshops"]) == 2
    assert all(w["center_id"].startswith("AL-") for w in data["workshops"])


def test_province_queries_add_districts_only_with_by_area():
    base = wc.province_queries("Hà Nội", by_area=False)
    assert [q for q, _ in base] == [t.format(p="Hà Nội") for t, _ in wc.QUERY_PLAN]

    queries = wc.province_queries("Hà Nội", by_area=True)
    areas = len(wc.PROVINCE_AREAS["Hà Nội"])
    assert len(queries) == len(wc.QUERY_PLAN) + areas * len(wc.AREA_QUERY_PLAN)
    assert ("gara ô tô Cầu Giấy Hà Nội", None) in queries
    # A province without a district list only gets the province-wide plan.
    assert wc.province_queries("Huế", by_area=True) == wc.province_queries("Huế", by_area=False)


def test_bbox_narrows_the_search_and_gets_its_own_cache_entry(tmp_path):
    bodies = []

    class Fake(AwsPlacesClient):
        def _post(self, url, body, headers, attempts=4):
            bodies.append(body)
            return {"ResultItems": [_aws_raw("a1", "Gara A")]}

    client = Fake("k", tmp_path)
    hanoi = wc.PROVINCE_BBOX["Hà Nội"]
    client.search("gara ô tô Hà Nội", repair_only=True, max_pages=1)
    client.search("gara ô tô Hà Nội", repair_only=True, max_pages=1, bbox=hanoi)
    client.search("gara ô tô Hà Nội", repair_only=True, max_pages=1, bbox=hanoi)

    assert [b["Filter"]["BoundingBox"] for b in bodies] == [VIETNAM_BBOX, hanoi]
    assert client.cache_hits == 1
    # Without a bbox the cache key is unchanged, so caches from earlier crawls stay valid.
    assert client._cache_file("q", True, 1) == client._cache_file("q", True, 1, None)


def test_google_bbox_becomes_location_rectangle(tmp_path):
    sent = {}

    class Fake(GooglePlacesClient):
        def _post(self, url, body, headers, attempts=4):
            sent.update(body)
            return {"places": []}

    Fake("k", tmp_path).search("gara", repair_only=True, max_pages=1, bbox=[105.28, 20.56, 106.02, 21.39])
    assert sent["locationRestriction"]["rectangle"] == {
        "low": {"latitude": 20.56, "longitude": 105.28},
        "high": {"latitude": 21.39, "longitude": 106.02},
    }
