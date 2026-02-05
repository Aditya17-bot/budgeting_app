#!/bin/bash

echo "========================================"
echo "  SMS Budget Tracker - PWA Launcher"
echo "========================================"
echo ""
echo "This will start both the Streamlit app and PWA server"
echo ""

echo "[1] Starting Streamlit App (port 8501)..."
streamlit run app.py --server.port=8501 &
STREAMLIT_PID=$!

echo "[2] Starting PWA Server (port 8080)..."
python pwa_server.py &
PWA_PID=$!

echo ""
echo "✅ Both servers are starting!"
echo ""
echo "📱 PWA Landing Page: http://localhost:8080"
echo "🚀 Streamlit App: http://localhost:8501"
echo ""
echo "💡 Open http://localhost:8080 in your browser"
echo "   Then install it as a mobile app!"
echo ""

# Wait for user input to stop
read -p "Press Enter to stop all servers..."

kill $STREAMLIT_PID $PWA_PID 2>/dev/null
echo "Servers stopped."
