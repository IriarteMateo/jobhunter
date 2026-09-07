"""Proveedores de IA intercambiables. Sin key configurada, el sistema opera
completo con el motor determinístico."""
from __future__ import annotations

import json
import logging
import re

import httpx

from app.ai.base import AIProvider, LLMAnalysis, ValidationError, validate_llm_payload
from app.ai.prompts import SYSTEM_PROMPT
from app.config import settings

logger = logging.getLogger(__name__)

_JSON_BLOCK = re.compile(r"\{.*\}", re.S)


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_BLOCK.search(text)
        if not match:
            raise ValidationError("la respuesta no contiene JSON")
        return json.loads(match.group(0))


class HeuristicProvider(AIProvider):
    """No llama a ningún modelo: el análisis determinístico ya está calculado."""

    name = "heuristic"
    is_llm = False

    async def analyze(self, prompt: str) -> LLMAnalysis:
        return LLMAnalysis(confidence=0.0)


class AnthropicProvider(AIProvider):
    name = "anthropic"
    is_llm = True
    URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self._client = httpx.AsyncClient(timeout=settings.ai_timeout_seconds)

    async def analyze(self, prompt: str) -> LLMAnalysis:
        resp = await self._client.post(
            self.URL,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": 1500,
                "temperature": 0,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        text = "".join(block.get("text", "") for block in data.get("content", []))
        return validate_llm_payload(_extract_json(text))

    async def close(self) -> None:
        await self._client.aclose()


class OpenAIProvider(AIProvider):
    name = "openai"
    is_llm = True
    URL = "https://api.openai.com/v1/chat/completions"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self._client = httpx.AsyncClient(timeout=settings.ai_timeout_seconds)

    async def analyze(self, prompt: str) -> LLMAnalysis:
        resp = await self._client.post(
            self.URL,
            headers={"Authorization": f"Bearer {self.api_key}", "content-type": "application/json"},
            json={
                "model": self.model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        return validate_llm_payload(_extract_json(text))

    async def close(self) -> None:
        await self._client.aclose()


def build_provider() -> AIProvider:
    provider = (settings.ai_provider or "heuristic").lower()
    if provider == "anthropic" and settings.anthropic_api_key:
        return AnthropicProvider(settings.anthropic_api_key, settings.anthropic_model)
    if provider == "openai" and settings.openai_api_key:
        return OpenAIProvider(settings.openai_api_key, settings.openai_model)
    if provider in ("anthropic", "openai"):
        logger.warning("AI_PROVIDER=%s pero falta la API key: se usa el motor determinístico.", provider)
    return HeuristicProvider()
