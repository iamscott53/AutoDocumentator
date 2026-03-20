"""SegraCopilotProvider — combines Graph Search grounding with Azure OpenAI generation.

Architecture (agent pattern):
  1. Authenticate via MSAL (Entra ID)
  2. Optionally search tenant via Microsoft Graph for grounding docs
  3. Build a deterministic prompt with grounding + structured input
  4. Call Azure OpenAI for generation
  5. Validate output against strict SOP schema
  6. Return structured SOPDocument

This does NOT call a "Copilot Chat Completions" endpoint.
It uses the same Azure OpenAI infrastructure that powers M365 Copilot.
"""

import json
import logging
import os
import re

from src.ai_providers import AIProvider
from src.segra.schemas import SOP_SCHEMA_JSON, SOPDocument, validate_sop

log = logging.getLogger(__name__)


class SegraCopilotProvider(AIProvider):
    """Segra enterprise M365 Copilot provider.

    Combines:
      - Microsoft Graph Search API (optional grounding)
      - Azure OpenAI (generation)

    All configuration comes from environment variables or explicit kwargs.
    No secrets are stored in code.
    """

    name = "segra_copilot"
    supports_vision = True  # Azure OpenAI GPT-4o supports vision

    def __init__(
        self,
        tenant_id: str = "",
        client_id: str = "",
        endpoint: str = "",
        deployment: str = "",
        api_version: str = "2024-12-01-preview",
        api_key: str = "",
        aoai_auth: str = "key",
        grounding_enabled: str = "false",
        grounding_query: str = "SOP template standard operating procedure",
        dry_run: str = "false",
        **_,
    ):
        # Resolve from env vars, falling back to explicit kwargs
        self._tenant_id = os.environ.get("AZURE_TENANT_ID", tenant_id)
        self._client_id = os.environ.get("AZURE_CLIENT_ID", client_id)
        self._client_secret = os.environ.get("AZURE_CLIENT_SECRET", "")
        self._endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", endpoint)
        self._deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", deployment)
        self._api_version = os.environ.get("AZURE_OPENAI_API_VERSION", api_version)
        self._api_key = os.environ.get("AZURE_OPENAI_API_KEY", api_key)
        self._aoai_auth = os.environ.get("AZURE_OPENAI_AUTH", aoai_auth)
        self._grounding_enabled = os.environ.get(
            "GRAPH_GROUNDING_ENABLED", grounding_enabled
        ).lower() == "true"
        self._grounding_query = os.environ.get("GRAPH_GROUNDING_QUERY", grounding_query)
        self._dry_run = os.environ.get("DRY_RUN", dry_run).lower() == "true"

        # Lazy-initialized clients
        self._openai_client = None
        self._graph_client = None
        self._auth = None

    # ── Lazy initialization ──────────────────────────────────

    def _get_openai_client(self):
        """Create the Azure OpenAI client on first use."""
        if self._openai_client is not None:
            return self._openai_client

        from openai import AzureOpenAI

        if self._aoai_auth == "entra":
            # Use Entra ID token for Azure OpenAI
            auth = self._get_auth()
            token = auth.get_aoai_token()
            self._openai_client = AzureOpenAI(
                azure_endpoint=self._endpoint,
                azure_ad_token=token,
                api_version=self._api_version,
                timeout=60.0,
            )
        else:
            # Use API key
            self._openai_client = AzureOpenAI(
                azure_endpoint=self._endpoint,
                api_key=self._api_key,
                api_version=self._api_version,
                timeout=60.0,
            )

        return self._openai_client

    def _get_auth(self):
        """Create the MSAL auth helper on first use."""
        if self._auth is not None:
            return self._auth

        from src.segra.auth import EntraAuth

        if not self._tenant_id or not self._client_id:
            raise RuntimeError(
                "AZURE_TENANT_ID and AZURE_CLIENT_ID are required. "
                "Set them in environment variables or Settings."
            )

        self._auth = EntraAuth(
            tenant_id=self._tenant_id,
            client_id=self._client_id,
            client_secret=self._client_secret or None,
        )
        return self._auth

    def _get_graph_client(self):
        """Create the Graph Search client on first use."""
        if self._graph_client is not None:
            return self._graph_client

        from src.segra.graph_client import GraphSearchClient

        auth = self._get_auth()
        self._graph_client = GraphSearchClient(
            token_provider=auth.get_graph_token
        )
        return self._graph_client

    # ── AIProvider interface ─────────────────────────────────

    def analyze_image(self, image_base64: str, prompt: str) -> str:
        """Send an image + prompt to Azure OpenAI."""
        if self._dry_run:
            return self._dry_run_response("analyze_image", prompt)

        client = self._get_openai_client()
        response = client.chat.completions.create(
            model=self._deployment,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_base64}",
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        return response.choices[0].message.content.strip()

    def complete(self, prompt: str) -> str:
        """Send a text prompt to Azure OpenAI."""
        if self._dry_run:
            return self._dry_run_response("complete", prompt)

        client = self._get_openai_client()
        response = client.chat.completions.create(
            model=self._deployment,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip()

    # ── SOP generation with grounding ────────────────────────

    def generate_sop(self, steps_summary: list[dict]) -> SOPDocument:
        """Generate a full SOP document with optional tenant grounding.

        This is the main entry point for Segra Copilot integration.

        Args:
            steps_summary: List of dicts with step data from the recording.

        Returns:
            A validated SOPDocument instance.
        """
        # Step 1: Optional Graph Search for grounding
        grounding_context = ""
        if self._grounding_enabled:
            grounding_context = self._fetch_grounding()

        # Step 2: Build the deterministic prompt
        prompt = self._build_sop_prompt(steps_summary, grounding_context)

        # Step 3: Dry run check
        if self._dry_run:
            log.info(
                "=== DRY RUN — prompt length: %d chars, "
                "grounding: %s, steps: %d ===",
                len(prompt),
                "yes" if grounding_context else "no",
                len(steps_summary),
            )
            return SOPDocument(
                title="[DRY RUN] No API call made",
                purpose="Dry run mode is enabled. No data was sent.",
                procedure_steps=[],
            )

        # Step 4: Call Azure OpenAI
        raw_response = self.complete(prompt)

        # Step 5: Parse and validate
        data = self._parse_json(raw_response)
        if not data:
            raise ValueError("AI returned invalid JSON. Raw response logged.")

        return validate_sop(data)

    def _fetch_grounding(self) -> str:
        """Search tenant docs via Graph and format as grounding context."""
        try:
            from src.segra.graph_client import build_grounding_context

            client = self._get_graph_client()
            snippets = client.search_grounding_docs(self._grounding_query)
            return build_grounding_context(snippets)
        except Exception as e:
            log.warning("Graph grounding failed (continuing without): %s", e)
            return ""

    @staticmethod
    def _build_sop_prompt(
        steps_summary: list[dict], grounding_context: str
    ) -> str:
        """Build the deterministic SOP generation prompt."""
        grounding_section = ""
        if grounding_context:
            grounding_section = (
                f"\n{grounding_context}\n\n"
                "Use any relevant templates, formatting standards, or terminology "
                "from the grounding documents above.\n"
            )

        return (
            "You are an SOP (Standard Operating Procedure) document generator.\n"
            "You must respond with ONLY valid JSON matching the exact schema below.\n"
            "Do not include markdown fences, commentary, or any text outside the JSON.\n\n"
            f"REQUIRED OUTPUT SCHEMA:\n{SOP_SCHEMA_JSON}\n"
            f"{grounding_section}\n"
            "RECORDED PROCEDURE STEPS:\n"
            f"{json.dumps(steps_summary, indent=2)}\n\n"
            "INSTRUCTIONS:\n"
            "1. Generate a professional 'title' and 'purpose' for this procedure.\n"
            "2. Set 'scope' to describe who should follow this procedure.\n"
            "3. List any 'prerequisites' (software, access, data needed).\n"
            "4. For each recorded step, create a 'procedure_steps' entry with:\n"
            "   - 'step': sequential number\n"
            "   - 'action': clear imperative instruction (Click..., Enter..., Select...)\n"
            "   - 'expected_result': what the user should see after this step\n"
            "5. Add 'validation' steps to verify the procedure succeeded.\n"
            "6. Add 'rollback' steps if the procedure can be undone.\n"
            "7. Add common 'troubleshooting' entries if applicable.\n"
            "8. Add 'security_notes' for any sensitive actions.\n"
            "9. Add 'references' to any related documentation.\n\n"
            "Respond with ONLY the JSON object. No other text."
        )

    @staticmethod
    def _parse_json(text: str) -> dict | None:
        """Parse JSON from the AI response."""
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    pass
            log.warning("Failed to parse SOP JSON: %.300s...", text)
            return None

    @staticmethod
    def _dry_run_response(method: str, prompt: str) -> str:
        """Return a placeholder response in dry-run mode (no content logged)."""
        log.info("[DRY RUN] %s called — prompt length: %d chars", method, len(prompt))
        # Never log prompt content — it may contain grounding data from tenant docs
        return json.dumps({
            "title": "[DRY RUN]",
            "purpose": "Dry run mode — no API call was made.",
            "procedure_steps": [],
        })
