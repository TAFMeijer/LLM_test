from google import genai
import os
import pandas as pd
import io

def get_schema_context():
    """
    Reads db_schema.xlsx and returns the schema as paired rows to preserve
    parent-child relationships (module→intervention, cost_group→cost_input).
    """
    try:
        if not os.path.exists("db_schema.xlsx"):
            return ""

        df = pd.read_excel("db_schema.xlsx")
        
        # Format as a table of rows to preserve parent-child relationships
        lines = []
        # Header
        lines.append("  " + " | ".join(df.columns))
        lines.append("  " + "-" * (len(" | ".join(df.columns)) + 2))
        # Rows (no deduplication — repeats are intentional to show parent-child links)
        for _, row in df.iterrows():
            lines.append("  " + " | ".join(str(v) if pd.notna(v) else "" for v in row))
        
        if not lines:
            return ""

        return "Valid values (each row shows which values belong together):\n" + "\n".join(lines)
    except Exception as e:
        print(f"Error reading schema context: {e}")
        return ""

def translate_to_pseudo_sql(query):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in environment variables")
        
    client = genai.Client(api_key=api_key)

    model = 'gemini-2.5-flash'
    
    schema_context = get_schema_context()

    system_prompt = f"""
You are a precise SQL assistant. Your job is to translate a user's question into a T-SQL SELECT query for SQL Server — but ONLY when you are confident you understand exactly what they want.

## Schema

Table: GC7Budget
Columns:
  country
  implementation_period_name
  module
  intervention
  cost_group
  cost_input
  total_amount

{schema_context}

## Column Relationships (Hierarchies)

There are two parent-child hierarchies in the data:

1. **module → intervention**: Each module has a specific subset of interventions. An intervention only belongs to one module. Use the valid values table above to determine which interventions belong to which module.
2. **cost_group → cost_input**: Each cost_group has a specific subset of cost_inputs. A cost_input only belongs to one cost_group.

IMPORTANT: Every cost_group has a cost_input with the exact same name. When a user refers to a value that exists as both a cost_group and a cost_input, ALWAYS filter on cost_group, not cost_input, unless the user explicitly asks for cost_input level detail.

## Filtering Rules

When the user mentions a specific value (e.g., a country, module, or intervention):
1. Check if it clearly matches one of the valid values in the table above (exact or obvious abbreviation).
2. If YES — use an exact match: WHERE column = 'ExactValue'
3. If the match is CLOSE but uncertain (e.g., typo, partial name, acronym that could mean multiple things) — ask for clarification. Do NOT guess.
4. Do NOT use LIKE unless the user explicitly asks for a partial/fuzzy match.
5. Use the hierarchy table to infer the correct column: if the user mentions a value that is a module name, filter on module; if it is an intervention name, filter on intervention. Same logic applies to cost_group vs. cost_input.

## Aggregation Rules

- Default: aggregate (SUM total_amount) grouped by country.
- If the user asks for a breakdown by module, intervention, cost_group, cost_input, or another column — group by that column instead.
- If it is unclear which level of detail the user wants, ask.

## Output Rules

- Return ONLY a single T-SQL SELECT query, nothing else.
- Always alias SUM(total_amount) AS [total amount].
- Do NOT use square brackets or quotes for identifiers.
- Do NOT use schema prefixes like dbo.
- Use ONLY the table and column names listed above.
- Always end the query with ORDER BY [total amount] DESC, unless the user explicitly asks for a different sort order.

## Special Responses

- If the question cannot be answered from this schema: return exactly CANNOT_ANSWER
- If you are unsure about ANY of the following, ask a clarifying question instead of guessing:
    * Which specific value the user means (e.g., ambiguous name, unknown acronym, or a value that appears in multiple columns)
    * Whether the user means a module or an intervention (they are related but different levels of detail)
    * Whether the user means a cost_group or a cost_input (when the name is the same, always prefer cost_group — but ask if the user seems to want cost_input level detail)
    * Which level of detail they want (e.g., by module vs. by intervention, or by cost_group vs. by cost_input)

When asking for clarification, return exactly:
CLARIFICATION_NEEDED: <your question in plain, non-technical language>

Do NOT use SQL terms like "GROUP BY", "aggregate", or "filter" in your clarifying question.
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
