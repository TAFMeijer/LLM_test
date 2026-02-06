import os
import urllib.parse
from sqlalchemy import create_engine, text
import csv
import io

TABLE_MAP = {
    "GC7Budget": "[dbo].[GC7 Budget Data]"
}

COLUMN_MAP = {
    "GC7Budget": {
        "country": "[Country]",
        "implementation_period_name": "[ImplementationPeriodName]",
        "intervention": "[Intervention]",
        "module": "[Module]",
        "cost_input": "[Cost Input]",
        "total_amount": "[Total Amount]",
    }
}

FORBIDDEN_KEYWORDS = ["insert", "update", "delete", "drop", "alter", "truncate"]

def translate_to_true_sql(pseudo_sql):
    # Basic validation
    lower_sql = pseudo_sql.lower()
    for keyword in FORBIDDEN_KEYWORDS:
        if keyword in lower_sql:
            raise ValueError(f"Forbidden keyword detected: {keyword}")
            
    # Translation
    true_sql = pseudo_sql
    
    # Replace Table Names
    for logical_table, true_table in TABLE_MAP.items():
        # Simple replacement - in a real scenario, this might need more robust parsing
        # to avoid replacing substrings in other contexts.
        # Given the strict system prompt, simple replacement should work for now.
        true_sql = true_sql.replace(logical_table, true_table)
        
    # Replace Column Names
    # We need to iterate through tables to find which columns belong to which table
    # But since the SQL might not fully qualify columns, we might just replace known column names
    # if they are unique enough.
    # A safer approach for this specific schema where columns are unique:
    for table, columns in COLUMN_MAP.items():
        for logical_col, true_col in columns.items():
            true_sql = true_sql.replace(logical_col, true_col)
            
    return true_sql

def execute_query(sql):
    user = os.getenv("SQL_USER_NAME")
    password = os.getenv("SQL_PWD")
    
    if not user or not password:
        raise ValueError("Database credentials not found in environment variables")
        
    connection_string = (
        "mssql+pymssql://"
        + urllib.parse.quote_plus(user)
        + ":"
        + urllib.parse.quote_plus(password)
        + "@sqlsv-tgf1-n-pmdc19rm.database.windows.net:1433/sqldb-TGF1-N-PMDC19RM"
    )
    
    engine = create_engine(connection_string)
    
    with engine.connect() as connection:
        result = connection.execute(text(sql))
        columns = result.keys()
        data = result.fetchall()
        
    return data, columns

def results_to_csv(data, columns):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(columns)
    writer.writerows(data)
    return output.getvalue()
