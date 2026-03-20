"""AI provider implementations for multiple services."""

import base64
import io
from abc import ABC, abstractmethod


class AIProvider(ABC):
    """Base class for all AI providers."""

    name: str = "base"
    supports_vision: bool = False

    @abstractmethod
    def analyze_image(self, image_base64: str, prompt: str) -> str:
        """Send an image with a text prompt, return the response text."""

    @abstractmethod
    def complete(self, prompt: str) -> str:
        """Send a text-only prompt, return the response text."""


# ── Anthropic (Claude) ──────────────────────────────────────


class AnthropicProvider(AIProvider):
    name = "anthropic"
    supports_vision = True

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6-20250514", **_):
        from anthropic import Anthropic

        self.client = Anthropic(api_key=api_key, timeout=60.0)
        self.model = model

    def analyze_image(self, image_base64: str, prompt: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_base64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        return response.content[0].text.strip()

    def complete(self, prompt: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()


# ── OpenAI (ChatGPT) ────────────────────────────────────────


class OpenAIProvider(AIProvider):
    name = "openai"
    supports_vision = True

    def __init__(self, api_key: str, model: str = "gpt-4o", **_):
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key, timeout=60.0)
        self.model = model

    def analyze_image(self, image_base64: str, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
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
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip()


# ── Azure OpenAI (Copilot / Enterprise) ─────────────────────


class AzureOpenAIProvider(AIProvider):
    name = "azure_openai"
    supports_vision = True

    def __init__(
        self,
        api_key: str,
        endpoint: str,
        deployment: str,
        api_version: str = "2024-12-01-preview",
        **_,
    ):
        from openai import AzureOpenAI

        self.client = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
            timeout=60.0,
        )
        self.deployment = deployment

    def analyze_image(self, image_base64: str, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.deployment,
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
        response = self.client.chat.completions.create(
            model=self.deployment,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip()


# ── Ollama (Local Models) ───────────────────────────────────


class OllamaProvider(AIProvider):
    name = "ollama"
    supports_vision = True  # llava, bakllava, moondream support vision

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llava",
        **_,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def analyze_image(self, image_base64: str, prompt: str) -> str:
        import httpx

        response = httpx.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "images": [image_base64],
                "stream": False,
            },
            timeout=120.0,
        )
        response.raise_for_status()
        return response.json()["response"].strip()

    def complete(self, prompt: str) -> str:
        import httpx

        response = httpx.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
            },
            timeout=120.0,
        )
        response.raise_for_status()
        return response.json()["response"].strip()


# ── Google (Gemini) ──────────────────────────────────────────


class GoogleProvider(AIProvider):
    name = "google"
    supports_vision = True

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash", **_):
        from google import generativeai as genai

        genai.configure(api_key=api_key)
        self.genai_model = genai.GenerativeModel(model)

    def analyze_image(self, image_base64: str, prompt: str) -> str:
        from PIL import Image

        image_bytes = base64.b64decode(image_base64)
        image = Image.open(io.BytesIO(image_bytes))
        response = self.genai_model.generate_content([prompt, image])
        return response.text.strip()

    def complete(self, prompt: str) -> str:
        response = self.genai_model.generate_content(prompt)
        return response.text.strip()


# ── Provider Registry ────────────────────────────────────────

def _get_segra_class():
    from src.segra.copilot_provider import SegraCopilotProvider
    return SegraCopilotProvider

