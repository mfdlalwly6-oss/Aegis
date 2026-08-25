"""
OpenRouter AI Client — يدير 8 مفاتيح مع round-robin وfallback تلقائي.
"""

from __future__ import annotations

import itertools
import os
import time

import httpx
import structlog

logger = structlog.get_logger(__name__)


class OpenRouterClient:
    ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
    PRIMARY_MODEL = "google/gemma-2-9b-it:free"
    FALLBACK_MODELS = [
        "meta-llama/llama-3.2-3b-instruct:free",
        "mistralai/mistral-7b-instruct:free",
        "microsoft/phi-3-mini-128k-instruct:free",
    ]

    def __init__(self) -> None:
        raw = os.environ.get("OPENROUTER_KEYS", "").strip()
        self.keys: list[str] = [k.strip() for k in raw.split(",") if k.strip()]
        self._cycle = itertools.cycle(self.keys) if self.keys else None
        self._dead: dict[str, float] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.keys)

    def _next_key(self) -> str | None:
        if not self._cycle:
            return None
        for _ in range(len(self.keys)):
            k = next(self._cycle)
            dead_until = self._dead.get(k, 0)
            if dead_until < time.time():
                return k
        return None

    def _mark_dead(self, key: str, seconds: int = 60) -> None:
        self._dead[key] = time.time() + seconds

    async def chat(self, prompt: str, timeout: float = 10.0) -> dict:
        """Send an Arabic fraud-analysis prompt; expect strict JSON reply."""
        if not self.enabled:
            return {"ok": False, "error": "no_keys", "model": "disabled"}

        for model in [self.PRIMARY_MODEL, *self.FALLBACK_MODELS]:
            key = self._next_key()
            if not key:
                continue
            try:
                async with httpx.AsyncClient(timeout=timeout) as cli:
                    r = await cli.post(
                        self.ENDPOINT,
                        headers={
                            "Authorization": f"Bearer {key}",
                            "HTTP-Referer": "https://aegis-security.io",
                        },
                        json={
                            "model": model,
                            "messages": [
                                {
                                    "role": "system",
                                    "content": "أنت محلل احتيال مالي. أجب بـ JSON فقط، بدون أي نص إضافي.",
                                },
                                {"role": "user", "content": prompt},
                            ],
                            "response_format": {"type": "json_object"},
                            "temperature": 0.2,
                            "max_tokens": 400,
                        },
                    )
                if r.status_code == 401 or r.status_code == 429:
                    self._mark_dead(key, 300)
                    continue
                r.raise_for_status()
                content = r.json()["choices"][0]["message"]["content"]
                return {"ok": True, "content": content, "model": model, "key_used": key[-6:]}
            except Exception as e:
                logger.warning("openrouter.retry", model=model, error=str(e))
                continue

        return {"ok": False, "error": "all_models_failed", "model": "fallback"}
