from flask import Flask, render_template, request, jsonify, send_file
import os
from dotenv import load_dotenv
from services.llm_service import translate_to_sql, generate_observations
from services.db_service import execute_query, add_percentage_column, results_to_xlsx, validate_sql

load_dotenv()

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/interpret', methods=['POST'])
def interpret():
    """Step 1: NL -> Pseudo SQL (LLM only). Returns either pseudo_sql or clarification_needed."""
    data = request.json
    user_query = data.get('query')

    if not user_query:
        return jsonify({'error': 'No query provided'}), 400

    try:
        clarification = data.get('clarification')
        if clarification:
            user_query = f"{user_query} (Context: {clarification})"

        sql = translate_to_sql(user_query)

        if sql.startswith("CLARIFICATION_NEEDED"):
            question = sql.replace("CLARIFICATION_NEEDED:", "").strip()
            return jsonify({
                'status': 'clarification_needed',
                'question': question,
                'original_query': data.get('query')
            })

        return jsonify({
            'status': 'ready',
            'sql': sql
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/execute', methods=['POST'])
def execute():
    """Step 2: Run the SQL the LLM produced directly against the DB."""
    data = request.json
    sql = data.get('sql')

    if not sql:
        return jsonify({'error': 'No sql provided'}), 400

    try:
        validate_sql(sql)  # safety check (no INSERT/UPDATE/DELETE/DROP etc.)
        df = execute_query(sql)
        df = add_percentage_column(df)

        # For the CSV (sent to observations LLM), format % of total as a readable string
        df_csv = df.copy()
        if "% of total" in df_csv.columns:
            df_csv["% of total"] = df_csv["% of total"].map(lambda x: f"{x * 100:.1f}%")
        csv_content = df_csv.to_csv(index=False)

        return jsonify({
            'status': 'success',
            'sql': sql,
            'csv_data': csv_content
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/observations', methods=['POST'])
def observations():
    data = request.json
    user_query = data.get('query', '')
    csv_data = data.get('csv_data', '')

    if not csv_data:
        return jsonify({'error': 'No data provided'}), 400

    try:
        text = generate_observations(user_query, csv_data)
        return jsonify({'observations': text})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/download', methods=['POST'])
def download_file():
    data = request.get_json()
    true_sql = data.get("true_sql")
    filename = data.get("filename", "query_results.xlsx")

    df_budget = execute_query(true_sql)
    df_budget = add_percentage_column(df_budget)
    xlsx_content = results_to_xlsx(df_budget)

    return send_file(
        xlsx_content,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
