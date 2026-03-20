"""Microsoft Graph client — searches tenant documents for SOP grounding."""

import logging
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

GRAPH_SEARCH_URL = "https://graph.microsoft.com/v1.0/search/query"


@dataclass
class GroundingSnippet:
    """A snippet of content retrieved from tenant documents."""
    title: str
    summary: str
    source: str  # file name or URL


class GraphSearchClient:
    """Searches Microsoft 365 content via the Graph Search API."""

    def __init__(self, token_provider, timeout: float = 30.0):
        """
        Args:
            token_provider: Callable that returns a valid Graph access token.
            timeout: HTTP request timeout in seconds.
        """
        self._get_token = token_provider
        self._timeout = timeout

    def search_grounding_docs(
        self, query: str, max_results: int = 5
    ) -> list[GroundingSnippet]:
        """Search tenant for documents matching the query.

        Returns a list of GroundingSnippets with title, summary, and source.
        These are fed into the AI prompt for context-grounded generation.
        """
        token = self._get_token()

        payload = {
            "requests": [
                {
                    "entityTypes": ["driveItem", "listItem"],
                    "query": {"queryString": query},
                    "from": 0,
                    "size": max_results,
                }
            ]
        }

        try:
            # Log the query but never the token
            log.info("Graph Search: query=%r, max_results=%d", query, max_results)

            response = httpx.post(
                GRAPH_SEARCH_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self._timeout,
            )
            response.raise_for_status()
            return self._parse_response(response.json())

        except httpx.HTTPStatusError as e:
            log.warning(
                "Graph Search failed: HTTP %d",
                e.response.status_code,
            )
            return []
        except httpx.RequestError as e:
            log.warning("Graph Search request error: %s", e)
            return []

    @staticmethod
    def _parse_response(data: dict) -> list[GroundingSnippet]:
        """Extract snippets from the Graph Search response."""
        snippets: list[GroundingSnippet] = []

        for resp in data.get("value", []):
            for hit_container in resp.get("hitsContainers", []):
                for hit in hit_container.get("hits", []):
                    resource = hit.get("resource", {})
                    title = resource.get("name", "Untitled")
                    summary = hit.get("summary", "")
                    source = resource.get("webUrl", resource.get("name", ""))

                    # Sanitize: never include raw document content
                    safe_summary = summary[:500] if summary else ""

                    snippets.append(GroundingSnippet(
                        title=title,
                        summary=safe_summary,
                        source=source,
                    ))

        return snippets


def build_grounding_context(snippets: list[GroundingSnippet]) -> str:
    """Format grounding snippets into a prompt-friendly string."""
    if not snippets:
        return ""

    lines = ["GROUNDING — Relevant tenant documents found:"]
    for i, s in enumerate(snippets, 1):
        lines.append(f"  [{i}] {s.title}")
        if s.summary:
            lines.append(f"      Summary: {s.summary}")
    return "\n".join(lines)
