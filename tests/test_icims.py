from unittest.mock import MagicMock, patch

import pytest


def _make_job_item(title="Solutions Engineer", href="https://careers-acme.icims.com/jobs/123/job", location="US-MA-Boston"):
    return f"""
    <li class="iCIMS_JobCardItem">
      <div class="row">
        <div class="col-xs-6 header left">
          <span class="sr-only field-label">Location : Location</span>
          <span>{location}</span>
        </div>
        <div class="col-xs-12 title">
          <a class="iCIMS_Anchor" href="{href}" title="123 - {title}">
            <span class="sr-only field-label">Title</span>
            <h3>{title}</h3>
          </a>
        </div>
      </div>
    </li>"""


def _make_page_html(jobs_html, current_page=1, total_pages=1):
    return f"""
    <html><body>
    <span class="search-results-text">Search Results<br/>Page {current_page} of {total_pages}</span>
    <ul>{"".join(jobs_html)}</ul>
    </body></html>"""


def _mock_response(html):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.text = html
    return resp


class TestFetchJobs:
    def test_returns_job_listing_objects(self):
        from scrapers.icims import fetch_jobs
        html = _make_page_html([_make_job_item()])
        with patch("scrapers.icims.requests.get", return_value=_mock_response(html)):
            results, geo = fetch_jobs("acme")
        assert len(results) == 1
        assert results[0].title == "Solutions Engineer"
        assert "123" in results[0].url
        assert geo == 0

    def test_url_strips_query_string(self):
        from scrapers.icims import fetch_jobs
        href = "https://careers-acme.icims.com/jobs/456/job?in_iframe=1"
        html = _make_page_html([_make_job_item(href=href)])
        with patch("scrapers.icims.requests.get", return_value=_mock_response(html)):
            results, _ = fetch_jobs("acme")
        assert "?" not in results[0].url
        assert results[0].url == "https://careers-acme.icims.com/jobs/456/job"

    def test_geo_filter_excludes_non_us(self):
        from scrapers.icims import fetch_jobs
        html = _make_page_html([_make_job_item(location="Canada-ON-Toronto")])
        with patch("scrapers.icims.requests.get", return_value=_mock_response(html)):
            results, geo = fetch_jobs("acme")
        assert results == []
        assert geo == 1

    def test_title_geo_filter_excludes_emea(self):
        from scrapers.icims import fetch_jobs
        html = _make_page_html([_make_job_item(title="Solutions Engineer - EMEA")])
        with patch("scrapers.icims.requests.get", return_value=_mock_response(html)):
            results, geo = fetch_jobs("acme")
        assert results == []
        assert geo == 1

    def test_pagination_fetches_all_pages(self):
        from scrapers.icims import fetch_jobs
        page1 = _make_page_html(
            [_make_job_item(title="Job 1", href="https://careers-acme.icims.com/jobs/1/job")],
            current_page=1, total_pages=2
        )
        page2 = _make_page_html(
            [_make_job_item(title="Job 2", href="https://careers-acme.icims.com/jobs/2/job")],
            current_page=2, total_pages=2
        )
        with patch("scrapers.icims.requests.get", side_effect=[
            _mock_response(page1), _mock_response(page2)
        ]):
            results, _ = fetch_jobs("acme")
        assert len(results) == 2

    def test_http_error_returns_empty_list(self):
        from scrapers.icims import fetch_jobs
        with patch("scrapers.icims.requests.get", side_effect=Exception("timeout")):
            results, geo = fetch_jobs("acme")
        assert results == []
        assert geo == 0

    def test_http_status_error_returns_empty_list(self):
        from scrapers.icims import fetch_jobs
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("404")
        with patch("scrapers.icims.requests.get", return_value=mock_resp):
            results, geo = fetch_jobs("acme")
        assert results == []
        assert geo == 0

    def test_missing_anchor_skipped(self):
        from scrapers.icims import fetch_jobs
        html = """<html><body>
        <span>Page 1 of 1</span>
        <li class="iCIMS_JobCardItem"><div class="row">no anchor here</div></li>
        </body></html>"""
        with patch("scrapers.icims.requests.get", return_value=_mock_response(html)):
            results, _ = fetch_jobs("acme")
        assert results == []

    def test_empty_page_stops_pagination(self):
        from scrapers.icims import fetch_jobs
        html = _make_page_html([], current_page=1, total_pages=1)
        with patch("scrapers.icims.requests.get", return_value=_mock_response(html)):
            results, _ = fetch_jobs("acme")
        assert results == []

    def test_location_extracted_from_header_left(self):
        from scrapers.icims import fetch_jobs
        html = _make_page_html([_make_job_item(location="US-NY-New York")])
        with patch("scrapers.icims.requests.get", return_value=_mock_response(html)):
            results, _ = fetch_jobs("acme")
        assert results[0].location == "US-NY-New York"

    def test_us_remote_location_passes_geo_filter(self):
        from scrapers.icims import fetch_jobs
        html = _make_page_html([_make_job_item(location="Remote")])
        with patch("scrapers.icims.requests.get", return_value=_mock_response(html)):
            results, geo = fetch_jobs("acme")
        assert len(results) == 1
        assert geo == 0

    def test_slug_with_careers_prefix_is_normalized(self):
        from scrapers.icims import fetch_jobs
        html = _make_page_html([_make_job_item()])
        with patch("scrapers.icims.requests.get", return_value=_mock_response(html)) as mock_get:
            fetch_jobs("careers-acme")
        called_url = mock_get.call_args[0][0]
        assert "careers-careers-acme" not in called_url
        assert "careers-acme.icims.com" in called_url
