from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional
from services.database_service import db_service
from services.llm_service import llm_service

router = APIRouter()

# Request Models
class QueryRequest(BaseModel):
    connection_id: str = Field(..., description="Connection ID")
    question: str = Field(..., description="Natural language query")

class DirectSQLRequest(BaseModel):
    connection_id: str = Field(..., description="Connection ID")
    sql_query: str = Field(..., description="SQL query to execute")

@router.post("/natural-language")
async def query_natural_language(request: QueryRequest):
    """Convert natural language to SQL and execute"""
    try:
        # Get database schema
        schema = db_service.get_database_schema(request.connection_id)
        
        # Generate SQL from natural language
        sql_result = llm_service.generate_sql(request.question, schema)
        
        if not sql_result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate SQL: {sql_result.get('error', 'Unknown error')}"
            )
        
        # Execute the generated SQL
        query_result = db_service.execute_query(request.connection_id, sql_result["sql_query"])
        
        return {
            "question": request.question,
            "generated_sql": sql_result["sql_query"],
            "query_result": query_result
        }
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post("/sql")
async def execute_sql(request: DirectSQLRequest):
    """Execute a direct SQL query"""
    try:
        result = db_service.execute_query(request.connection_id, request.sql_query)
        return {
            "sql_query": request.sql_query,
            "result": result
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/model-status")
async def check_model_status():
    """Check if LLM model is available"""
    try:
        status = llm_service.check_model_availability()
        return status
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
