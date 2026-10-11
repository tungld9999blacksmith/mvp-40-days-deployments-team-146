"""Amazon Location (GrabMaps) adapter against a mocked HTTP transport (location-search spec §12)."""

from __future__ import annotations

import json
import logging

import httpx
import pytest

from src.infrastructure.location.aws_places import AwsGrabPlacesProvider
from src.modules.location.domain import LatLng, PlaceType
from src.modules.location.ports import PlaceNotFoundError, PlaceOutOfCoverageError, ProviderUnavailableError

KEY = "secret-key-123"

VN_ADDRESS = {
    "Label": "Đường Cầu Giấy, Phường Cầu Giấy, Hà Nội, Việt Nam",
    "Country": {"Code2": "VN", "Code3": "VNM", "Name": "Việt Nam"},
    "Region": {"Name": "Hà Nội"},
    "SubDistrict": "Phường Cầu Giấy",
    "Street": "Đường Cầu Giấy",
}


def _suggest_item(place_id: str, title: str, *, country: str = "VN", kind: str = "Place", place_type="PointOfInterest"):
    return {
        "SuggestResultItemType": kind,
        "Title": title,
        "Place": {
            "PlaceId": place_id,
            "PlaceType": place_type,
            "Address": {**VN_ADDRESS, "Country": {"Code2": country}},
            "Position": [105.7939, 21.0301],
            "Distance": 6420.4,
        },
        "Highlights": {"Title": [{"StartIndex": 11, "EndIndex": 19, "Value": "Cầu Giấy"}]},
    }


class Recorder:
    """Mock transport that records requests and replays queued responses."""

    def __init__(self, *responses: httpx.Response | Exception) -> None:
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def body(self, index: int = 0) -> dict:
        return json.loads(self.requests[index].content)


def _provider(recorder: Recorder, **kwargs) -> AwsGrabPlacesProvider:
    client = httpx.AsyncClient(transport=httpx.MockTransport(recorder))
    return AwsGrabPlacesProvider(KEY, client=client, **kwargs)


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    monkeypatch.setattr("src.infrastructure.location.aws_places.RETRY_BACKOFF_SECONDS", 0)


@pytest.mark.asyncio
async def test_suggest_with_bias_position_sends_lng_lat_and_no_bbox():
    rec = Recorder(httpx.Response(200, json={"ResultItems": [_suggest_item("p1", "Công viên Cầu Giấy")]}))
    items = await _provider(rec).suggest("cau giay", near=LatLng(21.0285, 105.8542), limit=5)

    req = rec.requests[0]
    assert req.method == "POST"
    assert req.url.host == "places.geo.ap-southeast-1.amazonaws.com"
    assert req.url.path == "/v2/suggest"
    assert req.url.params["key"] == KEY
    body = rec.body()
    assert body["QueryText"] == "cau giay" and body["MaxResults"] == 5 and body["Language"] == "vi"
    assert body["BiasPosition"] == [105.8542, 21.0285]
    assert body["Filter"] == {"IncludeCountries": ["VNM"]}  # BiasPosition excludes BoundingBox
    assert "IntendedUse" not in body  # Suggest is SingleUse only

    (item,) = items
    assert (item.place_id, item.title, item.place_type) == ("p1", "Công viên Cầu Giấy", PlaceType.POI)
    assert item.position == LatLng(21.0301, 105.7939)
    assert item.distance_meters == 6420
    assert [(h.start, h.end) for h in item.highlights] == [(11, 19)]


@pytest.mark.asyncio
async def test_suggest_without_position_filters_by_vietnam_bbox_and_drops_queries_and_foreign():
    results = [
        _suggest_item("p1", "Cầu Giấy", place_type="District"),
        _suggest_item("q1", "cau giay ha noi", kind="Query"),
        _suggest_item("p2", "Cau Giay Bangkok", country="TH"),
        _suggest_item("p3", "Phố Cầu Giấy", place_type="Street"),
    ]
    rec = Recorder(httpx.Response(200, json={"ResultItems": results}))
    items = await _provider(rec).suggest("cau giay", near=None, limit=8)

    assert rec.body()["Filter"]["BoundingBox"] == [102.14, 8.18, 109.47, 23.39]
    assert "BiasPosition" not in rec.body()
    assert [(i.place_id, i.place_type) for i in items] == [("p1", PlaceType.AREA), ("p3", PlaceType.STREET)]


@pytest.mark.asyncio
async def test_get_place_maps_address_and_normalizes_province():
    place = {
        "PlaceId": "p 1/x",
        "PlaceType": "PointAddress",
        "Title": "25 Đường Cầu Giấy",
        "Address": {**VN_ADDRESS, "AddressNumber": "25", "Region": {"Name": "Thành phố Hà Nội"}},
        "Position": [105.7939, 21.0301],
    }
    rec = Recorder(httpx.Response(200, json=place))
    detail = await _provider(rec).get_place("p 1/x")

    req = rec.requests[0]
    assert req.method == "GET"
    assert req.url.raw_path.startswith(b"/v2/place/p%201%2Fx?")  # id is URL-encoded as one segment
    assert req.url.params["language"] == "vi"
    assert "intended-use" not in req.url.params  # not supported by GrabMaps on GetPlace
    assert detail.place_type == PlaceType.ADDRESS
    assert detail.street == "25 Đường Cầu Giấy"
    assert detail.ward == "Phường Cầu Giấy"
    assert (detail.province, detail.province_raw) == ("Hà Nội", "Thành phố Hà Nội")
    assert detail.position == LatLng(21.0301, 105.7939)
    assert detail.address_line == VN_ADDRESS["Label"]
    assert detail.provider == "aws-grabmaps"


