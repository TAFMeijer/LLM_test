from services.llm_service import get_schema_context
import os

if __name__ == "__main__":
    if os.path.exists("db_schema.xlsx"):
        print("Found db_schema.xlsx")
        context = get_schema_context()
        print("Schema Context Preview:")
        print(context[:500]) # Print first 500 chars
    else:
        print("db_schema.xlsx not found, skipping test.")
