@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 (
    echo ERROR: Cannot open the SchoolFlow project folder.
    pause
    exit /b 1
)

set "PYTHON=%~dp0.venv\Scripts\python.exe"
set "APP=%~dp0Shared_Demo.py"

if not exist "%PYTHON%" (
    echo ERROR: Python was not found in the project's .venv folder.
    echo Restore the existing project environment before starting the app.
    pause
    exit /b 1
)
if not exist "%APP%" (
    echo ERROR: Shared_Demo.py was not found.
    echo Keep this launcher in the project root.
    pause
    exit /b 1
)

"%PYTHON%" -c "import streamlit, pandas, openpyxl, supabase, postgrest, httpx"
if errorlevel 1 (
    echo ERROR: A required application dependency is missing or cannot be imported.
    echo Check SchoolFlow_AI_MVP\requirements.txt and the existing .venv environment.
    pause
    exit /b 1
)

echo Starting SchoolFlow AI. Keep this window open while using the app.
set "STREAMLIT_SERVER_ADDRESS=127.0.0.1"
"%PYTHON%" -m streamlit run "%APP%" --browser.serverAddress 127.0.0.1 --browser.gatherUsageStats false
set "RESULT=%ERRORLEVEL%"
echo.
echo SchoolFlow AI stopped with exit code %RESULT%.
pause
exit /b %RESULT%
