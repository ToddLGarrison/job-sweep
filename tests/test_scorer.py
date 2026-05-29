from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_opp(
    page_id: str = "page-1",
    name: str = "Acme / Solutions Engineer / 2026",
    job_url: str = "https://jobs.example.com/se/123",
    stage: str = "Qualification",
    fit_score: str = "",
) -> dict:
    return {
        "page_id": page_id,
        "name": name,
        "job_url": job_url,
        "stage": stage,
        "fit_score": fit_score,
    }


def _mock_claude_response(score: str) -> MagicMock:
    msg = MagicMock()
    msg.content = [MagicMock(text=score)]
    return msg


def _make_html(text: str) -> str:
    return f"<html><body><p>{text}</p></body></html>"


# Long enough to pass the 200-char description length guard.
_MOCK_HTML = "<html><body><p>" + "x" * 300 + "</p></body></html>"


# ---------------------------------------------------------------------------
# score_opportunity
# ---------------------------------------------------------------------------

class TestScoreOpportunity:
    def test_returns_valid_star_string(self):
        from scorer import score_opportunity
        with patch("scorer._anthropic_client") as mock_client:
            mock_client.messages.create.return_value = _mock_claude_response("⭐⭐⭐")
            result = score_opportunity("Solutions Engineer", "Great role at a SaaS company.")
        assert result == "⭐⭐⭐"

    def test_five_star_accepted(self):
        from scorer import score_opportunity
        with patch("scorer._anthropic_client") as mock_client:
            mock_client.messages.create.return_value = _mock_claude_response("⭐⭐⭐⭐⭐")
            result = score_opportunity("SE", "Perfect match.")
        assert result == "⭐⭐⭐⭐⭐"

    def test_one_star_accepted(self):
        from scorer import score_opportunity
        with patch("scorer._anthropic_client") as mock_client:
            mock_client.messages.create.return_value = _mock_claude_response("⭐")
            result = score_opportunity("SE", "Requires Java.")
        assert result == "⭐"

    def test_handles_api_error_gracefully(self):
        from scorer import score_opportunity
        with patch("scorer._anthropic_client") as mock_client:
            mock_client.messages.create.side_effect = Exception("API rate limit")
            result = score_opportunity("SE", "Some description.")
        assert result is None

    def test_handles_invalid_response(self):
        from scorer import score_opportunity
        with patch("scorer._anthropic_client") as mock_client:
            mock_client.messages.create.return_value = _mock_claude_response("maybe 3 stars?")
            result = score_opportunity("SE", "Some description.")
        assert result is None

    def test_strips_whitespace_from_response(self):
        from scorer import score_opportunity
        with patch("scorer._anthropic_client") as mock_client:
            mock_client.messages.create.return_value = _mock_claude_response("⭐⭐\n")
            result = score_opportunity("SE", "Some description.")
        assert result == "⭐⭐"

    def test_passes_title_and_description_to_api(self):
        from scorer import score_opportunity
        with patch("scorer._anthropic_client") as mock_client:
            mock_client.messages.create.return_value = _mock_claude_response("⭐⭐⭐")
            score_opportunity("TAM", "Manage enterprise accounts.")
        call_kwargs = mock_client.messages.create.call_args
        user_msg = call_kwargs.kwargs["messages"][0]["content"]
        assert "TAM" in user_msg
        assert "Manage enterprise accounts." in user_msg


# ---------------------------------------------------------------------------
# batch_score_unscored
# ---------------------------------------------------------------------------

