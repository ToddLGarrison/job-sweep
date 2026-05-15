import json
from unittest.mock import MagicMock, patch

import pytest

from scrapers.comeet import _extract_location, _parse_positions, fetch_jobs


def _make_page(positions: list) -> str:
    data = json.dumps(positions)
    return f"<html><script>var COMPANY_POSITIONS_DATA = {data};\n</script></html>"


def _position(
    name="Solutions Engineer",
    url="https://www.comeet.com/jobs/cyera/17.008/solutions-engineer/A1.234",
    country="US",
    city="Austin",
    state="TX",
    is_remote=False,
    details=None,
):
    return {
        "name": name,
        "url_active_page": url,
        "location": {
            "country": country,
            "city": city,
            "state": state,
            "is_remote": is_remote,
        },
        "custom_fields": {
            "details": details or [],
        },
    }


# --- _parse_positions ---

class TestParsePositions:
    def test_parses_standard_format(self):
        pos = [_position()]
        page = _make_page(pos)
        result = _parse_positions(page)
        assert len(result) == 1
        assert result[0]["name"] == "Solutions Engineer"

    def test_parses_multiple_positions(self):
        pos = [_position(name="SE"), _position(name="CSM")]
        result = _parse_positions(_make_page(pos))
        assert len(result) == 2

    def test_raises_when_not_found(self):
        with pytest.raises(ValueError, match="COMPANY_POSITIONS_DATA not found"):
            _parse_positions("<html><script>var x = 1;</script></html>")

    def test_fallback_broad_match(self):
        # No newline after the semicolon — should use fallback regex
        data = json.dumps([_position()])
        page = f"<script>COMPANY_POSITIONS_DATA = {data};</script>"
        result = _parse_positions(page)
        assert len(result) == 1


# --- _extract_location ---

class TestExtractLocation:
    def test_us_city_state(self):
        loc = {"country": "US", "city": "Austin", "state": "TX", "is_remote": False}
        assert _extract_location(loc) == "Austin, TX"

    def test_us_city_only(self):
        loc = {"country": "US", "city": "Denver", "state": "", "is_remote": False}
        assert _extract_location(loc) == "Denver"

    def test_us_remote(self):
        loc = {"country": "US", "city": "", "state": "", "is_remote": True}
        assert _extract_location(loc) == "Remote"

    def test_us_no_city_no_remote(self):
        loc = {"country": "US", "city": "", "state": "", "is_remote": False}
        assert _extract_location(loc) == "United States"

    def test_non_us_city_country(self):
        loc = {"country": "IL", "city": "Tel Aviv", "state": "", "is_remote": False}
        assert _extract_location(loc) == "Tel Aviv, Israel"

    def test_non_us_country_only(self):
        loc = {"country": "DE", "city": "", "state": "", "is_remote": False}
        assert _extract_location(loc) == "Germany"

    def test_non_us_remote_returns_country_name(self):
        loc = {"country": "CA", "city": "", "state": "", "is_remote": True}
        assert _extract_location(loc) == "Canada"

    def test_unknown_country_code_returned_as_is(self):
        loc = {"country": "ZZ", "city": "Atlantis", "state": "", "is_remote": False}
        assert _extract_location(loc) == "Atlantis, ZZ"

    def test_empty_dict(self):
        assert _extract_location({}) == ""

    def test_india_country_code(self):
        loc = {"country": "IN", "city": "Hyderabad", "state": "", "is_remote": False}
        assert _extract_location(loc) == "Hyderabad, India"

    def test_canada_code_not_california(self):
        loc = {"country": "CA", "city": "Toronto", "state": "ON", "is_remote": False}
        assert _extract_location(loc) == "Toronto, Canada"


# --- fetch_jobs ---

