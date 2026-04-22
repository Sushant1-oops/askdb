import ollama
from typing import Dict, Any, Optional
import re
import json

class LLMQueryService:
    """Service for converting natural language to SQL using Ollama"""
    
    def __init__(self, model_name: str = "sqlcoder"):
        self.model_name = model_name
        self.client = ollama
    
    def _extract_sql(self, response: str) -> str:
        """Extract SQL query from LLM response"""
        # Try to find SQL in code blocks
        code_block_pattern = r"```sql\s*(.*?)\s*```"
        matches = re.findall(code_block_pattern, response, re.DOTALL | re.IGNORECASE)
        
        if matches:
            return matches[0].strip()
        
        # Try without sql tag
        code_block_pattern = r"```\s*(.*?)\s*```"
        matches = re.findall(code_block_pattern, response, re.DOTALL)
        
        if matches:
            return matches[0].strip()
        
        # If no code blocks, try to find SELECT, INSERT, UPDATE, DELETE statements
        sql_patterns = [
            r"(SELECT\s+.*?(?:;|$))",
            r"(INSERT\s+.*?(?:;|$))",
            r"(UPDATE\s+.*?(?:;|$))",
            r"(DELETE\s+.*?(?:;|$))",
            r"(CREATE\s+.*?(?:;|$))",
            r"(DROP\s+.*?(?:;|$))",
            r"(ALTER\s+.*?(?:;|$))"
        ]
        
        for pattern in sql_patterns:
            matches = re.findall(pattern, response, re.DOTALL | re.IGNORECASE)
            if matches:
                return matches[0].strip()
        
        # If nothing found, return cleaned response
        return response.strip()
    
    def _build_prompt(self, question: str, schema: Dict[str, Any]) -> str:
        """Build prompt for LLM with database schema"""
        
        # Format schema information
        schema_text = f"Database: {schema['database']}\n\nTables:\n"
        
        for table_name, table_info in schema['tables'].items():
            schema_text += f"\nTable: {table_name}\n"
            schema_text += "Columns:\n"
            
            for col in table_info['columns']:
                pk_marker = " (PRIMARY KEY)" if col.get('primary_key') else ""
                nullable = "NULL" if col['nullable'] else "NOT NULL"
                schema_text += f"  - {col['name']}: {col['type']} {nullable}{pk_marker}\n"
        
        prompt = f"""You are an expert SQL query generator. Given a database schema and a user question, generate a valid SQL query.

{schema_text}

User Question: {question}

Instructions:
1. Generate ONLY the SQL query, nothing else
2. Use proper SQL syntax
3. Include appropriate WHERE clauses, JOINs, and aggregations as needed
4. Use table and column names exactly as shown in the schema
5. For questions asking about counts, use COUNT()
6. For questions asking about averages, use AVG()
7. For questions asking about sums, use SUM()
8. Always use proper JOIN syntax when multiple tables are involved
9. Do NOT include explanations or markdown formatting
10. Return only the executable SQL query

SQL Query:"""
        
        return prompt
    
    def generate_sql(self, question: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Generate SQL query from natural language question"""
        try:
            # Build prompt
            prompt = self._build_prompt(question, schema)
            
            # Call Ollama
            response = self.client.generate(
                model=self.model_name,
                prompt=prompt,
                options={
                    "temperature": 0.1,  # Low temperature for more deterministic outputs
                    "top_p": 0.9,
                    "num_predict": 500
                }
            )
            
            # Extract SQL from response
            raw_response = response['response']
            sql_query = self._extract_sql(raw_response)
            
            # Clean up the query
            sql_query = sql_query.strip().rstrip(';') + ';'
            
            return {
                "success": True,
                "sql_query": sql_query,
                "raw_response": raw_response
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "sql_query": None
            }
    
    def check_model_availability(self) -> Dict[str, Any]:
        """Check if the SQL model is available"""
        try:
            models = self.client.list()
            model_names = [model['name'] for model in models.get('models', [])]
            
            return {
                "available": self.model_name in model_names or any(self.model_name in name for name in model_names),
                "installed_models": model_names,
                "recommended_model": self.model_name
            }
        except Exception as e:
            return {
                "available": False,
                "error": str(e)
            }

# Singleton instance
llm_service = LLMQueryService()
