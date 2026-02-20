#!/bin/bash
# Budget Query Assistant — start Flask + Cloudflare Quick Tunnel
# Usage: ./start.sh
# Note: Run from home network (corporate network blocks tunnel services)

set -e
cd "$(dirname "$0")"
source venv/bin/activate

# Kill any previous instance
lsof -ti :5000 | xargs kill -9 2>/dev/null || true
pkill -9 cloudflared 2>/dev/null || true
sleep 1

# Start Flask in background
echo "Starting Flask..."
python app.py &> /tmp/flask.log &
sleep 2

# Start Cloudflare Quick Tunnel (no account needed)
echo "Starting Cloudflare tunnel..."
echo "Your public URL will appear below in a few seconds — share it with colleagues:"
echo ""
cloudflared tunnel --url http://localhost:5000 --no-autoupdate
