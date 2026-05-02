import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.llm_service import llm_service

schema = {
    'database': 'test_database.sqlite',
    'tables': {
        'users': {
            'columns': [
                {'name': 'id', 'type': 'INTEGER', 'nullable': False},
                {'name': 'name', 'type': 'TEXT', 'nullable': True}
            ]
        }
    }
}

res = llm_service.generate_sql("Show me all users", schema)
print("Result:", res)
