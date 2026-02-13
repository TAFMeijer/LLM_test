document.addEventListener('DOMContentLoaded', () => {
    const queryInput = document.getElementById('queryInput');
    const submitBtn = document.getElementById('submitBtn');
    const statusDiv = document.getElementById('status');
    const resultDiv = document.getElementById('result');
    const errorDiv = document.getElementById('error');
    const pseudoSqlCode = document.getElementById('pseudoSql');
    const trueSqlCode = document.getElementById('trueSql');
    const downloadLink = document.getElementById('downloadLink');

    // Ensure status is hidden initially (though HTML class should handle it)
    statusDiv.classList.add('hidden');

    // Auto-resize textarea
    const adjustHeight = () => {
        queryInput.style.height = 'auto';
        queryInput.style.height = queryInput.scrollHeight + 'px';
    };

    queryInput.addEventListener('input', adjustHeight);

    // Handle Enter key
    queryInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            submitBtn.click();
        }
    });

    submitBtn.addEventListener('click', async () => {
        const query = queryInput.value.trim();
        if (!query) return;

        // Reset UI
        resultDiv.classList.add('hidden');
        errorDiv.classList.add('hidden');
        statusDiv.classList.remove('hidden');
        submitBtn.disabled = true;

        try {
            const response = await fetch('/api/query', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ query }),
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'An error occurred');
            }

            // Update UI with results
            pseudoSqlCode.textContent = data.pseudo_sql;
            trueSqlCode.textContent = data.true_sql;

            downloadLink.onclick = async () => {
                const response = await fetch('/api/download', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ true_sql: data.true_sql }),
                });

                const blob = await response.blob();

                const url = window.URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = "query_results.xlsx";
                document.body.appendChild(a);
                a.click();
                a.remove();
            };

            resultDiv.classList.remove('hidden');

        } catch (error) {
            errorDiv.textContent = error.message;
            errorDiv.classList.remove('hidden');
        } finally {
            statusDiv.classList.add('hidden');
            submitBtn.disabled = false;
        }
    });
});
