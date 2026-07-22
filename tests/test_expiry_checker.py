from unittest.mock import MagicMock, patch

import pytest

from expiry_checker import (
    EXPIRY_MISS_THRESHOLD,
    ExpiryStats,
    _apply_miss,
    _infer_ats,
    check_url_live,
    run_expiry_check,
)


# --- check_url_live ---

class TestCheckUrlLive:
    def test_greenhouse_404_returns_false(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch("expiry_checker.requests.get", return_value=mock_resp):
            assert check_url_live("https://boards.greenhouse.io/acme/jobs/123", "Greenhouse") is False

    def test_greenhouse_200_returns_true(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("expiry_checker.requests.get", return_value=mock_resp):
            assert check_url_live("https://boards.greenhouse.io/acme/jobs/123", "Greenhouse") is True

    def test_lever_404_returns_false(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch("expiry_checker.requests.get", return_value=mock_resp):
            assert check_url_live("https://jobs.lever.co/acme/abc", "Lever") is False

    def test_lever_200_returns_true(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("expiry_checker.requests.get", return_value=mock_resp):
            assert check_url_live("https://jobs.lever.co/acme/abc", "Lever") is True

    def test_ashby_200_no_longer_available_returns_false(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "Sorry, this job is no longer available."
        with patch("expiry_checker.requests.get", return_value=mock_resp):
            assert check_url_live("https://jobs.ashbyhq.com/acme/123", "Ashby") is False

    def test_ashby_200_position_filled_returns_false(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "This position has been filled."
        with patch("expiry_checker.requests.get", return_value=mock_resp):
            assert check_url_live("https://jobs.ashbyhq.com/acme/123", "Ashby") is False

    def test_ashby_200_job_not_found_returns_false(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "Job not found on this board."
        with patch("expiry_checker.requests.get", return_value=mock_resp):
            assert check_url_live("https://jobs.ashbyhq.com/acme/123", "Ashby") is False

    def test_ashby_200_normal_content_returns_true(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "We are hiring a Solutions Engineer to join our team."
        with patch("expiry_checker.requests.get", return_value=mock_resp):
            assert check_url_live("https://jobs.ashbyhq.com/acme/123", "Ashby") is True

    def test_ashby_404_returns_false(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch("expiry_checker.requests.get", return_value=mock_resp):
            assert check_url_live("https://jobs.ashbyhq.com/acme/123", "Ashby") is False

    def test_workday_posting_available_true_returns_true(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "postingAvailable: true, other: stuff"
        with patch("expiry_checker.requests.get", return_value=mock_resp):
            assert check_url_live("https://acme.wd5.myworkdayjobs.com/en-US/careers/job/SE_R123", "Workday") is True

    def test_workday_posting_available_false_returns_false(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "postingAvailable: false, other: stuff"
        with patch("expiry_checker.requests.get", return_value=mock_resp):
            assert check_url_live("https://acme.wd5.myworkdayjobs.com/en-US/careers/job/SE_R123", "Workday") is False

    def test_workday_non_200_returns_false(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch("expiry_checker.requests.get", return_value=mock_resp):
            assert check_url_live("https://acme.wd5.myworkdayjobs.com/en-US/careers/job/SE_R123", "Workday") is False

    def test_workday_signal_absent_defaults_to_live(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body>no workday config here</body></html>"
        with patch("expiry_checker.requests.get", return_value=mock_resp):
            assert check_url_live("https://acme.wd5.myworkdayjobs.com/en-US/careers/job/SE_R123", "Workday") is True

    def test_empty_url_raises(self):
        with pytest.raises(ValueError, match="empty URL"):
            check_url_live("", "Greenhouse")

    def test_unknown_ats_raises(self):
        with pytest.raises(ValueError, match="Unknown ATS"):
            check_url_live("https://example.com/job/123", "LinkedIn")

    def test_case_insensitive_ats(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("expiry_checker.requests.get", return_value=mock_resp):
            assert check_url_live("https://boards.greenhouse.io/x/jobs/1", "greenhouse") is True


# --- _infer_ats ---

class TestInferAts:
    def test_greenhouse_url(self):
        assert _infer_ats("https://boards.greenhouse.io/acme/jobs/123") == "Greenhouse"

    def test_lever_url(self):
        assert _infer_ats("https://jobs.lever.co/acme/abc") == "Lever"

    def test_ashby_url(self):
        assert _infer_ats("https://jobs.ashbyhq.com/acme/123") == "Ashby"

    def test_workday_url(self):
        assert _infer_ats("https://crowdstrike.wd5.myworkdayjobs.com/en-US/crowdstrikecareers/job/SE_R123") == "Workday"

    def test_unknown_url(self):
        assert _infer_ats("https://careers.example.com/job/123") == ""


# --- _apply_miss ---

class TestApplyMiss:
    def test_first_miss_increments_to_1(self):
        count, should_close = _apply_miss(0)
        assert count == 1
        assert should_close is False

    def test_ninth_miss_increments_to_9(self):
        count, should_close = _apply_miss(8)
        assert count == 9
        assert should_close is False

    def test_tenth_miss_triggers_close(self):
        count, should_close = _apply_miss(9)
        assert count == EXPIRY_MISS_THRESHOLD
        assert should_close is True

    def test_beyond_threshold_still_closes(self):
        count, should_close = _apply_miss(10)
        assert count == 11
        assert should_close is True


# --- run_expiry_check ---

def _make_opp(page_id, name, url, consecutive_misses=0):
    return {"page_id": page_id, "name": name, "url": url, "consecutive_misses": consecutive_misses}


class TestRunExpiryCheck:
    def test_missing_url_skipped(self):
        opp = _make_opp("p1", "Acme / SE / 2026", "")
        with patch("expiry_checker.notion.fetch_active_opportunities", return_value=[opp]):
            with patch("expiry_checker.notion.update_opportunity_expiry") as mock_update:
                stats = run_expiry_check(dry_run=True)
        assert stats.still_live == 0
        assert stats.newly_missed == 0
        mock_update.assert_not_called()

    def test_unknown_ats_url_skipped(self):
        opp = _make_opp("p1", "Acme / SE / 2026", "https://careers.acme.com/job/1")
        with patch("expiry_checker.notion.fetch_active_opportunities", return_value=[opp]):
            with patch("expiry_checker.notion.update_opportunity_expiry") as mock_update:
                stats = run_expiry_check(dry_run=True)
        assert stats.still_live == 0
        assert stats.newly_missed == 0
        mock_update.assert_not_called()

    def test_live_url_increments_still_live(self):
        opp = _make_opp("p1", "Acme / SE / 2026", "https://boards.greenhouse.io/acme/jobs/1")
        mock_resp = MagicMock(status_code=200)
        with patch("expiry_checker.notion.fetch_active_opportunities", return_value=[opp]):
            with patch("expiry_checker.requests.get", return_value=mock_resp):
                with patch("expiry_checker.notion.update_opportunity_expiry") as mock_update:
                    stats = run_expiry_check(dry_run=True)
        assert stats.still_live == 1
        assert stats.newly_missed == 0
        mock_update.assert_not_called()  # consecutive_misses was 0, no reset needed

    def test_live_url_resets_misses_when_nonzero(self):
        opp = _make_opp("p1", "Acme / SE / 2026", "https://boards.greenhouse.io/acme/jobs/1", consecutive_misses=3)
        mock_resp = MagicMock(status_code=200)
        with patch("expiry_checker.notion.fetch_active_opportunities", return_value=[opp]):
            with patch("expiry_checker.requests.get", return_value=mock_resp):
                with patch("expiry_checker.notion.update_opportunity_expiry") as mock_update:
                    stats = run_expiry_check(dry_run=True)
        assert stats.still_live == 1
        mock_update.assert_called_once_with("p1", consecutive_misses=0, dry_run=True)

    def test_first_miss_increments_to_1_stage_unchanged(self):
        opp = _make_opp("p1", "Acme / SE / 2026", "https://boards.greenhouse.io/acme/jobs/1", consecutive_misses=0)
        mock_resp = MagicMock(status_code=404)
        with patch("expiry_checker.notion.fetch_active_opportunities", return_value=[opp]):
            with patch("expiry_checker.requests.get", return_value=mock_resp):
                with patch("expiry_checker.notion.update_opportunity_expiry") as mock_update:
                    stats = run_expiry_check(dry_run=True)
        assert stats.newly_missed == 1
        assert stats.auto_closed == 0
        mock_update.assert_called_once_with("p1", consecutive_misses=1, dry_run=True)

    def test_ninth_miss_increments_stage_unchanged(self):
        opp = _make_opp("p1", "Acme / SE / 2026", "https://boards.greenhouse.io/acme/jobs/1", consecutive_misses=8)
        mock_resp = MagicMock(status_code=404)
        with patch("expiry_checker.notion.fetch_active_opportunities", return_value=[opp]):
            with patch("expiry_checker.requests.get", return_value=mock_resp):
                with patch("expiry_checker.notion.update_opportunity_expiry") as mock_update:
                    stats = run_expiry_check(dry_run=True)
        assert stats.newly_missed == 1
        assert stats.auto_closed == 0
        mock_update.assert_called_once_with("p1", consecutive_misses=9, dry_run=True)

    def test_tenth_miss_auto_closes(self):
        opp = _make_opp("p1", "Acme / SE / 2026", "https://boards.greenhouse.io/acme/jobs/1", consecutive_misses=9)
        mock_resp = MagicMock(status_code=404)
        with patch("expiry_checker.notion.fetch_active_opportunities", return_value=[opp]):
            with patch("expiry_checker.requests.get", return_value=mock_resp):
                with patch("expiry_checker.notion.update_opportunity_expiry") as mock_update:
                    stats = run_expiry_check(dry_run=True)
        assert stats.newly_missed == 1
        assert stats.auto_closed == 1
        assert "Acme / SE / 2026" in stats.closed_roles
        mock_update.assert_called_once_with(
            "p1", consecutive_misses=10, stage="Closed Lost", dry_run=True
        )

    def test_http_error_increments_error_count(self):
        opp = _make_opp("p1", "Acme / SE / 2026", "https://boards.greenhouse.io/acme/jobs/1")
        with patch("expiry_checker.notion.fetch_active_opportunities", return_value=[opp]):
            with patch("expiry_checker.requests.get", side_effect=Exception("timeout")):
                with patch("expiry_checker.notion.update_opportunity_expiry") as mock_update:
                    stats = run_expiry_check(dry_run=True)
        assert stats.errors == 1
        assert stats.still_live == 0
        assert stats.newly_missed == 0
        mock_update.assert_not_called()
