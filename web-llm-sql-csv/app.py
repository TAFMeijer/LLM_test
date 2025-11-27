from flask import Flask, render_template, request, jsonify, send_file
import os
from dotenv import load_dotenv
from services.llm_service import translate_to_pseudo_sql
from services.db_service import translate_to_true_sql, execute_query, results_to_csv
import io

load_dotenv()

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/query', methods=['POST'])
def query():
    data = request.json
    user_query = data.get('query')
    
    if not user_query:
        return jsonify({'error': 'No query provided'}), 400
    
    try:
        # Step 1: NL -> Pseudo SQL
        pseudo_sql = translate_to_pseudo_sql(user_query)
        
        # Step 2: Pseudo SQL -> True SQL
        true_sql = translate_to_true_sql(pseudo_sql)
        
        # Step 3: Execute Query
        results, columns = execute_query(true_sql)
        
        # Step 4: Generate CSV
        csv_content = results_to_csv(results, columns)
        
        return jsonify({
            'status': 'success',
            'pseudo_sql': pseudo_sql,
            'true_sql': true_sql,
            'csv_data': csv_content
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
