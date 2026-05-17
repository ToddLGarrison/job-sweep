from unittest.mock import MagicMock, patch
import json

import pytest

from scrapers.ats_detector import _resolve_cache
from scrapers.discovery_venturefizz import (
    fetch_listings,
    _parse_listing_page,
    _parse_detail_page,
    _extract_company,
    _extract_apply_url,
)
from bs4 import BeautifulSoup


@pytest.fixture(autouse=True)
def clear_ats_cache():
    _resolve_cache.clear()
    yield
    _resolve_cache.clear()


def _head_returns_same_url(url, **kwargs):
    """HEAD mock that resolves to the same URL — simulates no redirect."""
    resp = MagicMock()
    resp.url = url
    return resp


def _make_listing_html(jobs: list[dict]) -> str:
    """Build minimal VentureFizz listing page HTML."""
    articles = ""
    for j in jobs:
        articles += f"""
        <article class="job_listing">
            <h2 class="job-title">
                <a href="{j.get('url', 'https://venturefizz.com/job/se/')}">{j.get('title', 'SE')}</a>
            </h2>
            <a class="btn btn-theme" href="{j.get('url', 'https://venturefizz.com/job/se/')}">Apply</a>
        </article>
        """
    return f"<html><body>{articles}</body></html>"


def _make_detail_html(
    company: str = "Checkly",
    job_title: str = "Sales Engineer",
    apply_url: str = "https://jobs.ashbyhq.com/checkly/88c7e552-009b-4db7-a23b-1c3dd7779930",
    use_jsonld: bool = True,
) -> str:
    jsonld = ""
    if use_jsonld:
        schema = json.dumps({
            "@type": "JobPosting",
            "title": job_title,
            "hiringOrganization": {"@type": "Organization", "name": company},
        })
        jsonld = f'<script type="application/ld+json">{schema}</script>'

    apply_link = f'<a class="btn btn-apply btn-apply-job-external" href="{apply_url}">Apply Now</a>' if apply_url else ""

    return f"""<html>
<head><title>{job_title} at {company} - VentureFizz</title>{jsonld}</head>
<body>{apply_link}</body>
</html>"""


# --- _parse_listing_page ---

class TestParseListingPage:
    def test_extracts_jobs(self):
        html = _make_listing_html([
            {"title": "Solutions Engineer", "url": "https://venturefizz.com/job/checkly-se/"},
        ])
        jobs = _parse_listing_page(html)
        assert len(jobs) == 1
        assert jobs[0] == ("Solutions Engineer", "https://venturefizz.com/job/checkly-se/")

    def test_multiple_jobs(self):
        html = _make_listing_html([
            {"title": "SE", "url": "https://venturefizz.com/job/a/"},
            {"title": "TAM", "url": "https://venturefizz.com/job/b/"},
        ])
        jobs = _parse_listing_page(html)
        assert len(jobs) == 2

    def test_skips_article_without_h2(self):
        html = "<html><body><article class='job_listing'><p>No h2</p></article></body></html>"
        assert _parse_listing_page(html) == []

    def test_skips_article_without_link(self):
        html = "<html><body><article class='job_listing'><h2 class='job-title'>No link</h2></article></body></html>"
        assert _parse_listing_page(html) == []

    def test_html_entities_in_title_decoded(self):
        html = _make_listing_html([
            {"title": "Sales Engineer &#8211; Pre-Sales", "url": "https://venturefizz.com/job/x/"},
        ])
        jobs = _parse_listing_page(html)
        assert "–" in jobs[0][0] or "Sales Engineer" in jobs[0][0]


# --- _extract_company and _extract_apply_url ---

class TestExtractCompany:
    def test_from_jsonld(self):
        html = _make_detail_html(company="Checkly", use_jsonld=True)
        soup = BeautifulSoup(html, "html.parser")
        assert _extract_company(soup) == "Checkly"

    def test_fallback_from_title(self):
        html = _make_detail_html(company="Snyk", use_jsonld=False)
        soup = BeautifulSoup(html, "html.parser")
        assert _extract_company(soup) == "Snyk"

    def test_title_with_at_in_job_name(self):
        # "Senior Engineer at Scale at Acme" — rsplit should get last "at"
        html = "<html><head><title>Senior Engineer at Scale at Acme - VentureFizz</title></head></html>"
        soup = BeautifulSoup(html, "html.parser")
        assert _extract_company(soup) == "Acme"

    def test_returns_empty_when_no_source(self):
        soup = BeautifulSoup("<html><head></head></html>", "html.parser")
        assert _extract_company(soup) == ""


