import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from digest import (
    build_digest,
    build_subject,
    merge_stats,
    read_and_clear_last_run,
    send_digest,
    write_last_run,
)

_MOCK_SNAPSHOT = {
    "Qualification": 5,
    "Prioritized": 3,
    "Create Resume": 1,
    "Contacted / Applied": 2,
}

_EMPTY_STATS: dict = {
    "new_roles": [],
    "discovery_new_roles": [],
    "closed_roles": [],
    "errors": [],
    "geo_filtered": 0,
    "red_flagged": 0,
}


@pytest.fixture(autouse=True)
def mock_pipeline_snapshot():
    with patch("digest.notion.fetch_pipeline_snapshot", return_value=_MOCK_SNAPSHOT):
        yield


# --- build_digest ---

class TestBuildDigest:
    def test_new_roles_formatted(self):
        stats = {**_EMPTY_STATS, "new_roles": [
            "Snyk / SE / 2026 [Workday]",
            "Checkly / AE / 2026 [Ashby]",
        ]}
        body = build_digest(stats)
        assert "NEW ROLES ADDED (2)" in body
        assert "Snyk / SE / 2026 [Workday]" in body
        assert "Checkly / AE / 2026 [Ashby]" in body

    def test_no_new_roles_shows_message(self):
        body = build_digest(_EMPTY_STATS)
        assert "NEW ROLES ADDED (0)" in body
        assert "No new roles found in this period." in body

    def test_discovery_section_omitted_when_empty(self):
        body = build_digest({**_EMPTY_STATS, "new_roles": ["X / Y / 2026 [Z]"]})
        assert "DISCOVERY FINDS" not in body

    def test_discovery_section_present_when_populated(self):
        stats = {**_EMPTY_STATS, "discovery_new_roles": ["Postman / CSE / 2026 [Greenhouse]"]}
        body = build_digest(stats)
        assert "DISCOVERY FINDS (1)" in body
        assert "Postman / CSE / 2026 [Greenhouse]" in body

    def test_errors_section_omitted_when_empty(self):
        body = build_digest(_EMPTY_STATS)
        assert "ERRORS" not in body

    def test_errors_section_present(self):
        stats = {**_EMPTY_STATS, "errors": [["SomeCo", "Connection timeout"]]}
        body = build_digest(stats)
        assert "ERRORS (1)" in body
        assert "SomeCo: Connection timeout" in body

    def test_auto_closed_omitted_when_empty(self):
        body = build_digest(_EMPTY_STATS)
        assert "AUTO-CLOSED" not in body

    def test_auto_closed_present(self):
        stats = {**_EMPTY_STATS, "closed_roles": ["OldCo / SE / 2025"]}
        body = build_digest(stats)
        assert "AUTO-CLOSED ROLES (1)" in body
        assert "OldCo / SE / 2025" in body

    def test_pipeline_snapshot_included(self):
        body = build_digest(_EMPTY_STATS)
        assert "PIPELINE SNAPSHOT" in body
        assert "Qualification" in body
        assert "Prioritized" in body
        assert "Total active" in body
        assert "11" in body  # 5+3+1+2

    def test_footer_present(self):
        body = build_digest(_EMPTY_STATS)
        assert "Next sweep:" in body
        assert "6:00 AM ET daily" in body

    def test_multiple_errors_formatted(self):
        stats = {**_EMPTY_STATS, "errors": [
            ["CompA", "Timeout"],
            ["Discovery", "Rate limit"],
        ]}
        body = build_digest(stats)
        assert "ERRORS (2)" in body
        assert "CompA: Timeout" in body
        assert "Discovery: Rate limit" in body


class TestBuildSubject:
    def test_subject_with_roles(self):
        stats = {**_EMPTY_STATS, "new_roles": ["A", "B"], "discovery_new_roles": ["C"]}
        subject = build_subject(stats)
        assert "(3 new roles)" in subject
        assert "Job Sweep Digest" in subject

    def test_subject_with_zero_roles(self):
        subject = build_subject(_EMPTY_STATS)
        assert "(0 new roles)" in subject


# --- merge_stats ---

