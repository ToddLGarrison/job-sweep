from unittest.mock import MagicMock, patch, call
import json

import pytest

from scrapers.discovery_builtinboston import (
    fetch_listings,
    _parse_listing_page,
    _extract_how_to_apply,
)


def _make_listing_html(cards: list[dict]) -> str:
    """Build minimal Built In Boston listing page HTML with job cards."""
    card_html = ""
    for c in cards:
        card_html += f"""
        <div data-id="job-card">
            <a data-id="company-title"><span>{c.get('company', 'Acme')}</span></a>
            <a data-id="job-card-title" href="{c.get('href', '/job/se/1234')}">
                {c.get('title', 'Solutions Engineer')}
            </a>
        </div>
        """
    return f"<html><body>{card_html}</body></html>"


def _make_detail_html(how_to_apply: str, company: str = "Acme", title: str = "SE") -> str:
    job_json = json.dumps({
        "job": {
            "id": 1234,
            "howToApply": how_to_apply,
            "companyName": company,
            "title": title,
            "isEasyApply": False,
        },
        "siteId": 6,
    })
    return f"<html><script>Builtin.jobPostInit({job_json})</script></html>"


# --- _parse_listing_page ---

class TestParseListingPage:
    def test_extracts_cards(self):
        html = _make_listing_html([
            {"company": "Snyk", "title": "Solutions Engineer", "href": "/job/se/9001"},
        ])
        cards = _parse_listing_page(html)
        assert len(cards) == 1
        assert cards[0] == ("Snyk", "Solutions Engineer", "https://www.builtinboston.com/job/se/9001")

    def test_skips_card_without_title_link(self):
        html = "<html><body><div data-id='job-card'><span>No link</span></div></body></html>"
        cards = _parse_listing_page(html)
        assert cards == []

    def test_multiple_cards(self):
        html = _make_listing_html([
            {"company": "Acme", "title": "SE", "href": "/job/se/1"},
            {"company": "Beta Corp", "title": "TAM", "href": "/job/tam/2"},
        ])
        cards = _parse_listing_page(html)
        assert len(cards) == 2
        assert cards[1][0] == "Beta Corp"
        assert cards[1][1] == "TAM"

    def test_absolute_href_preserved(self):
        html = "<html><body><div data-id='job-card'><a data-id='company-title'><span>C</span></a><a data-id='job-card-title' href='https://external.com/job/1'>Title</a></div></body></html>"
        cards = _parse_listing_page(html)
        assert cards[0][2] == "https://external.com/job/1"


# --- _extract_how_to_apply ---

class TestExtractHowToApply:
    def test_extracts_url(self):
        html = _make_detail_html("https://jobs.lever.co/stripe/abc12345-0000-0000-0000-000000000000")
        assert _extract_how_to_apply(html) == "https://jobs.lever.co/stripe/abc12345-0000-0000-0000-000000000000"

    def test_returns_empty_when_no_init(self):
        assert _extract_how_to_apply("<html><body>no script</body></html>") == ""

    def test_returns_empty_on_malformed_json(self):
        html = "<script>Builtin.jobPostInit({bad json})</script>"
        assert _extract_how_to_apply(html) == ""

    def test_returns_empty_when_how_to_apply_missing(self):
        html = "<script>Builtin.jobPostInit({\"job\": {\"id\": 1}})</script>"
        assert _extract_how_to_apply(html) == ""


# --- fetch_listings ---

