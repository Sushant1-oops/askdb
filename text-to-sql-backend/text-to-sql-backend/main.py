from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import uvicorn
from datetime import datetime
import uuid

app = FastAPI(
    title="Text-to-SQL API",
    description="Natural Language to SQL Query System with Multi-Database Support",
    version="1.0.0"
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage for database connections (use Redis in production)
active_connections = {}

# Models
class DatabaseConnection(BaseModel):
    db_type: str = Field(..., description="Database type: postgresql, mysql, or sqlite")
    host: Optional[str] = Field(None, description="Database host")
    port: Optional[int] = Field(None, description="Database port")
    database: str = Field(..., description="Database name")
    username: Optional[str] = Field(None, description="Database username")
    password: Optional[str] = Field(None, description="Database password")
    file_path: Optional[str] = Field(None, description="SQLite file path")

class QueryRequest(BaseModel):
    connection_id: str = Field(..., description="Connection ID")
    question: str = Field(..., description="Natural language query")

class DirectSQLRequest(BaseModel):
    connection_id: str = Field(..., description="Connection ID")
    sql_query: str = Field(..., description="SQL query to execute")

class ExportRequest(BaseModel):
    connection_id: str = Field(..., description="Connection ID")
    table_name: str = Field(..., description="Table name to export")
    format: str = Field(..., description="Export format: csv, excel, or pdf")

# Routes
from routers import database, query, export

app.include_router(database.router, prefix="/api/database", tags=["Database"])
app.include_router(query.router, prefix="/api/query", tags=["Query"])
app.include_router(export.router, prefix="/api/export", tags=["Export"])

@app.get("/")
async def root():
    return {
        "message": "Text-to-SQL API",
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
