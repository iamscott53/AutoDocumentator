"""Tests for Segra M365 Copilot integration modules."""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Schema Validation Tests ──────────────────────────────────

class TestSOPSchema(unittest.TestCase):
    """Unit tests for the SOP document schema."""

    def test_valid_full_document(self):
        from src.segra.schemas import validate_sop

        data = {
            "title": "How to Reset a Password",
            "purpose": "This procedure documents the password reset workflow.",
            "scope": "IT Help Desk staff",
            "prerequisites": ["Admin portal access", "VPN connection"],
            "procedure_steps": [
                {"step": 1, "action": "Open the admin portal", "expected_result": "Login page appears"},
                {"step": 2, "action": "Click User Management", "expected_result": "User list loads"},
            ],
            "validation": ["Verify user can log in with new password"],
            "rollback": ["Restore previous password from backup"],
            "troubleshooting": [
                {"symptom": "Portal not loading", "cause": "VPN disconnected", "fix": "Reconnect VPN"}
            ],
            "security_notes": ["Never share temporary passwords via email"],
            "references": ["https://wiki.internal/password-policy"],
        }

        doc = validate_sop(data)
        self.assertEqual(doc.title, "How to Reset a Password")
        self.assertEqual(len(doc.procedure_steps), 2)
        self.assertEqual(doc.procedure_steps[0].step, 1)
        self.assertEqual(doc.troubleshooting[0].symptom, "Portal not loading")

    def test_minimal_document(self):
        from src.segra.schemas import validate_sop

        data = {
            "title": "Minimal SOP",
            "purpose": "Testing minimal fields.",
        }

        doc = validate_sop(data)
        self.assertEqual(doc.title, "Minimal SOP")
        self.assertEqual(doc.procedure_steps, [])
        self.assertEqual(doc.prerequisites, [])

    def test_missing_required_field(self):
        from pydantic import ValidationError
        from src.segra.schemas import validate_sop

        with self.assertRaises(ValidationError):
            validate_sop({"purpose": "No title provided"})

    def test_invalid_step_structure(self):
        from pydantic import ValidationError
        from src.segra.schemas import validate_sop

        with self.assertRaises(ValidationError):
            validate_sop({
                "title": "Bad Steps",
                "purpose": "Testing",
                "procedure_steps": [{"wrong_field": "oops"}],
            })

    def test_extra_fields_ignored(self):
        from src.segra.schemas import validate_sop

        data = {
            "title": "Extra Fields",
            "purpose": "Should ignore extras.",
            "unknown_field": "this is fine",
        }

        doc = validate_sop(data)
        self.assertEqual(doc.title, "Extra Fields")


# ── Provider Contract Tests (mocked HTTP) ────────────────────

class TestSegraCopilotProvider(unittest.TestCase):
    """Contract tests for the SegraCopilotProvider with mocked HTTP."""

    def _make_provider(self, **overrides):
        from src.segra.copilot_provider import SegraCopilotProvider

        defaults = {
            "endpoint": "https://test.openai.azure.com/",
            "deployment": "gpt-4o-test",
            "api_key": "test-key-123",
            "tenant_id": "test-tenant",
            "client_id": "test-client",
        }
        defaults.update(overrides)
        return SegraCopilotProvider(**defaults)

    def test_dry_run_returns_placeholder(self):
        provider = self._make_provider(dry_run="true")
        result = provider.complete("test prompt")
        data = json.loads(result)
        self.assertEqual(data["title"], "[DRY RUN]")

    def test_dry_run_generate_sop(self):
        provider = self._make_provider(dry_run="true")
        sop = provider.generate_sop([
            {"number": 1, "action_type": "click", "current_description": "Click button"},
        ])
        self.assertIn("DRY RUN", sop.title)

    @patch("src.segra.copilot_provider.SegraCopilotProvider._get_openai_client")
    def test_generate_sop_valid_response(self, mock_get_client):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "title": "Test SOP",
            "purpose": "Testing the pipeline.",
            "procedure_steps": [
                {"step": 1, "action": "Click the button", "expected_result": "Dialog opens"},
            ],
        })
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        provider = self._make_provider()
        sop = provider.generate_sop([
            {"number": 1, "action_type": "click", "current_description": "Click button"},
        ])

        self.assertEqual(sop.title, "Test SOP")
        self.assertEqual(len(sop.procedure_steps), 1)
        self.assertEqual(sop.procedure_steps[0].action, "Click the button")

    @patch("src.segra.copilot_provider.SegraCopilotProvider._get_openai_client")
    def test_generate_sop_invalid_json_raises(self, mock_get_client):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "This is not JSON at all."
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        provider = self._make_provider()
        with self.assertRaises(ValueError):
            provider.generate_sop([{"number": 1}])


