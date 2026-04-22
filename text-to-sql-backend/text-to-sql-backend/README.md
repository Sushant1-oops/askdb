# Text-to-SQL Backend API

A powerful FastAPI backend that converts natural language questions to SQL queries using Ollama LLMs.

## Features

- 🔌 **Multi-Database Support**: PostgreSQL, MySQL, SQLite
- 🤖 **AI-Powered Query Generation**: Natural language to SQL using Ollama
- 📊 **Schema Exploration**: View database tables, columns, and relationships
- ⚡ **Fast Query Execution**: Optimized database operations
- 📥 **Multiple Export Formats**: CSV, Excel, PDF
- 🔒 **Secure Connections**: Proper connection pooling and error handling

## Prerequisites

- Python 3.9+
- Ollama installed and running
- SQLCoder model (or compatible SQL model)

## Installation

1. **Install Ollama** (if not already installed):
   ```bash
   # macOS/Linux
   curl -fsSL https://ollama.com/install.sh | sh
   
   # Windows: Download from https://ollama.com/download
   ```

2. **Pull the SQLCoder model**:
   ```bash
   ollama pull sqlcoder
   
   # Alternative models:
   # ollama pull codellama:7b
   # ollama pull deepseek-coder:6.7b
   ```

3. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment** (optional):
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

## Usage

### Start the Server

```bash
python main.py
```

Or with uvicorn directly:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at:
- API: http://localhost:8000
- Docs: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### API Endpoints

#### Database Connection

**Connect to Database**
```http
POST /api/database/connect
Content-Type: application/json

{
  "db_type": "postgresql",
  "host": "localhost",
  "port": 5432,
  "database": "mydb",
  "username": "user",
  "password": "password"
}
```

**List Connections**
```http
GET /api/database/connections
```

**Get Tables**
```http
GET /api/database/connections/{connection_id}/tables
```

**Get Database Schema**
```http
GET /api/database/connections/{connection_id}/schema
```

#### Query

**Natural Language Query**
```http
POST /api/query/natural-language
Content-Type: application/json

{
  "connection_id": "uuid-here",
  "question": "Show me all customers who made purchases last month"
}
```

**Direct SQL Query**
```http
POST /api/query/sql
Content-Type: application/json

{
  "connection_id": "uuid-here",
  "sql_query": "SELECT * FROM customers LIMIT 10"
}
```

#### Export

**Export Table**
```http
POST /api/export/table
Content-Type: application/json

{
  "connection_id": "uuid-here",
  "table_name": "customers",
  "format": "excel"
}
```

**Export Query Results**
```http
POST /api/export/query
Content-Type: application/json

{
  "connection_id": "uuid-here",
  "sql_query": "SELECT * FROM orders WHERE total > 1000",
  "format": "pdf"
}
```

## Database Connection Examples

### SQLite
```json
{
  "db_type": "sqlite",
  "database": "mydb.db",
  "file_path": "/path/to/mydb.db"
}
```

### PostgreSQL
```json
{
  "db_type": "postgresql",
  "host": "localhost",
  "port": 5432,
  "database": "mydb",
  "username": "postgres",
  "password": "password"
}
```

### MySQL
```json
{
  "db_type": "mysql",
  "host": "localhost",
  "port": 3306,
  "database": "mydb",
  "username": "root",
  "password": "password"
}
```

## Model Configuration

The default model is `sqlcoder`, which is optimized for SQL generation. You can use alternative models:

- `codellama:7b` - Good general-purpose code model
- `deepseek-coder:6.7b` - Fast and efficient
- `llama3` - Latest version, good reasoning

To change the model, edit `services/llm_service.py`:
```python
llm_service = LLMQueryService(model_name="your-model-here")
```

## Performance Tips

1. **Connection Pooling**: Connections are automatically pooled
2. **Query Limits**: Use limits for large tables
3. **Schema Caching**: Schema is cached per connection
4. **Model Selection**: Smaller models are faster but less accurate

## Troubleshooting

### Ollama Not Running
```bash
# Check if Ollama is running
curl http://localhost:11434/api/version

# Start Ollama
ollama serve
```

### Model Not Found
```bash
# List installed models
ollama list

# Pull the required model
ollama pull sqlcoder
```

### Database Connection Failed
- Check database credentials
- Ensure database is running
- Verify network connectivity
- Check firewall rules

## Development

### Project Structure
```
text-to-sql-backend/
├── main.py                 # FastAPI application
├── requirements.txt        # Python dependencies
├── routers/               # API routes
│   ├── database.py        # Database operations
│   ├── query.py           # Query execution
│   └── export.py          # Data export
└── services/              # Business logic
    ├── database_service.py # Database management
    ├── llm_service.py      # LLM integration
    └── export_service.py   # Export functionality
```

### Running Tests
```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run tests
pytest
```

## License

MIT License

## Support

For issues and questions, please open an issue on GitHub.
