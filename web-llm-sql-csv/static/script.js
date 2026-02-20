document.addEventListener('DOMContentLoaded', () => {
    const chat = document.getElementById('chat');
    const queryInput = document.getElementById('queryInput');
    const sendBtn = document.getElementById('sendBtn');

    let originalQuery = '';
    let pendingTrueSql = '';
    let pendingCsvData = '';
    let awaitingClarification = false;
    let lastSuccessfulQuery = '';  // tracks the last query that returned a result
    let observationsShown = false; // only show observations once per thread

    // ── Helpers ────────────────────────────────────────────────────────────

    /** Auto-grow textarea */
    const adjustHeight = (el) => {
        el.style.height = 'auto';
        el.style.height = Math.min(el.scrollHeight, 160) + 'px';
    };
    queryInput.addEventListener('input', () => adjustHeight(queryInput));

    /** Scroll chat to bottom */
    const scrollBottom = () => {
        chat.scrollTop = chat.scrollHeight;
    };

    /** Append a bubble row and return the inner .bubble element */
    const appendBubble = (role, html = '', extraClass = '') => {
        const row = document.createElement('div');
        row.className = `bubble-row bubble-row--${role}`;

        const bubble = document.createElement('div');
        bubble.className = `bubble bubble--${role}${extraClass ? ' ' + extraClass : ''}`;
        bubble.innerHTML = html;

        row.appendChild(bubble);
        chat.appendChild(row);
        scrollBottom();
        return bubble;
    };

    /** Show animated typing indicator; returns a remove() function */
    const showTyping = () => {
        const row = document.createElement('div');
        row.className = 'bubble-row bubble-row--assistant';
        row.innerHTML = `
            <div class="typing-indicator">
                <span></span><span></span><span></span>
            </div>`;
        chat.appendChild(row);
        scrollBottom();
        return () => row.remove();
    };

    /** Disable / enable the send button */
    const setLoading = (on) => {
        sendBtn.disabled = on;
        queryInput.disabled = on;
    };

    // ── Core query flow ────────────────────────────────────────────────────

    const handleQuery = async (queryText, clarificationText = null) => {
        setLoading(true);

        // ── Step 1: LLM interprets the question ──────────────────────────
        const removeTyping1 = showTyping();

        const payload = { query: queryText };
        if (clarificationText) payload.clarification = clarificationText;

        let interpretData;
        try {
            const res = await fetch('/api/interpret', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            interpretData = await res.json();
            removeTyping1();

            if (!res.ok) throw new Error(interpretData.error || 'An error occurred');
        } catch (err) {
            removeTyping1();
            appendBubble('assistant', escHtml(err.message), 'bubble--error');
            setLoading(false);
            queryInput.value = '';
            adjustHeight(queryInput);
            queryInput.focus();
            return;
        }

        // ── Clarification needed — ask and stop here ──────────────────────
        if (interpretData.status === 'clarification_needed') {
            removeTyping1();
            originalQuery = interpretData.original_query || queryText;
            awaitingClarification = true;
            appendBubble('assistant', escHtml(interpretData.question));
            setLoading(false);
            queryInput.value = '';
            adjustHeight(queryInput);
            queryInput.focus();
            return;
        }

        // ── Cannot answer — tell the user and stop ────────────────────────
        if (interpretData.status === 'cannot_answer') {
            removeTyping1();
            appendBubble('assistant', 'Sorry, I cannot answer this.');
            setLoading(false);
            queryInput.value = '';
            adjustHeight(queryInput);
            queryInput.focus();
            return;
        }

        // ── Question is clear — acknowledge, then execute ─────────────────
        removeTyping1();
        const ack = clarificationText
            ? 'Thanks for clarifying, here you go!'
            : 'Here you go!';
        appendBubble('assistant', escHtml(ack));

        // ── Step 2: Execute the SQL query ─────────────────────────────────
        const removeTyping2 = showTyping();

        try {
            const res = await fetch('/api/execute', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sql: interpretData.sql }),
            });
            const data = await res.json();
            removeTyping2();

            if (!res.ok) throw new Error(data.error || 'An error occurred');

            pendingTrueSql = data.sql;
            pendingCsvData = data.csv_data;
            awaitingClarification = false;
            lastSuccessfulQuery = queryText;  // remember for follow-up loop

            // Result bubble: collapsible debug info + download button
            const resultBubble = appendBubble('assistant', '');
            resultBubble.innerHTML = `
                <div class="result-bubble">
                    <details class="debug-details">
                        <summary>Show query details</summary>
                        <div class="debug-info">
                                <p><strong>SQL:</strong> <code>${escHtml(data.sql)}</code></p>
                        </div>
                    </details>
                    <a class="download-btn" href="#">⬇ Download Excel</a>
                </div>`;

            resultBubble.querySelector('.download-btn').addEventListener('click', async (e) => {
                e.preventDefault();
                await downloadExcel(pendingTrueSql);
            });

            // Kick off observations only on the first result
            if (!observationsShown) {
                observationsShown = true;
                fetchObservations(queryText, pendingCsvData);
            } else {
                appendBubble('assistant', 'Is everything clear, or would you like something added or corrected?');
            }

        } catch (err) {
            removeTyping2();
            appendBubble('assistant', escHtml(err.message), 'bubble--error');
        } finally {
            setLoading(false);
            queryInput.value = '';
            adjustHeight(queryInput);
            queryInput.focus();
        }
    };

    // ── Observations ───────────────────────────────────────────────────────

    const fetchObservations = async (queryText, csvData) => {
        const removeTyping = showTyping();
        try {
            const res = await fetch('/api/observations', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: queryText, csv_data: csvData }),
            });
            const data = await res.json();
            removeTyping();

            if (data.observations) {
                const row = document.createElement('div');
                row.className = 'bubble-row bubble-row--assistant';
                const card = document.createElement('div');
                card.className = 'obs-card';
                const label = document.createElement('div');
                label.className = 'obs-card-label';
                label.textContent = 'AI-generated Observations';
                const body = document.createElement('p');
                body.textContent = data.observations;
                card.appendChild(label);
                card.appendChild(body);
                row.appendChild(card);
                chat.appendChild(row);
                scrollBottom();

                // Follow-up prompt
                appendBubble('assistant', 'Is everything clear, or would you like something added or corrected?');
            }
        } catch {
            removeTyping();
            // Silently fail — observations are supplementary
        }
    };

    // ── Excel download ─────────────────────────────────────────────────────

    const downloadExcel = async (trueSql) => {
        const now = new Date();
        const dd = String(now.getDate()).padStart(2, '0');
        const mmm = now.toLocaleString('en-GB', { month: 'short' });
        const yy = String(now.getFullYear()).slice(-2);
        const hh = String(now.getHours()).padStart(2, '0');
        const mm = String(now.getMinutes()).padStart(2, '0');
        const filename = `Budget Query ${dd}-${mmm}-${yy} ${hh}${mm}.xlsx`;

        const res = await fetch('/api/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ true_sql: trueSql, filename }),
        });
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = filename;
        document.body.appendChild(a);
        a.click(); a.remove();
    };

    // ── Send ───────────────────────────────────────────────────────────────

    const send = () => {
        const text = queryInput.value.trim();
        if (!text) return;

        appendBubble('user', escHtml(text));

        if (awaitingClarification) {
            // Mid-clarification reply
            awaitingClarification = false;
            handleQuery(originalQuery, text);
        } else if (lastSuccessfulQuery) {
            // Follow-up on a previous result — pass as clarification context
            originalQuery = lastSuccessfulQuery;
            handleQuery(lastSuccessfulQuery, text);
        } else {
            // Fresh query
            originalQuery = text;
            lastSuccessfulQuery = '';
            handleQuery(text);
        }
    };

    sendBtn.addEventListener('click', send);
    queryInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
    });

    // ── Utility ────────────────────────────────────────────────────────────

    const escHtml = (str) =>
        String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
});