# ── Graph Client Tests (mocked HTTP) ─────────────────────────

class TestGraphClient(unittest.TestCase):
    """Contract tests for the Microsoft Graph Search client."""

    @patch("httpx.post")
    def test_search_returns_snippets(self, mock_post):
        from src.segra.graph_client import GraphSearchClient

        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "value": [{
                    "hitsContainers": [{
                        "hits": [{
                            "summary": "Standard procedure for password reset.",
                            "resource": {
                                "name": "PasswordReset_SOP.docx",
                                "webUrl": "https://sharepoint/sites/IT/PasswordReset_SOP.docx",
                            },
                        }]
                    }]
                }]
            },
        )
        mock_post.return_value.raise_for_status = MagicMock()

        client = GraphSearchClient(token_provider=lambda: "fake-token")
        snippets = client.search_grounding_docs("password reset")

        self.assertEqual(len(snippets), 1)
        self.assertEqual(snippets[0].title, "PasswordReset_SOP.docx")
        self.assertIn("password reset", snippets[0].summary)

    @patch("httpx.post")
    def test_search_handles_http_error(self, mock_post):
        import httpx
        from src.segra.graph_client import GraphSearchClient

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        mock_post.return_value = mock_response
        mock_post.return_value.raise_for_status.side_effect = httpx.HTTPStatusError(
            "403", request=MagicMock(), response=mock_response
        )

        client = GraphSearchClient(token_provider=lambda: "fake-token")
        snippets = client.search_grounding_docs("test")

        self.assertEqual(snippets, [])


# ── Renderer Tests ───────────────────────────────────────────

class TestRenderer(unittest.TestCase):
    """Tests for HTML/Markdown rendering of SOPDocument."""

    def _sample_sop(self):
        from src.segra.schemas import SOPDocument, ProcedureStep

        return SOPDocument(
            title="Test Procedure",
            purpose="For testing.",
            procedure_steps=[
                ProcedureStep(step=1, action="Do thing", expected_result="Thing done"),
            ],
        )

    def test_html_contains_title(self):
        from src.segra.renderer import render_html

        html = render_html(self._sample_sop())
        self.assertIn("Test Procedure", html)
        self.assertIn("<table>", html)

    def test_html_escapes_xss(self):
        from src.segra.renderer import render_html
        from src.segra.schemas import SOPDocument

        sop = SOPDocument(
            title='<script>alert("xss")</script>',
            purpose="Testing XSS.",
        )
        html = render_html(sop)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_markdown_contains_table(self):
        from src.segra.renderer import render_markdown

        md = render_markdown(self._sample_sop())
        self.assertIn("| # | Action |", md)
        self.assertIn("| 1 | Do thing |", md)


# ── Fixture-Based Stable Output Test ─────────────────────────

class TestFixtureStableOutput(unittest.TestCase):
    """Tests that the sample fixture produces stable, valid output."""

    def test_fixture_through_provider_dry_run(self):
        from src.segra.copilot_provider import SegraCopilotProvider

        fixture_path = Path(__file__).parent / "fixtures" / "sample_recording.json"
        with open(fixture_path) as f:
            fixture = json.load(f)

        provider = SegraCopilotProvider(
            endpoint="https://test.openai.azure.com/",
            deployment="gpt-4o",
            api_key="test",
            dry_run="true",
        )

        sop = provider.generate_sop(fixture["steps"])
        self.assertIn("DRY RUN", sop.title)

    def test_fixture_renders_all_formats(self):
        import tempfile
        from src.segra.schemas import SOPDocument, ProcedureStep
        from src.segra.renderer import render_html, render_markdown, render_docx

        sop = SOPDocument(
            title="Fixture SOP",
            purpose="Generated from fixture data.",
            procedure_steps=[
                ProcedureStep(step=1, action="Open browser", expected_result="Browser opens"),
                ProcedureStep(step=2, action="Navigate to URL", expected_result="Page loads"),
            ],
        )

        html = render_html(sop)
        self.assertIn("Fixture SOP", html)

        md = render_markdown(sop)
        self.assertIn("Fixture SOP", md)

        with tempfile.TemporaryDirectory() as tmpdir:
            docx_path = render_docx(sop, Path(tmpdir) / "test.docx")
            self.assertTrue(docx_path.exists())


if __name__ == "__main__":
    unittest.main()