class TestFetchListings:
    def _mock_responses(self, listing_html: str, detail_htmls: list[str]):
        call_count = 0

        def side_effect(url, **kwargs):
            nonlocal call_count
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            if call_count == 0:
                resp.text = listing_html
            else:
                resp.text = detail_htmls[call_count - 1] if (call_count - 1) < len(detail_htmls) else ""
            call_count += 1
            return resp

        return side_effect

    def test_returns_discovery_listing_for_known_ats(self):
        listing = _make_listing_html([
            {"company": "Snyk", "title": "Solutions Engineer", "href": "/job/se/9001"},
        ])
        detail = _make_detail_html(
            "https://job-boards.greenhouse.io/snyk/jobs/7920513905",
            company="Snyk",
        )
        with patch("scrapers.discovery_builtinboston.requests.get") as mock_get, \
             patch("scrapers.discovery_builtinboston.time.sleep"):
            mock_get.side_effect = self._mock_responses(listing, [detail])
            results, _ = fetch_listings("Solutions Engineer")
        assert len(results) == 1
        assert results[0].title == "Solutions Engineer"
        assert results[0].company_name == "Snyk"
        assert results[0].ats == "Greenhouse"
        assert results[0].slug == "snyk"
        assert results[0].url == "https://job-boards.greenhouse.io/snyk/jobs/7920513905"

    def test_skips_unknown_ats(self, capsys):
        listing = _make_listing_html([
            {"company": "Liberty Mutual", "title": "Solutions Engineer", "href": "/job/se/8854970"},
        ])
        detail = _make_detail_html(
            "https://searchjobs.libertymutualgroup.com/careers/job/618516127729",
            company="Liberty Mutual",
        )
        with patch("scrapers.discovery_builtinboston.requests.get") as mock_get, \
             patch("scrapers.discovery_builtinboston.time.sleep"):
            mock_get.side_effect = self._mock_responses(listing, [detail])
            results, unknown_ats = fetch_listings("Solutions Engineer")
        assert results == []
        assert unknown_ats == 1
        assert "UNKNOWN ATS [BuiltInBoston]" in capsys.readouterr().out

    def test_skips_card_with_empty_apply_url(self):
        listing = _make_listing_html([
            {"company": "Acme", "title": "SE", "href": "/job/se/1"},
        ])
        detail = _make_detail_html("", company="Acme")
        with patch("scrapers.discovery_builtinboston.requests.get") as mock_get, \
             patch("scrapers.discovery_builtinboston.time.sleep"):
            mock_get.side_effect = self._mock_responses(listing, [detail])
            results, _ = fetch_listings("Solutions Engineer")
        assert results == []

    def test_listing_http_error_returns_empty(self):
        with patch("scrapers.discovery_builtinboston.requests.get") as mock_get:
            mock_get.side_effect = Exception("connection timeout")
            results, _ = fetch_listings("Solutions Engineer")
        assert results == []

    def test_detail_http_error_skips_card(self):
        listing = _make_listing_html([
            {"company": "Acme", "title": "SE", "href": "/job/se/1"},
            {"company": "Beta", "title": "CSM", "href": "/job/csm/2"},
        ])
        good_detail = _make_detail_html(
            "https://job-boards.greenhouse.io/beta/jobs/999",
            company="Beta",
        )

        call_count = 0

        def side_effect(url, **kwargs):
            nonlocal call_count
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            if call_count == 0:
                resp.text = listing
                call_count += 1
                return resp
            elif call_count == 1:
                call_count += 1
                raise Exception("404 Not Found")
            else:
                resp.text = good_detail
                call_count += 1
                return resp

        with patch("scrapers.discovery_builtinboston.requests.get") as mock_get, \
             patch("scrapers.discovery_builtinboston.time.sleep"):
            mock_get.side_effect = side_effect
            results, _ = fetch_listings("Solutions Engineer")
        assert len(results) == 1
        assert results[0].company_name == "Beta"

    def test_workday_url_detected(self):
        listing = _make_listing_html([
            {"company": "Snyk", "title": "Senior SE", "href": "/job/sse/9044230"},
        ])
        detail = _make_detail_html(
            "https://snyk.wd103.myworkdayjobs.com/External/job/United-States---Boston-Office/Senior-SE_JR100617",
            company="Snyk",
        )
        with patch("scrapers.discovery_builtinboston.requests.get") as mock_get, \
             patch("scrapers.discovery_builtinboston.time.sleep"):
            mock_get.side_effect = self._mock_responses(listing, [detail])
            results, _ = fetch_listings("Solutions Engineer")
        assert len(results) == 1
        assert results[0].ats == "Workday"
        assert results[0].slug == "snyk.wd103/External"

    def test_multiple_cards_multiple_ats(self):
        listing = _make_listing_html([
            {"company": "Snyk", "title": "SE", "href": "/job/se/1"},
            {"company": "Bestow", "title": "SE", "href": "/job/se/2"},
            {"company": "Liberty", "title": "SE", "href": "/job/se/3"},
        ])
        details = [
            _make_detail_html("https://snyk.wd103.myworkdayjobs.com/External/job/X/Y_Z", "Snyk"),
            _make_detail_html("https://jobs.ashbyhq.com/bestow/affb8966-2538-44d7-b334-07f152ff73fc", "Bestow"),
            _make_detail_html("https://searchjobs.libertymutualgroup.com/careers/job/123", "Liberty"),
        ]
        with patch("scrapers.discovery_builtinboston.requests.get") as mock_get, \
             patch("scrapers.discovery_builtinboston.time.sleep"):
            mock_get.side_effect = self._mock_responses(listing, details)
            results, unknown_ats = fetch_listings("Solutions Engineer")
        assert len(results) == 2
        assert unknown_ats == 1
        assert {r.ats for r in results} == {"Workday", "Ashby"}
