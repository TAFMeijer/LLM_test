import os
import urllib.parse
from sqlalchemy import create_engine, text
import csv
import io
import pandas as pd
import openpyxl

FORBIDDEN_KEYWORDS = ["insert", "update", "delete", "drop", "alter", "truncate", "HPMT", "THFA", "select * from"]

def validate_sql(sql):
    """Safety check — reject any non-SELECT statements."""
    lower_sql = sql.lower()
    for keyword in FORBIDDEN_KEYWORDS:
        if keyword in lower_sql:
            raise ValueError(f"Forbidden keyword detected: {keyword}")


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
        #result = connection.execute(text(sql))
        #columns = result.keys()
        #data = result.fetchall()
        df_Budget = pd.read_sql( text(sql), connection )

    #return data, columns
    return df_Budget


def add_percentage_column(df: pd.DataFrame) -> pd.DataFrame:
    """
    Appends a '% of total' column as a raw float ratio (e.g. 0.2341).
    Excel formatting is applied separately in results_to_xlsx.
    """
    if len(df) <= 1:
        return df  # Single value — skip

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    if len(numeric_cols) != 1:
        return df  # Ambiguous or no numeric column — skip

    amount_col = numeric_cols[0]
    total = df[amount_col].sum()
    if total == 0:
        return df

    df = df.copy()
    df["% of total"] = df[amount_col] / total  # raw ratio, full precision
    return df

def results_to_csv(data, columns):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(columns)
    writer.writerows(data)
    return output.getvalue()

def results_to_xlsx(df: pd.DataFrame):
    """
    Converts a pandas DataFrame to an in-memory Excel (.xlsx) file.
    Applies #0.0% number format to the '% of total' column if present.
    Returns a BytesIO object.
    """
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Results")

        # Apply percentage format to the '% of total' column
        if "% of total" in df.columns:
            ws = writer.sheets["Results"]
            col_idx = df.columns.get_loc("% of total") + 1  # 1-based for openpyxl
            for row in ws.iter_rows(min_row=2, min_col=col_idx, max_col=col_idx):
                for cell in row:
                    cell.number_format = "#0.0%"

        # Apply #,##0 format to all other numeric columns
        ws = writer.sheets["Results"]
        numeric_cols = df.select_dtypes(include="number").columns
        for col_name in numeric_cols:
            if col_name == "% of total":
                continue
            col_idx = df.columns.get_loc(col_name) + 1
            for row in ws.iter_rows(min_row=2, min_col=col_idx, max_col=col_idx):
                for cell in row:
                    cell.number_format = "#,##0"

    output.seek(0)
    return output

