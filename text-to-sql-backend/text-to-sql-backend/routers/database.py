from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from services.database_service import db_service

router = APIRouter()

# Request Models
class DatabaseConnection(BaseModel):
    db_type: str = Field(..., description="Database type: postgresql, mysql, or sqlite")
    host: Optional[str] = Field(None, description="Database host")
    port: Optional[int] = Field(None, description="Database port")
    database: str = Field(..., description="Database name")
    username: Optional[str] = Field(None, description="Database username")
    password: Optional[str] = Field(None, description="Database password")
    file_path: Optional[str] = Field(None, description="SQLite file path")

@router.post("/connect", status_code=status.HTTP_201_CREATED)
async def connect_database(connection: DatabaseConnection):
    """Connect to a database"""
    try:
        result = db_service.create_connection(
            db_type=connection.db_type,
            database=connection.database,
            host=connection.host,
            port=connection.port,
            username=connection.username,
            password=connection.password,
            file_path=connection.file_path
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.get("/connections")
async def list_connections():
    """List all active database connections"""
    return {"connections": db_service.list_connections()}

@router.get("/connections/{connection_id}")
async def get_connection(connection_id: str):
    """Get connection information"""
    try:
        return db_service.get_connection_info(connection_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

@router.delete("/connections/{connection_id}")
async def disconnect_database(connection_id: str):
    """Disconnect from a database"""
    try:
        result = db_service.close_connection(connection_id)
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

@router.get("/connections/{connection_id}/tables")
async def list_tables(connection_id: str):
    """List all tables in the database"""
    try:
        tables = db_service.list_tables(connection_id)
        return {"tables": tables, "count": len(tables)}
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

@router.get("/connections/{connection_id}/tables/{table_name}/schema")
async def get_table_schema(connection_id: str, table_name: str):
    """Get schema for a specific table"""
    try:
        schema = db_service.get_table_schema(connection_id, table_name)
        return schema
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

@router.get("/connections/{connection_id}/tables/{table_name}/data")
async def get_table_data(connection_id: str, table_name: str, limit: Optional[int] = 100):
    """Get data from a specific table"""
    try:
        result = db_service.get_table_data(connection_id, table_name, limit)
        return result
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

@router.get("/connections/{connection_id}/schema")
async def get_database_schema(connection_id: str):
    """Get complete database schema"""
    try:
        schema = db_service.get_database_schema(connection_id)
        return schema
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