class TestFetchJobs:
    def _mock_response(self, positions: list):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = _make_page(positions)
        return mock_resp

    def test_returns_job_listing_objects(self):
        pos = [_position()]
        with patch("scrapers.comeet.requests.get") as mock_get:
            mock_get.return_value = self._mock_response(pos)
            listings, geo_filtered = fetch_jobs("cyera/17.008")
        assert len(listings) == 1
        assert listings[0].title == "Solutions Engineer"
        assert listings[0].location == "Austin, TX"
        assert geo_filtered == 0

    def test_geo_filter_excludes_non_us(self):
        pos = [_position(country="IN", city="Hyderabad", state="")]
        with patch("scrapers.comeet.requests.get") as mock_get:
            mock_get.return_value = self._mock_response(pos)
            listings, geo_filtered = fetch_jobs("cyera/17.008")
        assert listings == []
        assert geo_filtered == 1

    def test_title_geo_filter_excludes_emea(self):
        pos = [_position(name="Solutions Engineer, EMEA")]
        with patch("scrapers.comeet.requests.get") as mock_get:
            mock_get.return_value = self._mock_response(pos)
            listings, geo_filtered = fetch_jobs("cyera/17.008")
        assert listings == []
        assert geo_filtered == 1

    def test_remote_us_passes_geo_filter(self):
        pos = [_position(country="US", city="", state="", is_remote=True)]
        with patch("scrapers.comeet.requests.get") as mock_get:
            mock_get.return_value = self._mock_response(pos)
            listings, geo_filtered = fetch_jobs("cyera/17.008")
        assert len(listings) == 1
        assert listings[0].location == "Remote"

    def test_non_us_remote_geo_filtered(self):
        pos = [_position(country="GB", city="", state="", is_remote=True)]
        with patch("scrapers.comeet.requests.get") as mock_get:
            mock_get.return_value = self._mock_response(pos)
            listings, geo_filtered = fetch_jobs("cyera/17.008")
        assert listings == []
        assert geo_filtered == 1

    def test_missing_title_skipped(self):
        pos = [_position(name="")]
        with patch("scrapers.comeet.requests.get") as mock_get:
            mock_get.return_value = self._mock_response(pos)
            listings, _ = fetch_jobs("cyera/17.008")
        assert listings == []

    def test_missing_url_skipped(self):
        pos = [_position(url="")]
        with patch("scrapers.comeet.requests.get") as mock_get:
            mock_get.return_value = self._mock_response(pos)
            listings, _ = fetch_jobs("cyera/17.008")
        assert listings == []

    def test_http_error_returns_empty(self):
        with patch("scrapers.comeet.requests.get") as mock_get:
            mock_get.side_effect = Exception("timeout")
            listings, geo_filtered = fetch_jobs("cyera/17.008")
        assert listings == []
        assert geo_filtered == 0

    def test_http_status_error_returns_empty(self):
        with patch("scrapers.comeet.requests.get") as mock_get:
            mock = MagicMock()
            mock.raise_for_status.side_effect = Exception("404 Not Found")
            mock_get.return_value = mock
            listings, geo_filtered = fetch_jobs("cyera/17.008")
        assert listings == []
        assert geo_filtered == 0

    def test_parse_error_returns_empty(self):
        with patch("scrapers.comeet.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.text = "<html>no positions here</html>"
            mock_get.return_value = mock_resp
            listings, geo_filtered = fetch_jobs("cyera/17.008")
        assert listings == []
        assert geo_filtered == 0

    def test_description_extracted_from_custom_fields(self):
        details = [
            {"value": "<p>Join our team.</p>"},
            {"value": "3+ years &amp; strong skills"},
        ]
        pos = [_position(details=details)]
        with patch("scrapers.comeet.requests.get") as mock_get:
            mock_get.return_value = self._mock_response(pos)
            listings, _ = fetch_jobs("cyera/17.008")
        assert "Join our team" in listings[0].description
        assert "3+ years & strong skills" in listings[0].description

    def test_url_active_page_preferred_over_hosted(self):
        position = {
            "name": "SE",
            "url_active_page": "https://active.url/1",
            "url_comeet_hosted_page": "https://hosted.url/2",
            "location": {"country": "US", "city": "NYC", "state": "NY", "is_remote": False},
            "custom_fields": {"details": []},
        }
        page = _make_page([position])
        with patch("scrapers.comeet.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.text = page
            mock_get.return_value = mock_resp
            listings, _ = fetch_jobs("cyera/17.008")
        assert listings[0].url == "https://active.url/1"

    def test_falls_back_to_hosted_url_when_active_missing(self):
        position = {
            "name": "SE",
            "url_active_page": "",
            "url_comeet_hosted_page": "https://hosted.url/2",
            "location": {"country": "US", "city": "NYC", "state": "NY", "is_remote": False},
            "custom_fields": {"details": []},
        }
        page = _make_page([position])
        with patch("scrapers.comeet.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.text = page
            mock_get.return_value = mock_resp
            listings, _ = fetch_jobs("cyera/17.008")
        assert listings[0].url == "https://hosted.url/2"

    def test_multiple_positions_mixed_geo(self):
        positions = [
            _position(name="SE US", country="US", city="SF", state="CA"),
            _position(name="SE India", country="IN", city="Pune", state=""),
            _position(name="SE Remote", country="US", city="", state="", is_remote=True),
        ]
        with patch("scrapers.comeet.requests.get") as mock_get:
            mock_get.return_value = self._mock_response(positions)
            listings, geo_filtered = fetch_jobs("cyera/17.008")
        assert len(listings) == 2
        assert geo_filtered == 1