class TestBatchScoreUnscored:
    def _setup_patches(self, opps, score="⭐⭐⭐", html=None):
        """Return a context-manager-friendly set of patches."""
        return (
            patch("scorer.notion.fetch_unscored_opportunities", return_value=opps),
            patch("scorer.notion.update_fit_score"),
            patch("scorer.score_opportunity", return_value=score),
            patch("scorer.requests.get", return_value=MagicMock(text=html or _MOCK_HTML)),
            patch("scorer.time.sleep"),
        )

    def test_skips_opportunities_with_no_job_url(self):
        from scorer import batch_score_unscored
        opps = [_make_opp(job_url="")]
        with patch("scorer.notion.fetch_unscored_opportunities", return_value=opps), \
             patch("scorer.notion.update_fit_score") as mock_update, \
             patch("scorer.time.sleep"):
            stats = batch_score_unscored()
        assert stats["skipped"] == 1
        assert stats["scored"] == 0
        mock_update.assert_not_called()

    def test_skips_already_scored_opportunities(self):
        from scorer import batch_score_unscored
        opps = [_make_opp(fit_score="⭐⭐⭐")]
        with patch("scorer.notion.fetch_unscored_opportunities", return_value=opps), \
             patch("scorer.notion.update_fit_score") as mock_update, \
             patch("scorer.time.sleep"):
            stats = batch_score_unscored()
        assert stats["skipped"] == 1
        assert stats["scored"] == 0
        mock_update.assert_not_called()

    def test_dry_run_makes_zero_notion_writes(self):
        from scorer import batch_score_unscored
        opps = [_make_opp()]
        with patch("scorer.notion.fetch_unscored_opportunities", return_value=opps), \
             patch("scorer.notion.update_fit_score") as mock_update, \
             patch("scorer.score_opportunity", return_value="⭐⭐⭐"), \
             patch("scorer.requests.get", return_value=MagicMock(text=_MOCK_HTML)), \
             patch("scorer.time.sleep"):
            stats = batch_score_unscored(dry_run=True)
        mock_update.assert_not_called()
        assert stats["scored"] == 1

    def test_sleep_called_between_api_calls(self):
        from scorer import batch_score_unscored
        opps = [_make_opp("p1"), _make_opp("p2"), _make_opp("p3")]
        with patch("scorer.notion.fetch_unscored_opportunities", return_value=opps), \
             patch("scorer.notion.update_fit_score"), \
             patch("scorer.score_opportunity", return_value="⭐⭐"), \
             patch("scorer.requests.get", return_value=MagicMock(text=_MOCK_HTML)), \
             patch("scorer.time.sleep") as mock_sleep:
            batch_score_unscored()
        assert mock_sleep.call_count == 3
        mock_sleep.assert_called_with(1)

    def test_description_truncated_to_3000_chars(self):
        from scorer import score_opportunity as real_score, batch_score_unscored
        long_text = "x" * 5000
        html = f"<html><body>{long_text}</body></html>"
        opps = [_make_opp()]
        captured = {}
        def capture_score(title, description):
            captured["description"] = description
            return "⭐⭐⭐"
        with patch("scorer.notion.fetch_unscored_opportunities", return_value=opps), \
             patch("scorer.notion.update_fit_score"), \
             patch("scorer.score_opportunity", side_effect=capture_score), \
             patch("scorer.requests.get", return_value=MagicMock(text=html)), \
             patch("scorer.time.sleep"):
            batch_score_unscored()
        assert len(captured["description"]) <= 3000

    def test_http_error_fetching_jd_counts_as_error(self):
        from scorer import batch_score_unscored
        opps = [_make_opp()]
        with patch("scorer.notion.fetch_unscored_opportunities", return_value=opps), \
             patch("scorer.notion.update_fit_score"), \
             patch("scorer.requests.get", side_effect=Exception("connection refused")), \
             patch("scorer.time.sleep"):
            stats = batch_score_unscored()
        assert stats["errors"] == 1
        assert stats["scored"] == 0

    def test_api_error_counts_as_error(self):
        from scorer import batch_score_unscored
        opps = [_make_opp()]
        with patch("scorer.notion.fetch_unscored_opportunities", return_value=opps), \
             patch("scorer.notion.update_fit_score"), \
             patch("scorer.score_opportunity", return_value=None), \
             patch("scorer.requests.get", return_value=MagicMock(text=_MOCK_HTML)), \
             patch("scorer.time.sleep"):
            stats = batch_score_unscored()
        assert stats["errors"] == 1
        assert stats["scored"] == 0

    def test_title_extracted_from_name(self):
        from scorer import batch_score_unscored
        opps = [_make_opp(name="Snyk / Customer Success Engineer / 2026")]
        captured = {}
        def capture_score(title, description):
            captured["title"] = title
            return "⭐⭐⭐⭐"
        with patch("scorer.notion.fetch_unscored_opportunities", return_value=opps), \
             patch("scorer.notion.update_fit_score"), \
             patch("scorer.score_opportunity", side_effect=capture_score), \
             patch("scorer.requests.get", return_value=MagicMock(text=_MOCK_HTML)), \
             patch("scorer.time.sleep"):
            batch_score_unscored()
        assert captured["title"] == "Customer Success Engineer"

    def test_returns_correct_counts(self):
        from scorer import batch_score_unscored
        opps = [
            _make_opp("p1"),                        # scores OK
            _make_opp("p2", job_url=""),            # skipped (no URL)
            _make_opp("p3", fit_score="⭐⭐"),       # skipped (already scored)
        ]
        with patch("scorer.notion.fetch_unscored_opportunities", return_value=opps), \
             patch("scorer.notion.update_fit_score"), \
             patch("scorer.score_opportunity", return_value="⭐⭐⭐"), \
             patch("scorer.requests.get", return_value=MagicMock(text=_MOCK_HTML)), \
             patch("scorer.time.sleep"):
            stats = batch_score_unscored()
        assert stats == {"scored": 1, "skipped": 2, "errors": 0}

    def test_notion_write_error_counts_as_error(self):
        from scorer import batch_score_unscored
        opps = [_make_opp()]
        with patch("scorer.notion.fetch_unscored_opportunities", return_value=opps), \
             patch("scorer.notion.update_fit_score", side_effect=Exception("Notion API error")), \
             patch("scorer.score_opportunity", return_value="⭐⭐⭐"), \
             patch("scorer.requests.get", return_value=MagicMock(text=_MOCK_HTML)), \
             patch("scorer.time.sleep"):
            stats = batch_score_unscored()
        assert stats["errors"] == 1
        assert stats["scored"] == 0
