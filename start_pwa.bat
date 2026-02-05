@echo off
echo ========================================
echo   SMS Budget Tracker - PWA Launcher
echo ========================================
echo.
echo This will start both the Streamlit app and PWA server
echo.

echo [1] Starting Streamlit App (port 8501)...
start "Streamlit App" cmd /k "streamlit run app.py --server.port=8501"

echo [2] Starting PWA Server (port 8080)...
start "PWA Server" cmd /k "python pwa_server.py"

echo.
echo ✅ Both servers are starting!
echo.
echo 📱 PWA Landing Page: http://localhost:8080
echo 🚀 Streamlit App: http://localhost:8501
echo.
echo 💡 Open http://localhost:8080 in your browser
echo    Then install it as a mobile app!
echo.
pause
