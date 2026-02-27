from google import genai
import os
import pandas as pd
import io

def get_schema_context():
    """
    Reads db_schema.xlsx and returns valid-value tables for both sheets:
    - GC7_budget  → budget hierarchy (module/intervention/cost)
    - Geography   → geography lookup (region/department)
    """
    try:
        if not os.path.exists("db_schema.xlsx"):
            return "", ""

        xl = pd.ExcelFile("db_schema.xlsx")

        def sheet_to_table(sheet_name):
            if sheet_name not in xl.sheet_names:
                return ""
            df = xl.parse(sheet_name)
            lines = []
            lines.append("  " + " | ".join(str(c) for c in df.columns))
            lines.append("  " + "-" * (sum(len(str(c)) for c in df.columns) + 3 * (len(df.columns) - 1) + 2))
            for _, row in df.iterrows():
                lines.append("  " + " | ".join(str(v) if pd.notna(v) else "" for v in row))
            return "\n".join(lines)

        budget_context = sheet_to_table("GC7_budget")
        geo_context = sheet_to_table("Geography")
        return budget_context, geo_context

    except Exception as e:
        print(f"Error reading schema context: {e}")
        return "", ""

def translate_to_sql(query):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in environment variables")
        
    client = genai.Client(api_key=api_key)

    model = 'gemini-2.5-flash'

    budget_context, geo_context = get_schema_context()

    system_prompt = f"""
You are a precise SQL assistant. Your job is to translate a user's question into a T-SQL SELECT query for SQL Server — but ONLY when you are confident you understand exactly what they want.

## Tables

### Table 1: [dbo].[GC7 Budget Data]  (alias: b)
Columns:
  [Country]                    — country name (join key to Geography Lookup)
  [ImplementationPeriodName]   — grant / implementation period
  [Module]                     — programme module
  [Intervention]               — intervention within a module
  [Cost Category]              — cost group / grouping (parent of Cost Input)
  [Cost Input]                 — individual cost line
  [Total Amount]               — budget amount (numeric)

### Table 2: [dbo].[Geography Lookup]  (alias: g)
Columns:
  [Geography Name]   — country name (join key to GC7 Budget Data)
  [NewRegioShort]    — region abbreviation (e.g. HIA1, EECA, Asia)
  [NewDept]          — department abbreviation

### Join key
  b.[Country] = g.[Geography Name]

## Valid Values — Budget context schema
Each row shows all unique values in that column.
{budget_context}

## Valid Values — Geography context schema
Each row shows all unique values in that column.
{geo_context}

## Column Relationships

1. **[Module] → [Intervention]**: Each module has a specific set of interventions. An intervention belongs to exactly one module. In the budget context schema module and intervention are shown as pairs
2. **[Cost Category] → [Cost Input]**: Each cost category has a specific set of cost inputs. In the budget context schema cost category and cost input are shown as pairs. When a value is both a cost category and a cost input name, ALWAYS filter on [Cost Category] unless the user explicitly asks for cost input detail.

## Filtering Rules

1. Check if the user's value clearly matches a valid value above (exact or obvious abbreviation).
2. If YES — use exact match: WHERE [Column] = 'ExactValue', but ONLY use = when the requested value is an exact match to the valid value.
3. If CLOSE but uncertain — ask for clarification. Do NOT guess.
4. Do NOT use LIKE unless the user explicitly asks for a fuzzy match.
5. Infer the correct column from the hierarchy (module vs. intervention, cost category vs. cost input).

## JOIN Rules

- Use a JOIN only when the user's question requires regional ([NewRegioShort]) or departmental ([NewDept]) grouping/filtering:
    SELECT ...
    FROM [dbo].[GC7 Budget Data] b
    LEFT JOIN [dbo].[Geography Lookup] g ON b.[Country] = g.[Geography Name]
- If the question only involves budget columns (country, module, intervention, cost, period), query [dbo].[GC7 Budget Data] alone — no join needed.

## Aggregation Rules

- Default: SUM([Total Amount]) grouped by b.[Country].
- Adjust GROUP BY based on what the user asks for (module, region, department, etc.).
- If the level of detail is unclear, ask.

## Output Rules

- Return ONLY a single T-SQL SELECT query, nothing else.
- NEVER use SELECT * (you must explicitly name the columns or aggregations you are selecting).
- Always alias SUM([Total Amount]) AS [total amount].
- Use exact bracketed column and table names as shown above.
- Do NOT add schema prefixes (dbo.) in column aliases.
- Always end with ORDER BY [total amount] DESC unless the user asks otherwise.

## Special Responses

- If the question cannot be answered from this schema: return exactly CANNOT_ANSWER
- If you are unsure about any of the following, ask instead of guessing:
    * Which specific value the user means
    * Whether the user means module or intervention level
    * Whether the user means cost category or cost input level
    * Which level of geographic aggregation (country / region / department)

When asking for clarification, return exactly:
CLARIFICATION_NEEDED: <your question in plain, non-technical language>

Do NOT use SQL terms like "GROUP BY", "aggregate", "filter", or "JOIN" in your clarifying question.
"""
    
    full_prompt = f"{system_prompt}\n\nUser Question: {query}\nSQL Query:"
    
    response = client.models.generate_content(model=model, contents=full_prompt)
    text = response.text.strip()
    
    # Check for clarification request
    if text.startswith("CLARIFICATION_NEEDED"):
        return text

    # Clean up common LLM artifacts
    if text.startswith("```"):
        text = text.replace("```sql", "").replace("```", "")
    
    if text.lower().startswith("sql:"):
        text = text[4:]
        
    return text.strip()


def generate_observations(user_query: str, csv_data: str) -> str:
    """
    Reads the CSV result of a query and returns high-level observations
    written in plain business language for the end user.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in environment variables")

    client = genai.Client(api_key=api_key)
    model = 'gemini-3-pro-preview'

    # Parse the CSV so we can include a clean summary in the prompt
    try:
        df = pd.read_csv(io.StringIO(csv_data))
        row_count = len(df)
        col_names = ", ".join(df.columns.tolist())
        data_preview = df.to_string(index=False)
    except Exception:
        data_preview = csv_data
        row_count = "unknown"
        col_names = ""

    observations_system_prompt = f"""\
You are a senior budget analyst with deep expertise in global health financing, particularly Global Fund programmes. \
The user asked a question about budget data and the system returned a table of results. \
Your job is to write 1-2 concise, strategic and insightful observations that help the user contextualize the numbers.

## Guidelines
- Write for a senior technical/medical advisor audience with a stretegic lens. Do NOT mention SQL, columns, or database terms.
- Combine what you see in the data with your broader knowledge of global health budgets, typical cost structures, \
and Global Fund programme design — where relevant and accurate.
- Highlight what stands out: the largest values, notable proportions, unexpected patterns, or anything worth flagging.
- If a country or programme area has an unusually high or low share, note it and briefly explain why that might be the case.
- Keep each observation to 1 sentence.
- Do NOT repeat the user's question back to them.
- Do NOT suggest further queries or next steps.
- Format your response as a short bulleted list using "•" as the bullet character.
- Do NOT use markdown headers or bold text.

## User's original question
{user_query}

## Query results ({row_count} rows, columns: {col_names})
{data_preview}
"""

    response = client.models.generate_content(model=model, contents=observations_system_prompt)
    return response.text.strip()
