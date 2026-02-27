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
# Get local IP for office network sharing
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || hostname -I | awk '{print $1}' 2>/dev/null)

# Start Cloudflare Tunnel (Persistent to global-health-data.org)
echo "Starting Cloudflare tunnel..."
echo "Your app is now live globally at: https://global-health-data.org/BudgetQuery"
if [ -n "$LOCAL_IP" ]; then
    echo "Colleagues on the SAME office network can also access it at: http://$LOCAL_IP:5000/BudgetQuery"
fi
echo ""
cloudflared tunnel --config cf_config.yml run budget-query
