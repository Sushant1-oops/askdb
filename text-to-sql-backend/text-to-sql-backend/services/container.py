"""Composition root: builds the singletons the routers share."""

from __future__ import annotations

from config import settings
from services.database_service import DatabaseService
from services.executor import GuardedExecutor
from services.export_service import ExportService
from services.history import HistoryStore
from services.insight import Summarizer
from services.judge import Judge
from services.llm_client import LLMClient
from services.pipeline import QueryPipeline
from services.sql_generator import SQLGenerator

db_service = DatabaseService(settings)
history_store = HistoryStore()
llm_client = LLMClient(settings.groq_api_key, settings.model_chain, settings.llm_timeout_seconds)
executor = GuardedExecutor(db_service, settings)
generator = SQLGenerator(llm_client, settings.model_chain, include_samples=settings.llm_include_samples)
judge = Judge(llm_client, settings.judge_model_chain, rows_to_llm=settings.result_rows_to_llm)
summarizer = Summarizer(llm_client, settings.model_chain, rows_to_llm=settings.result_rows_to_llm)
pipeline = QueryPipeline(
    db=db_service, executor=executor, generator=generator, judge=judge, summarizer=summarizer,
    history=history_store, llm=llm_client, settings=settings,
)
export_service = ExportService()
