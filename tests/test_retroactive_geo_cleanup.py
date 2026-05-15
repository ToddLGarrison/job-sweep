import os
import sys
from unittest.mock import MagicMock, call, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from retroactive_geo_cleanup import (
    _extract_title,
    _get_location,
    _should_geo_close,
    run_cleanup,
)


# --- _extract_title ---

class TestExtractTitle:
    def test_standard_format(self):
        assert _extract_title("Acme / Solutions Engineer / 2026") == "Solutions Engineer"

    def test_title_with_spaces(self):
        assert _extract_title("Stripe / Customer Success Manager / 2026") == "Customer Success Manager"

    def test_title_with_geo_suffix(self):
        assert _extract_title("Postman / Enterprise Solutions Engineer, LATAM / 2026") == "Enterprise Solutions Engineer, LATAM"

    def test_only_one_segment_returns_full_name(self):
        assert _extract_title("Just a name") == "Just a name"

    def test_empty_string(self):
        assert _extract_title("") == ""


# --- _get_location ---

class TestGetLocation:
    def test_rich_text_location(self):
        props = {"Location": {"rich_text": [{"plain_text": "Hyderabad IN"}]}}
        assert _get_location(props) == "Hyderabad IN"

    def test_missing_location_property(self):
        props = {}
        assert _get_location(props) == ""

    def test_empty_rich_text(self):
        props = {"Location": {"rich_text": []}}
        assert _get_location(props) == ""


# --- _should_geo_close ---

class TestShouldGeoClose:
    def test_geo_title_emea(self):
        should_close, flag = _should_geo_close("Customer Success Engineer, EMEA", "Remote")
        assert should_close is True
        assert flag == "GEO_TITLE"

    def test_geo_title_country(self):
        should_close, flag = _should_geo_close("Solutions Engineer, Japan", "")
        assert should_close is True
        assert flag == "GEO_TITLE"

    def test_geo_location_india(self):
        should_close, flag = _should_geo_close("Solutions Engineer", "Hyderabad IN")
        assert should_close is True
        assert flag == "GEO_LOCATION"

    def test_geo_location_canada(self):
        should_close, flag = _should_geo_close("Customer Success Manager", "Toronto, ON")
        assert should_close is True
        assert flag == "GEO_LOCATION"

    def test_clean_us_remote(self):
        should_close, flag = _should_geo_close("Solutions Engineer", "Remote")
        assert should_close is False
        assert flag == ""

    def test_clean_us_city(self):
        should_close, flag = _should_geo_close("Customer Success Manager", "San Francisco, CA")
        assert should_close is False
        assert flag == ""

    def test_clean_empty_location(self):
        should_close, flag = _should_geo_close("Solutions Engineer", "")
        assert should_close is False
        assert flag == ""

    def test_geo_title_takes_precedence_over_location(self):
        # Even if location is US, a geo title should still flag it
        should_close, flag = _should_geo_close("Solutions Engineer, LATAM", "Remote")
        assert should_close is True
        assert flag == "GEO_TITLE"


# --- run_cleanup ---

def _make_opp(page_id, name, url="https://jobs.greenhouse.io/x/1", location=""):
    return {"page_id": page_id, "name": name, "url": url, "location": location}


class TestRunCleanup:
    def _mock_client(self):
        client = MagicMock()
        return client

    def test_geo_title_flagged_and_closed(self):
        opp = _make_opp("p1", "Acme / Solutions Engineer, EMEA / 2026")
        mock_client = self._mock_client()
        with patch("retroactive_geo_cleanup._fetch_active_opps", return_value=[opp]):
            result = run_cleanup(dry_run=False, client=mock_client)
        assert result["closed_title"] == 1
        assert result["closed_location"] == 0
        assert result["skipped"] == 0
        mock_client.pages.update.assert_called_once_with(
            page_id="p1",
            properties={"Stage": {"select": {"name": "Closed Lost"}}},
        )

    def test_geo_location_flagged_and_closed(self):
        opp = _make_opp("p2", "Acme / Solutions Engineer / 2026", location="Hyderabad IN")
        mock_client = self._mock_client()
        with patch("retroactive_geo_cleanup._fetch_active_opps", return_value=[opp]):
            result = run_cleanup(dry_run=False, client=mock_client)
        assert result["closed_location"] == 1
        assert result["closed_title"] == 0
        mock_client.pages.update.assert_called_once()

    def test_clean_record_skipped(self):
        opp = _make_opp("p3", "Acme / Solutions Engineer / 2026", location="Remote")
        mock_client = self._mock_client()
        with patch("retroactive_geo_cleanup._fetch_active_opps", return_value=[opp]):
            result = run_cleanup(dry_run=False, client=mock_client)
        assert result["skipped"] == 1
        assert result["closed_title"] == 0
        assert result["closed_location"] == 0
        mock_client.pages.update.assert_not_called()

    def test_dry_run_makes_no_notion_writes(self):
        opp = _make_opp("p4", "Acme / Solutions Engineer, Japan / 2026")
        mock_client = self._mock_client()
        with patch("retroactive_geo_cleanup._fetch_active_opps", return_value=[opp]):
            result = run_cleanup(dry_run=True, client=mock_client)
        assert result["closed_title"] == 1
        mock_client.pages.update.assert_not_called()

    def test_mixed_records_counted_correctly(self):
        opps = [
            _make_opp("p1", "Acme / Solutions Engineer, EMEA / 2026"),
            _make_opp("p2", "Beta / Customer Success Manager / 2026", location="Hyderabad IN"),
            _make_opp("p3", "Gamma / Solutions Engineer / 2026", location="Remote"),
            _make_opp("p4", "Delta / Technical Account Manager / 2026", location="Austin, TX"),
        ]
        mock_client = self._mock_client()
        with patch("retroactive_geo_cleanup._fetch_active_opps", return_value=opps):
            result = run_cleanup(dry_run=False, client=mock_client)
        assert result["checked"] == 4
        assert result["closed_title"] == 1
        assert result["closed_location"] == 1
        assert result["skipped"] == 2
        assert mock_client.pages.update.call_count == 2
