"""
Médico 360 — Camada de abstração para providers de IA.
Providers por tipo, modelos vêm do banco (model_pricing).
System prompt configurável — padrão é SYSTEM_PROMPT_AGREGADOR.
"""

import json as json_lib
from abc import ABC, abstractmethod
from dataclasses import dataclass
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

    @abstractmethod
    async def complete(self, model_id: str, prompt: str, timeout: int = 30, system_prompt: str | None = None, temperature: float = 1.0) -> ProviderResponse:
        ...

    @abstractmethod
    async def stream(self, model_id: str, prompt: str, timeout: int = 30, system_prompt: str | None = None, temperature: float = 1.0) -> AsyncIterator[StreamToken]:
        ...


# ── Anthropic ────────────────────────────────────────────────

class AnthropicProvider(BaseProvider):

    async def complete(self, model_id: str, prompt: str, timeout: int = 30, system_prompt: str | None = None, temperature: float = 1.0) -> ProviderResponse:
        sys_prompt = system_prompt or SYSTEM_PROMPT_AGREGADOR
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model_id,
                    "max_tokens": 4096,
                    "temperature": temperature,
                    "system": sys_prompt,
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
                model_id=model_id,
                provider="Anthropic",
            )

    async def stream(self, model_id: str, prompt: str, timeout: int = 30, system_prompt: str | None = None) -> AsyncIterator[StreamToken]:
        sys_prompt = system_prompt or SYSTEM_PROMPT_AGREGADOR
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model_id,
                    "max_tokens": 4096,
                    "stream": True,
                    "system": sys_prompt,
                    "messages": [{"role": "user", "content": prompt}],
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload == "[DONE]":
                        break
                    event = json_lib.loads(payload)
                    event_type = event.get("type", "")
                    if event_type == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            yield StreamToken(delta=delta.get("text", ""))
                    elif event_type == "message_delta":
                        usage = event.get("usage", {})
                        yield StreamToken(delta="", done=True, tokens_out=usage.get("output_tokens"))


# ── OpenAI ───────────────────────────────────────────────────

class OpenAIProvider(BaseProvider):

    async def complete(self, model_id: str, prompt: str, timeout: int = 30, system_prompt: str | None = None, temperature: float = 1.0) -> ProviderResponse:
        sys_prompt = system_prompt or SYSTEM_PROMPT_AGREGADOR
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model_id,
                    "messages": [
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "max_completion_tokens": 4096,
                    "temperature": temperature,
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
                model_id=model_id,
                provider="OpenAI",
            )

    async def stream(self, model_id: str, prompt: str, timeout: int = 30, system_prompt: str | None = None) -> AsyncIterator[StreamToken]:
        sys_prompt = system_prompt or SYSTEM_PROMPT_AGREGADOR
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model_id,
                    "messages": [
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "max_completion_tokens": 4096,
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
                    event = json_lib.loads(payload)
                    delta = event["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield StreamToken(delta=content)


# ── Google (Gemini) ──────────────────────────────────────────

class GeminiProvider(BaseProvider):

    async def complete(self, model_id: str, prompt: str, timeout: int = 15, system_prompt: str | None = None) -> ProviderResponse:
        sys_prompt = system_prompt or SYSTEM_PROMPT_AGREGADOR
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}"
            f":generateContent?key={settings.google_ai_api_key}"
        )
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                url,
                json={
                    "system_instruction": {"parts": [{"text": sys_prompt}]},
                    "contents": [{"parts": [{"text": prompt}]}],
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
                model_id=model_id,
                provider="Google",
            )

    async def stream(self, model_id: str, prompt: str, timeout: int = 15, system_prompt: str | None = None) -> AsyncIterator[StreamToken]:
        sys_prompt = system_prompt or SYSTEM_PROMPT_AGREGADOR
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}"
            f":streamGenerateContent?alt=sse&key={settings.google_ai_api_key}"
        )
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                url,
                json={
                    "system_instruction": {"parts": [{"text": sys_prompt}]},
                    "contents": [{"parts": [{"text": prompt}]}],
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    event = json_lib.loads(line[6:])
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
                                delta="", done=True,
                                tokens_in=usage.get("promptTokenCount"),
                                tokens_out=usage.get("candidatesTokenCount"),
                            )


# ── Perplexity ───────────────────────────────────────────────

class PerplexityProvider(BaseProvider):

    async def complete(self, model_id: str, prompt: str, timeout: int = 15, system_prompt: str | None = None) -> ProviderResponse:
        sys_prompt = system_prompt or SYSTEM_PROMPT_AGREGADOR
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.perplexity_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model_id,
                    "messages": [
                        {"role": "system", "content": sys_prompt},
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
                model_id=model_id,
                provider="Perplexity",
            )

    async def stream(self, model_id: str, prompt: str, timeout: int = 15, system_prompt: str | None = None) -> AsyncIterator[StreamToken]:
        sys_prompt = system_prompt or SYSTEM_PROMPT_AGREGADOR
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.perplexity_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model_id,
                    "messages": [
                        {"role": "system", "content": sys_prompt},
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
                    event = json_lib.loads(payload)
                    delta = event["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield StreamToken(delta=content)


# ── Registry por tipo ────────────────────────────────────────

PROVIDER_TYPE_REGISTRY: dict[str, BaseProvider] = {
    "anthropic": AnthropicProvider(),
    "openai": OpenAIProvider(),
    "google": GeminiProvider(),
    "perplexity": PerplexityProvider(),
}


def get_provider_by_type(provider_type: str) -> BaseProvider:
    """Retorna o provider correspondente ao tipo."""
    provider = PROVIDER_TYPE_REGISTRY.get(provider_type)
    if not provider:
        raise ValueError(f"Provider type não suportado: {provider_type}")
    return provider