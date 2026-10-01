"""Central configuration.

Every tunable lives here and is read from the environment (or ``.env``) once.
Nothing else in the codebase calls ``os.getenv`` directly, which keeps behaviour
predictable and makes the pipeline easy to test with a hand-built ``Settings``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

try:  
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  
    pass


def _env_str(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return default if value is None or value.strip() == "" else value.strip()


def _env_int(name: str, default: int, *, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: List[str]) -> List[str]:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]




DEFAULT_RESTRICTED_COLUMN_PATTERN = (
    r"(^|_)(password|passwd|pwd|passhash|secret|api_?key|(access|refresh|auth|session)_?token|"
    r"token|private_?key|ssn|social_security(_number)?|credit_?card|card_?number|cvv|cvc|iban)($|_)"
    r"|password_?hash|hashed_?password"
)


@dataclass
class Settings:
    
    groq_api_key: str = ""
    model_chain: List[str] = field(
        default_factory=lambda: ["llama-3.3-70b-versatile", "qwen/qwen3-32b", "llama-3.1-8b-instant"]
    )
    judge_model_chain: List[str] = field(
        default_factory=lambda: ["qwen/qwen3-32b", "llama-3.3-70b-versatile"]
    )
    llm_timeout_seconds: float = 30.0
    
    result_rows_to_llm: int = 20
    
    llm_include_samples: bool = True

    
    max_repair_attempts: int = 2
    judge_enabled: bool = True
    judge_min_score: float = 0.7
    max_judge_revisions: int = 1
    max_question_chars: int = 1000

    
    max_rows: int = 1000
    max_export_rows: int = 50_000
    query_timeout_seconds: int = 20
    restricted_column_pattern: str = DEFAULT_RESTRICTED_COLUMN_PATTERN

    
    schema_cache_ttl_seconds: int = 600
    profile_budget_seconds: float = 8.0
    sample_values_max: int = 12

    
    cors_origins: List[str] = field(default_factory=list)
    cors_origin_regex: str = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"
    data_dir: str = "./data"
    max_upload_mb: int = 100
    debug: bool = False

    @property
    def restricted_column_re(self) -> "re.Pattern[str]":
        return re.compile(self.restricted_column_pattern, re.IGNORECASE)

    @property
    def llm_configured(self) -> bool:
        key = self.groq_api_key
        return bool(key) and not key.startswith("gsk_your_key")

    @classmethod
    def from_env(cls) -> "Settings":
        defaults = cls()
        return cls(
            groq_api_key=_env_str("GROQ_API_KEY"),
            model_chain=_env_list("MODEL_CHAIN", defaults.model_chain),
            judge_model_chain=_env_list("JUDGE_MODEL_CHAIN", defaults.judge_model_chain),
            llm_timeout_seconds=_env_float("LLM_TIMEOUT_SECONDS", defaults.llm_timeout_seconds),
            result_rows_to_llm=_env_int("RESULT_ROWS_TO_LLM", defaults.result_rows_to_llm),
            llm_include_samples=_env_bool("LLM_INCLUDE_SAMPLES", defaults.llm_include_samples),
            max_repair_attempts=_env_int(
                "MAX_REPAIR_ATTEMPTS",
                _env_int("MAX_CORRECTION_RETRIES", defaults.max_repair_attempts),
            ),
            judge_enabled=_env_bool("JUDGE_ENABLED", defaults.judge_enabled),
            judge_min_score=_env_float("JUDGE_MIN_SCORE", defaults.judge_min_score),
            max_judge_revisions=_env_int("MAX_JUDGE_REVISIONS", defaults.max_judge_revisions),
            max_question_chars=_env_int("MAX_QUESTION_CHARS", defaults.max_question_chars, minimum=50),
            max_rows=_env_int("MAX_ROWS", defaults.max_rows, minimum=1),
            max_export_rows=_env_int("MAX_EXPORT_ROWS", defaults.max_export_rows, minimum=1),
            query_timeout_seconds=_env_int("QUERY_TIMEOUT_SECONDS", defaults.query_timeout_seconds, minimum=1),
            restricted_column_pattern=_env_str("RESTRICTED_COLUMN_PATTERN", defaults.restricted_column_pattern),
            schema_cache_ttl_seconds=_env_int("SCHEMA_CACHE_TTL_SECONDS", defaults.schema_cache_ttl_seconds),
            profile_budget_seconds=_env_float("PROFILE_BUDGET_SECONDS", defaults.profile_budget_seconds),
            cors_origins=_env_list("CORS_ORIGINS", []),
            data_dir=_env_str("DATA_DIR", defaults.data_dir),
            max_upload_mb=_env_int("MAX_UPLOAD_MB", defaults.max_upload_mb, minimum=1),
            debug=_env_bool("DEBUG", False),
        )


settings = Settings.from_env()
