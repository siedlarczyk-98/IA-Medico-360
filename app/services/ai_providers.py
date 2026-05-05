"""
Médico 360 — Camada de abstração para providers de IA.
Cada provider implementa a mesma interface para o Agregador.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator

import httpx

from app.core.config import get_settings
from app.core.prompts import SYSTEM_PROMPT_AGREGADOR

settings = get_settings()


@dataclass
class ProviderResponse:
    """Resposta padronizada de qualquer provider."""
    text: str
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    model_id: str = ""
    provider: str = ""


@dataclass
class StreamToken:
    """Token individual para streaming."""
    delta: str
    done: bool = False
    tokens_in: int | None = None
    tokens_out: int | None = None


class BaseProvider(ABC):
    """Interface base para todos os providers de IA."""

    provider_name: str = ""
    model_id: str = ""
    timeout: int = 30

    @abstractmethod
    async def complete(self, prompt: str) -> ProviderResponse:
        """Resposta completa (non-streaming)."""
        ...

    @abstractmethod
    async def stream(self, prompt: str) -> AsyncIterator[StreamToken]:
        """Streaming token a token."""
        ...


# ── Anthropic (Claude) ──────────────────────────────────────

class AnthropicProvider(BaseProvider):
    provider_name = "Anthropic"
    model_id = "claude-sonnet-4-20250514"
    timeout = 30  # RN-SHERLOCK-001: 30s

    async def complete(self, prompt: str) -> ProviderResponse:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model_id,
                    "max_tokens": 4096,
                    "system": SYSTEM_PROMPT_AGREGADOR,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            data = resp.json()

            text = "".join(
                block["text"] for block in data["content"] if block["type"] == "text"
            )
            usage = data.get("usage", {})
            return ProviderResponse(
                text=text,
                tokens_in=usage.get("input_tokens"),
                tokens_out=usage.get("output_tokens"),
                model_id=self.model_id,
                provider=self.provider_name,
            )

    async def stream(self, prompt: str) -> AsyncIterator[StreamToken]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model_id,
                    "max_tokens": 4096,
                    "stream": True,
                    "system": SYSTEM_PROMPT_AGREGADOR,
                    "messages": [{"role": "user", "content": prompt}],
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    import json
                    payload = line[6:]
                    if payload == "[DONE]":
                        break
                    event = json.loads(payload)
                    event_type = event.get("type", "")

                    if event_type == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            yield StreamToken(delta=delta.get("text", ""))

                    elif event_type == "message_delta":
                        usage = event.get("usage", {})
                        yield StreamToken(
                            delta="",
                            done=True,
                            tokens_out=usage.get("output_tokens"),
                        )


# ── OpenAI (GPT-4o) ─────────────────────────────────────────

class OpenAIProvider(BaseProvider):
    provider_name = "OpenAI"
    model_id = "gpt-4o"
    timeout = 30

    async def complete(self, prompt: str) -> ProviderResponse:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model_id,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT_AGREGADOR},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 4096,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            usage = data.get("usage", {})
            return ProviderResponse(
                text=choice["message"]["content"],
                tokens_in=usage.get("prompt_tokens"),
                tokens_out=usage.get("completion_tokens"),
                model_id=self.model_id,
                provider=self.provider_name,
            )

    async def stream(self, prompt: str) -> AsyncIterator[StreamToken]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model_id,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT_AGREGADOR},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 4096,
                    "stream": True,
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload == "[DONE]":
                        yield StreamToken(delta="", done=True)
                        break
                    import json
                    event = json.loads(payload)
                    delta = event["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield StreamToken(delta=content)


# ── Google (Gemini Flash) ────────────────────────────────────

class GeminiProvider(BaseProvider):
    provider_name = "Google"
    model_id = "gemini-2.5-flash"
    timeout = 15

    async def complete(self, prompt: str) -> ProviderResponse:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_id}"
            f":generateContent?key={settings.google_ai_api_key}"
        )
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                url,
                json={
                    "system_instruction": {
                        "parts": [{"text": SYSTEM_PROMPT_AGREGADOR}]
                    },
                    "contents": [
                        {"parts": [{"text": prompt}]}
                    ],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            usage = data.get("usageMetadata", {})
            return ProviderResponse(
                text=text,
                tokens_in=usage.get("promptTokenCount"),
                tokens_out=usage.get("candidatesTokenCount"),
                model_id=self.model_id,
                provider=self.provider_name,
            )

    async def stream(self, prompt: str) -> AsyncIterator[StreamToken]:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_id}"
            f":streamGenerateContent?alt=sse&key={settings.google_ai_api_key}"
        )
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                url,
                json={
                    "system_instruction": {
                        "parts": [{"text": SYSTEM_PROMPT_AGREGADOR}]
                    },
                    "contents": [
                        {"parts": [{"text": prompt}]}
                    ],
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    import json
                    event = json.loads(line[6:])
                    candidates = event.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        for part in parts:
                            if "text" in part:
                                yield StreamToken(delta=part["text"])

                        finish = candidates[0].get("finishReason")
                        if finish:
                            usage = event.get("usageMetadata", {})
                            yield StreamToken(
                                delta="",
                                done=True,
                                tokens_in=usage.get("promptTokenCount"),
                                tokens_out=usage.get("candidatesTokenCount"),
                            )


# ── Perplexity (Sonar Pro) ──────────────────────────────────

class PerplexityProvider(BaseProvider):
    provider_name = "Perplexity"
    model_id = "sonar-pro"
    timeout = 15

    async def complete(self, prompt: str) -> ProviderResponse:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.perplexity_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model_id,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT_AGREGADOR},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 4096,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            usage = data.get("usage", {})
            return ProviderResponse(
                text=choice["message"]["content"],
                tokens_in=usage.get("prompt_tokens"),
                tokens_out=usage.get("completion_tokens"),
                model_id=self.model_id,
                provider=self.provider_name,
            )

    async def stream(self, prompt: str) -> AsyncIterator[StreamToken]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.perplexity_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model_id,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT_AGREGADOR},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 4096,
                    "stream": True,
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload == "[DONE]":
                        yield StreamToken(delta="", done=True)
                        break
                    import json
                    event = json.loads(payload)
                    delta = event["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield StreamToken(delta=content)


# ── Registry ────────────────────────────────────────────────

PROVIDER_REGISTRY: dict[str, BaseProvider] = {
    "claude-sonnet-4-20250514": AnthropicProvider(),
    "gpt-4o": OpenAIProvider(),
    "gemini-2.5-flash": GeminiProvider(),
    "sonar-pro": PerplexityProvider(),
}


def get_provider(model_id: str) -> BaseProvider:
    """Retorna o provider correspondente ao model_id."""
    provider = PROVIDER_REGISTRY.get(model_id)
    if not provider:
        raise ValueError(f"Modelo não suportado: {model_id}")
    return provider