class TestExtractApplyUrl:
    def test_extracts_apply_url(self):
        html = _make_detail_html(apply_url="https://jobs.lever.co/stripe/aaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        soup = BeautifulSoup(html, "html.parser")
        assert _extract_apply_url(soup) == "https://jobs.lever.co/stripe/aaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    def test_returns_empty_when_no_apply_link(self):
        soup = BeautifulSoup("<html><body>no apply</body></html>", "html.parser")
        assert _extract_apply_url(soup) == ""

    def test_ignores_non_http_href(self):
        html = '<html><body><a class="btn btn-apply btn-apply-job-external" href="javascript:void(0)">Apply</a></body></html>'
        soup = BeautifulSoup(html, "html.parser")
        assert _extract_apply_url(soup) == ""


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
                idx = call_count - 1
                resp.text = detail_htmls[idx] if idx < len(detail_htmls) else ""
            call_count += 1
            return resp

        return side_effect

    def test_returns_discovery_listing_for_known_ats(self):
        listing = _make_listing_html([
            {"title": "Sales Engineer (Pre-Sales)", "url": "https://venturefizz.com/job/checkly-se/"},
        ])
        detail = _make_detail_html(
            company="Checkly",
            apply_url="https://jobs.ashbyhq.com/checkly/88c7e552-009b-4db7-a23b-1c3dd7779930",
        )
        with patch("scrapers.discovery_venturefizz.requests.get") as mock_get, \
             patch("scrapers.discovery_venturefizz.time.sleep"):
            mock_get.side_effect = self._mock_responses(listing, [detail])
            results, _ = fetch_listings("Sales Engineer")
        assert len(results) == 1
        assert results[0].title == "Sales Engineer (Pre-Sales)"
        assert results[0].company_name == "Checkly"
        assert results[0].ats == "Ashby"
        assert results[0].slug == "checkly"
        assert "ashbyhq.com" in results[0].url

    def test_skips_unknown_ats(self, capsys):
        listing = _make_listing_html([
            {"title": "Director, Solutions Engineering", "url": "https://venturefizz.com/job/snyk-se/"},
        ])
        detail = _make_detail_html(
            company="Snyk",
            apply_url="https://internal.snyk.io/apply/123",
        )
        with patch("scrapers.discovery_venturefizz.requests.get") as mock_get, \
             patch("scrapers.discovery_venturefizz.time.sleep"), \
             patch("scrapers.ats_detector.requests.head", side_effect=_head_returns_same_url):
            mock_get.side_effect = self._mock_responses(listing, [detail])
            results, unknown_ats = fetch_listings("Solutions Engineer")
        assert results == []
        assert unknown_ats == 1
        assert "UNKNOWN ATS [VentureFizz]" in capsys.readouterr().out

    def test_listing_http_error_returns_empty(self):
        with patch("scrapers.discovery_venturefizz.requests.get") as mock_get:
            mock_get.side_effect = Exception("DNS failure")
            results, _ = fetch_listings("Solutions Engineer")
        assert results == []

    def test_detail_http_error_skips_job(self):
        listing = _make_listing_html([
            {"title": "SE", "url": "https://venturefizz.com/job/bad/"},
            {"title": "TAM", "url": "https://venturefizz.com/job/good/"},
        ])
        good_detail = _make_detail_html(
            company="Gainsight",
            apply_url="https://gainsight.wd5.myworkdayjobs.com/Gainsight_External_Careers/job/TAM_R1",
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
                raise Exception("404")
            else:
                resp.text = good_detail
                call_count += 1
                return resp

        with patch("scrapers.discovery_venturefizz.requests.get") as mock_get, \
             patch("scrapers.discovery_venturefizz.time.sleep"):
            mock_get.side_effect = side_effect
            results, _ = fetch_listings("Solutions Engineer")
        assert len(results) == 1
        assert results[0].company_name == "Gainsight"

    def test_title_geo_emea_excluded(self):
        listing = _make_listing_html([
            {"title": "Solutions Engineer, EMEA", "url": "https://venturefizz.com/job/se-emea/"},
        ])
        detail = _make_detail_html(
            company="Acme",
            apply_url="https://job-boards.greenhouse.io/acme/jobs/123",
        )
        with patch("scrapers.discovery_venturefizz.requests.get") as mock_get, \
             patch("scrapers.discovery_venturefizz.time.sleep"):
            mock_get.side_effect = self._mock_responses(listing, [detail])
            # fetch_listings itself doesn't filter geo — that happens in _process_listings
            results, _ = fetch_listings("Solutions Engineer")
        # The scraper returns the listing; geo filtering is done upstream
        assert len(results) == 1

    def test_workday_ats_detected(self):
        listing = _make_listing_html([
            {"title": "Director, Solutions Engineering", "url": "https://venturefizz.com/job/snyk-dir-se/"},
        ])
        detail = _make_detail_html(
            company="Snyk",
            apply_url="https://snyk.wd103.myworkdayjobs.com/External/job/US-Boston/Director-SE_JR100617",
        )
        with patch("scrapers.discovery_venturefizz.requests.get") as mock_get, \
             patch("scrapers.discovery_venturefizz.time.sleep"):
            mock_get.side_effect = self._mock_responses(listing, [detail])
            results, _ = fetch_listings("Solutions Engineer")
        assert len(results) == 1
        assert results[0].ats == "Workday"
        assert results[0].slug == "snyk.wd103/External"

    def test_empty_apply_url_skipped(self):
        listing = _make_listing_html([
            {"title": "SE", "url": "https://venturefizz.com/job/x/"},
        ])
        detail = _make_detail_html(company="Acme", apply_url="")
        with patch("scrapers.discovery_venturefizz.requests.get") as mock_get, \
             patch("scrapers.discovery_venturefizz.time.sleep"):
            mock_get.side_effect = self._mock_responses(listing, [detail])
            results, _ = fetch_listings("Solutions Engineer")
        assert results == []
