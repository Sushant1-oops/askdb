import requests
import json

BASE = "http://localhost:8000"

# 1. Check model status
print("=== Model Status ===")
r = requests.get(f"{BASE}/api/query/model-status")
print(json.dumps(r.json(), indent=2))

# 2. Connect to SQLite test database
print("\n=== Connect to DB ===")
r = requests.post(f"{BASE}/api/database/connect", json={
    "db_type": "sqlite",
    "database": "test_database",
    "file_path": "test_database.sqlite"
})
conn = r.json()
print(json.dumps(conn, indent=2))
conn_id = conn.get("connection_id", "")

if conn_id:
    # 3. List tables
    print("\n=== Tables ===")
    r = requests.get(f"{BASE}/api/database/connections/{conn_id}/tables")
    tables = r.json()
    print(json.dumps(tables, indent=2))

    # 4. Test a simple natural language query
    print("\n=== NL Query: Simple ===")
    r = requests.post(f"{BASE}/api/query/natural-language", json={
        "connection_id": conn_id,
        "question": "Show me all employees"
    }, timeout=120)
    result = r.json()
    print(f"Status: {r.status_code}")
    print(f"SQL: {result.get('generated_sql')}")
    print(f"Model: {result.get('model_used')}")
    print(f"Retries: {result.get('retries')}")
    qr = result.get("query_result", {})
    print(f"Success: {qr.get('success')}")
    if qr.get("rows"):
        print(f"Rows: {len(qr['rows'])}")
    if qr.get("error"):
        print(f"Error: {qr['error']}")

    # 5. Test a complex query
    print("\n=== NL Query: Complex ===")
    r = requests.post(f"{BASE}/api/query/natural-language", json={
        "connection_id": conn_id,
        "question": "Show me the top 3 departments with the highest average salary"
    }, timeout=120)
    result = r.json()
    print(f"Status: {r.status_code}")
    print(f"SQL: {result.get('generated_sql')}")
    print(f"Model: {result.get('model_used')}")
    print(f"Retries: {result.get('retries')}")
    qr = result.get("query_result", {})
    print(f"Success: {qr.get('success')}")
    if qr.get("rows"):
        print(f"Rows: {qr['rows']}")
    if qr.get("error"):
        print(f"Error: {qr['error']}")
else:
    print("ERROR: No connection ID returned!")
