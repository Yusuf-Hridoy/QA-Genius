"""The PageSpeed client: no live network, no key in any log line."""

import json
import logging
import re
from pathlib import Path

import httpx
import pytest

from qagenius import pagespeed
from qagenius.pagespeed import (
    NO_KEY_ERROR,
    PRIVATE_URL_ERROR,
    PSI_URL,
    RATE_LIMIT_ERROR,
    TIMEOUT_ERROR,
    Measurement,
    PageSpeedError,
    measure,
    parse,
    validate_public_url,
)

SAMPLE = json.loads(
    (Path(__file__).parent / "fixtures" / "psi_sample.json").read_text(encoding="utf-8")
)
PAGE = "https://aurora-storefront.example/"
KEY = "AIzaTESTKEYmustneverbelogged"


class FakeClient:
    """Stands in for httpx.Client and remembers what it was asked for."""

    def __init__(self, payload=None, status=200, raises=None):
        self.payload = SAMPLE if payload is None else payload
        self.status = status
        self.raises = raises
        self.calls: list[tuple[str, dict]] = []

    def get(self, url, params=None):
        self.calls.append((url, dict(params or {})))
        if self.raises:
            raise self.raises
        return httpx.Response(
            self.status, json=self.payload, request=httpx.Request("GET", url)
        )

    def close(self):  # pragma: no cover - the route never owns this client
        pass


# ---------------------------------------------------------------- parsing


def test_lab_values_come_from_the_audits():
    found = parse(SAMPLE, PAGE, "mobile")
    assert found.lab["lcp"] == 3612.5
    assert found.lab["fcp"] == 1540
    assert found.lab["cls"] == 0.064
    assert found.lab["ttfb"] == 410
    assert found.lab["tbt"] == 340


def test_page_weight_turns_bytes_into_kilobytes():
    assert parse(SAMPLE, PAGE, "mobile").lab["weight"] == 2048.0


def test_field_values_come_from_the_loading_experience():
    found = parse(SAMPLE, PAGE, "mobile")
    assert found.field["lcp"] == 3820
    assert found.field["inp"] == 184


def test_the_field_layout_shift_is_scaled_down_by_a_hundred():
    """CrUX reports CLS as an integer x100: 12 means 0.12."""
    assert parse(SAMPLE, PAGE, "mobile").field["cls"] == pytest.approx(0.12)


def test_the_score_is_a_percentage():
    """Lighthouse scores 0-1; the page shows 0-100."""
    assert parse(SAMPLE, PAGE, "mobile").performance_score == 62


def test_a_page_with_no_real_user_data_still_parses():
    payload = dict(SAMPLE)
    payload.pop("loadingExperience")
    found = parse(payload, PAGE, "mobile")
    assert found.field == {}
    assert found.lab["lcp"] == 3612.5


def test_a_missing_audit_is_left_out_rather_than_guessed():
    payload = json.loads(json.dumps(SAMPLE))
    del payload["lighthouseResult"]["audits"]["server-response-time"]
    assert "ttfb" not in parse(payload, PAGE, "mobile").lab


def test_a_non_numeric_audit_value_is_ignored():
    payload = json.loads(json.dumps(SAMPLE))
    payload["lighthouseResult"]["audits"]["largest-contentful-paint"][
        "numericValue"
    ] = "fast"
    assert "lcp" not in parse(payload, PAGE, "mobile").lab


def test_the_measurement_remembers_what_was_measured():
    found = parse(SAMPLE, PAGE, "desktop")
    assert (found.url, found.strategy) == (PAGE, "desktop")
    assert found.fetched_at.startswith("20")


# ------------------------------------------------------------ url validation


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://example.com/path?q=1",
        "https://staging.aurora-storefront.example/checkout",
        "https://8.8.8.8/",
    ],
)
def test_a_public_url_is_allowed(url):
    assert validate_public_url(url) is None


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8000",
        "http://localhost",
        "http://127.0.0.1:8000/",
        "http://0.0.0.0/",
        "http://[::1]/",
        "http://192.168.1.5/",
        "http://10.0.0.2/",
        "http://172.16.4.4/",
        "http://169.254.1.1/",
        "http://build.local/",
    ],
)
def test_a_private_or_local_url_is_refused_with_the_k6_hint(url):
    assert validate_public_url(url) == PRIVATE_URL_ERROR


@pytest.mark.parametrize(
    "url", ["ftp://example.com", "javascript:alert(1)", "file:///etc/passwd", "example.com"]
)
def test_only_http_and_https_are_measured(url):
    reason = validate_public_url(url)
    assert reason and "http://" in reason


def test_an_empty_url_asks_for_one():
    assert "Paste the address" in validate_public_url("")


