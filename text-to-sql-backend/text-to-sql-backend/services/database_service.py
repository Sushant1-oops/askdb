from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from typing import Dict, List, Any, Optional
import uuid
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class DatabaseService:
    """Service for managing database connections and operations.

    Supports SQLite, PostgreSQL, and MySQL with proper identifier quoting
    and connection health checking.
    """

    def __init__(self):
        self.connections: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Identifier quoting — dialect-aware
    # ------------------------------------------------------------------

    @staticmethod
    def _quote_identifier(name: str, db_type: str = "sqlite") -> str:
        """Quote a table or column name for safe use in SQL.

        SQLite & PostgreSQL use double quotes, MySQL uses backticks.
        """
        if db_type == "mysql":
            return f"`{name}`"
        return f'"{name}"'

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def create_connection(self, db_type: str, database: str,
                         host: Optional[str] = None, port: Optional[int] = None,
                         username: Optional[str] = None, password: Optional[str] = None,
                         file_path: Optional[str] = None) -> Dict[str, Any]:
        """Create a new database connection."""
        try:
            # Generate connection ID
            connection_id = str(uuid.uuid4())

            # Build connection string
            if db_type == "sqlite":
                conn_string = f"sqlite:///{file_path if file_path else database}"
            elif db_type == "postgresql":
                conn_string = f"postgresql://{username}:{password}@{host}:{port or 5432}/{database}"
                if host and "neon.tech" in host:
                    conn_string += "?sslmode=require"
            elif db_type == "mysql":
                conn_string = f"mysql+pymysql://{username}:{password}@{host}:{port or 3306}/{database}"
            else:
                raise ValueError(f"Unsupported database type: {db_type}")

            # Create engine with connection pooling
            engine = create_engine(
                conn_string,
                pool_pre_ping=True,
                pool_recycle=3600,
                echo=False,
            )

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
                "port": port,
            }

            return {
                "connection_id": connection_id,
                "db_type": db_type,
                "database": database,
                "status": "connected",
            }

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            raise Exception(f"Failed to connect to database: {str(e)}")

    def get_engine(self, connection_id: str) -> Engine:
        """Get SQLAlchemy engine for a connection."""
        if connection_id not in self.connections:
            raise ValueError(f"Connection {connection_id} not found")
        return self.connections[connection_id]["engine"]

    def get_db_type(self, connection_id: str) -> str:
        """Get the database type for a connection."""
        if connection_id not in self.connections:
            raise ValueError(f"Connection {connection_id} not found")
        return self.connections[connection_id]["db_type"]

    def get_connection_info(self, connection_id: str) -> Dict[str, Any]:
        """Get connection information."""
        if connection_id not in self.connections:
            raise ValueError(f"Connection {connection_id} not found")

        conn_info = self.connections[connection_id].copy()
        conn_info.pop("engine", None)  # Remove engine object
        return conn_info

    def test_connection(self, connection_id: str) -> bool:
        """Test if a connection is still alive."""
        try:
            engine = self.get_engine(connection_id)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def list_tables(self, connection_id: str) -> List[str]:
        """List all tables in the database."""
        engine = self.get_engine(connection_id)
        inspector = inspect(engine)
        return inspector.get_table_names()

    def get_table_schema(self, connection_id: str, table_name: str) -> Dict[str, Any]:
        """Get detailed schema for a table."""
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
            "indexes": indexes,
        }

    def get_database_schema(self, connection_id: str) -> Dict[str, Any]:
        """Get complete database schema."""
        engine = self.get_engine(connection_id)
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        schema = {
            "database": self.connections[connection_id]["database"],
            "tables": {},
        }

        for table in tables:
            columns = inspector.get_columns(table)
            pk_constraint = inspector.get_pk_constraint(table)
            pk_cols = set(pk_constraint.get("constrained_columns", []))

            schema["tables"][table] = {
                "columns": [
                    {
                        "name": col["name"],
                        "type": str(col["type"]),
                        "nullable": col.get("nullable", True),
                        "default": col.get("default"),
                        "primary_key": col["name"] in pk_cols,
                    }
                    for col in columns
                ]
            }

        return schema

    # ------------------------------------------------------------------
    # Rich schema — includes DDL, foreign keys, sample data, row counts
    # ------------------------------------------------------------------

    def get_rich_schema(self, connection_id: str) -> Dict[str, Any]:
        """Get a rich schema payload optimised for LLM prompt injection.

        For each table the dict contains:
          - columns   (list of dicts)
          - ddl       (CREATE TABLE statement as a string)
          - foreign_keys (list of FK dicts)
          - sample_data  (first 3 rows as list of dicts)
          - row_count    (int)
        """
        engine = self.get_engine(connection_id)
        db_type = self.get_db_type(connection_id)
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        schema: Dict[str, Any] = {
            "database": self.connections[connection_id]["database"],
            "db_type": db_type,
            "tables": {},
        }

        for table in tables:
            columns = inspector.get_columns(table)
            foreign_keys = inspector.get_foreign_keys(table)
            pk_constraint = inspector.get_pk_constraint(table)
            pk_cols = set(pk_constraint.get("constrained_columns", []))

            # Build column info list
            col_info = []
            for c in columns:
                col_info.append({
                    "name": c["name"],
                    "type": str(c["type"]),
                    "nullable": c.get("nullable", True),
                    "default": c.get("default"),
                    "primary_key": c["name"] in pk_cols,
                })

            # Build DDL
            ddl = self._build_create_table_ddl(table, col_info, foreign_keys)

            # Sample data (3 rows)
            sample_data = self._fetch_sample_rows(engine, table, db_type, limit=3)

            # Row count
            row_count = self._fetch_row_count(engine, table, db_type)

            schema["tables"][table] = {
                "columns": col_info,
                "ddl": ddl,
                "foreign_keys": [
                    {
                        "constrained_columns": fk.get("constrained_columns", []),
                        "referred_table": fk.get("referred_table", ""),
                        "referred_columns": fk.get("referred_columns", []),
                    }
                    for fk in foreign_keys
                ],
                "sample_data": sample_data,
                "row_count": row_count,
            }

        return schema

    @staticmethod
    def _build_create_table_ddl(table_name: str,
                                 columns: List[Dict[str, Any]],
                                 foreign_keys: List[Dict]) -> str:
        """Synthesise a CREATE TABLE DDL statement from inspector metadata."""
        col_lines = []
        for c in columns:
            line = f"  {c['name']} {c['type']}"
            if c.get("primary_key"):
                line += " PRIMARY KEY"
            if not c.get("nullable", True):
                line += " NOT NULL"
            if c.get("default") is not None:
                line += f" DEFAULT {c['default']}"
            col_lines.append(line)

        for fk in foreign_keys:
            local = ", ".join(fk.get("constrained_columns", []))
            ref_table = fk.get("referred_table", "")
            ref_cols = ", ".join(fk.get("referred_columns", []))
            col_lines.append(f"  FOREIGN KEY ({local}) REFERENCES {ref_table}({ref_cols})")

        return f"CREATE TABLE {table_name} (\n" + ",\n".join(col_lines) + "\n);"

    @staticmethod
    def _fetch_sample_rows(engine: Engine, table: str,
                           db_type: str = "sqlite", limit: int = 3) -> List[Dict]:
        """Return a few sample rows as list-of-dicts with safe identifier quoting."""
        try:
            # Quote table name based on dialect
            if db_type == "mysql":
                quoted_table = f"`{table}`"
            else:
                quoted_table = f'"{table}"'

            with engine.connect() as conn:
                result = conn.execute(text(f"SELECT * FROM {quoted_table} LIMIT {limit}"))
                cols = list(result.keys())
                rows = []
                for row in result.fetchall():
                    row_dict = {}
                    for i, col in enumerate(cols):
                        val = row[i]
                        # Convert non-serializable types to string
                        if isinstance(val, (bytes, bytearray)):
                            val = val.hex()
                        elif isinstance(val, datetime):
                            val = val.isoformat()
                        row_dict[col] = val
                    rows.append(row_dict)
                return rows
        except Exception as e:
            logger.warning(f"Could not fetch sample rows for {table}: {e}")
            return []

    @staticmethod
    def _fetch_row_count(engine: Engine, table: str,
                         db_type: str = "sqlite") -> Optional[int]:
        """Return the total row count for a table."""
        try:
            if db_type == "mysql":
                quoted_table = f"`{table}`"
            else:
                quoted_table = f'"{table}"'

            with engine.connect() as conn:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {quoted_table}"))
                return result.scalar()
        except Exception as e:
            logger.warning(f"Could not fetch row count for {table}: {e}")
            return None

    # ------------------------------------------------------------------
    # Query execution
    # ------------------------------------------------------------------

    def execute_query(self, connection_id: str, query: str) -> Dict[str, Any]:
        """Execute SQL query and return results.

        Handles SELECT (returns rows), DML (returns affected count),
        and catches all errors gracefully.
        """
        engine = self.get_engine(connection_id)

        # Strip trailing semicolons and whitespace — SQLAlchemy doesn't need them
        clean_query = query.strip().rstrip(";").strip()
        if not clean_query:
            return {"success": False, "error": "Empty query"}

        try:
            with engine.connect() as conn:
                result = conn.execute(text(clean_query))

                # Check if query returns results
                if result.returns_rows:
                    columns = list(result.keys())
                    raw_rows = result.fetchall()
                    rows = []
                    for row in raw_rows:
                        row_dict = {}
                        for i, col in enumerate(columns):
                            val = row[i]
                            # Handle non-JSON-serializable types
                            if isinstance(val, (bytes, bytearray)):
                                val = val.hex()
                            elif isinstance(val, datetime):
                                val = val.isoformat()
                            elif isinstance(val, set):
                                val = list(val)
                            row_dict[col] = val
                        rows.append(row_dict)

                    return {
                        "success": True,
                        "columns": columns,
                        "rows": rows,
                        "row_count": len(rows),
                    }
                else:
                    # For INSERT, UPDATE, DELETE
                    conn.commit()
                    return {
                        "success": True,
                        "message": "Query executed successfully",
                        "rows_affected": result.rowcount,
                    }

        except Exception as e:
            error_msg = str(e)
            # Extract the core error message from SQLAlchemy wrapper
            if "OperationalError" in error_msg:
                match = re.search(r"\) (.+)", error_msg)
                if match:
                    error_msg = match.group(1)
            logger.warning(f"Query execution failed: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
            }

    def get_table_data(self, connection_id: str, table_name: str,
                       limit: Optional[int] = 100) -> Dict[str, Any]:
        """Get data from a table with safe identifier quoting."""
        db_type = self.get_db_type(connection_id)
        quoted_table = self._quote_identifier(table_name, db_type)
        query = f"SELECT * FROM {quoted_table}"
        if limit:
            query += f" LIMIT {limit}"

        return self.execute_query(connection_id, query)

    def close_connection(self, connection_id: str) -> Dict[str, str]:
        """Close a database connection."""
        if connection_id in self.connections:
            engine = self.connections[connection_id]["engine"]
            engine.dispose()
            del self.connections[connection_id]
            return {"status": "disconnected", "connection_id": connection_id}

        raise ValueError(f"Connection {connection_id} not found")

    def list_connections(self) -> List[Dict[str, Any]]:
        """List all active connections."""
        return [
            {
                "connection_id": conn_id,
                "db_type": conn_data["db_type"],
                "database": conn_data["database"],
                "created_at": conn_data["created_at"],
            }
            for conn_id, conn_data in self.connections.items()
        ]


# Need re for error parsing in execute_query
import re

# Singleton instance
db_service = DatabaseService()
