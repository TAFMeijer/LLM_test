from flask import Flask, render_template, request, jsonify, send_file
import os
from datetime import datetime
import pandas as pd
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

        if sql.strip() == "CANNOT_ANSWER":
            return jsonify({'status': 'cannot_answer'})

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

@app.route('/api/feedback', methods=['POST'])
def feedback():
    data = request.json
    
    feedback_entry = {
        'Timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'IP Address': request.remote_addr,
        'Original Query': data.get('query', ''),
        'Thumbs Up': data.get('thumbs_up', None),
        'Feedback Text': data.get('feedback_text', '')
    }
    
    file_path = 'feedback_logs.xlsx'
    
    try:
        if os.path.exists(file_path):
            df_existing = pd.read_excel(file_path)
            df_new = pd.DataFrame([feedback_entry])
            df_combined = pd.concat([df_existing, df_new], ignore_index=True)
            df_combined.to_excel(file_path, index=False)
        else:
            df_new = pd.DataFrame([feedback_entry])
            df_new.to_excel(file_path, index=False)
            
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    from werkzeug.middleware.dispatcher import DispatcherMiddleware
    from werkzeug.serving import run_simple
    
    # Mount the app at both / and /BudgetQuery
    application = DispatcherMiddleware(app, {
        '/BudgetQuery': app
    })
    
    run_simple('0.0.0.0', 5000, application, use_reloader=True, use_debugger=True)