def test_a_url_with_no_host_is_refused():
    assert validate_public_url("https:///just-a-path") == "That address has no host name."


def test_an_absurdly_long_url_is_refused():
    assert "longer than" in validate_public_url("https://example.com/" + "a" * 2100)


# ------------------------------------------------------------------ measure


def test_measure_asks_google_for_the_right_thing():
    client = FakeClient()
    found = measure(PAGE, "desktop", client=client)
    url, params = client.calls[0]
    assert url == PSI_URL
    assert params == {"url": PAGE, "strategy": "DESKTOP", "category": "PERFORMANCE"}
    assert found.performance_score == 62


def test_measure_sends_the_key_only_when_there_is_one():
    client = FakeClient()
    measure(PAGE, "mobile", client=client)
    assert "key" not in client.calls[0][1]

    keyed = FakeClient()
    measure(PAGE, "mobile", api_key=KEY, client=keyed)
    assert keyed.calls[0][1]["key"] == KEY


def test_a_private_url_never_reaches_google():
    client = FakeClient()
    with pytest.raises(PageSpeedError) as error:
        measure("http://localhost:8000", client=client)
    assert str(error.value) == PRIVATE_URL_ERROR
    assert client.calls == []


def test_an_unknown_strategy_is_refused_before_the_call():
    client = FakeClient()
    with pytest.raises(PageSpeedError, match="mobile or desktop"):
        measure(PAGE, "tablet", client=client)
    assert client.calls == []


def test_a_timeout_says_what_to_try_next():
    client = FakeClient(raises=httpx.TimeoutException("too slow"))
    with pytest.raises(PageSpeedError) as error:
        measure(PAGE, client=client)
    assert str(error.value) == TIMEOUT_ERROR


def test_a_rate_limit_without_a_key_explains_the_key():
    """Google's keyless quota is zero, so this is the usual first failure."""
    client = FakeClient(payload={"error": {"code": 429}}, status=429)
    with pytest.raises(PageSpeedError) as error:
        measure(PAGE, client=client)
    assert str(error.value) == NO_KEY_ERROR


def test_a_rate_limit_with_a_key_says_to_wait():
    client = FakeClient(payload={"error": {"code": 429}}, status=429)
    with pytest.raises(PageSpeedError) as error:
        measure(PAGE, api_key=KEY, client=client)
    assert str(error.value) == RATE_LIMIT_ERROR


def test_a_bad_request_repeats_googles_reason():
    client = FakeClient(
        payload={"error": {"code": 400, "message": "Unable to process request."}},
        status=400,
    )
    with pytest.raises(PageSpeedError) as error:
        measure(PAGE, client=client)
    assert "Unable to process request." in str(error.value)


def test_a_lighthouse_runtime_error_is_repeated():
    client = FakeClient(
        payload={
            "lighthouseResult": {
                "runtimeError": {"message": "The page did not respond in time."}
            }
        },
        status=500,
    )
    with pytest.raises(PageSpeedError) as error:
        measure(PAGE, client=client)
    assert "did not respond in time" in str(error.value)


def test_a_two_hundred_with_no_lighthouse_result_is_still_an_error():
    client = FakeClient(payload={}, status=200)
    with pytest.raises(PageSpeedError, match="couldn't load that page"):
        measure(PAGE, client=client)


def test_the_key_never_reaches_a_log_or_an_error(caplog):
    caplog.set_level(logging.DEBUG)
    client = FakeClient(payload={"error": {"code": 400, "message": "nope"}}, status=400)
    with pytest.raises(PageSpeedError) as error:
        measure(PAGE, api_key=KEY, client=client)
    assert KEY not in str(error.value)
    assert KEY not in caplog.text


def test_a_transport_failure_does_not_leak_the_request(caplog):
    caplog.set_level(logging.DEBUG)
    client = FakeClient(raises=httpx.ConnectError("boom"))
    with pytest.raises(PageSpeedError) as error:
        measure(PAGE, api_key=KEY, client=client)
    assert KEY not in str(error.value)
    assert KEY not in caplog.text


def test_the_module_only_ever_talks_to_googleapis():
    """The page under test is a parameter Google fetches, never a URL we open."""
    assert PSI_URL.startswith("https://www.googleapis.com/")
    source = Path(pagespeed.__file__).read_text(encoding="utf-8")
    hosts = {
        host
        for host in re.findall(r"https?://([A-Za-z0-9.-]*)", source)
        if any(char.isalpha() for char in host)
    }
    assert hosts == {"www.googleapis.com"}


def test_a_measurement_defaults_to_empty_rather_than_none():
    found = Measurement(url=PAGE, strategy="mobile")
    assert (found.lab, found.field, found.performance_score) == ({}, {}, None)
