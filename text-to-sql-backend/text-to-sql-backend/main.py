from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import uvicorn
from datetime import datetime
import logging

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="QueryForge — Text-to-SQL API",
    description="Natural Language to SQL Query System with Multi-Database Support. "
                "Powered by Groq Cloud AI with Llama 3.3 70B.",
    version="2.0.0",
)

# ---------------------------------------------------------------------------
# CORS — allow common dev ports
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:4173",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Global exception handler — prevents raw 500 errors
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled error on {request.method} {request.url.path}")
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"Internal server error: {str(exc)}",
            "path": str(request.url.path),
            "timestamp": datetime.utcnow().isoformat(),
        },
    )

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
from routers import database, query, export

app.include_router(database.router, prefix="/api/database", tags=["Database"])
app.include_router(query.router, prefix="/api/query", tags=["Query"])
app.include_router(export.router, prefix="/api/export", tags=["Export"])

@app.get("/")
async def root():
    return {
        "message": "QueryForge — Text-to-SQL API",
        "version": "2.0.0",
        "engine": "Groq Cloud (Llama 3.3 70B)",
        "docs": "/docs",
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
