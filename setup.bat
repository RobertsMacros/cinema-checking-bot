@echo off
echo === Cinema Digest Setup ===
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH.
    exit /b 1
)

REM Install dependencies
echo Installing dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies.
    exit /b 1
)

REM Create .env if it doesn't exist
if not exist .env (
    copy .env.example .env
    echo.
    echo Created .env from .env.example.
    echo Please edit .env with your API keys and SMTP credentials.
    echo.
    echo Required:
    echo   OMDB_API_KEY  - Get free key at https://www.omdbapi.com/apikey.aspx
    echo   TMDB_API_KEY  - Get free key at https://www.themoviedb.org/settings/api
    echo   SMTP_*        - Your email server settings
    echo.
) else (
    echo .env already exists, skipping.
)

echo.
echo Setup complete. To test:
echo   python -m cinema_digest.main --dry-run
echo.
