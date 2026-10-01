"""Thin, testable wrapper around the Groq chat-completions API.

Responsibilities: lazy client creation (the app boots without a key), an ordered
model fallback chain, JSON-mode with graceful degradation, and normalisation of
reasoning-model output (``<think>`` blocks). Everything above this layer talks to
the ``LLM`` protocol, so tests can inject a scripted fake.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Sequence

from services.errors import LLMUnavailableError

logger = logging.getLogger(__name__)

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE = re.compile(r"```(?:json|sql)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


@dataclass
class LLMResponse:
    text: str
    model: str


class LLM(Protocol):
    @property
    def configured(self) -> bool: ...

    def complete(
        self,
        messages: List[Dict[str, str]],
        *,
        models: Optional[Sequence[str]] = None,
        temperature: float = 0.0,
        max_tokens: int = 1500,
        json_mode: bool = False,
    ) -> LLMResponse: ...


def strip_reasoning(text: str) -> str:
    """Remove ``<think>`` blocks emitted by reasoning models."""
    text = _THINK.sub("", text)
    
    if "<think>" in text.lower():
        text = re.split(r"<think>", text, flags=re.IGNORECASE)[0]
    return text.strip()


def parse_json_object(raw: str) -> Optional[Dict[str, Any]]:
    """Best-effort extraction of a JSON object from model output."""
    text = strip_reasoning(raw)
    if not text:
        return None
    candidates: List[str] = [text]
    fenced = _FENCE.search(text)
    if fenced:
        candidates.insert(0, fenced.group(1))
    start = text.find("{")
    if start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(text[start : i + 1])
                    break
    for cand in candidates:
        try:
            obj = json.loads(cand)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(obj, dict):
            return obj
    return None


class LLMClient:
    def __init__(self, api_key: str, models: Sequence[str], timeout: float = 30.0) -> None:
        self.api_key = api_key
        self.models = list(models)
        self.timeout = timeout
        self._client: Any = None

    @property
    def configured(self) -> bool:
        return bool(self.api_key) and not self.api_key.startswith("gsk_your_key")

    def _get_client(self) -> Any:
        if not self.configured:
            raise LLMUnavailableError(
                "The AI engine is not configured. Set GROQ_API_KEY in the backend .env file."
            )
        if self._client is None:
            try:
                from groq import Groq
            except ImportError as exc:  
                raise LLMUnavailableError("The 'groq' package is not installed (pip install groq).") from exc
            self._client = Groq(api_key=self.api_key, timeout=self.timeout, max_retries=1)
        return self._client

    def complete(
        self,
        messages: List[Dict[str, str]],
        *,
        models: Optional[Sequence[str]] = None,
        temperature: float = 0.0,
        max_tokens: int = 1500,
        json_mode: bool = False,
    ) -> LLMResponse:
        client = self._get_client()
        chain = list(models) if models else self.models
        errors: List[str] = []

        for model in chain:
            for use_json in ([True, False] if json_mode else [False]):
                try:
                    kwargs: Dict[str, Any] = dict(
                        model=model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=False,
                    )
                    if use_json:
                        kwargs["response_format"] = {"type": "json_object"}
                    response = client.chat.completions.create(**kwargs)
                    text = strip_reasoning(response.choices[0].message.content or "")
                    if text:
                        return LLMResponse(text=text, model=model)
                    errors.append(f"{model}: empty response")
                    break
                except Exception as exc:  
                    status = getattr(exc, "status_code", None)
                    message = str(exc)[:200]
                    logger.warning("LLM call failed model=%s json=%s status=%s: %s", model, use_json, status, message)
                    
                    if use_json and status == 400:
                        continue
                    errors.append(f"{model}: {status or type(exc).__name__}")
                    break

        raise LLMUnavailableError(
            "The AI provider could not complete the request (" + "; ".join(errors[-3:]) + "). "
            "Check the API key, model names and rate limits."
        )

    def available_models(self) -> List[str]:
        client = self._get_client()
        listing = client.models.list()
        return sorted(m.id for m in (listing.data or []))