@pytest.mark.asyncio
async def test_get_place_builds_address_line_and_province_from_parts_when_label_missing():
    address = {
        "Country": {"Code3": "VNM"},
        "Street": "Lê Lợi",
        "Locality": "Thủ Dầu Một",
        "Region": {"Name": "Bình Dương"},
    }
    rec = Recorder(
        httpx.Response(200, json={"PlaceId": "p", "Title": "", "Address": address, "Position": [106.6, 11.0]})
    )
    detail = await _provider(rec).get_place("p")
    assert detail.address_line == "Lê Lợi, Thủ Dầu Một, Bình Dương"
    assert detail.title == detail.address_line
    assert detail.province == "TP. Hồ Chí Minh"  # merged into HCMC in 2025
    assert detail.country_code == "VN"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 404])
async def test_get_place_unknown_id_is_not_found(status):
    rec = Recorder(httpx.Response(status, headers={"x-amzn-ErrorType": "ValidationException"}, json={}))
    with pytest.raises(PlaceNotFoundError):
        await _provider(rec).get_place("bad")


@pytest.mark.asyncio
async def test_get_place_outside_vietnam():
    place = {"PlaceId": "p", "Address": {"Country": {"Code2": "TH"}}, "Position": [100.5, 13.7]}
    with pytest.raises(PlaceOutOfCoverageError):
        await _provider(Recorder(httpx.Response(200, json=place))).get_place("p")


@pytest.mark.asyncio
async def test_reverse_uses_storage_radius_cap_and_keeps_the_query_position():
    item = {
        "PlaceId": "r1",
        "PlaceType": "Street",
        "Title": "Đường Cầu Giấy",
        "Address": VN_ADDRESS,
        "Position": [105.79, 21.03],
    }
    rec = Recorder(httpx.Response(200, json={"ResultItems": [item]}))
    point = LatLng(21.0301, 105.7939)
    detail = await _provider(rec, reverse_radius_meters=500_000).reverse(point)

    assert rec.requests[0].url.path == "/v2/reverse-geocode"
    body = rec.body()
    assert body["QueryPosition"] == [105.7939, 21.0301]
    assert body["QueryRadius"] == 100_000  # GrabMaps maximum
    assert body["IntendedUse"] == "Storage"
    assert detail.position == point


@pytest.mark.asyncio
async def test_reverse_without_results_is_not_found():
    with pytest.raises(PlaceNotFoundError):
        await _provider(Recorder(httpx.Response(200, json={"ResultItems": []}))).reverse(LatLng(21.0, 105.8))


@pytest.mark.asyncio
async def test_throttling_is_retried_once_then_succeeds():
    rec = Recorder(
        httpx.Response(429, headers={"x-amzn-ErrorType": "ThrottlingException"}),
        httpx.Response(200, json={"ResultItems": []}),
    )
    assert await _provider(rec).suggest("ab", near=None, limit=3) == []
    assert len(rec.requests) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failures",
    [
        (httpx.Response(503), httpx.Response(500)),
        (httpx.ConnectTimeout("t"), httpx.ReadTimeout("t")),
    ],
)
async def test_repeated_5xx_or_timeout_is_unavailable(failures):
    rec = Recorder(*failures)
    with pytest.raises(ProviderUnavailableError) as exc:
        await _provider(rec).suggest("ab", near=None, limit=3)
    assert exc.value.misconfigured is False
    assert len(rec.requests) == 2


@pytest.mark.asyncio
async def test_access_denied_is_unavailable_misconfigured_without_retry(caplog):
    rec = Recorder(httpx.Response(403, headers={"x-amzn-ErrorType": "AccessDeniedException"}))
    with caplog.at_level(logging.ERROR), pytest.raises(ProviderUnavailableError) as exc:
        await _provider(rec).suggest("ab", near=None, limit=3)
    assert exc.value.misconfigured is True
    assert len(rec.requests) == 1
    assert "misconfigured" in caplog.text


def test_httpx_request_log_masks_the_api_key():
    _provider(Recorder())  # installs the filter
    record = logging.LogRecord("httpx", logging.INFO, __file__, 1, 'HTTP Request: %s %s "%s"',
                               ("POST", f"https://x/v2/suggest?key={KEY}&a=1", "HTTP/1.1 200 OK"), None)  # fmt: skip
    for f in logging.getLogger("httpx").filters:
        f.filter(record)
    assert KEY not in record.getMessage()
    assert "key=***&a=1" in record.getMessage()


def test_missing_key_is_rejected():
    with pytest.raises(ValueError):
        AwsGrabPlacesProvider("")
