from sqlalchemy import create_engine, inspect, text, MetaData
from sqlalchemy.engine import Engine
from typing import Dict, List, Any, Optional
import uuid
from datetime import datetime

class DatabaseService:
    """Service for managing database connections and operations"""
    
    def __init__(self):
        self.connections: Dict[str, Dict[str, Any]] = {}
    
    def create_connection(self, db_type: str, database: str, 
                         host: Optional[str] = None, port: Optional[int] = None,
                         username: Optional[str] = None, password: Optional[str] = None,
                         file_path: Optional[str] = None) -> Dict[str, Any]:
        """Create a new database connection"""
        try:
            # Generate connection ID
            connection_id = str(uuid.uuid4())
            
            # Build connection string
            if db_type == "sqlite":
                conn_string = f"sqlite:///{file_path if file_path else database}"
            elif db_type == "postgresql":
                conn_string = f"postgresql://{username}:{password}@{host}:{port or 5432}/{database}"
            elif db_type == "mysql":
                conn_string = f"mysql+pymysql://{username}:{password}@{host}:{port or 3306}/{database}"
            else:
                raise ValueError(f"Unsupported database type: {db_type}")
            
            # Create engine
            engine = create_engine(conn_string, pool_pre_ping=True)
            
            # Test connection
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            # Store connection
            self.connections[connection_id] = {
                "id": connection_id,
                "db_type": db_type,
                "database": database,
                "engine": engine,
                "created_at": datetime.utcnow().isoformat(),
                "host": host,
                "port": port
            }
            
            return {
                "connection_id": connection_id,
                "db_type": db_type,
                "database": database,
                "status": "connected"
            }
        
        except Exception as e:
            raise Exception(f"Failed to connect to database: {str(e)}")
    
    def get_engine(self, connection_id: str) -> Engine:
        """Get SQLAlchemy engine for a connection"""
        if connection_id not in self.connections:
            raise ValueError(f"Connection {connection_id} not found")
        return self.connections[connection_id]["engine"]
    
    def get_connection_info(self, connection_id: str) -> Dict[str, Any]:
        """Get connection information"""
        if connection_id not in self.connections:
            raise ValueError(f"Connection {connection_id} not found")
        
        conn_info = self.connections[connection_id].copy()
        conn_info.pop("engine", None)  # Remove engine object
        return conn_info
    
    def list_tables(self, connection_id: str) -> List[str]:
        """List all tables in the database"""
        engine = self.get_engine(connection_id)
        inspector = inspect(engine)
        return inspector.get_table_names()
    
    def get_table_schema(self, connection_id: str, table_name: str) -> Dict[str, Any]:
        """Get detailed schema for a table"""
        engine = self.get_engine(connection_id)
        inspector = inspect(engine)
        
        columns = inspector.get_columns(table_name)
        primary_keys = inspector.get_pk_constraint(table_name)
        foreign_keys = inspector.get_foreign_keys(table_name)
        indexes = inspector.get_indexes(table_name)
        
        return {
            "table_name": table_name,
            "columns": columns,
            "primary_keys": primary_keys,
            "foreign_keys": foreign_keys,
            "indexes": indexes
        }
    
    def get_database_schema(self, connection_id: str) -> Dict[str, Any]:
        """Get complete database schema"""
        engine = self.get_engine(connection_id)
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        schema = {
            "database": self.connections[connection_id]["database"],
            "tables": {}
        }
        
        for table in tables:
            columns = inspector.get_columns(table)
            schema["tables"][table] = {
                "columns": [
                    {
                        "name": col["name"],
                        "type": str(col["type"]),
                        "nullable": col.get("nullable", True),
                        "default": col.get("default"),
                        "primary_key": col.get("primary_key", False)
                    }
                    for col in columns
                ]
            }
        
        return schema
    
    def execute_query(self, connection_id: str, query: str) -> Dict[str, Any]:
        """Execute SQL query and return results"""
        engine = self.get_engine(connection_id)
        
        try:
            with engine.connect() as conn:
                result = conn.execute(text(query))
                
                # Check if query returns results
                if result.returns_rows:
                    columns = list(result.keys())
                    rows = [dict(zip(columns, row)) for row in result.fetchall()]
                    
                    return {
                        "success": True,
                        "columns": columns,
                        "rows": rows,
                        "row_count": len(rows)
                    }
                else:
                    # For INSERT, UPDATE, DELETE
                    conn.commit()
                    return {
                        "success": True,
                        "message": "Query executed successfully",
                        "rows_affected": result.rowcount
                    }
        
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_table_data(self, connection_id: str, table_name: str, 
                       limit: Optional[int] = 100) -> Dict[str, Any]:
        """Get data from a table"""
        query = f"SELECT * FROM {table_name}"
        if limit:
            query += f" LIMIT {limit}"
        
        return self.execute_query(connection_id, query)
    
    def close_connection(self, connection_id: str) -> Dict[str, str]:
        """Close a database connection"""
        if connection_id in self.connections:
            engine = self.connections[connection_id]["engine"]
            engine.dispose()
            del self.connections[connection_id]
            return {"status": "disconnected", "connection_id": connection_id}
        
        raise ValueError(f"Connection {connection_id} not found")
    
    def list_connections(self) -> List[Dict[str, Any]]:
        """List all active connections"""
        return [
            {
                "connection_id": conn_id,
                "db_type": conn_data["db_type"],
                "database": conn_data["database"],
                "created_at": conn_data["created_at"]
            }
            for conn_id, conn_data in self.connections.items()
        ]

# Singleton instance
db_service = DatabaseService()
