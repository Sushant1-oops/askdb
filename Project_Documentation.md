# Text-to-SQL Project Documentation

## 1. Project Overview
The **Text-to-SQL** project is a comprehensive full-stack application that seamlessly bridges the gap between natural language and database querying. It allows users to connect to various relational databases and query them simply by asking questions in plain English. By leveraging advanced local Large Language Models (LLMs), the application translates human intent into accurate, executable SQL queries, making data accessible to both technical and non-technical users.

## 2. Key Functionalities

### 🔌 Database Connection Management
- **Multi-Database Support**: Securely connect to PostgreSQL, MySQL, and SQLite databases.
- **Connection Pooling**: Optimized backend handling for fast and reliable query execution.

### 📊 Schema Exploration
- **Visual Insights**: Browse existing tables, columns, and relationships directly from the UI.
- **Schema Caching**: The backend caches the database schema per connection to ensure optimal performance during AI inference.

### 🤖 AI-Powered Query Generation
- **Natural Language Processing**: Submit plain English questions (e.g., "Show me all customers who made purchases last month").
- **Accurate SQL Translation**: The backend utilizes specialized coding LLMs (like `sqlcoder`) via Ollama to generate precise SQL statements based on the specific database schema.

### ⚡ Query Execution & Visualization
- **Direct SQL Execution**: Run the AI-generated queries or manually write/edit your own SQL commands.
- **Data Tables**: View the returned database records in clean, readable, and responsive tabular formats on the frontend.

### 📥 Data Export
- **Multiple Formats**: Instantly export your query results into CSV, Excel, or PDF files for external reporting and analysis.

## 3. Technology Stack

### Frontend (Client-Side)
- **Framework**: React.js powered by Vite for lightning-fast development and optimized builds.
- **Language**: JavaScript / TypeScript.
- **Styling**: Custom Vanilla CSS featuring a modern, dark-themed, glassmorphism design system.
- **Routing**: `react-router-dom` for seamless page navigation.
- **Key Libraries**: 
  - `lucide-react` for beautiful iconography.
  - `react-syntax-highlighter` for styling and highlighting generated SQL code blocks.
  - `react-hot-toast` for elegant user notifications and error handling.

### Backend (Server-Side & AI)
- **Framework**: FastAPI (Python) - known for high performance and automatic API documentation generation.
- **AI Integration**: Ollama (Local LLM engine) running models like `sqlcoder`, `codellama:7b`, or `deepseek-coder:6.7b`.
- **Database Drivers**: Built-in Python drivers to interface with PostgreSQL, MySQL, and SQLite.

## 4. Application Workflow

The end-to-end workflow of the application functions as follows:

1. **Environment Setup & Initialization**:
   - The user starts the local Ollama service with a pulled SQL generation model (e.g., `ollama pull sqlcoder`).
   - The FastAPI backend server is launched, exposing the REST API endpoints.
   - The React frontend is started via Vite (`npm run dev`).

2. **Connecting to the Database**:
   - The user inputs their database credentials (host, port, username, password, db name) in the frontend UI.
   - The frontend sends a `POST` request to the backend. The backend establishes a secure connection pool and retrieves the database schema.

3. **Schema Mapping**:
   - The backend maps the tables and columns and caches this schema. This context is crucial for the LLM to understand what data is available.

4. **Natural Language Querying**:
   - The user types a question into the chat/query interface.
   - The frontend transmits the question to the backend (`/api/query/natural-language`).
   - The backend constructs a highly detailed prompt containing the user's question alongside the cached database schema, and sends it to the local Ollama LLM.
   - The LLM processes the prompt and returns a properly formatted SQL query.

5. **Execution & Rendering**:
   - The generated SQL query is passed back to the frontend, where it is highlighted for the user to review.
   - The user can choose to execute the query (`/api/query/sql`), prompting the backend to run the SQL command directly against the connected database.
   - The resulting rows are returned as JSON and rendered in a dynamic data table on the UI.

6. **Exporting Results**:
   - If the user needs the data offline, they click the export button. The frontend requests a file generation (`/api/export/query`), and the backend streams back a downloadable CSV, Excel, or PDF document.

## 5. Summary
This project provides a robust, production-ready environment that democratizes data access. By coupling a sleek, modern React frontend with a high-performance FastAPI backend and powerful local AI models, it completely removes the necessity of knowing SQL to extract meaningful insights from relational databases.
