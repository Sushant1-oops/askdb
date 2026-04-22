from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Optional
from services.database_service import db_service
from services.export_service import export_service
import os

router = APIRouter()

# Request Models
class ExportRequest(BaseModel):
    connection_id: str = Field(..., description="Connection ID")
    table_name: str = Field(..., description="Table name to export")
    format: str = Field(..., description="Export format: csv, excel, or pdf")
    limit: Optional[int] = Field(None, description="Limit number of rows to export")

class QueryExportRequest(BaseModel):
    connection_id: str = Field(..., description="Connection ID")
    sql_query: str = Field(..., description="SQL query to execute and export")
    format: str = Field(..., description="Export format: csv, excel, or pdf")
    filename: Optional[str] = Field(None, description="Custom filename")

@router.post("/table")
async def export_table(request: ExportRequest):
    """Export table data to file"""
    try:
        # Get table data
        result = db_service.get_table_data(
            request.connection_id, 
            request.table_name, 
            request.limit
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("error", "Failed to fetch table data")
            )
        
        # Export to file
        filepath = export_service.export_query_results(
            result["rows"],
            request.format,
            request.table_name
        )
        
        # Return file
        return FileResponse(
            filepath,
            media_type=_get_media_type(request.format),
            filename=os.path.basename(filepath)
        )
    
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

@router.post("/query")
async def export_query(request: QueryExportRequest):
    """Export query results to file"""
    try:
        # Execute query
        result = db_service.execute_query(request.connection_id, request.sql_query)
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("error", "Failed to execute query")
            )
        
        if not result.get("rows"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Query returned no data to export"
            )
        
        # Export to file
        filename = request.filename or "query_results"
        filepath = export_service.export_query_results(
            result["rows"],
            request.format,
            filename
        )
        
        # Return file
        return FileResponse(
            filepath,
            media_type=_get_media_type(request.format),
            filename=os.path.basename(filepath)
        )
    
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

def _get_media_type(format: str) -> str:
    """Get media type for file format"""
    media_types = {
        "csv": "text/csv",
        "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pdf": "application/pdf"
    }
    return media_types.get(format.lower(), "application/octet-stream")