class TestMergeStats:
    def test_combines_all_lists(self):
        prev = {
            "new_roles": ["A"],
            "discovery_new_roles": ["D"],
            "closed_roles": ["C"],
            "errors": [["E", "msg"]],
            "geo_filtered": 2,
            "red_flagged": 1,
        }
        curr = {
            "new_roles": ["B"],
            "discovery_new_roles": [],
            "closed_roles": [],
            "errors": [],
            "geo_filtered": 1,
            "red_flagged": 0,
        }
        merged = merge_stats(curr, prev)
        assert merged["new_roles"] == ["A", "B"]
        assert merged["discovery_new_roles"] == ["D"]
        assert merged["closed_roles"] == ["C"]
        assert merged["errors"] == [["E", "msg"]]
        assert merged["geo_filtered"] == 3
        assert merged["red_flagged"] == 1

    def test_previous_roles_appear_before_current(self):
        prev = {"new_roles": ["prev"], "discovery_new_roles": [], "closed_roles": [], "errors": [], "geo_filtered": 0, "red_flagged": 0}
        curr = {"new_roles": ["curr"], "discovery_new_roles": [], "closed_roles": [], "errors": [], "geo_filtered": 0, "red_flagged": 0}
        merged = merge_stats(curr, prev)
        assert merged["new_roles"] == ["prev", "curr"]

    def test_empty_previous(self):
        curr = {**_EMPTY_STATS, "new_roles": ["X"], "geo_filtered": 5}
        merged = merge_stats(curr, {})
        assert merged["new_roles"] == ["X"]
        assert merged["geo_filtered"] == 5

    def test_both_empty(self):
        merged = merge_stats(_EMPTY_STATS, _EMPTY_STATS)
        assert merged["new_roles"] == []
        assert merged["geo_filtered"] == 0


# --- send_digest ---

class TestSendDigest:
    def test_skips_when_not_configured(self, capsys):
        with patch("digest.DIGEST_SMTP_HOST", None):
            send_digest("Subject", "Body")
        assert "skipped" in capsys.readouterr().out.lower()

    def test_sends_when_configured(self, capsys):
        mock_server = MagicMock()
        mock_smtp_cls = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        with patch("digest.DIGEST_SMTP_HOST", "smtp.example.com"), \
             patch("digest.DIGEST_SMTP_PORT", 587), \
             patch("digest.DIGEST_EMAIL_FROM", "from@example.com"), \
             patch("digest.DIGEST_EMAIL_TO", "to@example.com"), \
             patch("digest.DIGEST_SMTP_USER", "user"), \
             patch("digest.DIGEST_SMTP_PASSWORD", "secret"), \
             patch("digest.smtplib.SMTP", mock_smtp_cls):
            send_digest("Test Subject", "Test Body")

        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user", "secret")
        mock_server.sendmail.assert_called_once()
        assert "Digest sent" in capsys.readouterr().out


# --- temp file write/read ---

class TestTempFile:
    def test_write_and_read(self, tmp_path):
        test_file = tmp_path / "last_run.json"
        stats = {"new_roles": ["X / Y / 2026 [Z]"], "geo_filtered": 3}

        with patch("digest._LAST_RUN_FILE", test_file):
            write_last_run(stats)
            assert test_file.exists()
            result = read_and_clear_last_run()

        assert result == stats
        assert not test_file.exists()

    def test_read_deletes_file(self, tmp_path):
        test_file = tmp_path / "last_run.json"
        test_file.write_text(json.dumps({"new_roles": []}))

        with patch("digest._LAST_RUN_FILE", test_file):
            read_and_clear_last_run()

        assert not test_file.exists()

    def test_read_returns_none_when_missing(self, tmp_path):
        test_file = tmp_path / "nonexistent.json"
        with patch("digest._LAST_RUN_FILE", test_file):
            result = read_and_clear_last_run()
        assert result is None

    def test_read_returns_none_on_malformed_json(self, tmp_path):
        test_file = tmp_path / "bad.json"
        test_file.write_text("{bad json}")
        with patch("digest._LAST_RUN_FILE", test_file):
            result = read_and_clear_last_run()
        assert result is None
        assert not test_file.exists()
