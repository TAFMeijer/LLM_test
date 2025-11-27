import os
import urllib.parse
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

def list_tables():
    user = os.getenv("SQL_USER_NAME")
    password = os.getenv("SQL_PWD")
    
    if not user or not password:
        print("Error: Database credentials not found in environment variables")
        return

    connection_string = (
        "mssql+pymssql://"
        + urllib.parse.quote_plus(user)
        + ":"
        + urllib.parse.quote_plus(password)
        + "@sqlsv-tgf1-n-pmdc19rm.database.windows.net:1433/sqldb-TGF1-N-PMDC19RM"
    )
    
    try:
        engine = create_engine(connection_string)
        with engine.connect() as connection:
            print("Connected successfully!")
            print("\nListing tables in the database:")
            print("-" * 50)
            
            # Query to get all tables in the database
            result = connection.execute(text("""
                SELECT SCHEMA_NAME(schema_id) AS SchemaName, name AS TableName
                FROM sys.tables
                ORDER BY SchemaName, TableName;
            """))
            
            for row in result:
                print(f"[{row.SchemaName}].[{row.TableName}]")
                
            print("-" * 50)
            
    except Exception as e:
        print(f"Error connecting to database: {e}")

if __name__ == "__main__":
    list_tables()
