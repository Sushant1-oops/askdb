from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional
from services.database_service import db_service
from services.llm_service import llm_service
import logging
import time

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_CORRECTION_RETRIES = 3  # Increased from 2 for better accuracy

# Request Models
class QueryRequest(BaseModel):
    connection_id: str = Field(..., description="Connection ID")
    question: str = Field(..., description="Natural language query")

class DirectSQLRequest(BaseModel):
    connection_id: str = Field(..., description="Connection ID")
    sql_query: str = Field(..., description="SQL query to execute")


@router.post("/natural-language")
async def query_natural_language(request: QueryRequest):
    """Convert natural language to SQL and execute with self-correction.

    Pipeline:
      1. Fetch rich schema (DDL, sample data, foreign keys)
      2. Generate SQL via Groq LLM (dialect-aware)
      3. Execute the SQL
      4. If execution fails, self-correct up to MAX_CORRECTION_RETRIES times
      5. Return results with metadata
    """
    start_time = time.time()

    try:
        # Validate connection exists and is alive
        if not db_service.test_connection(request.connection_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Database connection is no longer active. Please reconnect."
            )

        # Get rich schema (DDL + sample data + foreign keys)
        schema = db_service.get_rich_schema(request.connection_id)
        db_type = db_service.get_db_type(request.connection_id)

        logger.info(
            f"NL Query: question='{request.question}', "
            f"db_type={db_type}, tables={list(schema.get('tables', {}).keys())}"
        )

        # Generate SQL from natural language
        sql_result = llm_service.generate_sql(request.question, schema, db_type)

        if not sql_result["success"]:
            return {
                "question": request.question,
                "generated_sql": None,
                "query_result": {
                    "success": False,
                    "error": f"SQL generation failed: {sql_result.get('error', 'Unknown error')}",
                },
                "model_used": sql_result.get("model_used", "unknown"),
                "retries": 0,
                "execution_time": round(time.time() - start_time, 2),
            }

        generated_sql = sql_result["sql_query"]
        model_used = sql_result.get("model_used", "unknown")
        retries = 0

        # Execute and self-correct loop
        query_result = db_service.execute_query(request.connection_id, generated_sql)

        while not query_result["success"] and retries < MAX_CORRECTION_RETRIES:
            retries += 1
            error_msg = query_result.get("error", "Unknown execution error")
            logger.info(
                f"Self-correction attempt {retries}/{MAX_CORRECTION_RETRIES} "
                f"for question='{request.question}' error='{error_msg}'"
            )

            fix_result = llm_service.fix_sql(
                original_question=request.question,
                bad_sql=generated_sql,
                error_msg=error_msg,
                schema=schema,
                db_type=db_type,
            )

            if not fix_result["success"]:
                logger.warning(f"Self-correction attempt {retries} failed: {fix_result.get('error')}")
                break

            generated_sql = fix_result["sql_query"]
            model_used = fix_result.get("model_used", model_used)
            query_result = db_service.execute_query(request.connection_id, generated_sql)

        execution_time = round(time.time() - start_time, 2)

        return {
            "question": request.question,
            "generated_sql": generated_sql,
            "query_result": query_result,
            "model_used": model_used,
            "retries": retries,
            "execution_time": execution_time,
            "db_type": db_type,
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error in natural-language query")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query processing failed: {str(e)}"
        )


@router.post("/sql")
async def execute_sql(request: DirectSQLRequest):
    """Execute a direct SQL query."""
    start_time = time.time()
    try:
        # Validate connection
        if not db_service.test_connection(request.connection_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Database connection is no longer active. Please reconnect."
            )

        result = db_service.execute_query(request.connection_id, request.sql_query)
        return {
            "sql_query": request.sql_query,
            "result": result,
            "execution_time": round(time.time() - start_time, 2),
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query execution failed: {str(e)}"
        )


@router.get("/model-status")
async def check_model_status():
    """Check if LLM model is available."""
    try:
        model_status = llm_service.check_model_availability()
        return model_status
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
