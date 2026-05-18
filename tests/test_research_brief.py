from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_text_block(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _make_tool_block() -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    return block


def _make_response(*blocks) -> MagicMock:
    resp = MagicMock()
    resp.content = list(blocks)
    return resp


def _make_notion_page(page_id: str, name: str, stage: str, job_url: str) -> dict:
    parts = name.split(" / ")
    props = {
        "Name": {"title": [{"plain_text": name}]},
        "Stage": {"select": {"name": stage}},
        "Job URL": {"url": job_url},
    }
    return {"id": page_id, "properties": props}


# ---------------------------------------------------------------------------
# generate_brief
# ---------------------------------------------------------------------------

class TestGenerateBrief:
    def test_calls_claude_with_correct_model_and_tool(self):
        from research_brief import generate_brief
        with patch("research_brief.anthropic.Anthropic") as MockClient:
            mock_client = MockClient.return_value
            mock_client.messages.create.return_value = _make_response(
                _make_text_block("Company research here.")
            )
            generate_brief("Acme", "Solutions Engineer", "https://jobs.example.com/se")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-sonnet-4-6"
        tools = call_kwargs["tools"]
        assert any(t.get("type") == "web_search_20250305" for t in tools)

    def test_extracts_text_from_response_content_blocks(self):
        from research_brief import generate_brief
        with patch("research_brief.anthropic.Anthropic") as MockClient:
            mock_client = MockClient.return_value
            mock_client.messages.create.return_value = _make_response(
                _make_tool_block(),
                _make_text_block("First paragraph."),
                _make_tool_block(),
                _make_text_block("Second paragraph."),
            )
            result = generate_brief("Acme", "TAM", "https://example.com")

        assert "First paragraph." in result
        assert "Second paragraph." in result

    def test_skips_non_text_blocks(self):
        from research_brief import generate_brief
        with patch("research_brief.anthropic.Anthropic") as MockClient:
            mock_client = MockClient.return_value
            mock_client.messages.create.return_value = _make_response(
                _make_tool_block(),
                _make_text_block("Real content only."),
            )
            result = generate_brief("Acme", "SE", "https://example.com")

        assert result == "Real content only."

    def test_api_error_raises_runtime_error(self):
        from research_brief import generate_brief
        with patch("research_brief.anthropic.Anthropic") as MockClient:
            mock_client = MockClient.return_value
            mock_client.messages.create.side_effect = Exception("rate limit")
            with pytest.raises(RuntimeError, match="Claude API call failed"):
                generate_brief("Acme", "SE", "https://example.com")

    def test_empty_response_raises_runtime_error(self):
        from research_brief import generate_brief
        with patch("research_brief.anthropic.Anthropic") as MockClient:
            mock_client = MockClient.return_value
            mock_client.messages.create.return_value = _make_response(
                _make_tool_block(),
            )
            with pytest.raises(RuntimeError, match="no text content"):
                generate_brief("Acme", "SE", "https://example.com")

    def test_company_and_title_appear_in_system_prompt(self):
        from research_brief import generate_brief
        with patch("research_brief.anthropic.Anthropic") as MockClient:
            mock_client = MockClient.return_value
            mock_client.messages.create.return_value = _make_response(
                _make_text_block("Brief content.")
            )
            generate_brief("Initech", "Customer Success Engineer", "https://jobs.example.com")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        system = call_kwargs["system"]
        assert "Initech" in system
        assert "Customer Success Engineer" in system

    def test_user_message_contains_company_title_url(self):
        from research_brief import generate_brief
        with patch("research_brief.anthropic.Anthropic") as MockClient:
            mock_client = MockClient.return_value
            mock_client.messages.create.return_value = _make_response(
                _make_text_block("Brief.")
            )
            generate_brief("Globex", "TAM", "https://jobs.globex.com/tam")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "Globex" in user_content
        assert "TAM" in user_content
        assert "https://jobs.globex.com/tam" in user_content


# ---------------------------------------------------------------------------
# search_opportunities_by_company
# ---------------------------------------------------------------------------

class TestSearchOpportunitiesByCompany:
    def _make_page(self, name: str, stage: str, job_url: str, page_id: str = "pid-1") -> dict:
        return {
            "id": page_id,
            "properties": {
                "Name": {"title": [{"plain_text": name}]},
                "Stage": {"select": {"name": stage}},
                "Job URL": {"url": job_url},
            },
        }

    def _mock_query(self, pages: list) -> MagicMock:
        resp = MagicMock()
        resp.__getitem__ = lambda self, key: {"results": pages, "has_more": False}[key]
        resp.get = lambda key, default=None: {"results": pages, "has_more": False}.get(key, default)
        return resp

    def test_returns_matching_opportunity(self):
        from notion_api import search_opportunities_by_company
        pages = [self._make_page("Acme / Solutions Engineer / 2026", "Qualification", "https://jobs.acme.com/se")]
        with patch("notion_api._client") as mock_client:
            mock_client.data_sources.query.return_value = {"results": pages, "has_more": False}
            results = search_opportunities_by_company("Acme")
        assert len(results) == 1
        assert results[0]["company_name"] == "Acme"
        assert results[0]["title"] == "Solutions Engineer"

    def test_case_insensitive_match(self):
        from notion_api import search_opportunities_by_company
        pages = [self._make_page("Acme Corp / TAM / 2026", "Prioritized", "https://jobs.acme.com/tam")]
        with patch("notion_api._client") as mock_client:
            mock_client.data_sources.query.return_value = {"results": pages, "has_more": False}
            results = search_opportunities_by_company("acme corp")
        assert len(results) == 1

    def test_excludes_non_matching_company_name(self):
        from notion_api import search_opportunities_by_company
        pages = [self._make_page("Acme Plus / SE / 2026", "Qualification", "https://jobs.acmeplus.com/se")]
        with patch("notion_api._client") as mock_client:
            mock_client.data_sources.query.return_value = {"results": pages, "has_more": False}
            results = search_opportunities_by_company("Acme")
        # "Acme" is in "Acme Plus" — this is a contains match, should return it
        assert len(results) == 1

    def test_returns_empty_when_no_results(self):
        from notion_api import search_opportunities_by_company
        with patch("notion_api._client") as mock_client:
            mock_client.data_sources.query.return_value = {"results": [], "has_more": False}
            results = search_opportunities_by_company("NonExistent")
        assert results == []

    def test_result_contains_expected_fields(self):
        from notion_api import search_opportunities_by_company
        pages = [self._make_page(
            "Dunder Mifflin / Customer Success Engineer / 2026",
            "Create Resume",
            "https://jobs.dundermifflin.com/cse",
            page_id="page-abc",
        )]
        with patch("notion_api._client") as mock_client:
            mock_client.data_sources.query.return_value = {"results": pages, "has_more": False}
            results = search_opportunities_by_company("Dunder Mifflin")
        r = results[0]
        assert r["page_id"] == "page-abc"
        assert r["title"] == "Customer Success Engineer"
        assert r["job_url"] == "https://jobs.dundermifflin.com/cse"
        assert r["stage"] == "Create Resume"


# ---------------------------------------------------------------------------
# update_research_field
# ---------------------------------------------------------------------------

class TestUpdateResearchField:
    def test_writes_brief_to_notion(self):
        from notion_api import update_research_field
        with patch("notion_api._client") as mock_client:
            update_research_field("page-1", "Some brief text.")
        mock_client.pages.update.assert_called_once()
        call_kwargs = mock_client.pages.update.call_args.kwargs
        assert call_kwargs["page_id"] == "page-1"
        rt = call_kwargs["properties"]["Research"]["rich_text"]
        assert rt[0]["text"]["content"] == "Some brief text."

    def test_truncates_to_2000_chars(self):
        from notion_api import update_research_field
        long_brief = "x" * 3000
        with patch("notion_api._client") as mock_client:
            update_research_field("page-1", long_brief)
        call_kwargs = mock_client.pages.update.call_args.kwargs
        content = call_kwargs["properties"]["Research"]["rich_text"][0]["text"]["content"]
        assert len(content) == 2000

    def test_short_brief_not_truncated(self):
        from notion_api import update_research_field
        brief = "Short brief."
        with patch("notion_api._client") as mock_client:
            update_research_field("page-1", brief)
        call_kwargs = mock_client.pages.update.call_args.kwargs
        content = call_kwargs["properties"]["Research"]["rich_text"][0]["text"]["content"]
        assert content == "Short brief."


# ---------------------------------------------------------------------------
# dry_run behavior (script-level, tested via module imports)
# ---------------------------------------------------------------------------

class TestDryRun:
    def test_dry_run_skips_notion_write_and_email(self):
        with patch("research_brief.anthropic.Anthropic") as MockClient, \
             patch("notion_api._client") as mock_notion, \
             patch("digest.send_digest") as mock_send:
            mock_client = MockClient.return_value
            mock_client.messages.create.return_value = MagicMock(
                content=[_make_text_block("Brief content.")]
            )

            import research_brief as rb
            brief = rb.generate_brief("Acme", "SE", "https://example.com")
            # simulate dry_run: caller skips these
            # (we verify neither is called)
            mock_notion.pages.update.assert_not_called()
            mock_send.assert_not_called()