PROVIDERS = {
    "segra_copilot": {
        "display_name": "Segra M365 Copilot",
        "class": _get_segra_class,  # Lazy — resolved in create_provider()
        "models": [],
        "package": "openai",
        "fields": {
            "endpoint": {
                "label": "Azure OpenAI Endpoint",
                "secret": False,
                "placeholder": "https://your-resource.openai.azure.com/",
            },
            "deployment": {
                "label": "Deployment Name",
                "secret": False,
                "placeholder": "gpt-4o",
            },
            "api_key": {
                "label": "Azure OpenAI API Key",
                "secret": True,
                "placeholder": "(or set AZURE_OPENAI_API_KEY env var)",
            },
            "tenant_id": {
                "label": "Entra Tenant ID",
                "secret": False,
                "placeholder": "(or set AZURE_TENANT_ID env var)",
            },
            "client_id": {
                "label": "Entra Client ID",
                "secret": False,
                "placeholder": "(or set AZURE_CLIENT_ID env var)",
            },
        },
    },
    "anthropic": {
        "display_name": "Anthropic (Claude)",
        "class": AnthropicProvider,
        "models": [
            "claude-sonnet-4-6-20250514",
            "claude-haiku-4-5-20251001",
            "claude-opus-4-6-20250610",
        ],
        "package": "anthropic",
        "fields": {
            "api_key": {"label": "API Key", "secret": True, "placeholder": "sk-ant-..."},
            "model": {"label": "Model", "type": "dropdown"},
        },
    },
    "openai": {
        "display_name": "OpenAI (ChatGPT)",
        "class": OpenAIProvider,
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "o3-mini"],
        "package": "openai",
        "fields": {
            "api_key": {"label": "API Key", "secret": True, "placeholder": "sk-..."},
            "model": {"label": "Model", "type": "dropdown"},
        },
    },
    "azure_openai": {
        "display_name": "Azure OpenAI (Copilot)",
        "class": AzureOpenAIProvider,
        "models": [],
        "package": "openai",
        "fields": {
            "api_key": {"label": "API Key", "secret": True, "placeholder": "your-azure-key"},
            "endpoint": {
                "label": "Endpoint URL",
                "secret": False,
                "placeholder": "https://your-resource.openai.azure.com/",
            },
            "deployment": {
                "label": "Deployment Name",
                "secret": False,
                "placeholder": "gpt-4o-deployment",
            },
            "api_version": {
                "label": "API Version",
                "secret": False,
                "placeholder": "2024-12-01-preview",
                "default": "2024-12-01-preview",
            },
        },
    },
    "ollama": {
        "display_name": "Ollama (Local)",
        "class": OllamaProvider,
        "models": ["llava", "llava:13b", "llava:34b", "bakllava", "moondream"],
        "package": None,  # uses httpx already installed
        "fields": {
            "base_url": {
                "label": "Base URL",
                "secret": False,
                "placeholder": "http://localhost:11434",
                "default": "http://localhost:11434",
            },
            "model": {"label": "Model", "type": "dropdown"},
        },
    },
    "google": {
        "display_name": "Google (Gemini)",
        "class": GoogleProvider,
        "models": ["gemini-2.0-flash", "gemini-2.5-pro", "gemini-2.5-flash"],
        "package": "google-generativeai",
        "fields": {
            "api_key": {"label": "API Key", "secret": True, "placeholder": "AI..."},
            "model": {"label": "Model", "type": "dropdown"},
        },
    },
}


def get_provider_names() -> list[str]:
    """Return list of all provider keys."""
    return list(PROVIDERS.keys())


def get_provider_display_names() -> dict[str, str]:
    """Return mapping of provider key -> display name."""
    return {k: v["display_name"] for k, v in PROVIDERS.items()}


def create_provider(provider_name: str, **kwargs) -> AIProvider:
    """Create an AI provider instance.

    Args:
        provider_name: Key from PROVIDERS dict
        **kwargs: Provider-specific configuration (api_key, model, etc.)

    Returns:
        Configured AIProvider instance

    Raises:
        ValueError: If provider_name is unknown
        ImportError: If required package is not installed
    """
    if provider_name not in PROVIDERS:
        available = ", ".join(PROVIDERS.keys())
        raise ValueError(f"Unknown provider: {provider_name}. Available: {available}")

    info = PROVIDERS[provider_name]

    # Check required package
    pkg = info.get("package")
    if pkg:
        try:
            __import__(pkg.replace("-", "_").split(".")[0])
        except ImportError:
            raise ImportError(
                f"The '{pkg}' package is required for {info['display_name']}.\n"
                f"Install it with:  pip install {pkg}"
            )

    # Filter kwargs to only include non-empty values
    filtered = {k: v for k, v in kwargs.items() if v}

    # Resolve lazy class references (callables that return the actual class)
    cls = info["class"]
    if callable(cls) and not isinstance(cls, type):
        cls = cls()

    return cls(**filtered)


def get_default_config(provider_name: str) -> dict:
    """Return default configuration for a provider."""
    info = PROVIDERS.get(provider_name, {})
    config = {}
    for field_name, field_info in info.get("fields", {}).items():
        if field_info.get("type") == "dropdown" and info.get("models"):
            config[field_name] = info["models"][0]
        elif "default" in field_info:
            config[field_name] = field_info["default"]
        else:
            config[field_name] = ""
    return config
